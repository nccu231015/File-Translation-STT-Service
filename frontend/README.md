# 🖼️ AI Dashboard：文件翻譯 & 語音摘要

全一電子 AI 助手前端介面，基於 **Next.js 16 + React 19 + TailwindCSS v4 + Radix UI**。

## 🔐 身份驗證 & 使用者隔離

### SSO 登入（LDAP）
- 使用者以**工號 + 密碼**登入，透過 FastAPI 後端代理至 LDAP API（避免 CORS）
- 登入成功後，`{ username, name, dpt }` 存入 `localStorage('user_session')`，重整頁面自動恢復
- 登出清除 session 並回到登入頁

### 每位使用者資料隔離

所有記錄以 `username` 作 namespace：

| 記錄類型 | localStorage Key |
|---|---|
| PDF 翻譯 metadata | `translation_files_${username}` |
| PDF binary（原始）| IndexedDB `${id}_original` |
| PDF binary（翻譯後）| IndexedDB `${id}_translated` |
| 語音會議記錄 | `meeting_records_${username}` |
| Word 文件 binary | IndexedDB `${id}_docx` |

不同員工登入後自動載入各自的記錄，`useRef` 機制防止切換使用者時的 React effect race condition。

---

## 🚀 功能介面

### 1. 文件翻譯
- 拖放 PDF 上傳、目標語言選擇、版面保留翻譯
- **持久化**：原始 PDF 與翻譯後 PDF 均存入 IndexedDB，重整頁面後可繼續預覽/下載
- **直連後端**：`lib/api/translation.ts` → `NEXT_PUBLIC_API_URL/pdf-translation`（無 Next.js 中轉，無 timeout 風險）

### 2. 語音摘要（會議模式）
- 上傳音訊 → STT → LLM 分析 → 展示決策事項 / 待辦事項 / 摘要
- **Word 下載持久化**：`.docx` 二進制存入 IndexedDB，重整頁面後下載按鈕自動恢復
- **直連後端**：`lib/api/stt.ts` → `NEXT_PUBLIC_API_URL/stt`（mode=meeting）

---

## 📐 前端架構

```
RootLayout
├── UserProvider         ← localStorage('user_session')
│   ├── TranslationProvider  ← localStorage + IndexedDB（PDF）
│   │   └── VoiceProvider    ← localStorage + IndexedDB（Word）
│   │       └── {pages}
```

### API 層（`lib/api/`）
| 檔案 | 呼叫端點 | 使用者 |
|------|---------|--------|
| `lib/api/translation.ts` | `POST /pdf-translation` | TranslationContext |
| `lib/api/stt.ts` | `POST /stt` | VoiceContext |

兩個模組均**直接呼叫後端**（瀏覽器端 fetch），不經過 Next.js Route Handler，沒有 timeout 問題。

---

## 🛠️ 開發模式
```bash
cd frontend
npm install
npm run dev
```

## 🐳 生產部署（PM2）
```bash
npm run build
pm2 start ecosystem.config.js
pm2 save && pm2 startup
```

## 📁 環境變數（`.env.production`）
```env
NEXT_PUBLIC_API_URL=http://<backend-ip>:8000
```
