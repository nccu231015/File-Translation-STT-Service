# 🎯 File Translation & STT Service

A full-stack AI productivity suite featuring **Document Translation**, **Speech-to-Text**, and **Intelligent Meeting Analysis**. Built with modern technologies and optimized for local deployment.

## 📋 Features

### 🔄 Document Translation
- Upload PDF files for intelligent translation
- Preserves formatting, tables, and document structure
- Supports English ↔ Traditional Chinese
- Powered by **Docling** for accurate PDF parsing
- Utilizes local LLM (Ollama) for context-aware translation

### 🎙️ Speech-to-Text (STT) & Meeting Intelligence
- Transcribe audio files (WAV, MP3, M4A, etc.)
- **Advanced Meeting Analysis**:
  - Structured output: Summary, Decisions, Action Items, Schedule
  - Professional Word (.docx) export
  - Strict type enforcement for reliability
- CPU-optimized for stability on standard hardware

### 💬 AI Chat Interface
- RAG-based document Q&A
- Context-aware responses using uploaded document content
- Powered by local Ollama models (**Default: qwen2.5:7b**)

## 🏗️ Architecture

```
File-Translation-STT-Service/
├── backend/          # Python FastAPI service (Docker)
│   ├── app/
│   │   ├── main.py
│   │   └── services/
│   │       ├── pdf_service.py
│   │       ├── stt_service.py
│   │       ├── llm_service.py
│   │       └── meeting_minutes_docx.py
│   └── pyproject.toml
├── frontend/         # Next.js 16 dashboard (npm)
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   └── package.json
├── docker-compose.yml
└── Dockerfile (Backend)
```

## 🚀 Quick Start

### Prerequisites
- **Docker Desktop** (for backend)
- **Node.js 20+** (for frontend)
- **Ollama** running locally with `qwen2.5:7b` model
  ```bash
  ollama pull qwen2.5:7b
  ```

### 1️⃣ Start Backend (Docker)
```bash
# Clone the repository
git clone <your-repo-url>
cd File-Translation-STT-Service

# Start backend services (FastAPI + Redis)
docker compose up -d --build
```

Backend will be available at: `http://localhost:8000`
- API Documentation: `http://localhost:8000/docs`

### 2️⃣ Start Frontend (npm)
```bash
cd frontend
npm install
npm run dev
```

Frontend will be available at: `http://localhost:3000`

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI
- **Package Manager**: uv
- **AI/ML**:
  - `faster-whisper` (STT, CPU-optimized)
  - `docling` (PDF parsing)
  - `ollama` (Local LLM)
  - `opencc` (Chinese conversion)
- **Database**: Redis (for caching)
- **Deployment**: Docker (CPU-only build)

### Frontend
- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript
- **UI**: Shadcn UI + Tailwind CSS
- **Charts**: Recharts
- **Deployment**: npm (development) / Docker (optional)

## ⚙️ Configuration

### Backend Environment Variables
Create `backend/.env`:
```env
OLLAMA_BASE_URL=http://host.docker.internal:11434  # For Docker
REDIS_HOST=redis
REDIS_PORT=6379
FORCE_CPU=true  # CPU-only mode (default)
```

### Frontend Configuration
The frontend uses Next.js API Routes for backend communication:
- `/api/pdf-translation` → Backend PDF processing
- `/api/stt` → Backend STT processing
- `/api/chat` → Backend chat interface

Default backend URL: `http://localhost:8000`

## 📊 Performance Notes

### CPU vs GPU
This project is **CPU-optimized** to work on standard hardware:
- **STT Processing**: Using `beam_size=1` for memory efficiency
- **PDF Processing**: Prioritizes compatibility over speed
- **Docker Image**: ~1.5GB (no NVIDIA libraries)

For GPU acceleration:
1. Remove `FORCE_CPU=true` from environment
2. Rebuild with GPU-enabled torch/whisper

### Memory Recommendations
- **Docker Memory**: 4-8GB recommended (Settings → Resources)
- **Large Files**: Audio files >50MB may require additional memory

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check container logs
docker compose logs app -f

# Ensure Ollama is running
curl http://localhost:11434/api/tags
```

### Frontend can't connect to backend
- Verify backend is running: `curl http://localhost:8000/`
- Check `NEXT_PUBLIC_API_URL` in API routes

### Large audio files fail
- Increase Docker memory limit (Docker Desktop → Settings → Resources)
- Check backend logs for OOM errors

## 📝 Development

### Backend Development
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

### Frontend Development
```bash
cd frontend
npm run dev
```

## 📦 Deployment

### Production Build
```bash
# Backend: Already containerized
docker compose up -d

# Frontend: Build for production
cd frontend
npm run build
npm start
```

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Backend tests pass
- Frontend builds without errors
- Code follows existing style conventions

## 📄 License

[Your License Here]

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai/) - Local LLM runtime
- [Docling](https://github.com/DS4SD/docling) - PDF parsing
- [Faster Whisper](https://github.com/guillaumekln/faster-whisper) - Efficient STT
- [Shadcn UI](https://ui.shadcn.com/) - Component library
