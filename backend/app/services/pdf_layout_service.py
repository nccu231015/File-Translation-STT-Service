import fitz  # PyMuPDF
import os
from typing import Callable
from .pdf_layout_detector import PDFLayoutDetector
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
    
    def __init__(self, translate_func: Callable[[str, str, str], str]):
        """
        Args:
            translate_func: Callback function (text, target_lang, context) -> translated_text
        """
        self.translate_func = translate_func
        self.layout_detector = PDFLayoutDetector()

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
            print(f"\n[PDF Layout] ===== Processing page {page_num + 1}/{total_pages} =====")
            
            try:
                # STEP 1: Layout Detection
                print(f"[PDF Layout] Step 1: Detecting layout...")
                layout_blocks = self.layout_detector.detect_layout(input_path, page_num)

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
                            # Validation
                            if block.page_width == 0 or block.page_height == 0:
                                print(f"[PDF Layout] WARNING: Block {idx} has invalid dimensions, skipping")
                                continue
                            
                            # Get color based on type
                            color = color_map.get(block.type, default_color)

                            # Convert pixel bbox to PDF pdf_rect
                            pdf_rect = self.layout_detector.pixel_to_pdf_rect(
                                block.bbox, page, block.page_width, block.page_height
                            )
                            
                            # Validate rect
                            if pdf_rect.is_empty or pdf_rect.width < 1 or pdf_rect.height < 1:
                                print(f"[PDF Layout] WARNING: Block {idx} produced invalid rect, skipping")
                                continue

                            # Draw Box with specific color
                            page.draw_rect(pdf_rect, color=color, width=1.5)
                            
                            # Draw Label (Type + Confidence)
                            label = f"{block.type} ({block.confidence:.2f})"
                            # Ensure text is slightly above or inside if at top
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
                    continue # Skip to next page (no translation in debug mode)
                
                
                # Filter logic
                
                # Filter logic
                # 1. Identify "Protected Areas" (Figures and Tables) with a 10-unit safety buffer
                figure_blocks = [b for b in layout_blocks if b.type.lower() in ['figure', 'table', 'equation']]
                protected_rects = []
                for fb in figure_blocks:
                    # Inflate the figure rect slightly
                    fb_rect = fitz.Rect(fb.bbox)
                    fb_rect.x0 -= 10
                    fb_rect.y0 -= 10
                    fb_rect.x1 += 10
                    fb_rect.y1 += 10
                    protected_rects.append(fb_rect)
                
                # 2. Identify Candidates (Text, Title, List)
                text_candidates = [b for b in layout_blocks if b.type.lower() in ['text', 'title', 'list']]
                
                text_blocks = []
                for tb in text_candidates:
                    tb_rect = fitz.Rect(tb.bbox)
                    is_protected = False
                    
                    # Check intersection with expanded protected rects
                    for p_rect in protected_rects:
                        if tb_rect.intersects(p_rect):
                            is_protected = True
                            break
                    
                    # --- CRITICAL: Titles/Headers should NEVER be protected/skipped by figures ---
                    if tb.type.lower() == 'title':
                        is_protected = False
                    
                    if not is_protected:
                        text_blocks.append(tb)

                # --- NEW STEP: Remove Overlapping Text Blocks (NMS) ---
                # Sort by area (largest first) to prioritize preserving container blocks
                text_blocks.sort(key=lambda b: fitz.Rect(b.bbox).get_area(), reverse=True)
                
                unique_blocks = []
                for i, current_block in enumerate(text_blocks):
                    curr_rect = fitz.Rect(current_block.bbox)
                    is_duplicate = False
                    
                    for kept_block in unique_blocks:
                        kept_rect = fitz.Rect(kept_block.bbox)
                        
                        # Check intersection
                        if curr_rect.intersects(kept_rect):
                            intersect_area = curr_rect.intersect(kept_rect).get_area()
                            curr_area = curr_rect.get_area()
                            
                            # If the current (smaller) block is >50% contained in a kept (larger) block, drop it
                            # Threshold set to 50% (balanced) to remove nested lists/duplicates but keep columns
                            if curr_area > 0 and (intersect_area / curr_area) > 0.5:
                                is_duplicate = True
                                # print(f"[PDF Layout] Dropping duplicate block (contained in larger block)")
                                break
                    
                    if not is_duplicate:
                        unique_blocks.append(current_block)
                
                text_blocks = unique_blocks
                # -----------------------------------------------------

                print(f"[PDF Layout] Page {page_num+1}: Found {len(text_blocks)} translatable blocks")
                
                # Collect full page context for better translation
                page_context = page.get_text()
                
                for idx, block in enumerate(text_blocks):
                    try:
                        # STEP 2: Text Extraction
                        pdf_rect = self.layout_detector.pixel_to_pdf_rect(
                            block.bbox, page, block.page_width, block.page_height
                        )
                        
                        block_text = page.get_textbox(pdf_rect).strip()
                        
                        # --- ADVANCED SKIP LOGIC ---
                        if not block_text: continue
                        
                        is_numeric = re.match(r'^[\d\s\.,\-\/%$€]+$', block_text)
                        
                        if len(block_text) < 3 and not any('\u4e00' <= c <= '\u9fff' for c in block_text):
                            if not block_text.isupper(): continue
                        
                        if is_numeric and block.type.lower() != 'title':
                            continue

                        # Extract formatting (pass block type to decide strategy)
                        format_info = self._extract_format_info(page, pdf_rect, block_type=block.type)
                        
                        print(f"[PDF Layout] Block {idx+1}/{len(text_blocks)}: '{block_text[:30]}...' ({block.type} | Size: {format_info['fontsize']})")
                        
                        # STEP 3: Translation
                        translated_text = self.translate_func(block_text, target_lang, page_context)
                        
                        if not translated_text or translated_text.strip() == block_text:
                            continue
                        
                        # STEP 4 & 5: Wipe and Render
                        page.draw_rect(pdf_rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=1)
                        self._insert_text_adaptive(page, pdf_rect, translated_text, target_lang, format_info)
                        
                    except Exception as block_error:
                        print(f"[PDF Layout] ERROR processing block {idx+1}: {block_error}")
                        continue
                
                print(f"[PDF Layout] Page {page_num + 1} completed successfully")
                
            except Exception as page_error:
                print(f"[PDF Layout] ERROR processing page {page_num + 1}: {page_error}")
                continue

        # Save translated PDF
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
        print(f"\n[PDF Layout] Translation completed. Saved to {output_path}")

    def _extract_format_info(self, page: fitz.Page, rect: fitz.Rect, block_type: str = "text") -> dict:
        """
        Extract formatting info using weighted voting.
        Larger fonts have higher influence on the final color and size.
        """
        # Shrink rect very slightly to avoid border noise (1px)
        search_rect = fitz.Rect(rect.x0 + 1, rect.y0 + 1, rect.x1 - 1, rect.y1 - 1)
        if search_rect.is_empty or search_rect.width < 1:
            search_rect = rect
            
        blocks = page.get_text("dict", clip=search_rect)["blocks"]
        
        format_info = {"font": "helv", "fontsize": 11, "color": (0, 0, 0), "bold": False}
        
        weighted_sizes = {} # size -> total_weight
        weighted_colors = {} # color_tuple -> total_weight
        
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
                        
                        # Collect size
                        weighted_sizes[sz] = weighted_sizes.get(sz, 0) + weight
                        
                        # Collect color
                        c = span.get("color", 0)
                        r = ((c >> 16) & 0xFF) / 255.0
                        g = ((c >> 8) & 0xFF) / 255.0
                        b = (c & 0xFF) / 255.0
                        color_tuple = (r, g, b)
                        weighted_colors[color_tuple] = weighted_colors.get(color_tuple, 0) + weight
                        
        # --- SAFEGUARD: Downgrade long titles to text ---
        if block_type.lower() == 'title' and total_chars > 50:
            block_type = 'text'

        # --- SAFEGUARD: Smart Bold Detection ---
        if total_chars > 0 and (bold_chars / total_chars) > 0.5:
            format_info["bold"] = True
        
        if weighted_sizes:
            # Logic: If it is a Title, prefer Max size for impact
            # If it is Text/List, prefer Dominant size for consistency
            if block_type.lower() == 'title':
                 # Let's use simple max for Titles to ensure they are big
                 format_info["fontsize"] = max(weighted_sizes.keys())
            else:
                 # For normal text, use the weighted mode (dominant size by mass)
                 format_info["fontsize"] = max(weighted_sizes, key=weighted_sizes.get)
                 
        if weighted_colors:
            format_info["color"] = max(weighted_colors, key=weighted_colors.get)
            
        return format_info

    def _insert_text_adaptive(self, page: fitz.Page, rect: fitz.Rect, text: str, target_lang: str, format_info: dict = None):
        """
        Insert translated text using insert_htmlbox for adaptive scaling.
        Preserves original formatting (font, size, color).
        Falls back to insert_textbox if htmlbox fails.
        """
        if format_info is None:
            format_info = {"font": "helv", "fontsize": 12, "color": (0, 0, 0)}
        
        # Determine font based on language
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        
        # Use original color
        r, g, b = format_info["color"]
        color_hex = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        
        # Check if translating Chinese -> English (or meaningful expansion)
        # If target is English, we set base font size to 85% of original to help fitting
        css_font_size = "100%"
        if target_lang and target_lang.lower().startswith("en"):
            css_font_size = "85%"

        # --- CRITICAL FIX: Erase Original Text Properly ---
        # Draw a white rectangle with 100% opacity over the original area
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=1)

        # Try insert_htmlbox for adaptive scaling
        try:
            # Use Noto Sans CJK TC for professional Chinese rendering
            # For English, use Roboto or Noto Sans for a modern look
            font_family = "'Noto Sans CJK TC', 'Microsoft JhengHei', 'Droid Sans Fallback', sans-serif" if is_chinese else "'Roboto', 'Noto Sans', 'Helvetica', 'Arial', sans-serif"
            font_weight = "bold" if format_info.get("bold") else "normal"
            
            # Smart Alignment: Center for small blocks (charts/labels), Left for paragraphs
            text_align = "left"
            if rect.width < 150:
                text_align = "center"
            
            html = f'<div style="font-family: {font_family}; color: {color_hex}; font-weight: {font_weight}; margin: 0; padding: 0;">{text}</div>'
            
            # insert_htmlbox returns a rect (the unused space) or None/Error code in older versions
            # In new PyMuPDF, it returns the rectangle of the inserted text or (0,0,0,0) if failed?
            # Actually, let's just use it and catch errors.
            
            rc = page.insert_htmlbox(
                rect,
                html,
                css=f"div {{ line-height: 1.3; font-size: {css_font_size}; text-align: {text_align}; }}", 
                # scale_low=0.1 -> Allow scaling down text to 10% (CRITICAL for small text)
                scale_low=0.1
            )
            
            # The return value 'rc' in newer PyMuPDF is the unused rectangle (fitz.Rect)
            # If it failed to fit even after scaling, the unused rect might be empty or valid.
            # But the previous error was comparing a tuple/rect with an int.
            # We assume if no exception was raised, it succeeded partially.
            print(f"[PDF Layout] Text inserted using htmlbox (auto-scaled)")
            return
        
        except Exception as e:
            # print(f"[PDF Layout] htmlbox error: {e}, falling back to textbox")
            # Silently fallback to keep logs clean
            pass
        
        # Fallback: Use insert_textbox with manual scaling
        font_name = "china-t" if is_chinese else "helv"
        
        # Use original font size as maximum, with reasonable bounds
        original_size = format_info.get("fontsize", 12)
        min_size = 4 # Allow very small text (4pt) for footnotes/charts
        max_size = int(original_size * 1.2)  # Allow 20% larger max
        
        # Binary search or linear scan for best fit
        for fontsize in range(max_size, min_size - 1, -1):
            # Check if it fits without actually inserting (render_mode=1 or essentially checking return)
            # insert_textbox returns negative value if it doesn't fit
            rc = page.insert_textbox(
                rect,
                text,
                fontsize=fontsize,
                fontname=font_name,
                color=format_info["color"],
                align=fitz.TEXT_ALIGN_LEFT
            )
            
            if rc >= 0:  # Text fits!
                print(f"[PDF Layout] Text inserted using textbox (fontsize={fontsize}pt)")
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
