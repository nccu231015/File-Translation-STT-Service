
# Frontend Dashboard

This is the user interface for the AI Productivity Suite. It is a modern web application built with **Next.js 16 (App Router)** and **Shadcn UI**.

## ✨ Features

- **Dashboard**: Central hub for all AI tools
- **Document Translation**: Upload PDFs and get them translated (EN ↔ ZH) with formatting preserved
- **Voice Intelligence**: Powerful meeting analysis dashboard with:
  - Automatic transcription and speaker-aware summarization
  - Structured "Decisions" and "Action Items" extraction
  - Persistent record storage (via LocalStorage)
  - One-click export to professionally formatted Word (.docx) minutes
  - Improved file upload experience with reset capability
- **Report Generation**: (Mock) Generate visual analytics reports for production data
- **QA Interface**: RAG-based question answering system

## 🛠️ Stack

- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript
- **UI Components**: Shadcn UI (Radix UI + Tailwind CSS)
- **Styling**: Tailwind CSS
- **Visualization**: Recharts
- **Icons**: Lucide React
- **Markdown Rendering**: react-markdown

## 🚀 Setup & Development

### 1. Prerequisites
- Node.js 20+
- npm or yarn
- Backend running on `http://localhost:8000`

### 2. Installation
```bash
npm install
# or
yarn install
```

### 3. Environment Setup
The frontend communicates with the backend via Next.js API Routes:
- `/api/pdf-translation` → Backend PDF processing
- `/api/stt` → Backend STT processing
- `/api/chat` → Backend chat interface

Default backend URL is `http://127.0.0.1:8000`. To change:
- Edit `NEXT_PUBLIC_API_URL` in API route files
- Or set environment variable: `NEXT_PUBLIC_API_URL=http://your-backend:8000`

### 4. Run Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### 5. Build for Production
```bash
npm run build
npm start
```

## 📁 Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── api/           # Next.js API Routes (backend proxy)
│   │   ├── page.tsx       # Main dashboard
│   │   └── layout.tsx     # Root layout
│   ├── components/
│   │   ├── dashboard/     # Feature components
│   │   └── ui/            # Shadcn UI components
│   └── lib/
│       ├── api/           # API client functions
│       └── utils.ts       # Utility functions
└── public/                # Static assets
```

## 🔌 API Integration

### Backend Communication
The frontend uses Next.js API Routes to proxy requests to the backend. This approach:
- Avoids CORS issues
- Extends timeout limits (30 minutes for long-running tasks)
- Handles large file uploads

### Key API Routes
- `POST /api/pdf-translation` - PDF upload & translation
- `POST /api/stt` - Audio upload & transcription
- `POST /api/chat` - Text chat with AI

## 🎨 UI Components

Built with **Shadcn UI** for consistent, accessible components:
- Forms with validation
- File upload with drag-and-drop
- Toast notifications
- Progress indicators
- Charts and visualizations

## 🐛 Troubleshooting

### Backend Connection Issues
- Verify backend is running: `curl http://localhost:8000/`
- Check API route configuration in `src/app/api/*/route.ts`

### Build Errors
```bash
# Clear cache and rebuild
rm -rf .next
npm run build
```

### Large File Upload Timeouts
- API routes have 30-minute timeout (`maxDuration: 1800`)
- For very large files, consider chunked uploads

## 📦 Deployment

### Development
```bash
npm run dev
```

### Production (npm)
```bash
npm run build
npm start
```

The application will be available on port 3000.

## 🤝 Contributing

When adding new features:
1. Keep components modular
2. Use TypeScript for type safety
3. Follow Shadcn UI patterns
4. Update this README if adding new dependencies
