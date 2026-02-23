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

    async def translate_pdf(self, input_path: str, output_path: str, target_lang: str = "zh-TW", debug_mode: bool = False):
        """
        Main pipeline: Detect -> Extract -> Translate (Async) -> Render.
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

                # 1. Identify "Protected Areas" (Figures, Tables, Equations)
                figure_blocks = [b for b in layout_blocks if b.type.lower() in ['figure', 'table', 'equation']]
                print(f"[PDF Layout] Protected blocks: {len(figure_blocks)} ({', '.join([b.type for b in figure_blocks])})", flush=True)
                
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
                print(f"[PDF Layout] Text candidates: {len(text_candidates)} ({', '.join([b.type for b in text_candidates])})", flush=True)
                
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
                # Rescue 'Abandon' blocks that YOLO passed through (could be notes/captions).
                # NEVER rescue 'Figure', 'Table', 'Formula', or 'Equation' — wiping them destroys content!
                NEVER_RESCUE = {'figure', 'table', 'formula', 'equation'}
                ignored_blocks = [
                    b for b in layout_blocks 
                    if b.type.lower() not in ['text', 'title', 'list'] + list(NEVER_RESCUE)
                ]
                
                for ib in ignored_blocks:
                    ib_rect = self.layout_detector.pixel_to_pdf_rect(ib.bbox, page, ib.page_width, ib.page_height)
                    ib_text = page.get_text("text", clip=ib_rect).strip()
                    
                    # Rescue if the block contains meaningful text content (>10 chars, CJK or spaced words)
                    if len(ib_text) > 10:
                        has_content = any('\u4e00' <= c <= '\u9fff' for c in ib_text) or (' ' in ib_text and len(ib_text.split()) >= 2)
                        if has_content:
                            print(f"[PDF Layout] Rescuing text from {ib.type} block: '{ib_text[:40]}'", flush=True)
                            ib.type = 'Text'
                            text_blocks.append(ib)

                # Rescue completely undetected text (Orphans) using PyMuPDF blocks
                # This catches fine-print or metadata completely ignored by YOLO.
                print(f"[PDF Layout] Checking for completely un-detected text blocks...", flush=True)
                known_rects = [self.layout_detector.pixel_to_pdf_rect(b.bbox, page, b.page_width, b.page_height) for b in layout_blocks]
                page_blocks = page.get_text("dict").get("blocks", [])
                
                pg_w = layout_blocks[0].page_width if layout_blocks else page.rect.width
                pg_h = layout_blocks[0].page_height if layout_blocks else page.rect.height
                from .pdf_layout_detector_yolo import LayoutBlock
                
                for pb in page_blocks:
                    if pb.get("type") != 0: continue
                    for line in pb.get("lines", []):
                        line_rect = fitz.Rect(line["bbox"])
                        if line_rect.is_empty or line_rect.width < 10 or line_rect.height < 5:
                            continue
                        
                        overlap_ratio = 0
                        for kr in known_rects:
                            if line_rect.intersects(kr):
                                overlap_ratio = max(overlap_ratio, line_rect.intersect(kr).get_area() / line_rect.get_area())
                                if overlap_ratio > 0.4: break
                                    
                        if overlap_ratio <= 0.4:
                            line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                            if len(line_text) > 4 and (any('\u4e00' <= c <= '\u9fff' for c in line_text) or ' ' in line_text):
                                print(f"[PDF Layout] Orphan line rescue: '{line_text[:30]}'", flush=True)
                                scale_x = page.rect.width / pg_w
                                scale_y = page.rect.height / pg_h
                                orphan = LayoutBlock(
                                    bbox=(line_rect.x0 / scale_x, line_rect.y0 / scale_y, line_rect.x1 / scale_x, line_rect.y1 / scale_y),
                                    type='Text', confidence=1.0, page_width=pg_w, page_height=pg_h
                                )
                                text_blocks.append(orphan)

                # NMS Deduplication — Two-Pass Strategy
                # PASS 1 — Detect "container" blocks (large shells that simply
                #   wrap multiple smaller boxes). If ≥2 child blocks together
                #   cover ≥60% of a parent block, the parent is a shell →
                #   drop the parent and let the precise children do the wipe.
                # PASS 2 — Standard overlap dedup on the remaining blocks.
                # ------------------------------------------------------------
                print(f"[PDF Layout] NMS: Starting with {len(text_blocks)} blocks", flush=True)
                
                # Sort by Area DESCENDING (Largest First)
                text_blocks.sort(key=lambda b: fitz.Rect(b.bbox).get_area(), reverse=True)

                # --- PASS 1: Remove container/shell blocks ---
                container_indices = set()
                for i in range(len(text_blocks)):
                    if i in container_indices:
                        continue
                    rect_i = fitz.Rect(text_blocks[i].bbox)
                    area_i = rect_i.get_area()
                    if area_i == 0:
                        continue

                    child_area_sum = 0
                    child_count = 0
                    for j in range(i + 1, len(text_blocks)):
                        if j in container_indices:
                            continue
                        rect_j = fitz.Rect(text_blocks[j].bbox)
                        area_j = rect_j.get_area()
                        if area_j == 0 or area_j >= area_i:
                            continue  # only look at strictly smaller blocks
                        if rect_i.intersects(rect_j):
                            inter = rect_i.intersect(rect_j).get_area()
                            # Child is ≥70% inside the parent candidate
                            if area_j > 0 and inter / area_j > 0.70:
                                child_area_sum += area_j
                                child_count += 1

                    # Parent is a container shell if ≥2 children cover ≥60% of it
                    if child_count >= 2 and child_area_sum / area_i > 0.60:
                        container_indices.add(i)
                        print(
                            f"[PDF Layout] NMS Pass1: Block {i} is a container shell "
                            f"({child_count} children cover {child_area_sum/area_i:.0%}). Dropping parent.",
                            flush=True
                        )

                # Remove container shells from the candidate list
                text_blocks = [b for idx, b in enumerate(text_blocks) if idx not in container_indices]
                print(f"[PDF Layout] NMS Pass1: Removed {len(container_indices)} container shells, {len(text_blocks)} blocks remain", flush=True)

                # --- PASS 2: Standard overlap dedup ---
                unique_blocks = []
                dropped_count = 0

                for i, current_block in enumerate(text_blocks):
                    curr_rect = fitz.Rect(current_block.bbox)
                    curr_area = curr_rect.get_area()
                    is_duplicate = False

                    for kept_block in unique_blocks:
                        kept_rect = fitz.Rect(kept_block.bbox)
                        if curr_rect.intersects(kept_rect):
                            intersect_area = curr_rect.intersect(kept_rect).get_area()
                            # Drop if current block is >80% inside a kept block
                            if curr_area > 0 and (intersect_area / curr_area) > 0.80:
                                is_duplicate = True
                                print(
                                    f"[PDF Layout] NMS Pass2: Dropped block {i} "
                                    f"(>80% inside kept block). Overlap: {intersect_area/curr_area:.1%}",
                                    flush=True
                                )
                                break

                    if not is_duplicate:
                        unique_blocks.append(current_block)
                    else:
                        dropped_count += 1

                print(f"[PDF Layout] NMS Pass2: Kept {len(unique_blocks)} blocks, dropped {dropped_count}", flush=True)

                # Sort by Y position for top-to-bottom rendering order
                unique_blocks.sort(key=lambda b: b.bbox[1])
                text_blocks = unique_blocks
                
                # --- DEBUG MODE VISUALIZATION ---
                if debug_mode:
                    # Collect all blocks we want to visualize:
                    # 1. Original Layout blocks (like Figure, Table, Equation)
                    # 2. Rescued text blocks (from text_blocks list that aren't in layout_blocks)
                    blocks_to_draw = list(layout_blocks)
                    for tb in text_blocks:
                        if tb not in blocks_to_draw:
                            blocks_to_draw.append(tb)

                    print(f"[PDF Layout] Debug mode enabled. Drawing {len(blocks_to_draw)} blocks.")
                    
                    # Color mapping for different block types (RGB tuples)
                    color_map = {
                        "Text": (1, 0, 0),      # Red
                        "Title": (0, 0, 1),     # Blue
                        "List": (0, 0.5, 0),    # Dark Green
                        "Table": (1, 0.5, 0),   # Orange
                        "Figure": (0.5, 0, 0.5) # Purple
                    }
                    default_color = (0.5, 0.5, 0.5) # Grey for unknown

                    for idx, block in enumerate(blocks_to_draw):
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
                            
                            # If it's a rescued block, label it nicely
                            conf_label = "RESCUED" if block.confidence == 1.0 else f"{block.confidence:.2f}"
                            label = f"{block.type} ({conf_label})"
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

                # -----------------------------------------------------
                # NEW PIPELINE: Separate Wipe and Render Phases
                # -----------------------------------------------------
                
                print(f"[PDF Layout] Page {page_num+1}: Found {len(text_blocks)} translatable blocks", flush=True)
                
                # Context for translation
                page_context = page.get_text()
                
                # Store processed blocks to avoid re-extraction logic duplication
                # List of dict: { 'block': block, 'raw_rect': rect, 'text': str, 'format': dict }
                processed_queue = []
                # Removed text-based deduplication as geometric/Largest-First NMS is safer
                
                # --- PHASE 1: PREPARATION & WIPING ---
                # We collect all blocks first, then wipe them ALL at once.
                
                for idx, block in enumerate(text_blocks):
                    try:
                        # 1. Coordinate Conversion (Use exact YOLO bbox)
                        raw_rect = self.layout_detector.pixel_to_pdf_rect(
                            block.bbox, page, block.page_width, block.page_height
                        )
                        raw_rect.intersect(page.rect) # Ensure within page bounds
                        
                        # 2. Text Extraction (STRICT METHOD)
                        # Use get_text with clip instead of get_textbox for stricter extraction
                        block_text = page.get_text("text", clip=raw_rect).strip()
                        
                        # Filter Logic
                        if not block_text: continue
                        
                        print(f"[PDF Layout] Block {idx}: Extracted {len(block_text)} chars: '{block_text[:50]}...'", flush=True)
                        
                        # Skip purely numeric blocks (unless Title, e.g. "1.2.3")
                        is_numeric = re.match(r'^[\d\s\.,\-\/%$€]+$', block_text)
                        if is_numeric and block.type.lower() != 'title':
                            continue
                            
                        # Format Extraction
                        format_info = self._extract_format_info(page, raw_rect, block_type=block.type)
                        
                        # Queue it
                        processed_queue.append({
                            'block': block,
                            'raw_rect': raw_rect,
                            'text': block_text,
                            'format': format_info,
                            'sort_key': raw_rect.y0 # Key for sorting
                        })
                        
                        # EXECUTE WIPE using actual text bbox (more precise than YOLO bbox)
                        # Use PyMuPDF's real span positions + 1pt margin to avoid destroying nearby lines/tables
                        wipe_rect = self._get_precise_wipe_rect(page, raw_rect, margin=1)
                        page.draw_rect(wipe_rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=1)
                        
                    except Exception as e:
                        print(f"[PDF Layout] Prep Error Block {idx}: {e}")
                        continue

                # Sort by vertical position (Top to Bottom) to ensure logical rendering order
                processed_queue.sort(key=lambda x: x['sort_key'])

                # --- PHASE 2: TRANSLATION & RENDERING ---
                # Now that the canvas is clean, we can write text without fear of it being erased.
                
                print(f"[PDF Layout] Page {page_num+1}: Translating {len(processed_queue)} blocks...", flush=True)
                
                for i, item in enumerate(processed_queue):
                    try:
                        block_text = item['text']
                        raw_rect = item['raw_rect']
                        
                        print(f"[PDF Layout] Translating block {i+1}/{len(processed_queue)}...", flush=True)
                        
                        # Translation (Async Await)
                        translated_text = await self.translate_func(block_text, target_lang, page_context)
                        
                        if not translated_text or not translated_text.strip():
                            continue
                            
                        # Basic validation
                        if len(block_text) > 10 and len(translated_text.strip()) < 2 and not translated_text.strip().isdigit():
                             continue
                             
                        if translated_text.strip() == block_text:
                            continue
                            
                        # Render using exact bbox (no expansion to prevent overflow)
                        render_rect = raw_rect
                        
                        # Render
                        self._insert_text_adaptive(page, render_rect, translated_text, target_lang, item['format'], item['block'].type)
                        
                    except Exception as render_err:
                         print(f"[PDF Layout] Render Error Item {i}: {render_err}")
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

    def _get_precise_wipe_rect(self, page: fitz.Page, clip_rect: fitz.Rect, margin: int = 1) -> fitz.Rect:
        """
        Compute a precise wipe rectangle from actual text span positions.

        Strategy:
        - Search with a SLIGHTLY LARGER rect (3pt) so YOLO boundary chars are captured.
        - Use the NATURAL UNION of found spans as wipe rect (no added margin).
        - This is safe: we only find spans very close to the block edge; the natural
          union is bounded by actual ink, not an arbitrary pixel expansion.
        - Falls back to clip_rect if no text spans are found.
        """
        SEARCH_EXPAND = 3  # pts — how far outside clip_rect to look for boundary spans
        try:
            search_rect = fitz.Rect(
                clip_rect.x0 - SEARCH_EXPAND,
                clip_rect.y0 - SEARCH_EXPAND,
                clip_rect.x1 + SEARCH_EXPAND,
                clip_rect.y1 + SEARCH_EXPAND,
            )
            blocks = page.get_text("dict", clip=search_rect)["blocks"]
            span_rects = []
            for block in blocks:
                if block.get("type") != 0:  # only text blocks
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip():
                            span_rects.append(fitz.Rect(span["bbox"]))

            if span_rects:
                # Natural union of span bboxes: tightly covers every glyph,
                # no artificial margin that could touch neighbouring table lines.
                united = span_rects[0]
                for r in span_rects[1:]:
                    united = united | r
                return united

        except Exception as e:
            print(f"[PDF Layout] _get_precise_wipe_rect fallback: {e}", flush=True)

        # Fallback: YOLO bbox only (no expansion)
        return fitz.Rect(clip_rect)

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

    def _insert_text_adaptive(self, page: fitz.Page, rect: fitz.Rect, text: str, target_lang: str, format_info: dict = None, block_type: str = "text"):
        """
        Insert translated text using insert_htmlbox for adaptive scaling.
        Note: No wiping happens here to avoid overwriting neighbors.
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

        # Try insert_htmlbox for adaptive scaling
        try:
            font_family = "'Noto Sans CJK TC', 'Microsoft JhengHei', 'Droid Sans Fallback', sans-serif" if is_chinese else "'Roboto', 'Noto Sans', 'Helvetica', 'Arial', sans-serif"
            font_weight = "bold" if format_info.get("bold") else "normal"
            
            # Center small blocks (labels), Left for paragraphs
            text_align = "left"
            if rect.width < 150:
                text_align = "center"
                
            # HTML Escaping and Newline formatting
            safe_text = text.replace('<', '&lt;').replace('>', '&gt;')
            if block_type.lower() == 'list':
                html_text = safe_text.replace('\n', '<br/>')
            else:
                # Remove single newlines to allow natural HTML wrapping. Keep double newlines as paragraphs.
                html_text = safe_text.replace('\n\n', '<br/><br/>').replace('\n', ' ')
            
            html = f'<div style="font-family: {font_family}; color: {color_hex}; font-weight: {font_weight}; margin: 0; padding: 0;">{html_text}</div>'
            
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
