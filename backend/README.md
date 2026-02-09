# 🐍 AI Backend: Document & Audio Intelligence

FastAPI-based intelligence engine providing high-fidelity document translation and speech-to-text capabilities.

## 🚀 Key Modules

### 1. PDF Layout Preservation (`app/services/pdf_service.py`)
- **Engine**: DocLayout-YOLO (PDF-Extract-Kit) + PyMuPDF.
- **Breakthrough**: 3-4x faster than traditional Detectron2 with superior accuracy on diverse documents.
- **Logic**:
    - AI detects visual blocks (Title, Text, Table, **Formula**).
    - PyMuPDF extracts text from vector layer within AI-defined bboxes.
    - LLM translates blocks with context-awareness.
    - **Formula blocks are automatically skipped** to prevent math corruption.
    - Result is rendered back using `insert_htmlbox` for auto-scaling.

### 2. Audio Processing (`app/services/stt_service.py`)
- **Engine**: `faster-whisper` (Large-v3).
- **GPU Locking**: Serialized inference to prevent CUDA collision, wrapped in a non-blocking threadpool.

### 3. LLM Orchestration (`app/services/llm_service.py`)
- **Model**: gpt-oss:20b (via Ollama).
- **Optimization**: Smart cleaning of `<think>` tags and conversational prefixes.
- **Concurrency**: Fully async pipeline using `httpx` to handle multiple requests without blocking.

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
