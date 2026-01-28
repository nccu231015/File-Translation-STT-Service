
# Backend API Service

This directory contains the Python backend for the File Translation & STT Service. It is built using **FastAPI** and utilizes local LLMs (via Ollama) and Docling for document processing.

## 🚀 Features

- **Speech-to-Text (STT)**: Transcribes audio files using faster-whisper (CPU-optimized).
- **Meeting Analysis**: Analyzes transcribed text to generate summaries, decisions, and action items.
- **Meeting Analysis**: Advanced meeting minutes generation with structured summaries, decisions, action items, and schedule tracking. Supports direct Word (.docx) export.
- **PDF Translation**: High-fidelity PDF translation preserving layout and structure (via Docling + Qwen 3).
- **Chat Interface**: Simple RAG/Chat capability using local LLMs.
- **Robust Output**: Strict type enforcement and sanitization for LLM outputs to prevent frontend crashes.

## 🛠️ Stack

- **Framework**: FastAPI
- **Package Manager**: uv
- **AI/ML**: 
  - `docling` (Document parsing)
  - `faster-whisper` (CPU-optimized STT)
  - `ollama` (Local LLM inference, default model: **qwen3:8b**)
  - `opencc` (Chinese conversion)
  - `ffmpeg` (Audio processing)
- **Database/Cache**: Redis

## ⚙️ Setup & Installation

### 1. Prerequisites
- Python 3.11+
- `uv` package manager (`pip install uv`)
- Redis (running via Docker or locally)
- Ollama running locally with `qwen3:8b` model (Run `ollama pull qwen3:8b`)

### 2. Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Key variables:
- `OLLAMA_BASE_URL`: Points to Ollama instance (default: `http://localhost:11434`)
- `FORCE_CPU=true`: Enforces CPU-only mode (recommended)

### 3. Run Locally
```bash
# Install dependencies
uv sync

# Run the server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API Documentation: `http://localhost:8000/docs`

## 🐳 Docker Deployment (Recommended)

The backend is designed for Docker deployment with CPU-only optimization:

```bash
# From project root
docker compose up -d --build
```

This will:
- Build a CPU-optimized Python environment (~1.5GB)
- Start FastAPI on port 8000
- Start Redis on port 6379
- Mount code for hot-reload during development

### Performance Notes
- **CPU-Only Build**: No NVIDIA libraries, saves ~2GB
- **Memory**: Recommend 4-8GB Docker memory limit
- **Large Files**: Audio files >50MB may require additional resources

## 📊 API Endpoints

- `POST /stt` - Audio transcription (chat/meeting modes)
- `POST /pdf-translation` - PDF translation with structure preservation
- `POST /chat` - Text-based chat with AI
- `GET /` - Health check

See `/docs` for interactive API documentation.
