# 🎯 AI File Translation & Meeting Suite (GPU Enhanced)

A high-performance AI productivity framework tailored for **Document Structure preservation**, **High-Fidelity Transcription**, and **Structured Insight Generation**. Fully optimized for NVIDIA GPU (CUDA 12.1) and Local LLMs.

## 📋 Features

### 📄 Document Translation (Layout-Preserving)
- **Visual Intelligence**: Uses **DocLayout-YOLO** (PDF-Extract-Kit) to analyze document structure with **3-4x faster** inference than traditional Detectron2.
- **Multi-Layer Text Detection**: Combines YOLO visual detection with PyMuPDF span-level scanning to ensure no text block is missed — including annotations, footnotes, and colored inline notes.
- **Formula-Aware**: Automatically detects and skips mathematical formulas to prevent translation corruption.
- **Layout Fidelity**: Overwrites translation onto the original PDF, preserving tables, columns, and document flow.
- **Precise Text Erasure**: Uses PyMuPDF's **Redaction API** to permanently remove original text from the PDF content stream (instead of a visual white-overlay), eliminating transparent bleed-through artifacts.
- **Adaptive Scaling**: Automatically adjusts font sizes to prevent text overflow using the `htmlbox` rendering engine.
- **Local Power**: Powered by **gpt-oss:20b** for robust English ↔ Traditional Chinese translation.

### 🎙️ Speech-to-Text & Meeting Intelligence
- **Near-Human Accuracy**: Implements `faster-whisper` **large-v3** for superior transcription.
- **Intelligent Summarization**: Automatically extracts **Decisions**, **Action Items**, and **Key Bullet Points**.
- **Formatted Export**: One-click download of meeting minutes in professional **Office Word (.docx)** format.

### ⚡ Concurrency & Performance
- **Non-blocking APIs**: Heavy AI computations run in threadpools to keep the UI responsive for all users.
- **Multi-User Ready**: Concurrent request handling with explicit GPU locking to prevent resource collisions.
- **Speed Optimized**: Smart text block merging and high-threshold chunking logic to minimize LLM call latency.

---

## 🏗️ Technical Architecture

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Backend** | FastAPI (Python 3.10) | Async API Gateway |
| **Vision** | DocLayout-YOLO (PDF-Extract-Kit) | Document Layout Analysis |
| **STT** | Faster-Whisper (CUDA 12.1) | Transcription Engine |
| **LLM** | Ollama (gpt-oss:20b) | Translation & Reasoning |
| **Frontend** | Next.js (Tailwind + Shadcn) | User Dashboard |
| **Storage** | Redis + Local Storage | Cache & Temporary Files |

---

## 🚀 Quick Start

### 1. Requirements
- **Hardware**: NVIDIA GPU (A10/A40/3090/4090) with 24GB+ VRAM.
- **Software**: Docker + NVIDIA Container Toolkit + Ollama.
- **Model Prep**:
  ```bash
  ollama pull gpt-oss:20b
  ```

### 2. Launch (Docker)
```bash
# Clone the repo
git clone <repo-url>
cd File-Translation-STT-Service

# Start the full stack
docker compose up -d --build
```

- **Backend Docs**: `http://localhost:8000/docs`
- **Frontend Dashboard**: `http://localhost:3000`

---

## ⚙️ Environment Config (`.env`)
```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=gpt-oss:20b
FORCE_CPU=false
REDIS_HOST=redis
DOCLAYOUT_MODEL_PATH=/app/models/layout/doclayout_yolo_ft.pt
```

---

## 🧠 Technical Highlights

### DocLayout-YOLO Integration
We've migrated from traditional Detectron2 to **[DocLayout-YOLO](https://github.com/opendatalab/PDF-Extract-Kit)**, delivering:

- **3-4x Faster Inference**: YOLO's single-stage architecture vs. Faster R-CNN's two-stage.
- **Better Accuracy**: Trained on DocSynth-300K (diverse documents) vs. PubLayNet (academic-only).
- **Formula Detection**: Automatically identifies and preserves mathematical equations.
- **Smaller Footprint**: ~50MB model vs. ~250MB for Detectron2.

**Official Resources**:
- [PDF-Extract-Kit GitHub](https://github.com/opendatalab/PDF-Extract-Kit)
- [DocLayout-YOLO Paper](https://arxiv.org/abs/2410.12628)
- [Model Weights](https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0)

---

### PDF Translation Pipeline (v2)

The translation pipeline uses a multi-stage approach designed for robustness and accuracy:

#### 1. Layout Detection
YOLO runs on a 3x-zoom render of the page to detect content blocks (Title, Text, List, Table, Figure, Formula, Abandon).

#### 2. Multi-Layer Text Rescue
Blocks missed or mis-classified by YOLO are recovered via two mechanisms:
- **Abandon Rescue**: YOLO passes `abandon`-typed blocks downstream; the service rescues any that contain meaningful text content.
- **Orphan Line Rescue**: PyMuPDF scans every text line on the page. Lines not covered (>40%) by any YOLO block are added as independent translation targets.

#### 3. Two-Pass NMS (Non-Maximum Suppression)
- **Pass 1 — Container Shell Removal**: If a large block is covered ≥60% by two or more smaller child blocks, the large block is discarded in favour of the precise children. This ensures wipe rectangles are as tight as possible.
- **Pass 2 — Standard Overlap Dedup**: Drops any remaining block that is >80% contained within an already-kept block.

#### 4. Wipe Phase — Redaction API
For each retained block, the pipeline:
1. Searches for text spans within the YOLO bbox ± 3pt (to catch boundary glyphs).
2. Computes the **natural union** of found span bboxes (no artificial margin added).
3. Registers a **PDF redaction annotation** (`add_redact_annot`) on that area.

After all blocks are registered, `apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=False)` is called once per page. This:
- **Permanently removes** original text from the PDF content stream (not just a visual overlay).
- Preserves vector graphics, table borders, and raster images.

#### 5. Render Phase
Translated text is inserted using `insert_htmlbox` with adaptive CSS scaling, preserving the original font weight, colour, and text alignment.

---

## 📝 License & Contact
Developed with ❤️ by Antigravity.
