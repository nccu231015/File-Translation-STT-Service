# 🖼️ AI Dashboard: Document & Meeting Suite

The frontend interface for the File Translation & STT project, built with **Next.js 16** and **Shadcn UI**.

## 🔐 Authentication & Per-User Isolation

### SSO Login (LDAP)
- Users authenticate with their **employee ID (工號) and password** via the company LDAP system.
- Login is proxied through the FastAPI backend (`POST /api/login`) to avoid CORS issues.
- On success, user info (`username`, `name`, `dpt`) is stored in `localStorage('user_session')` and restored automatically on page refresh — no re-login required.
- Logout clears the session and redirects to the login page.

### Per-User Record Isolation
All records are namespaced by `username` in localStorage:

| Record Type | localStorage Key |
|---|---|
| PDF Translation history | `translation_files_${username}` |
| Voice / Meeting records | `meeting_records_${username}` |

When a different employee logs in, their own records are loaded automatically. Switching users never overwrites another user's data (guarded by a `useRef` pattern to avoid a React effect race condition where the save effect could clear data on key change).

---

## 🚀 Key Interfaces

### 1. Document Translation
- **Features**: Drag-and-drop PDF upload, target language selection, and layout-preserving rendering.
- **Preview**: Integration with PDF.js for original/translated comparison.
- **Intelligence**: Backend powered by DocLayout-YOLO for accurate block detection including formula recognition.
- **History**: Per-user translation history persisted in localStorage. Survives page refresh (metadata only; download links regenerated on next translation).

### 2. Speech-to-Text (Meeting Mode)
- **Features**: Real-time progress tracking, structured meeting minute cards (Decisions, Action Items), and Word (.docx) download.
- **Engine**: Faster-Whisper Large-v3 for near-human transcription accuracy.
- **History**: Per-user meeting records persisted in localStorage.

### 3. Intelligent Chat
- **Features**: Persistent sidebar with document history and Traditional Chinese conversion.
- **LLM**: Powered by gpt-oss:20b for context-aware responses.

---

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
- `POST /api/login` - LDAP SSO authentication proxy
- `POST /api/translate_pdf` - Layout-preserving PDF translation
- `POST /api/stt` - Speech-to-text with optional meeting analysis
- `POST /api/chat` - Conversational AI with context
