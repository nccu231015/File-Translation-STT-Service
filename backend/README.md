
# Backend API Service

This directory contains the Python backend for the File Translation & STT Service. It is built using **FastAPI** and utilizes local LLMs (via Ollama) and Docling for document processing.

## 🚀 Features

- **Speech-to-Text (STT)**: Transcribes audio files using faster-whisper (CPU-optimized).
- **Meeting Analysis**: Analyzes transcribed text to generate summaries, decisions, and action items.
- **Meeting Analysis**: Advanced meeting minutes generation with structured summaries, decisions, action items, and schedule tracking. Supports direct Word (.docx) export.
- **PDF Translation**: High-fidelity PDF translation preserving layout and structure.
  - **Pipeline**: LayoutParser (EfficientDet) -> Text Extraction -> Qwen3 Translation -> PDF Repaint.
  - **Debug Mode**: Visualize layout detection results with color-coded bounding boxes ensuring parsing accuracy before translation.
- **Chat Interface**: Simple RAG/Chat capability using local LLMs.
- **Robust Output**: Strict type enforcement and sanitization for LLM outputs to prevent frontend crashes.

## 🛠️ Stack

- **Framework**: FastAPI
- **Package Manager**: uv
- **AI/ML**: 
  - `docling` (Document parsing)
  - `faster-whisper` (CPU-optimized STT)
  - `ollama` (Local LLM inference, default model: **qwen2.5:7b**)
  - `layoutparser` + `efficientdet` (Layout Analysis)
  - `fitz` (PyMuPDF) (PDF Manipulation)
  - `opencc` (Chinese conversion)
  - `ffmpeg` (Audio processing)
- **Database/Cache**: Redis

## ⚙️ Setup & Installation

### 1. Prerequisites
- Python 3.10+ (Recommend 3.10/3.11 for ML libraries)
- `uv` package manager (`pip install uv`)
- Redis (running via Docker or locally)
- Ollama running locally with `qwen2.5:7b` model (Run `ollama pull qwen2.5:7b`)
- GPU recommended for faster LayoutParser inference (automatically detected)

### 2. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Key variables:
- `OLLAMA_BASE_URL`: Points to Ollama instance (default: `http://localhost:11434`)
- `FORCE_CPU=false`: Set to `true` to disable GPU usage.

### 3. Run Locally
```bash
# Install dependencies
uv sync

# Run the server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API Documentation: `http://localhost:8000/docs`

## 🐳 Docker Deployment (Recommended)

See root `DEPLOY_UBUNTU_2404.md` for production deployment instructions on GPU-enabled hosts.

```bash
# From project root
docker compose up -d --build
```

This will:
- Build a GPU-enabled Python environment (CUDA 12.6)
- Start FastAPI on port 8000
- Start Redis on port 6379
- Enable LayoutParser with EfficientDet backend

## 📊 API Endpoints

- `POST /stt` - Audio transcription (chat/meeting modes)
- `POST /pdf-translation` - PDF translation with structure preservation.
  - Form Data: `file` (PDF), `target_lang` (str), `debug` (bool, default=False)
- `POST /chat` - Text-based chat with AI
- `GET /` - Health check

See `/docs` for interactive API documentation.
