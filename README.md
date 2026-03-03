# 🎯 全一電子 AI 助手（地端部署版）

企業級地端 AI 平台，提供 **版面保留 PDF 翻譯** 與 **語音會議紀錄** 兩大核心功能。完全運行於企業內網，不外傳任何資料。

## 📋 功能模組

### 🔐 身份驗證 & 使用者隔離
- **LDAP SSO**：員工以工號 + 密碼登入，後端代理至內部 LDAP API（避免 CORS）
- **資料隔離**：翻譯記錄 & 會議紀錄以工號作 namespace 儲存於 `localStorage`，員工只看自己的資料
- **Session 持久化**：重整頁面自動恢復登入，無需重新輸入密碼

### 📄 文件翻譯（版面保留）
- **版面偵測**：使用 **DocLayout-YOLO（DocStructBench 模型）**，針對各種文件類型 fine-tuned，精準偵測各類版面區塊
- **Formula 保護**：自動識別數學公式並跳過翻譯，避免破壞公式內容
- **版面保真**：翻譯結果直接覆寫至原始 PDF，保留表格、欄位、圖片位置
- **精準抹除**：使用 PyMuPDF **Redaction API** 從 PDF content stream 永久移除原文（非視覺遮蓋），消除透明殘留
- **自適應縮放**：`insert_htmlbox` 自動調整字型大小，防止譯文溢出
- **在地推論**：由 **gpt-oss:20b**（Ollama）驅動，支援英語 ↔ 繁體中文

### 🎙️ 語音文字轉換 & 會議摘要
- **高精度辨識**：`faster-whisper large-v3`，接近人工級別的中文辨識準確率
- **智能摘要**：自動萃取**決策事項**、**待辦事項**、**討論摘要**
- **格式化匯出**：一鍵下載 Word（`.docx`）會議紀錄，跨重整後仍可下載
- **資料持久化**：Word 二進制檔案儲存於 IndexedDB，重整頁面後下載連結自動恢復

---

## 🏗️ 系統架構

| 元件 | 技術 | 職責 |
| :--- | :--- | :--- |
| **Frontend** | Next.js 16 + React 19 + TailwindCSS v4 | 使用者儀表板 |
| **Backend** | FastAPI (Python 3.10) + Uvicorn | API 閘道 |
| **Auth** | httpx → LDAP API 代理 | 員工 SSO |
| **Layout 偵測** | DocLayout-YOLO（DocStructBench） | 文件版面分析 |
| **STT** | faster-whisper large-v3（CUDA 12.1） | 語音辨識 |
| **LLM** | Ollama（gpt-oss:20b） | 翻譯 & 會議分析 |
| **前端儲存** | localStorage + IndexedDB | 使用者資料隔離 & PDF 持久化 |
| **部署** | Docker（GPU）+ PM2（Next.js） | 生產環境 |

---

## 🚀 快速啟動

### 前置需求
- **硬體**：NVIDIA GPU（建議 24GB+ VRAM）
- **軟體**：Docker + NVIDIA Container Toolkit + Ollama
- **模型準備**：
  ```bash
  ollama pull gpt-oss:20b
  ```

### 啟動後端（Docker）
```bash
git clone <repo-url>
cd File-Translation-STT-Service
docker compose up -d --build
```

### 啟動前端（PM2）
```bash
cd frontend
npm install
npm run build
pm2 start ecosystem.config.js
pm2 save && pm2 startup
```

- **API Docs**：`http://localhost:8000/docs`
- **Dashboard**：`http://localhost:3000`

---

## ⚙️ 環境變數（`.env`）

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=gpt-oss:20b
FORCE_CPU=false
DOCLAYOUT_MODEL_PATH=/app/models/layout/doclayout_yolo_docstructbench_imgsz1024.pt
```

---

## 🧠 PDF 翻譯 Pipeline

```
頁面 → YOLO 版面偵測 → 篩選可翻譯區塊 → Two-Pass NMS → Wipe（Redaction）→ LLM 翻譯 → Render
```

### 1. 版面偵測（DocLayout-YOLO DocStructBench）
- 頁面以 3x zoom（216 DPI）渲染成 numpy array 傳入 YOLO（`imgsz=1024, conf=0.2`）
- 偵測 10 類區塊：`title / plain text / abandon / figure / figure_caption / table / table_caption / table_footnote / isolate_formula / formula_caption`
- `Figure`、`Table`、`Formula` 標示為保護區，**不翻譯、不擦除**

### 2. Two-Pass NMS 去重
- **Pass 1**：移除「容器殼」（面積被 ≥2 個子區塊覆蓋 ≥60% 的大框）
- **Pass 2**：標準重疊去重（被已保留區塊覆蓋 >80% 則捨棄）

### 3. Wipe 階段（Redaction API）
- 搜尋 bbox ± 3pt 內的文字 span，取其自然聯集作為擦除範圍
- `page.add_redact_annot` → `page.apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=False)`
- 真正從 content stream 移除原文，保留向量圖形與表格邊框

### 4. Render 階段（insert_htmlbox）
- `insert_htmlbox` + 自適應 CSS（`scale_low=0.1`）
- 保留原始字重、顏色、對齊方式

---

## 📝 License
Developed by the 全一電子 AI Team.
