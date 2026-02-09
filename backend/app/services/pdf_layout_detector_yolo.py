"""
DocLayout-YOLO Layout Detector - Official PDF-Extract-Kit Integration
Official Repository: https://github.com/opendatalab/PDF-Extract-Kit
Official Model: https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0
"""
import numpy as np
from dataclasses import dataclass
from typing import List
import os
import fitz
import warnings

# Silence FutureWarnings from torch/YOLO
warnings.filterwarnings("ignore", category=FutureWarning)

@dataclass
class LayoutBlock:
    """Layout block matching existing PDFLayoutDetector interface"""
    bbox: tuple  # (x1, y1, x2, y2) in pixels
    type: str    # Mapped type: 'Title', 'Text', 'Figure', 'Table', 'Formula'
    confidence: float
    page_width: int
    page_height: int


class PDFLayoutDetectorYOLO:
    """
    DocLayout-YOLO wrapper for PDF layout detection.
    
    This implementation follows the official PDF-Extract-Kit approach while
    maintaining compatibility with the existing pdf_layout_service.py interface.
    
    Official Source:
    - Model: https://github.com/opendatalab/PDF-Extract-Kit/blob/main/pdf_extract_kit/tasks/layout_detection/models/yolo.py
    - Config: https://github.com/opendatalab/PDF-Extract-Kit/blob/main/configs/layout_detection.yaml
    """
    
    def __init__(self):
        """
        Initialize DocLayout-YOLO model following official PDF-Extract-Kit method.
        
        Official documentation:
        https://pdf-extract-kit.readthedocs.io/en/latest/algorithm/layout_detection.html
        """
        print("[DocLayout-YOLO] Initializing model...", flush=True)
        
        # Official class mapping from PDF-Extract-Kit
        # Source: pdf_extract_kit/tasks/layout_detection/models/yolo.py#L18-27
        self.id_to_names = {
            0: 'title', 
            1: 'plain text',
            2: 'abandon',  # Decorative elements, watermarks
            3: 'figure', 
            4: 'figure_caption', 
            5: 'table', 
            6: 'table_caption', 
            7: 'table_footnote', 
            8: 'isolate_formula',  # Mathematical formulas
            9: 'formula_caption'
        }
        
        # Map PDF-Extract-Kit categories to existing system types
        self.type_mapping = {
            'title': 'Title',
            'plain text': 'Text',
            'figure': 'Figure',
            'figure_caption': 'Text',  # Translate captions as text
            'table': 'Table',
            'table_caption': 'Text',
            'table_footnote': 'Text',
            'isolate_formula': 'Formula',  # NEW: Formulas should NOT be translated
            'formula_caption': 'Text',
            'abandon': 'Abandon'  # NEW: Skip these regions
        }
        
        # Load model following official pattern
        try:
            from doclayout_yolo import YOLOv10
            
            # Model path (configurable via env var)
            model_path = os.getenv(
                "DOCLAYOUT_MODEL_PATH", 
                "/app/models/layout/doclayout_yolo_ft.pt"
            )
            
            if not os.path.exists(model_path):
                raise FileNotFoundError(
                    f"DocLayout-YOLO model not found at {model_path}. "
                    f"Please ensure the model was downloaded during Docker build."
                )
            
            # Official initialization
            self.model = YOLOv10(model_path)
            
            # Official default configuration
            self.img_size = int(os.getenv("DOCLAYOUT_IMG_SIZE", "1280"))
            self.conf_thres = float(os.getenv("DOCLAYOUT_CONF_THRES", "0.15"))
            self.iou_thres = float(os.getenv("DOCLAYOUT_IOU_THRES", "0.30"))
            
            print(f"[DocLayout-YOLO] ✓ Model loaded: {model_path}", flush=True)
            print(f"[DocLayout-YOLO] ✓ Config: img_size={self.img_size}, conf={self.conf_thres}, iou={self.iou_thres}", flush=True)
            
        except ImportError as e:
            print(f"[DocLayout-YOLO] ERROR: doclayout-yolo package not installed", flush=True)
            print(f"[DocLayout-YOLO] Run: pip install doclayout-yolo==0.0.2", flush=True)
            raise
        except Exception as e:
            print(f"[DocLayout-YOLO] ERROR: {e}", flush=True)
            raise
    
    def detect_layout(self, pdf_path: str, page_num: int, page_width: float, page_height: float) -> List[LayoutBlock]:
        """
        High-level wrapper to detect layout for a specific PDF page.
        Maintains compatibility with pdf_layout_service.py calling convention.
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number (0-indexed)
            page_width: Original PDF page width
            page_height: Original PDF page height
            
        Returns:
            List of LayoutBlock objects
        """
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        # Render page to image at high resolution for detection
        # Using 3.0 zoom (approx 216 DPI) as typical for layout detection
        zoom = 3.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Convert to numpy array (H, W, 3)
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        
        # DocLayout-YOLO expects RGB
        if pix.n == 4:  # CMYK or RGBA
           pass # fitz handles conversion usually, but just in case
        
        # Run detection
        blocks = self.detect(img_array)
        
        doc.close()
        return blocks

    def detect(self, image: np.ndarray) -> List[LayoutBlock]:
        """
        Detect layout blocks in a page image.
        
        This method adapts the official PDF-Extract-Kit prediction interface
        to match the existing PDFLayoutDetector.detect() signature.
        
        Args:
            image: numpy array (H, W, 3) in RGB format
            
        Returns:
            List of LayoutBlock objects
            
        Official reference:
        https://github.com/opendatalab/PDF-Extract-Kit/blob/main/pdf_extract_kit/tasks/layout_detection/models/yolo.py#L50-80
        """
        h, w = image.shape[:2]
        
        # Official inference call
        # Source: pdf_extract_kit/tasks/layout_detection/models/yolo.py#L56
        results = self.model.predict(
            image, 
            imgsz=self.img_size,
            conf=self.conf_thres,
            iou=self.iou_thres,
            verbose=False,
            device='cuda'  # Explicitly use CUDA
        )[0]
        
        # Official result parsing
        # Source: Same file, lines 63-65
        boxes = results.boxes.xyxy.cpu().numpy()  # (N, 4) [x1, y1, x2, y2]
        classes = results.boxes.cls.cpu().numpy()  # (N,) class IDs
        scores = results.boxes.conf.cpu().numpy()  # (N,) confidence scores
        
        # Convert to LayoutBlock format
        blocks = []
        abandon_count = 0
        
        for box, cls, score in zip(boxes, classes, scores):
            cls_id = int(cls)
            raw_type = self.id_to_names.get(cls_id, 'unknown')
            
            # Skip 'abandon' regions (watermarks, decorations)
            if raw_type == 'abandon':
                abandon_count += 1
                continue
            
            mapped_type = self.type_mapping.get(raw_type, 'Text')
            
            block = LayoutBlock(
                bbox=tuple(box.tolist()),
                type=mapped_type,
                confidence=float(score),
                page_width=w,
                page_height=h
            )
            blocks.append(block)
        
        if abandon_count > 0:
            print(f"[DocLayout-YOLO] Filtered {abandon_count} abandon regions", flush=True)
        
        print(f"[DocLayout-YOLO] Detected {len(blocks)} blocks", flush=True)
        return blocks
    
    def pixel_to_pdf_rect(self, pixel_bbox, page, page_width, page_height):
        """
        Convert pixel coordinates to PDF coordinates.
        
        This is copied from the existing pdf_layout_detector.py for compatibility.
        
        Args:
            pixel_bbox: (x1, y1, x2, y2) in pixel coordinates
            page: fitz.Page object
            page_width: Width of rendered image in pixels
            page_height: Height of rendered image in pixels
            
        Returns:
            fitz.Rect in PDF coordinates
        """
        x1, y1, x2, y2 = pixel_bbox
        
        # Get PDF page dimensions
        pdf_rect = page.rect
        pdf_width = pdf_rect.width
        pdf_height = pdf_rect.height
        
        # Scale from pixel to PDF coordinates
        scale_x = pdf_width / page_width
        scale_y = pdf_height / page_height
        
        pdf_x1 = x1 * scale_x
        pdf_y1 = y1 * scale_y
        pdf_x2 = x2 * scale_x
        pdf_y2 = y2 * scale_y
        
        return fitz.Rect(pdf_x1, pdf_y1, pdf_x2, pdf_y2)
