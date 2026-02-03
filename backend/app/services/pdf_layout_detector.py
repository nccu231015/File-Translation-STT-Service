import fitz  # PyMuPDF
import numpy as np
import layoutparser as lp
from PIL import Image
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
import io
import re
import cv2

@dataclass
class LayoutBlock:
    """Represents a detected layout block"""
    type: str  # 'Text', 'Title', 'List', 'Table', 'Figure'
    bbox: Tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax)
    confidence: float
    page_width: int
    page_height: int

class PDFLayoutDetector:
    """
    Service for detecting PDF layout using LayoutParser (PaddleDetection backend).
    Documentation: https://github.com/Layout-Parser/layout-parser
    """
    
    def __init__(self):
        """Initialize LayoutParser with Detectron2 backend (Faster R-CNN)"""
        import threading
        self.lock = threading.Lock() # Prevent GPU inference collision
        try:
            import layoutparser as lp
            import torch
            
            # Using Detectron2 Faster R-CNN R50 FPN 3x model with PubLayNet
            # This is the gold standard for layout analysis
            # We use local weights because automatic download often fails
            print(f"[PDF Layout Detector] Initializing Detectron2 model...")
            
            import os
            model_path = "/root/.cache/layoutparser/models/faster_rcnn_R_50_FPN_3x.pth"
            if not os.path.exists(model_path):
                 print(f"[PDF Layout Detector] WARNING: Local model weights not found at {model_path}, LayoutParser will try to download...")
                 # No model_path arg means it will try to download from config
                 self.model = lp.Detectron2LayoutModel(
                    config_path='lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
                    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5],
                    label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}
                )
            else:
                print(f"[PDF Layout Detector] Loading local weights: {model_path}")
                self.model = lp.Detectron2LayoutModel(
                    config_path='lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
                    model_path=model_path, # Explicitly use local weights
                    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5],
                    label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"}
                )
            
            device = "GPU" if torch.cuda.is_available() else "CPU"
            print(f"[PDF Layout Detector] LayoutParser (Detectron2) initialized on {device}")
            
        except Exception as e:
            import traceback
            print(f"[PDF Layout Detector] Full error:")
            traceback.print_exc()
            print(f"[PDF Layout Detector] WARNING: LayoutParser initialization failed ({e}). Switching to PyMuPDF heuristic mode.")
            self.model = None
            
    def detect_layout(self, pdf_path: str, page_num: int, page_width: int, page_height: int) -> List[LayoutBlock]:
        """
        Detect layout using Detectron2 model.
        Returns a list of LayoutBlock objects.
        """
        if not self.model:
            return self._detect_layout_pymupdf(pdf_path, page_num)
            
        import fitz
        import numpy as np
        from PIL import Image
        import io
        
        print(f"[PDF Layout Detector] Page {page_num+1}: Rendering image (300 DPI)...", flush=True)
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        # High DPI for clear detection
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        img_array = np.array(img)
        print(f"[PDF Layout Detector] Page {page_num+1}: Image rendered ({img.size[0]}x{img.size[1]})", flush=True)
        
        # Inference (Protected by lock)
        print(f"[PDF Layout Detector] Page {page_num+1}: Running Detectron2 inference...", flush=True)
        # LayoutParser returns a Layout object (list of TextBlock)
        with self.lock:
            layout = self.model.detect(img_array)
        print(f"[PDF Layout Detector] Page {page_num+1}: AI found {len(layout)} raw blocks", flush=True)
        
        # 1. AI Predictions (Semantic Layer)
        if not isinstance(layout, lp.Layout):
            layout = lp.Layout(layout)
        
        ai_blocks = []
        for block in layout:
            r = block.coordinates
            ai_blocks.append({
                "type": block.type,
                "bbox": [r[0], r[1], r[2], r[3]], # x1,y1,x2,y2
                "area": (r[2]-r[0]) * (r[3]-r[1]),
                "score": block.score
            })
            
        # 2. PyMuPDF Extraction (Recall Layer & Text Content)
        # Get raw text blocks from PDF engine (guaranteed text presence)
        print(f"[PDF Layout Detector] Page {page_num+1}: Extracting text blocks via PyMuPDF...", flush=True)
        pdf_blocks = []
        raw_pdf_blocks = page.get_text("dict")["blocks"]
        
        # Scale PyMuPDF coordinates to Image coordinates
        pdf_w, pdf_h = page.rect.width, page.rect.height
        scale_x = page_width / pdf_w
        scale_y = page_height / pdf_h
        
        for b in raw_pdf_blocks:
            if b["type"] == 0: # Text block
                r = b["bbox"]
                # Get the first line text to check for bullet points
                first_line_text = ""
                if "lines" in b and len(b["lines"]) > 0:
                    spans = b["lines"][0].get("spans", [])
                    if spans:
                        first_line_text = spans[0].get("text", "").strip()

                img_bbox = [r[0] * scale_x, r[1] * scale_y, r[2] * scale_x, r[3] * scale_y]
                pdf_blocks.append({
                    "bbox": img_bbox,
                    "area": (img_bbox[2]-img_bbox[0]) * (img_bbox[3]-img_bbox[1]),
                    "text_lines": b.get("lines", []),
                    "first_text": first_line_text,
                    "original_bbox": r
                })

        # 3. Smart Merge Strategy
        print(f"[PDF Layout Detector] Page {page_num+1}: Merging AI + PDF blocks...", flush=True)
        final_blocks = []
        
        for p_block in pdf_blocks:
            px1, py1, px2, py2 = p_block["bbox"]
            p_area = p_block["area"]
            
            matched_type = "Text"
            max_ai_score = 0.0
            
            # Find overlapping AI block
            for ai_b in ai_blocks:
                ax1, ay1, ax2, ay2 = ai_b["bbox"]
                
                # Intersection
                ix1 = max(px1, ax1)
                iy1 = max(py1, ay1)
                ix2 = min(px2, ax2)
                iy2 = min(py2, ay2)
                
                if ix2 > ix1 and iy2 > iy1:
                    intersection = (ix2 - ix1) * (iy2 - iy1)
                    coverage = intersection / p_area if p_area > 0 else 0
                    
                    if coverage > 0.5:
                        # Prefer semantic tags
                        if ai_b["type"] != "Text":
                            matched_type = ai_b["type"]
                            max_ai_score = ai_b["score"]
                            break
                        elif matched_type == "Text":
                            max_ai_score = ai_b["score"]

            # --- Heuristic Correction (Rule-based) ---
            # 1. List Detection: Check for bullet points if AI failed or said "Text"
            # Common list markers: •, -, *, 1., (1), a.
            txt = p_block["first_text"]
            if matched_type == "Text":
                if re.match(r'^(\•|\-|\*|\d+\.|^\([0-9a-z]+\))', txt):
                    matched_type = "List"
                    # print(f"DEBUG: Auto-corrected Text to List based on content: '{txt}'")
            
            # 2. Title Detection: Geometry check
            p_center_y = (py1 + py2) / 2
            p_width = px2 - px1
            if matched_type == "Text":
                 if p_center_y < page_height * 0.15 and p_width < page_width * 0.85:
                     matched_type = "Title"

            final_blocks.append(LayoutBlock(
                type=matched_type,
                bbox=(px1, py1, px2, py2), 
                confidence=max_ai_score if max_ai_score > 0 else 1.0,
                page_width=page_width,
                page_height=page_height
            ))
            
        # 4. Add non-text AI blocks (Figures/Images/Tables)
        for ai_b in ai_blocks:
            if ai_b["type"] in ["Figure", "Table", "Image"]:
                 # Simple check to avoid duplicates (if a text block is fully inside)
                 # But usually we want Figures even if they contain text
                 final_blocks.append(LayoutBlock(
                    type=ai_b["type"],
                    bbox=tuple(ai_b["bbox"]),
                    confidence=ai_b["score"],
                    page_width=page_width,
                    page_height=page_height
                ))

        doc.close()
        print(f"[PDF Layout Detector] Page {page_num+1} Success: {len(final_blocks)} final blocks", flush=True)
        return final_blocks
    
    def _detect_layout_pymupdf(self, pdf_path: str, page_num: int) -> List[LayoutBlock]:
        """Heuristic fallback using PyMuPDF"""
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        w, h = int(page.rect.width), int(page.rect.height)
        
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b["type"] == 0:
                r = b["bbox"]
                blocks.append(LayoutBlock("Text", (r[0], r[1], r[2], r[3]), 1.0, w, h))
        doc.close()
        return blocks
        
    def pixel_to_pdf_rect(self, pixel_bbox: Tuple[float, float, float, float], 
                          page: fitz.Page, 
                          page_width_px: int, 
                          page_height_px: int) -> fitz.Rect:
        pdf_w, pdf_h = page.rect.width, page.rect.height
        if page_width_px == 0 or page_height_px == 0:
            return fitz.Rect(pixel_bbox)
        sx, sy = pdf_w / page_width_px, pdf_h / page_height_px
        x0, y0, x1, y1 = pixel_bbox
        return fitz.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy)
