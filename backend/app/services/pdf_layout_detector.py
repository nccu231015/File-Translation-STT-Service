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
        """Initialize LayoutParser with Detectron2 backend (Faster R-CNN)"""
        try:
            import layoutparser as lp
            import torch
            
            # Using Detectron2 Faster R-CNN R50 FPN 3x model with PubLayNet
            # This is the gold standard for layout analysis
            print(f"[PDF Layout Detector] Initializing Detectron2 model...")
            
            self.model = lp.Detectron2LayoutModel(
                config_path='lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
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
        
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        # High DPI for clear detection
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        img_array = np.array(img)
        
        # Inference
        layout = self.model.detect(img_array)
        
        blocks = []
        for block in layout:
            # block.coordinates is [x1, y1, x2, y2]
            rect = block.coordinates
            
            # Convert to normalized coordinates if needed, or keep absolute
            # Here we return absolute coordinates matching the image size
            # We might need to scale them back if the page_width/height passed in
            # are different from the rendered image size.
            
            # Note: The input page_width/height are from the PDF metadata (usually 72 DPI points)
            # The image was rendered at 300 DPI. We must scale back.
            img_h, img_w = img_array.shape[:2]
            scale_x = page_width / img_w
            scale_y = page_height / img_h
            
            x1, y1, x2, y2 = rect
            
            blocks.append(LayoutBlock(
                type=block.type,
                bbox=(x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y),
                confidence=block.score,
                page_width=page_width,
                page_height=page_height
            ))
            
        doc.close()
        print(f"[PDF Layout Detector] Detectron2 found {len(blocks)} blocks on page {page_num+1}")
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
