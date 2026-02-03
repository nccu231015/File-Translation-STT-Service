# 🐍 AI Backend: Document & Audio Intelligence

FastAPI-based intelligence engine providing high-fidelity document translation and speech-to-text capabilities.

## 🚀 Key Modules

### 1. PDF Layout Preservation (`app/services/pdf_service.py`)
- **Engine**: LayoutParser (Detectron2) + PyMuPDF.
- **Logic**:
    - AI detects visual blocks (Title, Text, Table).
    - PyMuPDF extracts text from vector layer within AI-defined bboxes.
    - LLM translates blocks with context-awareness.
    - Result is rendered back using `insert_htmlbox` for auto-scaling.

### 2. Audio Processing (`app/services/stt_service.py`)
- **Engine**: `faster-whisper` (Large-v3).
- **GPU Locking**: Serialized inference to prevent CUDA collision, wrapped in a non-blocking threadpool.

### 3. LLM Orchestration (`app/services/llm_service.py`)
- **Model**: gpt-oss:20b (via Ollama).
- **Optimization**: Smart cleaning of `<think>` tags and conversational prefixes.

## 🛠️ Installation (Local Dev)
1. **Requirements**: Python 3.10 + `uv`.
2. **Setup**:
   ```bash
   uv sync
   uv run uvicorn app.main:app --reload
   ```

## 🐳 Docker (Production)
The Dockerfile uses **NVIDIA CUDA 12.1** to support both Faster-Whisper and Detectron2.
```bash
docker compose up -d --build
```
