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
        
        # Apply Non-Maximum Suppression (NMS) properly
        # Note: Some versions of LP return a list, so we wrap it just in case
        if not isinstance(layout, lp.Layout):
            layout = lp.Layout(layout)
        
        # Use global NMS function if method missing, or ensure it's filtered
        # Trying the most robust way:
        layout = lp.Layout([b for b in layout if b.score > 0.15]) # Pre-filter
        # Use simple recursion NMS from layoutparser
        # Note: If layout.nms() fails, we skip it or hand-roll it, but let's try strict wrapping
        try:
             # Standard LP NMS
             layout = layout.nms(iou_threshold=0.1)
        except AttributeError:
             # Fallback if method doesn't exist in installed version
             pass
        
        blocks = []
        for idx, block in enumerate(layout):
            # block.block_1, block_2 ... are coordinates [x1, y1, x2, y2]
            # block.type is the label string
            # block.score is confidence
            
            rect = block.coordinates
            
            # --- Heuristic Correction (Hybrid Mode) ---
            # AI sometimes mistakes Title for Text. Let's fix it using geometry/content.
            b_type = block.type
            
            # 1. Title Correction: Short text at top of page or large font (requires text content check, 
            #    but here we only have boxes. We can infer by aspect ratio/position).
            #    Simple rule: If near top and is "Text", usually Title.
            y_center = (rect[1] + rect[3]) / 2
            if b_type == "Text" and y_center < page_height * 0.15 and (rect[2] - rect[0]) < page_width * 0.8:
                 # It's at the very top and not full width -> Likely a Title/Header
                 b_type = "Title"
            
            blocks.append(LayoutBlock(
                type=b_type, # Used corrected type
                bbox=(rect[0], rect[1], rect[2], rect[3]),
                confidence=block.score,
                page_width=page_width,
                page_height=page_height
            ))
            
            # Debug: Print block type to diagnose classification issues
            print(f"[PDF Layout Detector] Block {idx}: type={block.type}, confidence={block.score:.2f}")
            
            blocks.append(LayoutBlock(
                type=block.type, # 'Text', 'Title', etc.
                bbox=(rect[0], rect[1], rect[2], rect[3]),
                confidence=block.score,
                page_width=page_width,
                page_height=page_height
            ))
        
        doc.close()
        print(f"[PDF Layout Detector] LayoutParser found {len(blocks)} blocks")
        return blocks
    
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
