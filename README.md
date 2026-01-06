# AI 智慧助手 - STT & Translation

一個集成語音轉文字 (STT)、智慧聊天與 PDF 翻譯的全功能 AI 助手系統。

## ✨ 功能特色

- 🎤 **語音轉文字 (STT)**：使用 MLX Whisper 在 Apple Silicon 上實現超高速語音辨識
- 💬 **智慧對話**：基於 Ollama LLM 的自然語言對話，支援上下文記憶
- 📄 **PDF 智慧翻譯**：自動提取、翻譯 PDF 內容並生成摘要
- 🌏 **繁體中文優化**：所有 AI 輸出自動轉換為台灣繁體中文
- ⚡ **GPU 加速**：STT 使用 MLX (Apple Silicon)，翻譯與對話使用遠端 Ollama
- 🔄 **上下文感知**：PDF 摘要自動加入對話記憶，支援文件問答

## 🏗️ 技術棧

### 前端
- **框架**: React 18 + Vite
- **樣式**: CSS Modules (自訂設計系統)
- **狀態管理**: React Hooks
- **HTTP 客戶端**: Fetch API

### 後端
- **框架**: FastAPI (Python 3.11)
- **語音辨識**: MLX Whisper (Apple Silicon 優化)
- **LLM**: Ollama (qwen2.5:7b)
- **PDF 處理**: Docling (Markdown 轉換)
- **簡繁轉換**: OpenCC
- **快取/會話**: Redis
- **依賴管理**: uv

## 📦 系統架構

```
┌─────────────┐
│   瀏覽器    │
│  (React UI) │
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────┐      ┌──────────────┐
│  FastAPI    │◄────►│    Redis     │
│  (後端服務)  │      │ (會話快取)    │
└──────┬──────┘      └──────────────┘
       │
       ├──► MLX Whisper (STT - 本機 GPU)
       │
       └──► Ollama (LLM - 遠端主機)
              - 聊天對話
              - PDF 翻譯
              - 摘要生成
```

---

## 🚀 快速開始

### 前置需求

- **macOS** (Apple Silicon，M1/M2/M3)
- **Python 3.11+**
- **Node.js 18+**
- **Redis** (本機或遠端)
- **Ollama** (遠端主機，已安裝 `qwen2.5:7b` 模型)

---

## 📱 前端部署

### 1. 安裝依賴

```bash
cd frontend
npm install
```

### 2. 開發模式運行

```bash
npm run dev
```

前端會在 `http://localhost:5173` 啟動。

### 3. 生產環境打包

```bash
npm run build
```

打包後的檔案會輸出到 `frontend/dist/` 目錄。

### 前端結構說明

```
frontend/
├── src/
│   ├── App.jsx                 # 主應用組件（處理聊天、STT、PDF 上傳）
│   ├── components/
│   │   ├── Chat/
│   │   │   ├── ChatInput.jsx   # 聊天輸入框（含語音錄製）
│   │   │   ├── MessageList.jsx # 訊息列表（含載入動畫）
│   │   │   └── MessageItem.jsx # 單一訊息卡片
│   │   └── FileUpload.jsx      # PDF 檔案上傳器
│   └── index.css               # 全域樣式與設計系統
├── dist/                       # 打包輸出目錄（由後端提供服務）
└── package.json
```

### 關鍵設定

- **API 路徑**：所有 API 請求使用相對路徑（如 `/chat`, `/stt`），由後端統一處理。
- **自動下載**：PDF 翻譯完成後會自動觸發下載 `.txt` 檔案。
- **即時回饋**：語音錄製時顯示波形動畫，處理中顯示跳動點動畫。

---

## 🖥️ 後端部署

### 1. 安裝 uv（Python 依賴管理工具）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

或使用 Homebrew：

```bash
brew install uv
```

### 2. 安裝依賴（自動建立虛擬環境）

```bash
cd backend
uv sync
```

### 3. 配置環境變數

在 `backend/` 目錄下建立 `.env` 檔案：

```env
# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_USERNAME=
REDIS_DB=0

# Ollama 遠端主機配置
OLLAMA_BASE_URL=http://192.168.1.108:11434
```

### 4. 啟動後端服務

```bash
uv run uvicorn app.main:app --reload --port 8000
```

後端會在 `http://localhost:8000` 啟動，並自動載入前端靜態檔案。

### 後端結構說明

```
backend/
├── app/
│   ├── main.py                      # FastAPI 主程式（路由定義、靜態檔案服務）
│   └── services/
│       ├── stt_service.py           # 語音轉文字服務（MLX Whisper）
│       ├── llm_service.py           # LLM 聊天服務（Ollama + Redis + OpenCC）
│       └── pdf_service.py           # PDF 處理服務（Docling + 翻譯 + 摘要）
├── .env                             # 環境變數配置
├── pyproject.toml                   # Python 專案配置
└── uv.lock                          # 依賴鎖定檔案
```

### API 端點

| 端點 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 回傳前端 `index.html` |
| `/assets/*` | GET | 靜態資源（JS/CSS） |
| `/chat` | POST | 文字對話（Body: `{"text": "..."}`) |
| `/stt` | POST | 語音轉文字（FormData: `file`) |
| `/pdf-translation` | POST | PDF 翻譯與摘要（FormData: `file`) |

### 核心服務說明

#### 1. STT Service (`stt_service.py`)
- 使用 **MLX Whisper** (Apple Silicon 專屬優化)
- 模型：`mlx-community/whisper-small-mlx`
- 支援 `.webm`, `.wav`, `.mp3` 等音檔格式
- 平均處理時間：5-10 秒（3 分鐘音檔）

#### 2. LLM Service (`llm_service.py`)
- 使用 **Ollama API** (`/api/chat`)
- 模型：`qwen2.5:7b`
- 功能：
  - 對話管理（Redis 儲存歷史記錄）
  - PDF 摘要自動加入上下文
  - **OpenCC 自動簡轉繁**（輸出保證繁體中文）

#### 3. PDF Service (`pdf_service.py`)
- **Docling** 提取 PDF 內容為 Markdown
- **分塊翻譯**：每塊最多 1500 字，減少 LLM 呼叫次數
- **Map-Reduce 摘要**：
  - 短文件（< 3000 字）：直接生成摘要
  - 長文件：分段摘要 → 合併 → 最終摘要
- **OpenCC 自動簡轉繁**

---

## 🌐 對外分享（使用 Cloudflare Tunnel）

如果您想分享給其他人使用，推薦使用 **Cloudflare Tunnel**（免費、無廣告）：

### 1. 安裝 Cloudflared

```bash
brew install cloudflare/cloudflare/cloudflared
```

### 2. 啟動隧道

```bash
cloudflared tunnel --url localhost:8000
```

終端機會顯示一個公開網址（例如 `https://random-words.trycloudflare.com`），直接分享即可。

**注意事項：**
- ✅ 聊天功能、語音轉文字可正常使用
- ⚠️ 大型 PDF 翻譯可能因超時（100 秒限制）而中斷，建議在本機處理

---

## 📖 使用指南

### 1. 文字聊天
1. 在輸入框輸入訊息
2. 按 **Enter** 或點擊 **送出** 按鈕
3. AI 會根據上下文回覆（包含先前上傳的 PDF 摘要）

### 2. 語音轉文字
1. 點擊 **麥克風圖示** 開始錄音
2. 說話後點擊 **停止按鈕**
3. 系統會自動辨識並將文字送出給 AI 回覆

### 3. PDF 翻譯與摘要
1. 點擊 **📎 上傳 PDF** 按鈕
2. 選擇 PDF 檔案
3. 系統會：
   - 提取 PDF 內容
   - 翻譯為繁體中文
   - 生成摘要並顯示在聊天室
   - 自動下載翻譯檔案（`.txt`）
4. 後續可直接詢問關於該 PDF 的問題

---

## 🔧 常見問題

### Q1: 語音辨識失敗或很慢？
**A:** MLX Whisper 僅支援 Apple Silicon (M1/M2/M3)。如需在其他平台運行，需改用標準 `openai-whisper`（CPU 模式，較慢）。

### Q2: LLM 回覆是簡體中文？
**A:** 已整合 OpenCC 自動轉換，若仍出現簡體字請回報 issue。

### Q3: PDF 翻譯超時？
**A:** 大型 PDF（87+ 塊）可能需 5-10 分鐘。若透過 Cloudflare Tunnel 使用，建議小型 PDF 或在本機處理。

### Q4: Redis 連線失敗？
**A:** 確認 `.env` 中的 Redis 配置正確，並確保 Redis 服務已啟動：
```bash
redis-server --daemonize yes
```

### Q5: Ollama 連線失敗？
**A:** 確認遠端主機的 Ollama 正在運行，且設定了環境變數：
```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

---

## 📝 開發建議

### 本機開發流程
1. **啟動 Redis**：`redis-server`
2. **啟動後端**：`cd backend && uv run uvicorn app.main:app --reload`
3. **打開瀏覽器**：訪問 `http://localhost:8000`

**不需要單獨啟動前端開發伺服器**，因為後端已整合靜態檔案服務。

### 修改前端後的更新流程
```bash
cd frontend
npm run build
# 後端會自動載入新的 dist 檔案
```

---

## 📄 授權

MIT License

---

## 🙏 致謝

- [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) - Apple Silicon 語音辨識加速
- [Ollama](https://ollama.ai/) - 本地 LLM 服務
- [Docling](https://github.com/DS4SD/docling) - PDF 轉 Markdown
- [OpenCC](https://github.com/BYVoid/OpenCC) - 簡繁轉換
- [FastAPI](https://fastapi.tiangolo.com/) - 現代 Python Web 框架
- [React](https://react.dev/) - 前端框架
