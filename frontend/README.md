# 🖼️ AI Dashboard: Document & Meeting Suite

The frontend interface for the File Translation & STT project, built with **Next.js 16** and **Shadcn UI**.

## 🚀 Key Interfaces

### 1. Document Translation
- **Features**: Drag-and-drop PDF upload, target language selection, and layout-preserving rendering.
- **Preview**: Integration with PDF.js for original/translated comparison.
- **Intelligence**: Backend powered by DocLayout-YOLO for accurate block detection including formula recognition.

### 2. Speech-to-Text (Meeting Mode)
- **Features**: Real-time progress tracking, structured meeting minute cards (Decisions, Action Items), and Word (.docx) download.
- **Engine**: Faster-Whisper Large-v3 for near-human transcription accuracy.

### 3. Intelligent Chat
- **Features**: Persistent sidebar with document history and Traditional Chinese conversion.
- **LLM**: Powered by gpt-oss:20b for context-aware responses.

## 🛠️ Development
1. **Requirements**: Node.js 20+.
2. **Setup**:
   ```bash
   npm install
   npm run dev
   ```

## 🐳 Docker Deployment
```bash
docker build -t stt-frontend .
docker run -p 3000:3000 stt-frontend
```

## 🔗 API Endpoints
- `POST /api/translate_pdf` - Layout-preserving PDF translation
- `POST /api/stt` - Speech-to-text with optional meeting analysis
- `POST /api/chat` - Conversational AI with context
