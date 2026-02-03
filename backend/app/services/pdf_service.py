import os
import requests
import re
from opencc import OpenCC
from .pdf_layout_service import PDFLayoutPreservingService

class PDFService:
    def __init__(self, engine="ollama", target_lang="zh-TW"):
        self.engine = "ollama"
        self.target_lang = target_lang
        # Default model, can be overridden via environment variable
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:32b")
        self.s2tw = OpenCC("s2tw")
        
        self.layout_translator = PDFLayoutPreservingService(
            translate_func=self._translate_ollama
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
            r'translation note:.*?(?=\n|$)',
            r'Translation note:.*?(?=\n|$)',
            r'note:.*?(?=\n|$)',
            r'Note:.*?(?=\n|$)',
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
        MAX_CHUNK_SIZE = 500
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
                            "num_predict": 1024, # Safety cap
                            "top_p": 0.9,
                        },
                    },
                    timeout=120, # Reduced to 2 minutes
                )

                if r.status_code == 200:
                    out = r.json().get("message", {}).get("content", "").strip()
                    cleaned = self._clean_llm_response(out)
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
        """
        # Smart split at sentence boundaries
        # Priority: 。 (Chinese period) > \n (newline) > ； (semicolon) > ， (comma)
        import re
        
        # Split by periods, semicolons, or newlines
        # Keep the delimiter with the chunk
        chunks = re.split(r'([。\n；])', text)
        
        # Recombine chunks with their delimiters
        combined_chunks = []
        temp = ""
        for i, part in enumerate(chunks):
            temp += part
            if part in ['。', '\n', '；'] or len(temp) > 200:
                if temp.strip():
                    combined_chunks.append(temp)
                temp = ""
        if temp.strip():
            combined_chunks.append(temp)
        
        # If no natural boundaries found, force split by character count
        if len(combined_chunks) <= 1:
            combined_chunks = [text[i:i+200] for i in range(0, len(text), 200)]
        
        print(f"[PDF] Split into {len(combined_chunks)} chunks for translation")
        
        is_cn_to_en = target_lang.lower() in ['en', 'en-us', 'en-gb']
        translated_chunks = []
        previous_translation = ""
        
        for idx, chunk in enumerate(combined_chunks):
            if not chunk.strip():
                continue
                
            if is_cn_to_en:
                system_prompt = (
                    "Professional translator. Translate Chinese to English.\n"
                    "MUST translate every character. NO omissions.\n"
                )
                if previous_translation:
                    # Increased context window from 200 to 500 chars for Qwen3 32B
                    system_prompt += f"\nPREVIOUS CONTEXT:\n{previous_translation[-500:]}\n"
            else:
                system_prompt = (
                    "Professional translator. Translate English to Traditional Chinese.\n"
                    "MUST translate every word. NO omissions.\n"
                )
                if previous_translation:
                    system_prompt += f"\nPREVIOUS CONTEXT:\n{previous_translation[-500:]}\n"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Translate this part ({idx+1}/{len(combined_chunks)}):\n{chunk}"},
            ]

            max_retries = 2
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
                                "num_predict": 1024
                            },
                        },
                        timeout=120,
                    )

                    if r.status_code == 200:
                        out = r.json().get("message", {}).get("content", "").strip()
                        chunk_translation = self._clean_llm_response(out)
                        if target_lang == "zh-TW":
                            chunk_translation = self.s2tw.convert(chunk_translation)
                        print(f"  [Ollama-Chunk] Success! ({len(chunk_translation)} chars)", flush=True)
                        break
                except Exception as e:
                    print(f"  [Ollama-Chunk] Chunk {idx+1} error: {e}", flush=True)
            
            if chunk_translation:
                translated_chunks.append(chunk_translation)
                previous_translation = chunk_translation
            else:
                # Fallback: use original text if translation fails
                translated_chunks.append(chunk)
        
        # Merge all translated chunks
        final_translation = " ".join(translated_chunks)
        print(f"[PDF] Chunked translation complete. Original: {len(text)} chars -> Translated: {len(final_translation)} chars")
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
