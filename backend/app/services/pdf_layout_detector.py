import fitz  # PyMuPDF
import numpy as np
import layoutparser as lp
from PIL import Image
from typing import List, Tuple
from dataclasses import dataclass
import io
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
        """Initialize LayoutParser with EfficientDet backend (local model)"""
        try:
            from layoutparser.models import EfficientDetLayoutModel
            import os
            import glob
            
            # Find the downloaded PubLayNet model (could be .pth or .pth.tar after extraction)
            model_dir = "/root/.cache/layoutparser/models/"
            possible_paths = [
                model_dir + "publaynet-tf_efficientdet_d0.pth.tar",
                model_dir + "publaynet-tf_efficientdet_d0.pth",
            ]
            # Also check for extracted files
            possible_paths.extend(glob.glob(model_dir + "*.pth"))
            
            model_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    model_path = path
                    break
            
            if not model_path:
                raise FileNotFoundError(f"PubLayNet model not found in {model_dir}. Available files: {os.listdir(model_dir) if os.path.exists(model_dir) else 'directory does not exist'}")
            
            print(f"[PDF Layout Detector] Found model: {model_path}")
            
            print(f"[PDF Layout Detector] Initializing EfficientDet with PubLayNet model...")
            
            # Direct initialization with PubLayNet-specific model
            # NOTE: EfficientDet label_map in LayoutParser starts from 1, not 0
            self.model = EfficientDetLayoutModel(
                config_path='tf_efficientdet_d0',  # Built-in model architecture name
                model_path=model_path,              # PubLayNet-specific weights (5 classes)
                label_map={1: "Text", 2: "Title", 3: "List", 4: "Table", 5: "Figure"},
                extra_config={"CONFIDENCE_THRESHOLD": 0.15}
            )
            
            # Check if running on GPU
            import torch
            device = "GPU" if torch.cuda.is_available() else "CPU"
            print(f"[PDF Layout Detector] LayoutParser (EfficientDet/PubLayNet) initialized on {device}")
            
        except Exception as e:
            import traceback
            print(f"[PDF Layout Detector] Full error:")
            traceback.print_exc()
            print(f"[PDF Layout Detector] WARNING: LayoutParser initialization failed ({e}). Switching to PyMuPDF heuristic mode.")
            self.model = None
    
    
    def detect_layout(self, pdf_path: str, page_num: int) -> List[LayoutBlock]:
        """
        Detect layout blocks on a specific PDF page.
        """
        if not self.model:
            return self._detect_layout_pymupdf(pdf_path, page_num)
            
        try:
            return self._detect_layout_lp(pdf_path, page_num)
        except Exception as e:
            print(f"[PDF Layout] LayoutParser failed: {e}. Using fallback.")
            return self._detect_layout_pymupdf(pdf_path, page_num)
    
    def _detect_layout_lp(self, pdf_path: str, page_num: int) -> List[LayoutBlock]:
        """LayoutParser inference logic"""
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        # High DPI for better detection (LayoutParser expects good resolution)
        # 300 DPI is standard for document analysis; 200 might be too blurry
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        img_array = np.array(img)
        
        page_width, page_height = img.size
        
        # Inference
        # LayoutParser returns a Layout object (list of TextBlock)
        layout = self.model.detect(img_array)
        
        # 1. AI Predictions (Semantic Layer)
        if not isinstance(layout, lp.Layout):
            layout = lp.Layout(layout)
            
        # NMS with standard threshold (0.5) to avoid removing adjacent blocks
        layout = layout.nms(iou_threshold=0.5)
        
        raw_ai_blocks = []
        for block in layout:
            if block.score < 0.15:
                continue
            r = block.coordinates
            raw_ai_blocks.append({
                "type": block.type,
                "bbox": [r[0], r[1], r[2], r[3]], # x1,y1,x2,y2
                "area": (r[2]-r[0]) * (r[3]-r[1]),
                "score": block.score
            })
            
        # --- Containment Suppression (Fix Red/Green Overlap) ---
        # If a small block is inside a large block (e.g., Text inside List), drop the small one.
        indices_to_drop = set()
        for i, b1 in enumerate(raw_ai_blocks):
            for j, b2 in enumerate(raw_ai_blocks):
                if i == j: continue
                # Check if b1 is inside b2
                if (b1["bbox"][0] >= b2["bbox"][0] and b1["bbox"][1] >= b2["bbox"][1] and 
                    b1["bbox"][2] <= b2["bbox"][2] and b1["bbox"][3] <= b2["bbox"][3]):
                    # b1 is inside b2. Keep the larger semantic block (List/Table) usually.
                    # Unless b2 is just "Text" and b1 is "Title"? No, usually bigger is container.
                    indices_to_drop.add(i)
        
        ai_blocks = [b for i, b in enumerate(raw_ai_blocks) if i not in indices_to_drop]

        # 2. PyMuPDF Extraction (Recall Layer)
        # Get raw text blocks from PDF engine (guaranteed text presence)
        pdf_blocks = []
        raw_pdf_blocks = page.get_text("dict")["blocks"]
        
        # Scale PyMuPDF coordinates to Image coordinates
        pdf_w, pdf_h = page.rect.width, page.rect.height
        scale_x = page_width / pdf_w
        scale_y = page_height / pdf_h
        
        for b in raw_pdf_blocks:
            if b["type"] == 0: # Text block
                r = b["bbox"]
                # Scale to image px
                img_bbox = [r[0] * scale_x, r[1] * scale_y, r[2] * scale_x, r[3] * scale_y]
                pdf_blocks.append({
                    "bbox": img_bbox,
                    "text_len": len(b.get("lines", [])),
                    "original_bbox": r
                })

        # 3. Merge Strategy (The "Hybrid" Fix)
        final_blocks = []
        
        # For each PDF text block, check if it falls inside an AI block
        for p_block in pdf_blocks:
            px1, py1, px2, py2 = p_block["bbox"]
            p_center = ((px1+px2)/2, (py1+py2)/2)
            
            matched_type = "Text" # Default to Text (Recall Guarantee)
            max_score = 0.0
            matched_ai = False
            
            for ai_b in ai_blocks:
                ax1, ay1, ax2, ay2 = ai_b["bbox"]
                
                # Check center containment
                if (ax1 < p_center[0] < ax2) and (ay1 < p_center[1] < ay2):
                    matched_ai = True
                    # If AI says it's Title/Table/List/Figure -> Trust it
                    if ai_b["score"] > max_score:
                        matched_type = ai_b["type"]
                        max_score = ai_b["score"]
            
            # Heuristic: Fix AI mistaking Title for Text
            if matched_type == "Text":
                 # If near top and short -> Title
                 if p_center[1] < page_height * 0.15 and (px2 - px1) < page_width * 0.85:
                     matched_type = "Title"

            final_blocks.append(LayoutBlock(
                type=matched_type,
                bbox=(px1, py1, px2, py2), # Use precise PyMuPDF coordinates
                confidence=max_score if matched_ai else 1.0,
                page_width=page_width,
                page_height=page_height
            ))
            
        # 4. Add AI blocks that are NOT text (Figures/Images) 
        # because PyMuPDF get_text("dict") text blocks don't cover images well
        for ai_b in ai_blocks:
            if ai_b["type"] in ["Figure", "Table", "Image"]:
                # Add them (potential overlap with text inside table is acceptable for layout visualization)
                final_blocks.append(LayoutBlock(
                    type=ai_b["type"],
                    bbox=tuple(ai_b["bbox"]),
                    confidence=ai_b["score"],
                    page_width=page_width,
                    page_height=page_height
                ))

        doc.close()
        print(f"[PDF Layout Detector] Hybrid Merge: {len(ai_blocks)} AI blocks + {len(pdf_blocks)} PDF blocks -> {len(final_blocks)} final blocks")
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
