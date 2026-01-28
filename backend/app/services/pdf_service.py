import os
import requests
import re
from opencc import OpenCC
from .pdf_layout_service import PDFLayoutPreservingService

class PDFService:
    def __init__(self, engine="ollama", target_lang="zh-TW"):
        self.engine = "ollama"
        self.target_lang = target_lang
        self.ollama_model = "qwen2.5:7b"
        self.s2tw = OpenCC("s2tw")
        
        self.layout_translator = PDFLayoutPreservingService(
            translate_func=self._translate_ollama
        )

    def _clean_llm_response(self, text: str) -> str:
        """
        Removes common conversational filler prefixes and <think> blocks from LLM output.
        """
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
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

    def _detect_is_chinese(self, text: str) -> bool:
        """Detects if the text is primarily Chinese."""
        if not text:
            return False
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        return (chinese_chars / (len(text) + 1)) > 0.05

    def _translate_ollama(self, text: str, target_lang: str = "zh-TW", context: str = "") -> str:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        base_url = base_url.rstrip("/")
        api_url = f"{base_url}/api/chat"


        is_cn_to_en = target_lang.lower() in ['en', 'en-us', 'en-gb']
        
        if is_cn_to_en:
            system_prompt = (
                "You are a professional translator for formal business and academic documents. "
                "Translate the Chinese text segment into professional, fluent English.\n\n"
                "CRITICAL RULES:\n"
                "1. COMPLETE TRANSLATION: You MUST translate ALL Chinese text. Do NOT leave ANY Chinese characters untranslated.\n"
                "2. PROPER NOUNS: Only keep Chinese for organization names if they don't have English equivalents. Translate everything else.\n"
                "3. NATURALNESS: Produce natural, fluent English that reads like a native document.\n"
                "4. NO EXPLANATIONS: Output ONLY the translated English text.\n"
                "5. CONTEXT: Use the PAGE CONTEXT below to understand the full meaning, but ONLY translate the 'TARGET TEXT'.\n\n"
                f"=== PAGE CONTEXT (For Reference) ===\n{context[:8000]}\n=== END CONTEXT ===\n"
            )
        else:
            system_prompt = (
                "You are a professional translator for formal business and academic documents. "
                "Translate the English text segment into professional Traditional Chinese (Taiwan, zh-TW).\n\n"
                "CRITICAL RULES:\n"
                "1. FULL TRANSLATION: Translate ALL English content. Do NOT leave English words unless they are proper nouns or acronyms.\n"
                "2. NATURALNESS: Produce natural, fluent Traditional Chinese.\n"
                "3. NO EXPLANATIONS: Output ONLY the translated text.\n"
                "4. CONTEXT: Use the PAGE CONTEXT to understand meaning, but ONLY translate the 'TARGET TEXT'.\n\n"
                f"=== PAGE CONTEXT (For Reference) ===\n{context[:8000]}\n=== END CONTEXT ===\n"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"TARGET TEXT:\n{text}"},
        ]

        if text.strip().isdigit():
            return text

        max_retries = 3
        for attempt in range(max_retries):
            try:
                r = requests.post(
                    api_url,
                    json={
                        "model": self.ollama_model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "top_p": 0.9,
                            "top_k": 40,
                        },
                    },
                    timeout=300,
                )

                if r.status_code == 200:
                    out = r.json().get("message", {}).get("content", "").strip()
                    cleaned = self._clean_llm_response(out)
                    if target_lang == "zh-TW":
                        return self.s2tw.convert(cleaned)
                    return cleaned
                else:
                    print(f"[PDF] Translation failed (Attempt {attempt+1}): Status {r.status_code}")
            except Exception as e:
                print(f"[PDF] Translation error (Attempt {attempt+1}): {e}")
        
        print(f"[PDF] All retries failed for text: {text[:20]}...")

        return text

    def process_pdf(self, input_pdf_path: str, force_target_lang: str = None):
        """
        Processes the PDF: Uses PyMuPDF to preserve layout and translation.
        Returns a structured response, but now points to the translated PDF file.
        """
        if not os.path.exists(input_pdf_path):
            raise FileNotFoundError(f"File not found: {input_pdf_path}")

        print(f"[PDF] processing: {input_pdf_path}")
        
        target_lang = force_target_lang or "zh-TW"
        
        dir_name = os.path.dirname(input_pdf_path)
        base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
        output_pdf_path = os.path.join(dir_name, f"{base_name}_translated.pdf")
        
        try:
            self.layout_translator.translate_pdf(
                input_path=input_pdf_path,
                output_path=output_pdf_path,
                target_lang=target_lang
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
