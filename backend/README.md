# 🐍 AI Backend：文件翻譯 & 語音智能

FastAPI 驅動的 AI 引擎，提供版面保留 PDF 翻譯與語音轉文字兩大核心服務。

## 🔐 驗證

### `POST /api/login`
代理員工帳密至公司 LDAP 伺服器，回傳使用者身份。

**Request：**
```json
{ "username": "P0001196", "password": "****" }
```
**Response（成功）：**
```json
{ "username": "P0001196", "name": "王小明", "dpt": "業務部" }
```
**Response（失敗）：** HTTP 401

---

## 🚀 核心模組

### 1. PDF 版面保留翻譯（`app/services/`）

呼叫鏈：`pdf_service.py` → `pdf_layout_service.py` → `pdf_layout_detector_yolo.py`

#### 版面偵測（`pdf_layout_detector_yolo.py`）
- **模型**：DocLayout-YOLO **DocStructBench** fine-tuned 版本
  - HF Repo：`juliozhao/DocLayout-YOLO-DocStructBench`
  - 模型檔：`doclayout_yolo_docstructbench_imgsz1024.pt`（專為各種文件類型設計）
- 頁面以 **3x zoom**（216 DPI）渲染成 numpy array 傳入 YOLO
- 推論參數：`imgsz=1024, conf=0.2, iou=0.30`（官方 demo.py 預設值）
- 偵測 10 類區塊：`title / plain text / abandon / figure / figure_caption / table / table_caption / table_footnote / isolate_formula / formula_caption`

#### 翻譯 Pipeline（`pdf_layout_service.py`）

**Phase 0 — 區塊候選篩選**

| 步驟 | 說明 |
|------|------|
| 保護區標記 | `Figure`、`Table`、`Formula` 標為保護區；與保護區重疊 >80% 的文字區塊捨棄 |
| Two-Pass NMS | **Pass 1**：移除容器殼（面積被 ≥2 子區塊覆蓋 ≥60%）。**Pass 2**：標準重疊去重（>80% 在已保留區塊內則捨棄） |

**Phase 1 — Wipe（Redaction API）**

1. 將 YOLO pixel bbox 轉換為 PDF point 座標
2. 在 `bbox ± 3pt` 內搜尋文字 span，取其**自然聯集**作為擦除範圍
3. `page.add_redact_annot` 登記擦除標記
4. `page.apply_redactions(images=PDF_REDACT_IMAGE_NONE, graphics=False)` — 從 content stream 永久移除原文，保留向量圖形

**Phase 2 — 翻譯 & Render**

- 每個區塊傳入 `gpt-oss:20b`（Ollama）進行翻譯（附頁面脈絡）
- `page.insert_htmlbox` + 自適應 CSS：保留原始字重、顏色、對齊

### 2. 語音處理（`app/services/stt_service.py`）
- **引擎**：`faster-whisper`（large-v3）
- **GPU 鎖定**：`threading.Lock()` 保護推論，`run_in_threadpool` 非阻塞執行

### 3. LLM 協調（`app/services/llm_service.py`）
- **模型**：gpt-oss:20b（Ollama）
- **會議分析**：Map-Reduce 策略，chunk_size=15000 字，輸出結構化 JSON
- **後處理**：OpenCC `s2tw` 確保輸出為繁體中文（台灣）

---

## 🛠️ 本地開發
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

## 🐳 Docker（生產）
```bash
docker compose up -d --build
```

## 📦 模型依賴
- **版面偵測**：DocLayout-YOLO DocStructBench（~41MB，Dockerfile 自動下載）
- **STT**：faster-whisper large-v3（首次請求時自動下載）
- **LLM**：gpt-oss:20b（需手動 `ollama pull gpt-oss:20b`）
