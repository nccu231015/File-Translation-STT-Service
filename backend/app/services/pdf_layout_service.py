import asyncio
import fitz  # PyMuPDF
import os
import re
import tempfile
import uuid
from typing import Callable

from .pdf_layout_detector_yolo import LayoutBlock


class PDFLayoutPreservingService:
    """
    5-Step Pipeline (now with parallel page processing):
    1. Layout Detection (DocLayout-YOLO)
    2. Text Extraction (PyMuPDF vector-based)
    3. Translation (LLM — batched per page)
    4. Original Text Erase (redaction)
    5. Adaptive Rendering (insert_htmlbox)

    Pages are processed in parallel (controlled by PDF_PARALLEL_PAGES env var).
    Each page opens its own fitz.Document so there are no thread-safety issues.
    Final pages are merged in page-number order.
    """

    def __init__(self, translate_func: Callable[[str, str, str], str], layout_detector=None):
        self.translate_func = translate_func
        self.layout_detector = layout_detector

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    async def translate_pdf(
        self,
        input_path: str,
        output_path: str,
        target_lang: str = "zh-TW",
        debug_mode: bool = False,
    ):
        """
        Main pipeline: detect → extract → translate (async) → render.

        Pages up to PDF_PARALLEL_PAGES (default 2) are processed concurrently.
        Each page is saved to a temp PDF; results are merged in order.
        """
        # Peek at total page count without keeping the doc open
        with fitz.open(input_path) as probe:
            total_pages = len(probe)

        parallel = int(os.getenv("PDF_PARALLEL_PAGES", "2"))
        semaphore = asyncio.Semaphore(parallel)

        print(
            f"[PDF Layout] Starting translation: {total_pages} pages, "
            f"{parallel} concurrent (Target: {target_lang}, Debug: {debug_mode})",
            flush=True,
        )

        async def bounded(page_num: int):
            async with semaphore:
                return await self._process_single_page(
                    input_path, page_num, total_pages, target_lang, debug_mode
                )

        # Launch all pages; asyncio.gather preserves result order
        temp_paths = await asyncio.gather(*[bounded(i) for i in range(total_pages)])

        # Merge temp PDFs in page order → final output
        print("[PDF Layout] Merging translated pages...", flush=True)
        final_doc = fitz.open()
        for page_num, temp_path in enumerate(temp_paths):
            if temp_path and os.path.exists(temp_path):
                try:
                    page_doc = fitz.open(temp_path)
                    final_doc.insert_pdf(page_doc)
                    page_doc.close()
                    os.remove(temp_path)
                except Exception as merge_err:
                    print(
                        f"[PDF Layout] Merge error page {page_num + 1}: {merge_err}",
                        flush=True,
                    )
            else:
                # Fallback: copy the original page untouched
                print(
                    f"[PDF Layout] Page {page_num + 1} missing temp file — inserting original.",
                    flush=True,
                )
                with fitz.open(input_path) as orig:
                    final_doc.insert_pdf(orig, from_page=page_num, to_page=page_num)

        final_doc.save(output_path, garbage=4, deflate=True)
        final_doc.close()
        print(f"[PDF Layout] ✓ Saved to {output_path}", flush=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Per-page worker (fully self-contained, opens its own fitz.Document)
    # ──────────────────────────────────────────────────────────────────────────

    async def _process_single_page(
        self,
        input_path: str,
        page_num: int,
        total_pages: int,
        target_lang: str,
        debug_mode: bool,
    ) -> str | None:
        """
        Process one page of the PDF:
        - detect protected areas (YOLO)
        - extract text blocks (PyMuPDF)
        - wipe originals (redaction)
        - translate & render

        Opens its own fitz.Document so parallel calls are fully independent.
        Returns path to a temp PDF containing only this (translated) page,
        or None on unrecoverable error.
        """
        print(
            f"\n[PDF Layout] ===== Page {page_num + 1}/{total_pages} — START =====",
            flush=True,
        )

        doc = fitz.open(input_path)
        page = doc[page_num]

        try:
            # ── STEP 1: YOLO — detect protected areas ──────────────────────
            print(f"[PDF Layout] Page {page_num+1}: YOLO detecting protected areas...", flush=True)
            layout_blocks = self.layout_detector.detect_layout(
                input_path, page_num, page.rect.width, page.rect.height
            )

            PROTECTED_TYPES = {"figure", "table", "equation", "formula"}
            protected_rects_pdf = []
            for b in layout_blocks:
                if b.type.lower() in PROTECTED_TYPES:
                    pdf_rect = self.layout_detector.pixel_to_pdf_rect(
                        b.bbox, page, b.page_width, b.page_height
                    )
                    protected_rects_pdf.append(
                        fitz.Rect(
                            pdf_rect.x0 - 5, pdf_rect.y0 - 5,
                            pdf_rect.x1 + 5, pdf_rect.y1 + 5,
                        )
                    )
            print(
                f"[PDF Layout] Page {page_num+1}: Protected areas: {len(protected_rects_pdf)}",
                flush=True,
            )

            # ── STEP 2: PyMuPDF — exhaustive text block discovery ──────────
            print(f"[PDF Layout] Page {page_num+1}: PyMuPDF full text scan...", flush=True)
            pdf_page_w = page.rect.width
            pdf_page_h = page.rect.height

            text_blocks = []
            for pb in page.get_text("dict").get("blocks", []):
                if pb.get("type") != 0:
                    continue
                block_rect = fitz.Rect(pb["bbox"])
                if block_rect.is_empty or block_rect.width < 5 or block_rect.height < 5:
                    continue

                block_area = block_rect.get_area()
                is_protected = any(
                    block_area > 0
                    and block_rect.intersects(p)
                    and block_rect.intersect(p).get_area() / block_area > 0.30
                    for p in protected_rects_pdf
                )
                if is_protected:
                    continue

                block_text = "".join(
                    span.get("text", "")
                    for line in pb.get("lines", [])
                    for span in line.get("spans", [])
                ).strip()
                if not block_text or len(block_text) < 2:
                    continue

                text_blocks.append(
                    LayoutBlock(
                        bbox=(block_rect.x0, block_rect.y0, block_rect.x1, block_rect.y1),
                        type="Text",
                        confidence=1.0,
                        page_width=int(pdf_page_w),
                        page_height=int(pdf_page_h),
                    )
                )

            print(
                f"[PDF Layout] Page {page_num+1}: Text candidates: {len(text_blocks)}",
                flush=True,
            )

            # ── NMS: Two-Pass Dedup ─────────────────────────────────────────
            text_blocks.sort(key=lambda b: fitz.Rect(b.bbox).get_area(), reverse=True)

            # Pass 1 — remove container shells
            container_indices = set()
            for i in range(len(text_blocks)):
                if i in container_indices:
                    continue
                rect_i = fitz.Rect(text_blocks[i].bbox)
                area_i = rect_i.get_area()
                if area_i == 0:
                    continue
                child_area_sum = child_count = 0
                for j in range(i + 1, len(text_blocks)):
                    if j in container_indices:
                        continue
                    rect_j = fitz.Rect(text_blocks[j].bbox)
                    area_j = rect_j.get_area()
                    if area_j == 0 or area_j >= area_i:
                        continue
                    if rect_i.intersects(rect_j):
                        inter = rect_i.intersect(rect_j).get_area()
                        if area_j > 0 and inter / area_j > 0.70:
                            child_area_sum += area_j
                            child_count += 1
                if child_count >= 2 and child_area_sum / area_i > 0.60:
                    container_indices.add(i)

            text_blocks = [b for idx, b in enumerate(text_blocks) if idx not in container_indices]

            # Pass 2 — standard overlap dedup
            unique_blocks = []
            for i, current_block in enumerate(text_blocks):
                curr_rect = fitz.Rect(current_block.bbox)
                curr_area = curr_rect.get_area()
                is_dup = False
                for kept_block in unique_blocks:
                    kept_rect = fitz.Rect(kept_block.bbox)
                    if curr_rect.intersects(kept_rect):
                        inter_area = curr_rect.intersect(kept_rect).get_area()
                        if curr_area > 0 and (inter_area / curr_area) > 0.60:
                            is_dup = True
                            break
                if not is_dup:
                    unique_blocks.append(current_block)

            unique_blocks.sort(key=lambda b: b.bbox[1])
            text_blocks = unique_blocks
            print(
                f"[PDF Layout] Page {page_num+1}: NMS → {len(text_blocks)} blocks remain",
                flush=True,
            )

            # ── DEBUG MODE ─────────────────────────────────────────────────
            if debug_mode:
                color_map = {
                    "Text": (1, 0, 0), "Title": (0, 0, 1), "List": (0, 0.5, 0),
                    "Table": (1, 0.5, 0), "Figure": (0.5, 0, 0.5),
                }
                default_color = (0.5, 0.5, 0.5)
                blocks_to_draw = list(layout_blocks)
                for tb in text_blocks:
                    if tb not in blocks_to_draw:
                        blocks_to_draw.append(tb)
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
                        conf_label = "RESCUED" if block.confidence == 1.0 else f"{block.confidence:.2f}"
                        page.insert_text(
                            (pdf_rect.x0, pdf_rect.y0 - 5 if pdf_rect.y0 > 10 else pdf_rect.y0 + 10),
                            f"{block.type} ({conf_label})", fontsize=8, color=color,
                        )
                    except Exception:
                        continue
                # Fall through to save
            else:
                # ── PHASE 1: Prepare & Wipe ─────────────────────────────────
                page_context = page.get_text()
                processed_queue = []

                for idx, block in enumerate(text_blocks):
                    try:
                        raw_rect = self.layout_detector.pixel_to_pdf_rect(
                            block.bbox, page, block.page_width, block.page_height
                        )
                        raw_rect.intersect(page.rect)

                        block_text = page.get_text("text", clip=raw_rect).strip()
                        if not block_text:
                            continue

                        is_numeric = re.match(r'^[\d\s\.,\-\/%$€]+$', block_text)
                        if is_numeric and block.type.lower() != "title":
                            continue

                        format_info = self._extract_format_info(page, raw_rect, block_type=block.type)
                        processed_queue.append({
                            "block": block,
                            "raw_rect": raw_rect,
                            "text": block_text,
                            "format": format_info,
                            "sort_key": raw_rect.y0,
                        })

                        wipe_rect = self._get_precise_wipe_rect(page, raw_rect, margin=1)
                        page.add_redact_annot(wipe_rect, fill=(1, 1, 1))

                    except Exception as e:
                        print(f"[PDF Layout] Page {page_num+1} Prep Block {idx}: {e}")

                processed_queue.sort(key=lambda x: x["sort_key"])

                try:
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=False)
                    print(
                        f"[PDF Layout] Page {page_num+1}: Redactions applied ({len(processed_queue)} blocks)",
                        flush=True,
                    )
                except Exception as redact_err:
                    print(f"[PDF Layout] Page {page_num+1}: Redaction fallback — {redact_err}", flush=True)
                    for item in processed_queue:
                        try:
                            wipe_rect = self._get_precise_wipe_rect(page, item["raw_rect"], margin=1)
                            page.draw_rect(wipe_rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=1)
                        except Exception:
                            pass

                # ── PHASE 2: Translate & Render ─────────────────────────────
                print(
                    f"[PDF Layout] Page {page_num+1}: Translating {len(processed_queue)} blocks...",
                    flush=True,
                )
                for i, item in enumerate(processed_queue):
                    try:
                        translated_text = await self.translate_func(
                            item["text"], target_lang, page_context
                        )
                        if not translated_text or not translated_text.strip():
                            continue
                            
                        # Intercept the <SKIP> token from LLM for completely meaningless fragments
                        if "<SKIP>" in translated_text:
                            translated_text = translated_text.replace("<SKIP>", "").strip()
                            if not translated_text:
                                print(f"[PDF Layout] Skipping meaningless fragment: '{item['text']}'", flush=True)
                                continue
                        if (
                            len(item["text"]) > 10
                            and len(translated_text.strip()) < 2
                            and not translated_text.strip().isdigit()
                        ):
                            continue
                        if translated_text.strip() == item["text"]:
                            continue

                        self._insert_text_adaptive(
                            page,
                            item["raw_rect"],
                            translated_text,
                            target_lang,
                            item["format"],
                            item["block"].type,
                        )
                    except Exception as render_err:
                        print(f"[PDF Layout] Page {page_num+1} Render Item {i}: {render_err}")

        except Exception as page_error:
            print(
                f"[PDF Layout] ERROR on page {page_num + 1}: {page_error} — saving original page.",
                flush=True,
            )

        # Save this page to a uniquely named temp PDF and return its path
        temp_path = os.path.join(
            tempfile.gettempdir(),
            f"pdf_page_{page_num:04d}_{uuid.uuid4().hex[:8]}.pdf",
        )
        try:
            one_page = fitz.open()
            one_page.insert_pdf(doc, from_page=page_num, to_page=page_num)
            one_page.save(temp_path)
            one_page.close()
        except Exception as save_err:
            print(f"[PDF Layout] Page {page_num+1}: Failed to save temp file — {save_err}", flush=True)
            temp_path = None
        finally:
            doc.close()

        print(f"[PDF Layout] ===== Page {page_num + 1}/{total_pages} — DONE =====", flush=True)
        return temp_path

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers (unchanged from original)
    # ──────────────────────────────────────────────────────────────────────────

    def _get_precise_wipe_rect(self, page: fitz.Page, clip_rect: fitz.Rect, margin: int = 1) -> fitz.Rect:
        SEARCH_EXPAND = 3
        try:
            search_rect = fitz.Rect(
                clip_rect.x0 - SEARCH_EXPAND, clip_rect.y0 - SEARCH_EXPAND,
                clip_rect.x1 + SEARCH_EXPAND, clip_rect.y1 + SEARCH_EXPAND,
            )
            blocks = page.get_text("dict", clip=search_rect)["blocks"]
            span_rects = []
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip():
                            span_rects.append(fitz.Rect(span["bbox"]))
            if span_rects:
                united = span_rects[0]
                for r in span_rects[1:]:
                    united = united | r
                return united
        except Exception as e:
            print(f"[PDF Layout] _get_precise_wipe_rect fallback: {e}", flush=True)
        return fitz.Rect(clip_rect)

    def _extract_format_info(self, page: fitz.Page, rect: fitz.Rect, block_type: str = "text") -> dict:
        search_rect = fitz.Rect(rect.x0 + 1, rect.y0 + 1, rect.x1 - 1, rect.y1 - 1)
        if search_rect.is_empty or search_rect.width < 1:
            search_rect = rect

        blocks = page.get_text("dict", clip=search_rect)["blocks"]
        format_info = {"font": "helv", "fontsize": 11, "color": (0, 0, 0), "bold": False}
        weighted_sizes = {}
        weighted_colors = {}
        total_chars = bold_chars = 0

        for block in blocks:
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text_len = len(span.get("text", ""))
                        total_chars += text_len
                        if "bold" in span.get("font", "").lower():
                            bold_chars += text_len
                        sz = span.get("size", 11)
                        if sz < 4:
                            continue
                        weight = sz * sz
                        weighted_sizes[sz] = weighted_sizes.get(sz, 0) + weight
                        c = span.get("color", 0)
                        color_tuple = (
                            ((c >> 16) & 0xFF) / 255.0,
                            ((c >> 8) & 0xFF) / 255.0,
                            (c & 0xFF) / 255.0,
                        )
                        weighted_colors[color_tuple] = weighted_colors.get(color_tuple, 0) + weight

        if block_type.lower() == "title" and total_chars > 50:
            block_type = "text"
        if total_chars > 0 and (bold_chars / total_chars) > 0.5:
            format_info["bold"] = True
        if weighted_sizes:
            if block_type.lower() == "title":
                format_info["fontsize"] = max(weighted_sizes.keys())
            else:
                format_info["fontsize"] = max(weighted_sizes, key=weighted_sizes.get)
        if weighted_colors:
            format_info["color"] = max(weighted_colors, key=weighted_colors.get)

        return format_info

    def _insert_text_adaptive(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        text: str,
        target_lang: str,
        format_info: dict = None,
        block_type: str = "text",
    ):
        if format_info is None:
            format_info = {"font": "helv", "fontsize": 12, "color": (0, 0, 0)}

        is_chinese = any("\u4e00" <= c <= "\u9fff" for c in text)
        r, g, b = format_info["color"]
        color_hex = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        css_font_size = "85%" if (target_lang and target_lang.lower().startswith("en")) else "100%"

        try:
            font_family = (
                "'Noto Sans CJK TC', 'Microsoft JhengHei', 'Droid Sans Fallback', sans-serif"
                if is_chinese
                else "'Roboto', 'Noto Sans', 'Helvetica', 'Arial', sans-serif"
            )
            font_weight = "bold" if format_info.get("bold") else "normal"
            text_align = "center" if rect.width < 150 else "left"

            safe_text = text.replace("<", "&lt;").replace(">", "&gt;")
            if block_type.lower() == "list":
                html_text = safe_text.replace("\n", "<br/>")
            else:
                html_text = safe_text.replace("\n\n", "<br/><br/>").replace("\n", " ")

            html = (
                f'<div style="font-family: {font_family}; color: {color_hex}; '
                f'font-weight: {font_weight}; margin: 0; padding: 0;">{html_text}</div>'
            )
            css_style = (
                f"div {{ line-height: 1.25; font-size: {css_font_size}; "
                f"text-align: {text_align}; overflow-wrap: break-word; word-break: break-word; }}"
            )

            page.insert_htmlbox(rect, html, css=css_style, scale_low=0.1)
            return
        except Exception:
            pass

        # Fallback: insert_textbox with font size reduction
        font_name = "china-t" if is_chinese else "helv"
        original_size = format_info.get("fontsize", 12)
        for fontsize in range(int(original_size * 1.2), 3, -1):
            rc = page.insert_textbox(
                rect, text, fontsize=fontsize, fontname=font_name,
                color=format_info["color"], align=fitz.TEXT_ALIGN_LEFT,
            )
            if rc >= 0:
                return

        page.insert_textbox(
            rect, text, fontsize=4, fontname=font_name,
            color=format_info["color"], align=fitz.TEXT_ALIGN_LEFT,
        )
