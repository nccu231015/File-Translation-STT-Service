# 🖼️ AI Dashboard: Document & Meeting Suite

The frontend interface for the File Translation & STT project, built with **Next.js 16** and **Shadcn UI**.

## 🚀 Key Interfaces

### 1. Document Translation
- **Features**: Drag-and-drop PDF upload, target language selection, and layout-preserving rendering.
- **Preview**: Integration with PDF.js for original/translated comparison.

### 2. Speech-to-Text (Meeting Mode)
- **Features**: Real-time progress tracking, structured meeting minute cards (Decisions, Action Items), and Word (.docx) download.

### 3. Intelligent Chat
- **Features**: Persistent sidebar with document history and Traditional Chinese conversion.

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
