# 🐍 AI Backend: Document & Audio Intelligence

FastAPI-based intelligence engine providing high-fidelity document translation and speech-to-text capabilities.

## 🚀 Key Modules

### 1. PDF Layout Preservation (`app/services/`)

Core files: `pdf_service.py` → `pdf_layout_service.py` → `pdf_layout_detector_yolo.py`

#### Detection Layer (`pdf_layout_detector_yolo.py`)
- **Engine**: DocLayout-YOLO (PDF-Extract-Kit), 3-4x faster than Detectron2.
- YOLO renders the page at **3x zoom** and detects blocks: `Title`, `Text`, `List`, `Table`, `Figure`, `Formula`, `Abandon`.
- `Abandon` blocks are **passed through** (not filtered) to allow the rescue mechanism to evaluate them.

#### Translation Pipeline (`pdf_layout_service.py`) — v2

The pipeline is split into two clean phases per page:

**Phase 0 — Block Candidate Assembly**

| Step | Description |
|------|-------------|
| Protected areas | `Figure`, `Table`, `Equation` blocks are marked as protected; overlapping text blocks are dropped. |
| Abandon rescue | Blocks typed `Abandon` by YOLO that contain meaningful text (>10 chars, CJK or multi-word) are reclassified as `Text`. |
| Orphan line rescue | PyMuPDF scans every text **line** on the page. Lines with ≤40% overlap with any YOLO bbox are added as independent `Text` blocks (catches colored inline notes, footnotes, headers). |
| Two-Pass NMS | **Pass 1**: Drops "container shell" blocks whose area is ≥60% covered by ≥2 smaller child blocks — preserves precise children for tighter wipe rects. **Pass 2**: Standard overlap dedup; drops blocks >80% inside another kept block. |

**Phase 1 — Wipe**

1. Convert each block's bbox from YOLO pixel space to PDF point space.
2. Search for text spans within `bbox ± 3pt` using `page.get_text("dict")`.
3. Compute the **natural union** of found span bboxes (no artificial margin).
4. Register a **PDF redaction annotation** (`page.add_redact_annot`) on that area.
5. After all blocks are registered: `page.apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=False)`.
   - Permanently **removes** original text from the content stream (not just a visual overlay).
   - `graphics=False` preserves table borders and vector graphics.

**Phase 2 — Translate & Render**

- Each block is sent to the LLM (`gpt-oss:20b` via Ollama) for translation with page-level context.
- Translated text is rendered using `page.insert_htmlbox` with adaptive CSS: font family, size, weight, and colour are extracted from the original spans via weighted voting.
- Single newlines are stripped so English text wraps naturally; double newlines become `<br/><br/>` paragraph breaks.

### 2. Audio Processing (`app/services/stt_service.py`)
- **Engine**: `faster-whisper` (Large-v3).
- **GPU Locking**: Serialized inference to prevent CUDA collision, wrapped in a non-blocking threadpool.

### 3. LLM Orchestration (`app/services/llm_service.py`)
- **Model**: gpt-oss:20b (via Ollama).
- **Optimization**: Smart cleaning of `<think>` tags and conversational prefixes.
- **Concurrency**: Fully async pipeline using `httpx` to handle multiple requests without blocking.

---

## 🛠️ Installation (Local Dev)
1. **Requirements**: Python 3.10 + `uv`.
2. **Setup**:
   ```bash
   uv sync
   uv run uvicorn app.main:app --reload
   ```

## 🐳 Docker (Production)
The Dockerfile uses **NVIDIA CUDA 12.1** to support Faster-Whisper and DocLayout-YOLO.
```bash
docker compose up -d --build
```

## 📦 Model Dependencies
- **Layout Detection**: [DocLayout-YOLO](https://github.com/opendatalab/PDF-Extract-Kit) (~50MB, auto-downloaded)
- **STT**: faster-whisper large-v3 (auto-downloaded on first run)
- **LLM**: ollama gpt-oss:20b (requires manual `ollama pull`)
