# AI 智慧助手 v2.0 - STT, Meeting Minutes & Translation

一個整合語音轉文字 (STT)、會議自動記錄、智慧聊天與 PDF 翻譯的全功能 AI 助手系統。支援 Windows (CUDA/CPU) 與 Docker 部署。

## ✨ 功能特色 (v2.0)

- 🎤 **雙模式語音辨識**：
    - **聊天模式 (Chat Mode)**：即時語音轉文字並與 AI 進行對話。
    - **會議模式 (Meeting Mode)**：針對長錄音進行分析，自動生成 **重點摘要**、**決策事項** 與 **待辦清單**。
- 📂 **智慧檔案處理**：
    - **PDF 上傳**：自動提取內容、翻譯成繁體中文並生成摘要。
    - **音檔上傳**：支援 `.mp3`, `.wav`, `.m4a`，自動進行會議記錄分析並生成 `.txt` 報告。
- 💬 **智慧對話**：基於 Ollama LLM 的自然語言對話，支援上下文記憶 (Redis)。
- 🌏 **繁體中文優化**：所有 AI 輸出 (翻譯、摘要、對話) 自動轉換為台灣繁體中文。
- ⚡ **彈性運算**：支援 NVIDIA GPU 加速 (faster-whisper)，亦可在純 CPU 環境運行 (自動降級)。
- 🐳 **Docker 部署**：支援一鍵 Docker Compose 部署，包含前後端與 Redis。

## 🏗️ 技術棧

### 前端
- **框架**: React 18 + Vite
- **樣式**: TailwindCSS (Utility-first) + CSS Modules
- **狀態管理**: React Hooks
- **HTTP 客戶端**: Fetch API

### 後端
- **框架**: FastAPI (Python 3.11)
- **語音辨識**: faster-whisper (Windows/CUDA/CPU 自動適配)
- **LLM**: Ollama (qwen2.5:7b)
- **PDF 處理**: Docling (Markdown 轉換)
- **會議分析**: Map-Reduce 架構 (處理長文本摘要)
- **簡繁轉換**: OpenCC
- **快取/會話**: Redis
- **依賴管理**: uv

## 📦 系統架構

```
┌─────────────┐
│   瀏覽器    │
│ (React UI)  │
└──────┬──────┘
       │ HTTP (Restful API)
       ▼
┌─────────────┐      ┌──────────────┐
│  FastAPI    │◄────►│    Redis     │
│  (後端服務)  │      │ (會話快取)    │
└──────┬──────┘      └──────────────┘
       │
       ├──► faster-whisper (STT - 本機 GPU/CPU)
       │
       └──► Ollama (LLM - 遠端/本機主機)
              - 聊天對話
              - PDF 翻譯
              - 會議記錄分析 (Map-Reduce)
```

---

## 🚀 部署指南 (Windows Docker Desktop)

### 前置需求
1.  **Docker Desktop** (建議啟用 WSL 2)
2.  **Ollama** (需在 Host 主機或另一台機器上運行，並已安裝 `qwen2.5:7b` 模型)
    - 啟動指令：`OLLAMA_HOST=0.0.0.0 ollama serve`

### 1. 啟動服務
在專案根目錄執行：

```powershell
docker-compose up -d --build
```

這會自動：
- 建置前端 (React)
- 建置後端 (Python + 依賴)
- 啟動 Redis
- 透過 `host.docker.internal` 連接 Host 的 Ollama

### 2. 訪問應用
打開瀏覽器訪問： `http://localhost:8000`

### 3. GPU 支援 (Optional)
若要啟用 NVIDIA GPU 加速 (faster-whisper)，需：
1.  Windows 安裝 NVIDIA 驅動程式。
2.  WSL 2 安裝並更新 (`wsl --update`)。
3.  在 `docker-compose.yml` 中取消註解 `deploy`區塊。
4.  若無法使用 GPU，將環境變數 `FORCE_CPU=true` 設為啟用 (預設已啟用以確保相容性)。

---

## 📖 使用指南

### 1. 聊天模式 (Chat Mode)
- **文字聊天**：直接輸入文字，AI 會根據上下文回覆。
- **語音聊天**：
    1. 切換模式至 **"💬 Chat"** (預設)。
    2. 點擊 **麥克風** 開始說話，點擊停止。
    3. AI 會即時回覆。

### 2. 會議模式 (Meeting Mode)
- **即時錄音**：
    1. 切換模式至 **"📝 Meeting"**。
    2. 點擊 **麥克風** 錄製會議內容。
    3. 錄製結束後，系統會分析並產生會議記錄。
- **上傳音檔**：
    1. 點擊 **📎 (迴紋針)** 按鈕。
    2. 選擇 `.mp3`, `.wav` 或 `.m4a` 檔案。
    3. 系統自動進行長錄音分析。

**輸出結果**：
- 逐字稿
- 📋 **重點摘要**
- ✅ **決策事項**
- ⚡ **待辦清單**
- 自動下載 `.txt` 報告檔

### 3. PDF 文件翻譯
1. 點擊 **📎 (迴紋針)** 按鈕。
2. 選擇 `.pdf` 檔案。
3. 系統自動翻譯、產生摘要並下載翻譯檔。

---

## 🔧 開發者指南 (本機運行)

如果您不使用 Docker，想直接在原有環境運行：

### 後端準備
```bash
# 確保 Redis 已在 localhost:6379 運行
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端更新
若修改了前端程式碼：
```bash
cd frontend
npm run build
# 後端會自動載入新的 frontend/dist 檔案，無需重啟後端 (除非修改了 main.py)
```

---

## 📄 API 參考

| 端點 | 方法 | 參數 | 描述 |
|------|------|------|------|
| `/chat` | POST | `{"text": "..."}` | 一般文字對話 |
| `/stt` | POST | `file`, `mode="chat"` | 語音轉文字 + AI 回覆 |
| `/stt` | POST | `file`, `mode="meeting"` | 語音轉文字 + 會議分析 |
| `/pdf-translation` | POST | `file` | PDF 翻譯 + 摘要 |

---

## 🙏 致謝
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - 高效 STT 引擎
- [Ollama](https://ollama.ai/) - 本地 LLM
- [Docling](https://github.com/DS4SD/docling) - PDF 解析
