from typing import Dict, Any, List
from .sql_tools import FactorySqlTools
import datetime

class SqlAgent:
    """
    負責接收來自 Router Agent 交辦的問題，並透過呼叫 LLM 的 Tool/Function Calling，
    將用戶以自然語言表達的查詢條件轉換為我們定義的 SQL Tool API 參數。
    一旦取得 API 的回傳數據，它會將結構化的 JSON 資料轉換成親切合理的自然語言回覆。
    """
    
    def __init__(self, llm_service):
        self.llm = llm_service
        self.tools = FactorySqlTools()
        
    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        給 LLM 理解我們有哪些可用的工具 (A 類與 B 類)。
        這可以提供給相容 OpenAI Tool Calling 的模型使用。
        """
        return [
            # ── Q1: Real-time floor / line utilization status ─────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_line_operation_status",
                    "description": (
                        "【稼動狀態】查詢各樓層/所有產線的即時開工/停工狀態，呈現綠燈(開工)/紅燈(停工)，"
                        "並統計每樓層的稼動率 (RUN / [RUN+DOWN])。"
                        "適用於：『目前各樓層產線稼動狀態？』、『全廠有幾條產線開工？』。"
                        "若使用者指定樓層，傳入 floor；否則回傳全廠分層匯總。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {"type": "string", "description": "樓層編號，例如 '3'。不傳則回傳全廠。"},
                            "target_date": {"type": "string", "description": "查詢日期，例如 '2026-04-01'。預設今天。"}
                        }
                    }
                }
            },

            # ── Q2: Active lines + models for a specific floor ────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_floor_active_lines",
                    "description": (
                        "【指定樓層】查詢該樓層各條產線的開工/停工狀態，以及目前正在生產的機種與工單號碼。"
                        "回傳兩張表：(1) 產線狀態表（含綠/紅燈）；(2) 開工機種表。"
                        "適用於：『3 樓目前有幾條產線開工？』、『3 樓在生產什麼機種？』。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {"type": "string", "description": "樓層編號，例如 '3'。必填。"},
                            "target_date": {"type": "string", "description": "查詢日期，例如 '2026-04-01'。預設今天。"}
                        },
                        "required": ["floor"]
                    }
                }
            },

            # ── Q3: Work orders lagging behind schedule ───────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_lagging_workorders",
                    "description": (
                        "【工單落後】找出今日達成率低於目標的所有工單，標示落後嚴重度（🔴嚴重/<70%、🟡輕微/<90%）。"
                        "含對應產線號、機種、目標數量、實際產量，按達成率由低到高排序（最差的排前面）。"
                        "適用於：『哪些工單進度落後？』、『落後的工單在哪些產線？』。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "查詢日期，預設今天。"},
                            "threshold": {"type": "number", "description": "落後判斷門檻，預設 1.0 (100%)。"},
                            "limit": {"type": "integer", "description": "最多回傳幾筆，預設 50。"}
                        }
                    }
                }
            },

            # ── Q4: Production lines with high defect rates ───────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_high_defect_lines",
                    "description": (
                        "【高不良率產線】找出今日（或近 N 天）不良比例最高的產線，"
                        "計算公式：不良率 = 總不良數 / 總產量，由高到低排序。"
                        "適用於：『哪些產線不良比例特別高？』、『今天不良率前幾名的產線是？』。"
                        "若需比對歷史平均，請改用 get_defect_rate_anomaly_report。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "基準日期，預設今天。"},
                            "lookback_days": {"type": "integer", "description": "回溯天數，1=只看今天，7=近7天滾動，預設 1。"},
                            "limit": {"type": "integer", "description": "顯示筆數，預設 15。"}
                        }
                    }
                }
            },

            # ── Q5: Production quantity + defect rate trend with chart ─────────────
            {
                "type": "function",
                "function": {
                    "name": "get_production_trend_data",
                    "description": (
                        "【產量 & 不良率趨勢圖】查詢指定時間範圍內某條產線或某機種的產量與不良率時序資料，"
                        "同時回傳可直接渲染的圖表設定 (chart_config)：Bar Chart 呈現產量、Line Chart 呈現不良率，雙 Y 軸。"
                        "適用於：月對月(M-o-M)、年對年(Y-o-Y)、季對季(Q-o-Q)、某時間區間中每日/每週趨勢比對。"
                        "granularity 參數：daily(每日) | weekly(每週) | monthly(每月) | quarterly(每季) | yearly(每年)。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {"type": "string", "description": "查詢起始日期，例如 '2025-01-01'。"},
                            "end_date":   {"type": "string", "description": "查詢結束日期，例如 '2026-04-01'。"},
                            "line_no":    {"type": "string", "description": "產線號碼，例如 '136'。選填。"},
                            "model":      {"type": "string", "description": "機種名稱，例如 'M3820'。選填。"},
                            "granularity": {
                                "type": "string",
                                "enum": ["daily", "weekly", "monthly", "quarterly", "half_yearly", "yearly"],
                                "description": "時間粒度。daily=每日 | weekly=每週 | monthly=月對月 | quarterly=季對季 | half_yearly=上下半年(1H/2H) | yearly=年對年。預設 monthly。"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },

            # ── Q6: Single work order progress check (Y / N) ──────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_workorder_progress_check",
                    "description": (
                        "【單一工單進度確認】輸入工單號碼，回傳該工單是否落後（Y/N），"
                        "附帶嚴重度（🟢正常/🟡輕微落後/🔴嚴重落後）以及具體的生產改善建議。"
                        "適用於：『工單 N511-2512150027 進度落後嗎？』。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "work_order_no": {"type": "string", "description": "工單號碼，例如 'N511-2512150027'。必填。"},
                            "target_date":   {"type": "string", "description": "查詢日期，不填則查所有日期的累積資料。"}
                        },
                        "required": ["work_order_no"]
                    }
                }
            },

            # ── Q7: Defect rate fluctuation ranking with multi-line chart ──────────
            {
                "type": "function",
                "function": {
                    "name": "get_defect_rate_fluctuation_data",
                    "description": (
                        "【不良率波動排行 & 圖表】分析各機種在指定期間的不良率最高/最低值與波動幅度，"
                        "排行波動最大的機種，並回傳可直接渲染的多線折線圖 (chart_config)，每條線代表一個機種。"
                        "適用於：『哪些機種不良率波動最大？』、'M-o-M/Q-o-Q/Y-o-Y/1H-2H 不良率比對'，以及特定時間區間中每日或每週的波動比對。"
                        "granularity：daily(每日) | weekly(每週) | monthly(月對月) | quarterly(季對季) | half_yearly(上下半年1H/2H) | yearly(年對年)。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "end_date":    {"type": "string", "description": "分析截止日，預設今天。"},
                            "granularity": {
                                "type": "string",
                                "enum": ["daily", "weekly", "monthly", "quarterly", "half_yearly", "yearly"],
                                "description": "時間粒度：daily(每日) | weekly(每週) | monthly(月對月) | quarterly(季對季) | half_yearly(上下半年1H/2H) | yearly(年對年)。預設 quarterly。"
                            },
                            "periods":  {"type": "integer", "description": "要回溯幾個週期，例如 4 季，預設 4。"},
                            "limit":    {"type": "integer", "description": "最多顯示幾個機種，預設 10。"}
                        }
                    }
                }
            },

            # ── Q8: Defect quantity trend + cause ranking ─────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_defect_cause_analysis",
                    "description": (
                        "【不良趨勢 & 主因分析】查詢指定產線或機種在某時間區間內的不良數量趨勢，"
                        "回傳可渲染的雙 Y 軸折線圖（左軸=不良數量，右軸=不良率%），"
                        "同時列出不良主因（bllt 不良型態）前 N 大排行，並標示發生日期的集中性。"
                        "適用於：『某產線近一個月的不良主因是什麼？』、『這個機種最近不良數量哪天最多？』。"
                        "可只傳 line_no（僅查產線）或只傳 model（僅查機種），不需同時提供。"
                        "追問場景：若使用者未重新指定條件，請沿用對話中最近一次出現的產線/機種/日期。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date":  {"type": "string", "description": "查詢起始日期，例如 '2026-03-01'。不傳預設為 end_date 往前 30 天。"},
                            "end_date":    {"type": "string", "description": "查詢截止日期，例如 '2026-04-13'。不傳預設今天。"},
                            "line_no":     {"type": "string", "description": "產線號，例如 '302'。與 model 至少擇一傳入。"},
                            "model":       {"type": "string", "description": "機種名稱，例如 'M3820'。與 line_no 至少擇一傳入。"},
                            "granularity": {
                                "type": "string",
                                "enum": ["daily", "weekly", "monthly"],
                                "description": "趨勢圖時間粒度：daily=每日(預設) | weekly=每週 | monthly=每月。"
                            },
                            "top_n": {"type": "integer", "description": "不良主因顯示前幾大，預設 5，可設為 3。"}
                        }
                    }
                }
            },

        ]

    async def execute_task(self, question: str) -> str:
        """Alias for compatibility with router agent."""
        return await self.chat(question)

    async def chat(self, question: str, history: List[Dict[str, str]] = None) -> dict:
        """
        支援上下文記憶的聊天接口。
        Returns: {"response": str, "chart_config": dict | None}
        """
        current_date_info = f"目前的系統日期是 {datetime.date.today().isoformat()}。"
        
        system_prompt = f"""你是一個專業的製造業數據分析專家，服務於「全一電子」。
你的任務是根據使用者的問題，調用適當的 SQL 工具來獲取即時生產數據，並給出詳細、專業且易懂的分析回覆。

{current_date_info}

數據源提示：
- [Daily_Status_Report]：開工總覽、產量、績效排行與工單報表細節。欄位包含：NO(產線), jz(機種), WORK_ORDER_NO(工單), ACTUAL_PRO(實際產量), WORK_ORDER_NUM(目標數), ACHIEVING_RATE(達成率), NG_NUM(不良數), REJECT_RATE(不良率小數)。注意：BAD_PRO_RATE 欄位資料全為0，請勿使用。
- [Scx_base]：全廠產線主檔 (scx_no=產線號, scx_value=產線名稱, lc=樓層)。判斷停工必須以此表為基準。
- [blpjl_new_copy1]：詳細的不良項目與異常碼統計。
- [tjsjjl_new_copy1]：專業停機紀錄統計表。

工具路由規範：

1. **即時稼動狀態 (Q1)**：
   - 詢問「各樓層/全廠產線稼動狀態、開工/停工、稼動率」→ 必定調用 `get_line_operation_status`。
   - 回覆時，依據 floor_summary 呈現各樓層匯總表，再依 line_detail 呈現逐條產線狀態；「狀態燈」欄位值為 RUN/STOP，呈現時轉換：RUN → 🟢 開工、STOP → 🔴 停工。

2. **指定樓層產線數量與機種 (Q2)**：
   - 詢問「X 樓目前開工幾條、X 樓在生產什麼機種、X 樓的工單狀況」→ 必定調用 `get_floor_active_lines(floor=X)`。
   - 回覆時，使用 line_status_table（產線狀態表）與 active_model_table（機種表）分別呈現兩張 Markdown 表格；「狀態燈」欄位值為 RUN/STOP，呈現時轉換：RUN → 🟢 開工、STOP → 🔴 停工。

3. **工單進度落後 (Q3)**：
   - 詢問「哪些工單落後、哪些產線進度有問題、落後工單清單」→ 調用 `get_lagging_workorders`。
   - 回覆時，「落後嚴重度」欄位的值為 CRITICAL / MILD / NEAR，呈現時請轉換：CRITICAL → 🔴 嚴重落後、MILD → 🟡 輕微落後、NEAR → 🟡 接近達標，依達成率由低至高呈現。

4. **高不良率產線 (Q4)**：
   - 詢問「哪些產線不良比例高、不良率排行、異常比例」→ 優先調用 `get_high_defect_lines`。
   - 若使用者需要「與歷史比較的異常偏差」→ 再調用 `get_defect_rate_anomaly_report`。

5. **產量與不良率趨勢圖 (Q5)**：
   - 詢問「某機種/某產線的月對月、季對季、年對年、每日/每週/某時間區間的產量與不良率趨勢」→ 調用 `get_production_trend_data`。
   - granularity 對應：月對月=monthly、季對季=quarterly、半年對半年(1H/2H)=half_yearly、年對年=yearly、每日=daily、每週=weekly。
   - **圖表回覆規範**：回覆中必須提及「圖表資料已就緒，請參考隨附的 chart_config（Bar=產量, Line=不良率, 雙 Y 軸）」。同時以 Markdown 表格呈現 data 欄位的時序數據。

6. **單一工單進度確認 (Q6)**：
   - 使用者給出工單號碼，詢問「這張工單有沒有落後」→ 調用 `get_workorder_progress_check`。
   - 回覆必須包含：(a) Y/N 答案 (b) 嚴重度燈號，「是否落後」欄位值為 ON_TRACK / MILD_BEHIND / SEVERE_BEHIND，呈現時轉換：ON_TRACK → 🟢 正常、MILD_BEHIND → 🟡 輕微落後、SEVERE_BEHIND → 🔴 嚴重落後 (c) 具體的生產改善建議（直接從 recommendation 欄位呈現）。

7. **機種不良率波動排行 (Q7)**：
   - 詢問「哪些機種不良率波動最大、本季與上季比對、M-o-M/Q-o-Q/Y-o-Y/1H-2H 波動、某時間區間每日或每週波動」→ 調用 `get_defect_rate_fluctuation_data`。
   - granularity 對應：月對月=monthly、季對季=quarterly、半年對半年(1H/2H)=half_yearly、年對年=yearly、每日=daily、每週=weekly。
   - **重要規範**：除非使用者明確指定數量，否則**一律強制設定 `limit=5`**。
   - **圖表回覆規範**：回覆中必須提及「圖表已就緒（柱狀代表各機種產量，折線代表不良率）。為保持介面簡潔，圖例僅顯示折線項」。同時以 Markdown 表格呈現排行榜。

8. **不良趨勢 & 主因分析 (Q8)**：
   - 詢問「某產線/某機種近一個月/某時間區間的不良數量趨勢、不良主因前幾大」→ 調用 `get_defect_cause_analysis`。
   - **追問場景（極重要）**：若使用者已在上一輪指定過產線/機種/日期，但本輪未重新說明，請**直接沿用前一輪的條件**帶入工具參數，嚴禁空白呼叫。
   - 回覆時必須包含：(a) 說明「趨勢圖已就緒（雙 Y 軸折線：左軸=不良數量，右軸=不良率 %）」；(b) 以 Markdown 表格呈現不良主因排行，並說明集中性標示意義（⚠️集中發生=短期爆發需追查，🔴持續發生=長期問題需改善）。

9. **查無資料處理（極重要）**：如果工具回傳 data 為空，**嚴禁暴露後端變數或說「data 為空陣列」**。
    請婉轉回答：「目前系統中查無今日相關數據。可能原因：1. 現場尚未完成即時報工；2. 請確認查詢日期或工單範圍是否正確。」

10. **防幻覺最高指令**：
    - **嚴禁憑對話記憶回答具體數值**，必須即時調用工具向資料庫查詢。
    - 當工具回傳 TOP N 排行時，絕對不可宣稱「全廠只有 N 條產線/N 個工單」。
    - 達成率標準：`1.0 = 100%` 為完全達標，不可自行降低門檻。

11. **回覆風格**：
    - 有數據時：以 Markdown 表格呈現，適當加入🟢🔴🟡燈號，提供專業解說。
    - 有圖表時：說明「圖表設定已隨資料回傳（chart_config 欄位），前端可直接用 Recharts 或 Chart.js 渲染」。
    - **嚴禁**在回覆中出現「data 陣列」、「回傳結果」、「欄位顯示」、「系統參數」等技術術語。
    - 以「資深工廠主管的口吻」對話，正確範例：「目前 3 樓共有 12 條產線，其中 9 條開工、3 條停工，稼動率為 75%。」
"""
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history[-10:]:
                messages.append({"role": h["role"], "content": h["content"]})
        
        messages.append({"role": "user", "content": question})

        try:
            result = await self.llm.chat_with_tools(
                messages=messages,
                tools=self._get_tool_schemas(),
                tool_executor_obj=self.tools
            )
            response_text = self.llm.s2tw.convert(result["response"])
            return {"response": response_text, "chart_config": result.get("chart_config")}
        except Exception as e:
            print(f"[SQL Agent Error] {e}")
            return {"response": f"抱歉，在查詢資料庫時發生錯誤：{str(e)}", "chart_config": None}
