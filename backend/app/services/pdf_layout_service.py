import fitz
import os
import io
import re
from PIL import Image
import unicodedata

class PDFLayoutPreservingService:
    """
    A service that translates PDF files while preserving their original layout.
    It uses PyMuPDF (fitz) to extract text blocks, translate them, and re-insert them.
    """
    
    def __init__(self, translate_func):
        """
        Args:
            translate_func: A callback function (text, target_lang) -> translated_text
        """
        self.translate_func = translate_func
        # Create a reusable dummy document for text fitting calculations
        self.dummy_doc = fitz.open()
        # Create a large page to ensure any rect fits within it
        self.dummy_page = self.dummy_doc.new_page(width=5000, height=5000)

    def translate_pdf(self, input_path: str, output_path: str, target_lang: str = "zh-TW"):
        """
        Translates the PDF at input_path and saves it to output_path.
        """
        # Open the PDF
        doc = fitz.open(input_path)
        
        total_pages = len(doc)
        print(f"[PDF Layout] Starting translation for {input_path} ({total_pages} pages)")

        for page_num, page in enumerate(doc):
            print(f"[PDF Layout] Processing page {page_num + 1}/{total_pages}...")
            
            blocks = page.get_text("dict")["blocks"]
            
            drawings = page.get_drawings()
            chart_rects = [fitz.Rect(d["rect"]) for d in drawings]
            
            for b in blocks:
                if b["type"] == 1:
                    chart_rects.append(fitz.Rect(b["bbox"]))
            
            text_blocks = [b for b in blocks if b["type"] == 0]
            operations = []
            
            for block in text_blocks:
                bbox = fitz.Rect(block["bbox"])
                
                is_chart_text = False
                for chart_rect in chart_rects:
                     if bbox.intersects(chart_rect):
                        is_chart_text = True
                        break
                
                if is_chart_text:
                    try:
                        log_text = block['lines'][0]['spans'][0]['text']
                    except:
                        log_text = "Unknown"
                    print(f"[PDF Layout] Skipping chart-intersecting text: '{log_text[:20]}'")
                    continue

                block_text = ""
                for line in block["lines"]:
                    for span in line["spans"]:
                        block_text += span["text"] + " "
                
                block_text = block_text.strip()
                if not block_text or len(block_text) < 2:
                    continue
                
                bbox_area = bbox.width * bbox.height
                if len(block_text) < 5 or bbox_area < 500:
                    print(f"[PDF Layout] Skipping small block: '{block_text[:30]}'")
                    continue
                
                clean_text = block_text.strip()
                if clean_text in ['•', '·', '-', '–', '—', '*', '○', '●', '■', '□', '▪', '▫']:
                    continue
                
                try:
                    first_span = block["lines"][0]["spans"][0]
                    origin_font_size = first_span["size"]
                    origin_color = first_span.get("color", 0)
                    origin_font = first_span["font"]
                    
                    if origin_font_size < 8.0:
                        print(f"[PDF Layout] Skipping small font ({origin_font_size:.1f}): '{block_text[:30]}'")
                        continue
                        
                except IndexError:
                    continue
                
                print(f"[PDF Layout DEBUG] Block: text='{block_text[:50]}...' | "
                      f"bbox=({bbox.width:.1f}x{bbox.height:.1f}) | "
                      f"font_size={origin_font_size:.1f} | color=0x{origin_color:06X}")
                
                operations.append({
                    "bbox": bbox,
                    "text": block_text,
                    "font_size": origin_font_size,
                    "color": origin_color,
                    "font": origin_font
                })

            page_context = ""
            for block in text_blocks:
                for line in block["lines"]:
                    for span in line["spans"]:
                        page_context += span["text"] + " "
            
            print(f"[PDF Layout] Translating {len(operations)} blocks on page {page_num + 1}...")
            
            for idx, op in enumerate(operations):
                try:
                    translated_text = self.translate_func(op["text"], target_lang, context=page_context)
                    
                    if not translated_text or translated_text.strip() == "":
                        print(f"[PDF Layout] WARNING: Empty translation for block {idx}: '{op['text'][:30]}'")
                        continue
                    
                    page.add_redact_annot(op["bbox"], fill=(1, 1, 1))
                    page.apply_redactions()
                    self._insert_text_autoscale(
                        page,
                        op["bbox"],
                        translated_text,
                        color=op["color"],
                        max_font_size=op["font_size"],
                        target_lang=target_lang
                    )
                except Exception as block_error:
                    print(f"[PDF Layout] Error translating block {idx} ('{op['text'][:20]}'): {block_error}")
                    continue

        doc.save(output_path)
        doc.close()
        print(f"[PDF Layout] Translation saved to {output_path}")

    def _insert_text_autoscale(self, page, rect, text, color, max_font_size, target_lang="zh-TW"):
        """
        Inserts text into the given rect.
        Uses a dummy page to simulate writing and find the optimal font size that fits perfectly.
        """

        text = unicodedata.normalize('NFKC', text)
        def wide_to_half(s):
            result = ""
            for char in s:
                code = ord(char)
                if 0xFF01 <= code <= 0xFF5E:
                    result += chr(code - 0xFEE0)
                elif code == 0x3000:
                    result += chr(0x0020)
                else:
                    result += char
            return result
            
        text = wide_to_half(text)
        
        is_chinese = len(re.findall(r'[\u4e00-\u9fff]', text)) > len(text) * 0.1
        font_name = "china-t" if is_chinese else "helv"
        
        if color == 0:
            rgb_color = (0, 0, 0)
        else:
            r = ((color >> 16) & 0xFF) / 255.0
            g = ((color >> 8) & 0xFF) / 255.0
            b = (color & 0xFF) / 255.0
            
            if r < 0.2 and g < 0.2 and b < 0.2:
                rgb_color = (0, 0, 0)
            elif max_font_size <= 12 and b > r and b > g:
                rgb_color = (0, 0, 0)
            else:
                rgb_color = (r, g, b)
        
        is_translating_to_english = target_lang.lower() in ['en', 'en-us', 'en-gb']
        
        if is_chinese:
             fontsize = max_font_size - 1 if max_font_size > 10 else max_font_size
        else:
             fontsize = max_font_size
        
        min_fontsize = 8 if is_translating_to_english else 6
             
        best_fit_fontsize = min_fontsize
        
        while fontsize >= min_fontsize:
            try:
                rc = self.dummy_page.insert_textbox(
                    rect, text, fontsize=fontsize, fontname=font_name, 
                    color=rgb_color, align=fitz.TEXT_ALIGN_LEFT
                )
                if rc >= 0:
                    best_fit_fontsize = fontsize
                    break
            except Exception:
                pass
            fontsize -= 1 
                
        if best_fit_fontsize < 6: 
             best_fit_fontsize = 6
        
        if is_translating_to_english and best_fit_fontsize <= min_fontsize:
             rect.y1 = rect.y1 + (rect.height * 3)
        
        if is_chinese:
             approx_width = len(text) * best_fit_fontsize * 1.5
             if approx_width < rect.width:
                 rect.x1 = rect.x0 + approx_width
        
        try:
            page.insert_textbox(
                rect, 
                text, 
                fontsize=best_fit_fontsize, 
                fontname=font_name, 
                color=rgb_color,
                align=fitz.TEXT_ALIGN_LEFT,
                overlay=True
            )
        except Exception as e:
            print(f"[PDF Layout] Final write error: {e}")
