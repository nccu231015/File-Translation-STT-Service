import fitz  # PyMuPDF
import os
from typing import Callable
import re

class PDFLayoutPreservingService:
    """
    5-Step Pipeline:
    1. Layout Detection (Layout Parser)
    2. Text Extraction (PyMuPDF vector-based)
    3. Translation (LLM)
    4. Original Text Erase (white rectangle overlay)
    5. Adaptive Rendering (insert_htmlbox with auto-scaling)
    """
    
    def __init__(self, translate_func: Callable[[str, str, str], str], layout_detector=None):
        """
        Args:
            translate_func: Callback function (text, target_lang, context) -> translated_text
            layout_detector: Layout detection instance (PDFLayoutDetectorYOLO or similar)
        """
        self.translate_func = translate_func
        self.layout_detector = layout_detector

    def translate_pdf(self, input_path: str, output_path: str, target_lang: str = "zh-TW", debug_mode: bool = False):
        """
        Translates the PDF using the new 5-step pipeline.
        If debug_mode is True, draws bounding boxes and skips translation.
        """
        doc = fitz.open(input_path)
        total_pages = len(doc)
        
        print(f"[PDF Layout] Starting translation for {input_path} ({total_pages} pages)")
        print(f"[PDF Layout] Target language: {target_lang} (Debug Mode: {debug_mode})")

        for page_num, page in enumerate(doc):
            print(f"\n[PDF Layout] ===== Processing page {page_num + 1}/{total_pages} =====", flush=True)
            
            try:
                # STEP 1: Layout Detection
                print(f"[PDF Layout] Step 1: Detecting layout...", flush=True)
                layout_blocks = self.layout_detector.detect_layout(input_path, page_num, page.rect.width, page.rect.height)

                # --- DEBUG MODE VISUALIZATION ---
                if debug_mode:
                    print(f"[PDF Layout] Debug mode enabled. Drawing {len(layout_blocks)} blocks.")
                    
                    if len(layout_blocks) == 0:
                        print(f"[PDF Layout] WARNING: No layout blocks detected on page {page_num + 1}")
                    
                    # Color mapping for different block types (RGB tuples)
                    color_map = {
                        "Text": (1, 0, 0),      # Red
                        "Title": (0, 0, 1),     # Blue
                        "List": (0, 0.5, 0),    # Dark Green
                        "Table": (1, 0.5, 0),   # Orange
                        "Figure": (0.5, 0, 0.5) # Purple
                    }
                    default_color = (0.5, 0.5, 0.5) # Grey for unknown

                    for idx, block in enumerate(layout_blocks):
                        try:
                            if block.page_width == 0 or block.page_height == 0:
                                continue
                            
                            color = color_map.get(block.type, default_color)

                            pdf_rect = self.layout_detector.pixel_to_pdf_rect(
                                block.bbox, page, block.page_width, block.page_height
                            )
                            
                            if pdf_rect.is_empty or pdf_rect.width < 1 or pdf_rect.height < 1:
                                continue

                            page.draw_rect(pdf_rect, color=color, width=1.5)
                            
                            label = f"{block.type} ({block.confidence:.2f})"
                            text_point = (pdf_rect.x0, pdf_rect.y0 - 5 if pdf_rect.y0 > 10 else pdf_rect.y0 + 10)
                            
                            page.insert_text(
                                text_point,
                                label, 
                                fontsize=8, 
                                color=color
                            )
                            
                        except Exception as block_err:
                            print(f"[PDF Layout] ERROR drawing block {idx}: {block_err}")
                            continue
                    
                    print(f"[PDF Layout] Debug visualization completed for page {page_num + 1}")
                    continue # Skip to next page
                
                # 1. Identify "Protected Areas" (Figures, Tables, Equations)
                figure_blocks = [b for b in layout_blocks if b.type.lower() in ['figure', 'table', 'equation']]
                protected_rects = []
                for fb in figure_blocks:
                    fb_rect = fitz.Rect(fb.bbox)
                    fb_rect.x0 -= 10
                    fb_rect.y0 -= 10
                    fb_rect.x1 += 10
                    fb_rect.y1 += 10
                    protected_rects.append(fb_rect)
                
                # 2. Identify Candidates (Text, Title, List) and filter overlaps
                text_candidates = [b for b in layout_blocks if b.type.lower() in ['text', 'title', 'list']]
                
                text_blocks = []
                for tb in text_candidates:
                    tb_rect = fitz.Rect(tb.bbox)
                    is_protected = False
                    
                    for p_rect in protected_rects:
                        if tb_rect.intersects(p_rect):
                            intersect_area = tb_rect.intersect(p_rect).get_area()
                            tb_area = tb_rect.get_area()
                            
                            # Only drop if substantially covered (>80%) and not a wide paragraph
                            is_wide_block = tb_rect.width > 150
                            
                            if tb_area > 0 and (intersect_area / tb_area) > 0.8:
                                if is_wide_block:
                                    print(f"[PDF Layout] Wide block overlap > 80%, preserving.", flush=True)
                                else:
                                    is_protected = True
                                    break
                    
                    # Titles are never protected
                    if tb.type.lower() == 'title':
                        is_protected = False
                    
                    if not is_protected:
                        text_blocks.append(tb)

                # Rescue misclassified components
                # FIX: Only rescue 'Abandon' or unknown blocks.
                # NEVER rescue 'Figure' or 'Table' because converting them to Text causes the image to be wiped/erased!
                ignored_blocks = [
                    b for b in layout_blocks 
                    if b.type.lower() not in ['text', 'title', 'list', 'figure', 'table', 'equation']
                ]
                
                for ib in ignored_blocks:
                    ib_rect = self.layout_detector.pixel_to_pdf_rect(ib.bbox, page, ib.page_width, ib.page_height)
                    ib_text = page.get_textbox(ib_rect).strip()
                    
                    # If clean paragraph found, force reclassify as Text
                    if len(ib_text) > 15:
                        has_content = any('\u4e00' <= c <= '\u9fff' for c in ib_text) or ' ' in ib_text
                        if has_content:
                            print(f"[PDF Layout] Rescuing text from {ib.type} block.", flush=True)
                            ib.type = 'Text'
                            text_blocks.append(ib)

                # NMS Deduplication (Smallest First)
                # Process specific paragraphs before containers
                text_blocks.sort(key=lambda b: fitz.Rect(b.bbox).get_area(), reverse=False)
                
                unique_blocks = []
                for i, current_block in enumerate(text_blocks):
                    curr_rect = fitz.Rect(current_block.bbox)
                    is_duplicate = False
                    
                    for kept_block in unique_blocks:
                        kept_rect = fitz.Rect(kept_block.bbox)
                        
                        if curr_rect.intersects(kept_rect):
                            intersect_area = curr_rect.intersect(kept_rect).get_area()
                            kept_area = kept_rect.get_area()
                            
                            # CRITICAL FIX: Check if the KEPT block (small) is contained in CURRENT block (large)
                            # If the kept block is >80% inside the current block, current is a "container" -> DROP IT
                            if kept_area > 0 and (intersect_area / kept_area) > 0.8:
                                is_duplicate = True
                                break
                    
                    if not is_duplicate:
                        unique_blocks.append(current_block)
                
                text_blocks = unique_blocks

                print(f"[PDF Layout] Page {page_num+1}: Found {len(text_blocks)} translatable blocks", flush=True)
                
                # Collect full page context for better translation
                page_context = page.get_text()
                
                for idx, block in enumerate(text_blocks):
                    try:
                        # STEP 2: Text Extraction
                        raw_rect = self.layout_detector.pixel_to_pdf_rect(
                            block.bbox, page, block.page_width, block.page_height
                        )
                        
                        # Vertically inflate raw box to ensure full capture
                        v_pad = 2.0
                        raw_rect = fitz.Rect(
                            raw_rect.x0,
                            raw_rect.y0 - v_pad,
                            raw_rect.x1,
                            raw_rect.y1 + v_pad
                        )
                        raw_rect.intersect(page.rect)
                        
                        # Calculate render rect with padding for expansion
                        padding = 2.0
                        render_rect = fitz.Rect(
                            raw_rect.x0 - padding,
                            raw_rect.y0 - padding,
                            raw_rect.x1 + (padding*2),
                            raw_rect.y1 + padding
                        )
                        render_rect.intersect(page.rect)

                        block_text = page.get_textbox(raw_rect).strip()
                        
                        # --- Filter Logic ---
                        if not block_text: continue
                        
                        # Skip pure numbers unless it's a title
                        is_numeric = re.match(r'^[\d\s\.,\-\/%$€]+$', block_text)
                        if is_numeric and block.type.lower() != 'title':
                            continue

                        # Extract formatting from ORIGINAL box
                        format_info = self._extract_format_info(page, raw_rect, block_type=block.type)
                        
                        print(f"[PDF Layout] Page {page_num+1} | Block {idx+1}/{len(text_blocks)}: Translating...", flush=True)
                        
                        # STEP 3: Translation
                        translated_text = self.translate_func(block_text, target_lang, page_context)
                        
                        if not translated_text or not translated_text.strip():
                            continue
                            
                        # Safety check for bad cleaning (short translation for long original)
                        if len(block_text) > 10 and len(translated_text.strip()) < 2 and not translated_text.strip().isdigit():
                             continue

                        if translated_text.strip() == block_text:
                            continue
                        
                        # STEP 4 & 5: Wipe and Render
                        # Wipe original area + bleed
                        wipe_rect = fitz.Rect(raw_rect.x0-0.5, raw_rect.y0-0.5, raw_rect.x1+0.5, raw_rect.y1+0.5)
                        page.draw_rect(wipe_rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=1)
                        
                        self._insert_text_adaptive(page, render_rect, translated_text, target_lang, format_info)
                        
                    except Exception as block_error:
                        print(f"[PDF Layout] ERROR processing block {idx+1}: {block_error}", flush=True)
                        continue
                
                print(f"[PDF Layout] Page {page_num + 1} completed successfully", flush=True)
                
            except Exception as page_error:
                print(f"[PDF Layout] ERROR processing page {page_num + 1}: {page_error}", flush=True)
                continue

        # Save translated PDF
        print(f"[PDF Layout] Saving finalized PDF to {output_path}...", flush=True)
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
        print(f"\n[PDF Layout] Success! Translation saved to {output_path}", flush=True)

    def _extract_format_info(self, page: fitz.Page, rect: fitz.Rect, block_type: str = "text") -> dict:
        """
        Extract formatting info using weighted voting.
        """
        # Shrink rect very slightly to avoid border noise (1px)
        search_rect = fitz.Rect(rect.x0 + 1, rect.y0 + 1, rect.x1 - 1, rect.y1 - 1)
        if search_rect.is_empty or search_rect.width < 1:
            search_rect = rect
            
        blocks = page.get_text("dict", clip=search_rect)["blocks"]
        
        format_info = {"font": "helv", "fontsize": 11, "color": (0, 0, 0), "bold": False}
        
        weighted_sizes = {} 
        weighted_colors = {}
        
        total_chars = 0
        bold_chars = 0
        
        for block in blocks:
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text_len = len(span.get("text", ""))
                        total_chars += text_len
                        
                        if "bold" in span.get("font", "").lower():
                            bold_chars += text_len
                            
                        sz = span.get("size", 11)
                        if sz < 4: continue
                        
                        # Weight
                        weight = sz * sz
                        weighted_sizes[sz] = weighted_sizes.get(sz, 0) + weight
                        
                        c = span.get("color", 0)
                        r = ((c >> 16) & 0xFF) / 255.0
                        g = ((c >> 8) & 0xFF) / 255.0
                        b = (c & 0xFF) / 255.0
                        color_tuple = (r, g, b)
                        weighted_colors[color_tuple] = weighted_colors.get(color_tuple, 0) + weight
                        
        # Downgrade long titles to text
        if block_type.lower() == 'title' and total_chars > 50:
            block_type = 'text'

        # Bold Detection
        if total_chars > 0 and (bold_chars / total_chars) > 0.5:
            format_info["bold"] = True
        
        if weighted_sizes:
            if block_type.lower() == 'title':
                 format_info["fontsize"] = max(weighted_sizes.keys())
            else:
                 format_info["fontsize"] = max(weighted_sizes, key=weighted_sizes.get)
                 
        if weighted_colors:
            format_info["color"] = max(weighted_colors, key=weighted_colors.get)
            
        return format_info

    def _insert_text_adaptive(self, page: fitz.Page, rect: fitz.Rect, text: str, target_lang: str, format_info: dict = None):
        """
        Insert translated text using insert_htmlbox for adaptive scaling.
        """
        if format_info is None:
            format_info = {"font": "helv", "fontsize": 12, "color": (0, 0, 0)}
        
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        
        # Use original color
        r, g, b = format_info["color"]
        color_hex = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        
        # Adjust size for English
        css_font_size = "100%"
        if target_lang and target_lang.lower().startswith("en"):
            css_font_size = "85%"

        # Erase Original Text
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=1)

        # Try insert_htmlbox for adaptive scaling
        try:
            font_family = "'Noto Sans CJK TC', 'Microsoft JhengHei', 'Droid Sans Fallback', sans-serif" if is_chinese else "'Roboto', 'Noto Sans', 'Helvetica', 'Arial', sans-serif"
            font_weight = "bold" if format_info.get("bold") else "normal"
            
            # Center small blocks (labels), Left for paragraphs
            text_align = "left"
            if rect.width < 150:
                text_align = "center"
            
            html = f'<div style="font-family: {font_family}; color: {color_hex}; font-weight: {font_weight}; margin: 0; padding: 0;">{text}</div>'
            
            css_style = (
                f"div {{ "
                f"  line-height: 1.25; "
                f"  font-size: {css_font_size}; "
                f"  text-align: {text_align}; "
                f"  overflow-wrap: break-word; "
                f"  word-break: break-word; "
                f"}}"
            )

            rc = page.insert_htmlbox(
                rect,
                html,
                css=css_style, 
                scale_low=0.1
            )
            return
        
        except Exception:
            pass
        
        # Fallback to insert_textbox
        font_name = "china-t" if is_chinese else "helv"
        
        original_size = format_info.get("fontsize", 12)
        min_size = 4
        max_size = int(original_size * 1.2)
        
        for fontsize in range(max_size, min_size - 1, -1):
            rc = page.insert_textbox(
                rect,
                text,
                fontsize=fontsize,
                fontname=font_name,
                color=format_info["color"],
                align=fitz.TEXT_ALIGN_LEFT
            )
            
            if rc >= 0:
                return
        
        # If nothing fits, use minimum size and force output
        page.insert_textbox(
            rect,
            text,
            fontsize=min_size,
            fontname=font_name,
            color=format_info["color"],
            align=fitz.TEXT_ALIGN_LEFT
        )
        print(f"[PDF Layout] Text forced at minimum size ({min_size}pt)")
