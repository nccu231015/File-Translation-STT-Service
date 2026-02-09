import os
import requests
import re
from opencc import OpenCC
from .pdf_layout_service import PDFLayoutPreservingService
from .pdf_layout_detector_yolo import PDFLayoutDetectorYOLO

class PDFService:
    def __init__(self, engine="ollama", target_lang="zh-TW"):
        self.engine = "ollama"
        self.target_lang = target_lang
        # Default model is now gpt-oss:20b
        self.ollama_model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
        self.s2tw = OpenCC("s2tw")
        
        # Initialize with DocLayout-YOLO detector
        print("[PDF Service] Initializing with DocLayout-YOLO...", flush=True)
        self.layout_translator = PDFLayoutPreservingService(
            translate_func=self._translate_ollama,
            layout_detector=PDFLayoutDetectorYOLO()
        )

    def _clean_llm_response(self, text: str) -> str:
        """
        Removes common conversational filler prefixes and <think> blocks from LLM output.
        Also removes translation notes and meta-commentary.
        """
        # Remove <think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        
        # Remove translation notes (extremely aggressive)
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

    def _translate_ollama(self, text: str, target_lang: str = "zh-TW", context: str = "") -> str:
        """
        Smart chunked translation with optimized parameters for speed.
        """
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        base_url = base_url.rstrip("/")
        api_url = f"{base_url}/api/chat"

        if text.strip().isdigit():
            return text

        is_cn_to_en = target_lang.lower() in ['en', 'en-us', 'en-gb']
        
        # --- SMART CHUNKING ---
        # Drastically increased to 3000 to prevent unnecessary splitting.
        # Modern models (gpt-oss:20b) can handle 4k+ tokens easily.
        MAX_CHUNK_SIZE = 3000 
        if len(text) > MAX_CHUNK_SIZE:
            print(f"[PDF] Long text ({len(text)} chars). Chunking...", flush=True)
            return self._translate_with_chunking(text, target_lang, context, api_url)
        
        # --- SINGLE CHUNK ---
        system_prompt = "Translator. Output translation only. Natural Traditional Chinese."
        if is_cn_to_en:
            system_prompt = "Translator. Output translation only. Fluent English."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Text:\n{text}"},
        ]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  [Ollama] Sending block ({len(text)} chars) to {self.ollama_model}...", flush=True)
                r = requests.post(
                    api_url,
                    json={
                        "model": self.ollama_model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Lower temperature = faster search
                            "num_predict": 4096, # Increased to prevent truncation for large blocks
                            "top_p": 0.9,
                        },
                    },
                    timeout=180, 
                )

                if r.status_code == 200:
                    raw_out = r.json().get("message", {}).get("content", "").strip()
                    # Enabled debug log to see EXACTLY what the model returned
                    if not raw_out:
                        print(f"  [Ollama] DEBUG: Model returned literally nothing.", flush=True)
                    else:
                        # Extract preview without newlines (f-string can't contain backslash)
                        preview = raw_out[:100].replace('\n', ' ')
                        print(f"  [Ollama] RAW Response (first 100 chars): {preview}...", flush=True)
                    
                    cleaned = self._clean_llm_response(raw_out)
                    
                    if not cleaned and raw_out:
                         print(f"  [Ollama] WARNING: Response empty after cleaning! Raw was: {len(raw_out)} chars.", flush=True)

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

    def _translate_with_chunking(self, text: str, target_lang: str, context: str, api_url: str) -> str:
        """
        Split long text into chunks at natural boundaries and translate separately.
        Used only for exceptionally long blocks (>3000 chars).
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
                    r = requests.post(
                        api_url,
                        json={
                            "model": self.ollama_model,
                            "messages": messages,
                            "stream": False,
                            "options": {
                                "temperature": 0.1,
                                "num_predict": 4096,
                                "top_p": 0.9,
                            },
                        },
                        timeout=180,
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

    def process_pdf(self, input_pdf_path: str, force_target_lang: str = None, debug_mode: bool = False):
        """
        Processes the PDF: Uses PyMuPDF to preserve layout and translation.
        """
        if not os.path.exists(input_pdf_path):
            raise FileNotFoundError(f"File not found: {input_pdf_path}")

        print(f"[PDF] processing: {input_pdf_path} (Debug: {debug_mode})")
        
        target_lang = force_target_lang or "zh-TW"
        
        dir_name = os.path.dirname(input_pdf_path)
        base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
        output_pdf_path = os.path.join(dir_name, f"{base_name}_translated.pdf")
        
        try:
            self.layout_translator.translate_pdf(
                input_path=input_pdf_path,
                output_path=output_pdf_path,
                target_lang=target_lang,
                debug_mode=debug_mode
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

# Global instance
pdf_service = PDFService(engine="ollama")
