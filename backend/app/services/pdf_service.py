import os
import requests
import re
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from opencc import OpenCC


class PDFService:
    def __init__(self, engine="ollama", target_lang="zh-TW"):
        self.engine = "ollama"  # Enforce Ollama
        self.target_lang = target_lang
        self.ollama_model = "qwen2.5:7b"  # Default Ollama model

        # Initialize OpenCC for simplified to traditional Chinese conversion
        self.s2tw = OpenCC("s2tw")  # Simplified to Traditional (Taiwan standard)

        # Configure Docling to be more aggressive with tables but respectful of speed
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # Disable forced OCR to speed up processing
        pipeline_options.do_table_structure = (
            True  # Explicitly enable table structure recognition
        )
        pipeline_options.table_structure_options.mode = (
            TableFormerMode.ACCURATE
        )  # Use more accurate model

        self.converter = DocumentConverter(
            format_options={PdfFormatOption: pipeline_options}
        )

    def _clean_llm_response(self, text: str) -> str:
        """
        Removes common conversational filler prefixes and <think> blocks from LLM output.
        """
        # 1. Remove <think>...</think> blocks (common in reasoning models)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # 2. Remove localized filler prefixes
        prefixes_to_remove = [
            "Here is the translation:",
            "SURE, here is the translation:",
            "I'm ready to help.",
            "Translation:",
            "Sure!",
            "Here's the translation in Traditional Chinese:",
            "Here is the summary:",
            "Key points:",
            # ... existing ...
            "Summary:",
            "Final Summary:",
            "好的，",
            "當然，",
            "這是翻譯：",
            "翻譯如下：",
            "以下是翻譯：",
            "摘要如下：",
            "總結：",
        ]

        cleaned = text.strip()
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()

        return cleaned

    def _translate_ollama(self, text: str) -> str:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        base_url = base_url.rstrip("/")
        api_url = f"{base_url}/api/chat"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional translator. "
                    "Your ONLY task is to translate the provided text into Traditional Chinese (Taiwan standard, zh-TW).\n"
                    "CRITICAL RULES:\n"
                    "1. Output ONLY the translated Chinese text.\n"
                    "2. DO NOT include the original English text.\n"
                    "3. DO NOT output conversational fillers (e.g. 'Here is the translation').\n"
                    "4. Translate accurately and fluently."
                ),
            },
            {"role": "user", "content": f"The text to translate is:\n\n{text}"},
        ]

        try:
            r = requests.post(
                api_url,
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=300,
            )

            if r.status_code == 200:
                out = r.json().get("message", {}).get("content", "").strip()
                cleaned = self._clean_llm_response(out)
                # Convert simplified Chinese to traditional Chinese (Taiwan)
                return self.s2tw.convert(cleaned)
        except Exception as e:
            print(f"[PDF] Translation error (Ollama): {e}")

        return text

    def process_pdf(self, input_pdf_path: str):
        """
        Processes the PDF: Uses Docling to convert PDF to Markdown text, then translate.
        Returns a structured list.
        """
        if not os.path.exists(input_pdf_path):
            raise FileNotFoundError(f"File not found: {input_pdf_path}")

        print(f"[PDF] processing: {input_pdf_path}")
        print("[PDF] Attempting Docling conversion...")

        try:
            # 1. Convert PDF to Docling Document
            result = self.converter.convert(input_pdf_path)
            doc = result.document

            # Export to Markdown (best for LLM understanding)
            md_content = doc.export_to_markdown()

            # DEBUG: Check if extraction worked
            # print(
            #    f"\n--- [DEBUG] Docling Extracted Markdown (First 500 chars) ---\n{md_content[:500]}\n------------------------------------------------------------\n"
            # )

            # 2. Extract and Merge Chunks (OPTIMIZATION)
            # Instead of splitting by every new line, we group them into larger logical blocks.
            raw_chunks = [c.strip() for c in md_content.split("\n\n") if c.strip()]
            print(f"[PDF] Raw paragraphs extracted: {len(raw_chunks)}")

            merged_chunks = []
            current_chunk = []
            current_size = 0
            MAX_CHUNK_SIZE = (
                1500  # Reduced slightly to be safe with translation context
            )

            for p in raw_chunks:
                if len(p) < 2:
                    continue  # Skip noise

                # If adding this paragraph exceeds limit, save current chunk and start new one
                if current_size + len(p) > MAX_CHUNK_SIZE and current_chunk:
                    merged_chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0

                current_chunk.append(p)
                current_size += len(p)

            if current_chunk:
                merged_chunks.append("\n\n".join(current_chunk))

            print(
                f"[PDF] Merged into {len(merged_chunks)} translation blocks (Optimization)."
            )

            translated_paras = []
            total_chunks = len(merged_chunks)

            for i, chunk in enumerate(merged_chunks):
                print(f"[PDF] Translating block {i + 1}/{total_chunks}...")
                translated = self._translate_ollama(chunk)
                translated_paras.append(translated)

            # Generate Summary from the full translated text
            print("[PDF] Generating summary...")
            full_translated_text = "\n\n".join(translated_paras)
            summary = self._generate_summary(full_translated_text)
            print(f"[PDF] Generated Summary Content (First 200 chars): {summary[:200]}")

            return [
                {
                    "page": "Full Document",
                    "paragraphs": translated_paras,
                    "summary": summary,
                }
            ]

        except Exception as e:
            print(f"[PDF] Docling processing error: {e}")
            raise e

    def _generate_summary(self, text: str) -> str:
        """
        Generates a concise summary using Map-Reduce strategy.
        """
        chunk_size = 3000  # Reduced from 6000 to prevent timeouts on local LLM
        if len(text) <= chunk_size:
            return self._call_llm_for_summary(text, final=True)

        # Long document: Map-Reduce
        print("[PDF] Document is long. Starting Map-Reduce summarization...")
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        partial_summaries = []

        for idx, chunk in enumerate(chunks):
            print(f"[PDF] Summarizing part {idx + 1}/{len(chunks)}...")
            partial = self._call_llm_for_summary(chunk, final=False)
            if partial:
                partial_summaries.append(partial)

        if not partial_summaries:
            return "無法生成摘要。"

        combined_summary_text = "\n\n".join(partial_summaries)
        print("[PDF] Generating final summary from partials...")
        final_summary = self._call_llm_for_summary(combined_summary_text, final=True)
        return final_summary

    def _call_llm_for_summary(self, text: str, final: bool = False) -> str:
        """
        Helper to call LLM for summarization.
        """
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        base_url = base_url.rstrip("/")
        api_url = f"{base_url}/api/chat"

        if final:
            system_msg = (
                "You are a helpful AI assistant. "
                "Please read the following context and provide a comprehensive final summary in Traditional Chinese (zh-TW). "
                "Target length: Around 500 words. "
                "Focus on stitching the narrative together, highlighting key findings, and conclusions."
            )
            user_msg = f"Context:\n{text}"
        else:
            system_msg = (
                "You are a helpful AI assistant. "
                "Please read the following text segment and list the key points in Traditional Chinese (zh-TW). "
                "Keep it concise (around 100-150 words)."
            )
            user_msg = f"Text Segment:\n{text}"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        try:
            r = requests.post(
                api_url,
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=300,
            )
            if r.status_code == 200:
                out = r.json().get("message", {}).get("content", "").strip()
                cleaned = self._clean_llm_response(out)
                # Convert simplified Chinese to traditional Chinese (Taiwan)
                return self.s2tw.convert(cleaned)
        except Exception as e:
            print(f"[PDF] Summary generation error: {e}")
            return ""
        return ""

    def save_to_txt(self, pages_data, output_path):
        """
        Saves the processed data to a TXT file.
        """
        with open(output_path, "w", encoding="utf-8") as f:
            for page in pages_data:
                f.write(f"=== PAGE {page['page']} ===\n")
                for para in page["paragraphs"]:
                    f.write(para + "\n\n")
        return output_path


# Global instance
pdf_service = PDFService(
    engine="ollama"
)  # Defaulting to Ollama as requested implicitly by context, or google if preferred
