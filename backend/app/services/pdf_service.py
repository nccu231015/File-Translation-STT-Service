import os
import httpx
import re
from opencc import OpenCC
from .gpu_live_monitor import MODULE_DOCUMENT_TRANSLATION, gpu_work_acquire, gpu_work_release
from .pdf_layout_service import PDFLayoutPreservingService
from .pdf_layout_detector_yolo import PDFLayoutDetectorYOLO


def _env_int_bounded(key: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.getenv(key, str(default)))
    except ValueError:
        v = default
    return max(lo, min(v, hi))


class PDFService:
    def __init__(self, engine="ollama", target_lang="zh-TW"):
        self.engine = "ollama"
        self.target_lang = target_lang
        # Default model is now gpt-oss:20b
        self.ollama_model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
        # Translation temperature (can be overridden at runtime by n8n endpoint)
        self.temperature = 0.1
        self.s2tw = OpenCC("s2tw")
        # Match llm_service: per-request num_ctx for direct /api/chat calls (avoids huge Ollama defaults).
        self.ollama_num_ctx = _env_int_bounded("OLLAMA_NUM_CTX", 32768, 4096, 131072)

        # Initialize with DocLayout-YOLO detector
        print("[PDF Service] Initializing with DocLayout-YOLO...", flush=True)
        self.layout_translator = PDFLayoutPreservingService(
            translate_func=self._translate_ollama,
            translate_batch_func=self._translate_batch_ollama,
            layout_detector=PDFLayoutDetectorYOLO()
        )

    def _ollama_chat_options(self, **kwargs):
        opts = {"num_ctx": self.ollama_num_ctx}
        for k, v in kwargs.items():
            if v is not None:
                opts[k] = v
        return opts

    def _clean_llm_response(self, text: str) -> str:
        """
        Cleans LLM output by removing think blocks, conversational fillers, and meta-commentary.
        """
        # Remove <think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        
        # Remove translation notes
        translation_note_patterns = [
            r'\(translation note:.*?\)',
            r'\(note:.*?\)',
            r'\(Translation note:.*?\)',
            r'\(Note:.*?\)',
            r'\(.*?made sure to translate.*?\)',
            r'\(.*?I translated.*?\)',
            r'\(.*?literal translation.*?\)',
        ]
        
        for pattern in translation_note_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
        
        prefixes_to_remove = [
            "Here is the translation:", "Here is the translation of the TARGET TEXT:", 
            "Here's the translation:", "SURE, here is the translation:", "I'm ready to help.",
            "Translation:", "Sure!", "Here's the translation in Traditional Chinese:",
            "Here is the translated text:", "The translation is:", "I understand.",
            "Here is the summary:", "Key points:", "Summary:", "Final Summary:",
            "好的，", "當然，", "這是翻譯：", "翻譯如下：", "以下是翻譯：", "摘要如下：", "總結："
        ]

        cleaned = text.strip()
        
        changed = True
        max_iterations = 5
        iteration = 0
        while changed and iteration < max_iterations:
            changed = False
            iteration += 1
            for prefix in prefixes_to_remove:
                if cleaned.lower().startswith(prefix.lower()):
                    cleaned = cleaned[len(prefix):].strip()
                    changed = True
                    break

        return cleaned

    async def _translate_ollama(self, text: str, target_lang: str = "zh-TW", context: str = "") -> str:
        """
        Translates text using Ollama API (Async), handling smart chunking if necessary.
        """
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        base_url = base_url.rstrip("/")
        api_url = f"{base_url}/api/chat"

        if text.strip().isdigit():
            return text

        is_cn_to_en = target_lang.lower() in ['en', 'en-us', 'en-gb']
        
        # Chunking Strategy
        # Use simple chunking for very long blocks (>3000 chars)
        MAX_CHUNK_SIZE = 3000 
        if len(text) > MAX_CHUNK_SIZE:
            print(f"[PDF] Long text ({len(text)} chars). Chunking...", flush=True)
            return await self._translate_with_chunking(text, target_lang, context, api_url)
        
        # Single Block Translation
        system_prompt = (
            "Professional Translator. Translate to Traditional Chinese (Taiwan)."
            " RULES:"
            " 1. Output ONLY the translated text corresponding to the 'Target Text'."
            " 2. Ignore obvious OCR noise."
            " 3. The 'Target Text' may be a fragmented word due to line breaks."
            " 4. IMPORTANT: If 'Target Text' is the START of a split phrase, translate the WHOLE phrase utilizing the 'Page Context' to complete the meaning."
            " 5. IMPORTANT: If 'Target Text' is a meaningless tail/end fragment (e.g., '料)', 'tion', or '教，') that cannot stand alone and was translated in the previous part, output EXACTLY '<SKIP>'."
        )
        if is_cn_to_en:
            system_prompt = (
                "Translator. Output translation only. Fluent English. No original text.\n"
                "RULES:\n"
                "1. If 'Target Text' is the START of a split phrase, translate the WHOLE phrase utilizing the 'Page Context' to complete the meaning.\n"
                "2. If 'Target Text' is a meaningless tail/end fragment that cannot stand alone, output EXACTLY '<SKIP>'.\n"
                "3. Avoid literal translations of meaningless isolated characters.\n"
                "EXAMPLES:\n"
                "- Target Text: \"教，模型調教頻率為每個月進行\"\n  Output: \", and the model tuning is performed monthly.\" (DO NOT output 'Teaching')\n"
                "- Target Text: \"料)\"\n  Output: \"<SKIP>\"\n"
                "- Target Text: \"C.問題根因 (default 呈現本月的根因統計, highlight 前五大根因及其原始資\"\n  Output: \"C. Root Cause (default: display this month's root-cause statistics, highlighting the top five root causes and their original data\"\n"
            )

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if context:
            # Provide context but limit length to avoid massive prompt bloat per block
            messages.append({"role": "user", "content": f"Page Context for Reference:\n{context[:4000]}"})
        messages.append({"role": "user", "content": f"Target Text to Translate:\n{text}"})

        max_retries = 3
        # Use AsyncClient for non-blocking I/O
        async with httpx.AsyncClient(timeout=180.0) as client:
            for attempt in range(max_retries):
                try:
                    print(f"  [Ollama] Sending block ({len(text)} chars) to {self.ollama_model}...", flush=True)
                    r = await client.post(
                        api_url,
                        json={
                            "model": self.ollama_model,
                            "messages": messages,
                            "stream": False,
                            "options": self._ollama_chat_options(
                                temperature=self.temperature,
                                num_predict=4096,
                                top_p=0.9,
                            ),
                        }
                    )

                    if r.status_code == 200:
                        raw_out = r.json().get("message", {}).get("content", "").strip()
                        
                        if not raw_out:
                            print(f"  [Ollama] DEBUG: Model returned empty response.", flush=True)
                        else:
                            preview = raw_out[:100].replace('\n', ' ')
                            # print(f"  [Ollama] RAW Response (first 100 chars): {preview}...", flush=True)
                        
                        cleaned = self._clean_llm_response(raw_out)
                        
                        if not cleaned and raw_out:
                             print(f"  [Ollama] WARNING: Response empty after cleaning.", flush=True)

                        if not cleaned: 
                             print(f"  [Ollama] Empty response (Attempt {attempt+1})", flush=True)
                             continue
                             
                        result = self.s2tw.convert(cleaned) if target_lang == "zh-TW" else cleaned
                        print(f"  [Ollama] Success! Result: '{result[:30]}...'", flush=True)
                        return result
                    else:
                        print(f"  [Ollama] Failed: Status {r.status_code}", flush=True)
                except Exception as e:
                    print(f"  [Ollama] Error (Attempt {attempt+1}): {e}", flush=True)
        
        return text

    async def _translate_batch_ollama(self, texts: list, target_lang: str = "zh-TW", context: str = "") -> list:
        """
        Batch-translates a list of texts in a single Ollama API call.
        Returns a list of translations in the same order.
        Falls back to individual translation for any missing entries.
        """
        if not texts:
            return []

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        api_url = f"{base_url.rstrip('/')}/api/chat"
        is_cn_to_en = target_lang.lower() in ['en', 'en-us', 'en-gb']

        # Build numbered input using ##N## as delimiter
        numbered_input = "\n".join(f"##{i+1}## {t}" for i, t in enumerate(texts))

        if is_cn_to_en:
            system_prompt = (
                "Batch Translator. Translate each numbered item from Chinese to fluent English.\n"
                "RULES:\n"
                "1. Respond ONLY with translations. No commentary, no original text.\n"
                "2. Preserve the numbering format EXACTLY: ##N## [translation]\n"
                "3. Each item on its own line. Do NOT merge or skip numbers.\n"
                "4. Use <SKIP> ONLY when an item is a mid-word/mid-sentence TAIL fragment "
                "that was already translated as part of the previous item "
                "(e.g., 'tion', '料)', 'ching'). Short but COMPLETE items like table cell content, "
                "dates, or database names must be translated, NOT skipped.\n"
                "5. If an item starts mid-word/mid-phrase, use the Page Context to complete its meaning.\n"
                "EXAMPLE OUTPUT FORMAT:\n"
                "##1## Root Cause Analysis\n"
                "##2## FINE_USER User Table\n"
                "##3## <SKIP>\n"
                "##4## The model tuning is performed monthly.\n"
            )
        else:
            system_prompt = (
                "批次翻譯員。將每個編號項目翻譯成繁體中文（台灣）。\n"
                "規則：\n"
                "1. 只輸出翻譯結果，不要輸出原文或任何說明。\n"
                "2. 嚴格保留編號格式：##N## [翻譯]\n"
                "3. 每個項目獨立一行，不得合併或跳過編號。\n"
                "4. 只有在某項目是「上一項的殘尾碎塊」（例如：'料)'、'教，'、單一標點）時才使用 <SKIP>。\n"
                "   短小但意義完整的項目（如：表格欄位內容、日期、資料庫名稱）必須翻譯，不得跳過。\n"
                "5. 若項目是日期（如2024/09/19）或簡短標題，請保留或做對應翻譯。\n"
                "範例輸出格式：\n"
                "##1## 根因分析\n"
                "##2## FINE_USER 用戶表\n"
                "##3## <SKIP>\n"
                "##4## 模型調教每月執行一次。\n"
            )

        messages = [{"role": "system", "content": system_prompt}]
        if context:
            messages.append({"role": "user", "content": f"Page Context:\n{context[:3000]}"})
        messages.append({"role": "user", "content": f"Translate the following:\n{numbered_input}"})

        total = len(texts)
        print(f"  [Batch] Sending {total} blocks in 1 API call...", flush=True)

        max_retries = 2
        async with httpx.AsyncClient(timeout=300.0) as client:
            for attempt in range(max_retries):
                try:
                    r = await client.post(
                        api_url,
                        json={
                            "model": self.ollama_model,
                            "messages": messages,
                            "stream": False,
                            "options": self._ollama_chat_options(
                                temperature=self.temperature,
                                num_predict=8192,
                                top_p=0.9,
                            ),
                        }
                    )
                    if r.status_code == 200:
                        raw_content = r.json().get("message", {}).get("content", "")
                        raw_out = self._clean_llm_response(raw_content)

                        def _extract_parsed(text: str) -> dict:
                            """Extract ##N## translation map from text."""
                            result = {}
                            for m in re.finditer(r'##(\d+)##\s*(.*?)(?=\n##\d+##|\Z)', text, re.DOTALL):
                                idx = int(m.group(1))
                                val = m.group(2).strip()
                                result[idx] = val
                            return result

                        # Parse ##N## format from cleaned output
                        parsed = _extract_parsed(raw_out)

                        # Fallback: if thinking model placed translations inside <think> block,
                        # try extracting from raw content directly (before think removal)
                        if len(parsed) < total // 2:
                            think_match = re.search(r'<think>(.*?)</think>', raw_content, re.DOTALL)
                            if think_match:
                                parsed_from_think = _extract_parsed(think_match.group(1))
                                if len(parsed_from_think) > len(parsed):
                                    print(f"  [Batch] Recovered from <think> block: {len(parsed_from_think)} items.", flush=True)
                                    parsed = parsed_from_think

                        print(f"  [Batch] Parsed {len(parsed)}/{total} translations.", flush=True)

                        results = []
                        fallback_indices = []
                        for i, original_text in enumerate(texts):
                            n = i + 1
                            if n in parsed:
                                translation = parsed[n]
                                if target_lang == "zh-TW" and "<SKIP>" not in translation:
                                    translation = self.s2tw.convert(translation)
                                results.append(translation)
                            else:
                                results.append(None)
                                fallback_indices.append(i)

                        # Fallback: individually translate any missing blocks
                        if fallback_indices:
                            print(f"  [Batch] Fallback for {len(fallback_indices)} missing blocks.", flush=True)
                            for fi in fallback_indices:
                                fallback_result = await self._translate_ollama(texts[fi], target_lang, context)
                                results[fi] = fallback_result

                        return results
                    else:
                        print(f"  [Batch] Failed: {r.status_code}", flush=True)
                except Exception as e:
                    print(f"  [Batch] Error attempt {attempt+1}: {e}", flush=True)

        # Full fallback: translate individually
        print("  [Batch] Full fallback to individual translation.", flush=True)
        return [await self._translate_ollama(t, target_lang, context) for t in texts]

    async def _translate_with_chunking(self, text: str, target_lang: str, context: str, api_url: str) -> str:
        """
        Async chunked translation.
        """
        import re
        
        # Split by periods, semicolons, or newlines while keeping separators
        chunks = re.split(r'([。\n；])', text)
        
        combined_chunks = []
        current_chunk = ""
        # 20b model handles 1k+ chars easily
        TARGET_CHUNK_SIZE = 1000 
        
        for part in chunks:
            if len(current_chunk) + len(part) > TARGET_CHUNK_SIZE:
                if current_chunk.strip():
                    combined_chunks.append(current_chunk)
                current_chunk = part
            else:
                current_chunk += part
                
        if current_chunk.strip():
            combined_chunks.append(current_chunk)
        
        if not combined_chunks and text.strip():
            combined_chunks = [text]
            
        print(f"[PDF] Optimized chunking: {len(text)} chars -> {len(combined_chunks)} chunks (Target: {TARGET_CHUNK_SIZE})", flush=True)
        
        is_cn_to_en = target_lang.lower() in ['en', 'en-us', 'en-gb']
        translated_chunks = []
        previous_translation = ""
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            for idx, chunk in enumerate(combined_chunks):
                if not chunk.strip():
                    continue
                    
                system_prompt = "Translator. Output translation only. Natural Traditional Chinese."
                if is_cn_to_en:
                    system_prompt = "Translator. Output translation only. Fluent English."
                
                if previous_translation:
                    system_prompt += f"\nContext: {previous_translation[-200:]}..."

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Text:\n{chunk}"},
                ]

                max_retries = 3
                chunk_translation = None
                
                for attempt in range(max_retries):
                    try:
                        print(f"  [Ollama-Chunk] Sending chunk {idx+1}/{len(combined_chunks)} to {self.ollama_model}...", flush=True)
                        
                        r = await client.post(
                            api_url,
                            json={
                                "model": self.ollama_model,
                                "messages": messages,
                                "stream": False,
                                "options": self._ollama_chat_options(
                                    temperature=self.temperature,
                                    num_predict=4096,
                                    top_p=0.9,
                                ),
                            }
                        )

                        if r.status_code == 200:
                            raw_out = r.json().get("message", {}).get("content", "").strip()
                            chunk_translation = self._clean_llm_response(raw_out)
                            
                            if chunk_translation:
                                if target_lang == "zh-TW":
                                    chunk_translation = self.s2tw.convert(chunk_translation)
                                print(f"  [Ollama-Chunk] Success! ({len(chunk_translation)} chars)", flush=True)
                                break
                            else:
                                 print(f"  [Ollama-Chunk] Empty response (Attempt {attempt+1})", flush=True)
                        else:
                             print(f"  [Ollama-Chunk] Failed: {r.status_code}", flush=True)

                    except Exception as e:
                        print(f"  [Ollama-Chunk] Chunk {idx+1} error: {e}", flush=True)
                
                if chunk_translation:
                    translated_chunks.append(chunk_translation)
                    previous_translation = chunk_translation
                else:
                    print(f"  [Ollama-Chunk] FAILED chunk {idx+1}. Using original.", flush=True)
                    translated_chunks.append(chunk)
        
        final_translation = " ".join(translated_chunks)
        print(f"[PDF] Chunked translation complete. Original: {len(text)} chars -> Translated: {len(final_translation)} chars", flush=True)
        return final_translation

    async def process_pdf(self, input_pdf_path: str, force_target_lang: str = None, debug_mode: bool = False, is_complex_table: bool = False):
        """
        Processes the PDF (Async Entry Point).
        """
        if not os.path.exists(input_pdf_path):
            raise FileNotFoundError(f"File not found: {input_pdf_path}")

        print(f"[PDF] processing: {input_pdf_path} (Debug: {debug_mode})", flush=True)
        
        target_lang = force_target_lang or "zh-TW"
        
        dir_name = os.path.dirname(input_pdf_path)
        base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
        output_pdf_path = os.path.join(dir_name, f"{base_name}_translated.pdf")
        
        gpu_work_acquire(MODULE_DOCUMENT_TRANSLATION)
        try:
            # AWAIT the async translation process
            await self.layout_translator.translate_pdf(
                input_path=input_pdf_path,
                output_path=output_pdf_path,
                target_lang=target_lang,
                debug_mode=debug_mode,
                is_complex_table=is_complex_table
            )
            
            return [
                {
                    "page": "Full Document",
                    "file_path": output_pdf_path, 
                    "summary": "Summary generation disabled.",
                    "paragraphs": ["Content is inside the translated PDF file."]
                }
            ]

        except Exception as e:
            print(f"[PDF] Processing error: {e}")
            raise e
        finally:
            gpu_work_release(MODULE_DOCUMENT_TRANSLATION)

# Global instance
pdf_service = PDFService(engine="ollama")
