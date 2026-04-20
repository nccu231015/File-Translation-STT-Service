from typing import Dict, Any, List
from .sql_tools import FactorySqlTools
import datetime

class EquipmentSqlAgent:
    """
    負責處理「設備檢索」上下文的工具調用，將自然語言轉為 7 種設備分析功能：
      EQ-A: 各樓層設備即時稼動狀態
      EQ-B: 良率未達標設備（紅色標記）
      EQ-C: 指定樓層設備稼動燈號與稼動率
      EQ-D: 特定設備生産機種不良率趨勢（Bar+Line）
      EQ-E: 停機時數異常排行 Top-N（Pareto）
      EQ-F: 設備故障原因分布比較（兩期間對比）
      EQ-G: 故障原因熱點圖（設備 × 故障原因 Heat Map）
    """

    def __init__(self, llm_service):
        self.llm   = llm_service
        self.tools = FactorySqlTools()

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            # ── EQ-A ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_operation_status",
                    "description": (
                        "[設備] 查詢各樓層設備的即時稼動狀態。"
                        "按樓層與設備類型分組，呈現 RUN/DOWN 分鐘數、稼動率、良品數、不良數、良率。"
                        "可選擇指定樓層（如 '3F'）或查全廠。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {
                                "type": "string",
                                "description": "樓層，例如 '1F'、'3F'、'4F'。不傳則查全廠。"
                            },
                            "target_date": {
                                "type": "string",
                                "description": "查詢日期，格式 YYYY-MM-DD。不傳則用今天。"
                            }
                        }
                    }
                }
            },
            # ── EQ-B ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_underperforming_equipment",
                    "description": (
                        "[設備] 找出良率未達標的設備（預設門檻：80%）。"
                        "良率 = 良品數 / (良品數 + 不良數) × 100。"
                        "回傳達標狀態燈號（🔴未達標），含資料日期。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {
                                "type": "string",
                                "description": "查詢日期，格式 YYYY-MM-DD。不傳則用今天。"
                            },
                            "threshold": {
                                "type": "number",
                                "description": "良率門檻（百分比），預設 80.0。"
                            }
                        }
                    }
                }
            },
            # ── EQ-C ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_floor_equipment_status",
                    "description": (
                        "[設備] 查詢指定樓層各設備的即時稼動狀態、RUN/DOWN 時間及當日良率。"
                        "回傳稼動燈號（🟢RUN/🔴DOWN/🟡IDEL/⚫SHUTDOWN）、最新狀態碼與稼動率。"
                        "稼動率 = RUN分 / (RUN分 + DOWN分) × 100%。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {
                                "type": "string",
                                "description": "必填。樓層，例如 '1F'、'3F'、'4F'。"
                            },
                            "target_date": {
                                "type": "string",
                                "description": "查詢日期，格式 YYYY-MM-DD。不傳則用今天。"
                            }
                        },
                        "required": ["floor"]
                    }
                }
            },
            # ── EQ-D ─────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_model_production_trend",
                    "description": (
                        "[設備] 查詢特定設備在時間區間內生產了哪些機種，以及各機種的"
                        "產量與不良率趨勢。可用設備代碼（如 '94135B'）或設備名稱關鍵字"
                        "（如 '成型機A'）指定設備。"
                        "可選回傳 bar_line_combo 圖表（透過 include_chart 參數控制）。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "查詢開始日期，格式 YYYY-MM-DD。"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "查詢結束日期，格式 YYYY-MM-DD。"
                            },
                            "equipment_code": {
                                "type": "string",
                                "description": "設備代碼（SBMC/TOPIC），例如 '94135B'。與 equipment_name 擇一。"
                            },
                            "equipment_name": {
                                "type": "string",
                                "description": "設備名稱關鍵字，例如 '成型機A'。系統會模糊比對。與 equipment_code 擇一。"
                            },
                            "granularity": {
                                "type": "string",
                                "description": (
                                    "時間粒度：'daily'（每日）、'weekly'（每週）、"
                                    "'monthly'（月對月）、'quarterly'（季對季）、'yearly'（年對年）。"
                                    "預設 'monthly'。"
                                )
                            },
                            "include_chart": {
                                "type": "boolean",
                                "description": "是否需要畫圖/產生圖表配置？單純詢問「生產了哪些機種」設為 false。除非使用者明確詢問「不良比例、走勢」或要求「畫圖/產生圖表」，才設為 true。"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            # ── EQ-E ─────────────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_downtime_anomaly_ranking",
                    "description": (
                        "[EQ-E] 查詢指定期間內狀態時數前 N 名的設備（Pareto），"
                        "帶有各設備停機時數明細（DOWN-only：A001/A006-A009 計入停機）。"
                        "支援迴視期間：30天/一季/半年等。"
                        "可篩選樓層，帶樓層位置資訊。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "查詢開始日期 YYYY-MM-DD。"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "查詢結束日期 YYYY-MM-DD。"
                            },
                            "top_n": {
                                "type": "integer",
                                "description": "回傳前 N 名，預設 10。"
                            },
                            "floor": {
                                "type": "string",
                                "description": "指定樓層（如 '3F'），省略則查全廠。"
                            },
                            "include_chart": {
                                "type": "boolean",
                                "description": "是否產生 Pareto 圖表配置，預設 false。"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            # ── EQ-F ─────────────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_fault_pattern_comparison",
                    "description": (
                        "[EQ-F] 比較兩個期間的設備停機原因分佈，適用於："
                        "【此季對上季】【上半年對下半年】等對比分析。"
                        "可鎖定到特定設備、樓層或全廠。"
                        "回傳各原因停機時數對比表 + 趨勢標記。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "period_a_start": {
                                "type": "string",
                                "description": "期間A 開始日 YYYY-MM-DD。"
                            },
                            "period_a_end": {
                                "type": "string",
                                "description": "期間A 結束日 YYYY-MM-DD。"
                            },
                            "period_b_start": {
                                "type": "string",
                                "description": "期間B 開始日 YYYY-MM-DD。"
                            },
                            "period_b_end": {
                                "type": "string",
                                "description": "期間B 結束日 YYYY-MM-DD。"
                            },
                            "period_a_label": {
                                "type": "string",
                                "description": "期間A 顯示名稱，如 '本季'、'2026 Q1'、'上半年'。"
                            },
                            "period_b_label": {
                                "type": "string",
                                "description": "期間B 顯示名稱，如 '上季'、'2025 Q4'、'下半年'。"
                            },
                            "equipment_code": {
                                "type": "string",
                                "description": "鎖定特定設備代碼，省略則分析全廠/指定樓層。"
                            },
                            "equipment_name": {
                                "type": "string",
                                "description": "鎖定特定設備名稱關鍵字。"
                            },
                            "floor": {
                                "type": "string",
                                "description": "鎖定樓層（如 '3F'），省略則全廠。"
                            },
                            "include_chart": {
                                "type": "boolean",
                                "description": "是否產生分組柱狀圖表配置，預設 false。"
                            }
                        },
                        "required": ["period_a_start", "period_a_end", "period_b_start", "period_b_end"]
                    }
                }
            },
            # ── EQ-G ─────────────────────────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_fault_heatmap",
                    "description": (
                        "[EQ-G] 產生設備故障原因熱點圖（Heat Map），"
                        "X 軸 = 設備名稱，Y 軸 = 具體故障原因（NOTE），"
                        "儲格色階 = 發生次數（白→深紅）。"
                        "適用於：「哪台設備跟哪種故障最相關」「故障熱點圖」「特定設備的故障原因分佈」。"
                        "查詢特定設備時必須傳 equipment_code 或 equipment_name。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "開始日期 YYYY-MM-DD。"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "結束日期 YYYY-MM-DD。"
                            },
                            "equipment_code": {
                                "type": "string",
                                "description": "設備代碼（如 '64008A'）或設備編號（如 '401'）。查詢特定設備時必填，填此參數就不要填 floor。"
                            },
                            "equipment_name": {
                                "type": "string",
                                "description": "設備名稱關鍵字（如 '焊接機501'）。查詢特定設備時可用，填此參數就不要填 floor。"
                            },
                            "floor": {
                                "type": "string",
                                "description": "樓層篩選（如 '3F'），僅在使用者問整層樓時使用；查詢特定設備請勿填此欄位。"
                            },
                            "top_n_equipment": {
                                "type": "integer",
                                "description": "X 軸顯示的設備數，全廠查詢時預設 8；指定設備時自動忽略。"
                            },
                            "top_m_notes": {
                                "type": "integer",
                                "description": "Y 軸顯示的故障原因數，全廠查詢時預設 10；指定設備時自動擴展。"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
        ]

    @staticmethod
    def _get_period_info() -> str:
        """
        Pre-compute date boundaries for ALL comparison period types.
        Covers: monthly (M-o-M), quarterly (Q-o-Q), half-yearly (1H/2H), yearly (Y-o-Y).
        Returns a formatted string for injection into the system prompt.
        Any currently in-progress period is flagged with elapsed days and percentage.
        """
        import calendar
        today = datetime.date.today()
        y, m = today.year, today.month

        def _last(yr: int, mo: int) -> datetime.date:
            # Return the last calendar day of a given year-month
            return datetime.date(yr, mo, calendar.monthrange(yr, mo)[1])

        def _status(start: datetime.date, full_end: datetime.date) -> str:
            # Return a completion-status label for a period
            elapsed = (today - start).days + 1
            total   = (full_end - start).days + 1
            pct     = round(elapsed / total * 100, 1)
            if today >= full_end:
                return "✅ 完整期間"
            return f"⚠️ 尚未結束，已過 {elapsed}/{total} 天（{pct}%）"

        # ── Monthly (M-o-M) ──────────────────────────────────────────────
        cur_mo_s  = datetime.date(y, m, 1)
        cur_mo_f  = _last(y, m)
        pmy, pmm  = (y, m - 1) if m > 1 else (y - 1, 12)
        prev_mo_s = datetime.date(pmy, pmm, 1)
        prev_mo_f = _last(pmy, pmm)

        # ── Quarterly (Q-o-Q) ────────────────────────────────────────────
        cur_q    = (m - 1) // 3 + 1
        cur_q_s  = datetime.date(y, (cur_q - 1) * 3 + 1, 1)
        cur_q_f  = _last(y, cur_q * 3)
        pq       = cur_q - 1 if cur_q > 1 else 4
        pqy      = y if cur_q > 1 else y - 1
        prev_q_s = datetime.date(pqy, (pq - 1) * 3 + 1, 1)
        prev_q_f = cur_q_s - datetime.timedelta(days=1)

        # ── Half-yearly (1H / 2H) ────────────────────────────────────────
        if m <= 6:
            cur_h_lbl, cur_h_s, cur_h_f       = f"1H {y}",     datetime.date(y, 1, 1),     datetime.date(y, 6, 30)
            prev_h_lbl, prev_h_s, prev_h_f    = f"2H {y - 1}", datetime.date(y - 1, 7, 1), datetime.date(y - 1, 12, 31)
        else:
            cur_h_lbl, cur_h_s, cur_h_f       = f"2H {y}",     datetime.date(y, 7, 1),     datetime.date(y, 12, 31)
            prev_h_lbl, prev_h_s, prev_h_f    = f"1H {y}",     datetime.date(y, 1, 1),     datetime.date(y, 6, 30)

        # ── Yearly (Y-o-Y) ───────────────────────────────────────────────
        cur_yr_s  = datetime.date(y, 1, 1)
        cur_yr_f  = datetime.date(y, 12, 31)
        prev_yr_s = datetime.date(y - 1, 1, 1)
        prev_yr_f = datetime.date(y - 1, 12, 31)

        lines = [
            "【時間段邊界（調用工具時必須嚴格依此設定 start_date / end_date）】",
            f"▸ 月對月 (M-o-M)",
            f"  本月  {y}-{m:02d}: {cur_mo_s} ～ {today}  {_status(cur_mo_s, cur_mo_f)}",
            f"  上個月 {pmy}-{pmm:02d}: {prev_mo_s} ～ {prev_mo_f}  ✅ 完整期間",
            f"▸ 季對季 (Q-o-Q)  [Q1=1~3月, Q2=4~6月, Q3=7~9月, Q4=10~12月]",
            f"  本季  Q{cur_q} {y} : {cur_q_s} ～ {today}  {_status(cur_q_s, cur_q_f)}",
            f"  上一季 Q{pq} {pqy}: {prev_q_s} ～ {prev_q_f}  ✅ 完整期間",
            f"▸ 上下半年 (1H/2H)  [1H=1~6月, 2H=7~12月]",
            f"  本半年 {cur_h_lbl}: {cur_h_s} ～ {today}  {_status(cur_h_s, cur_h_f)}",
            f"  對比期 {prev_h_lbl}: {prev_h_s} ～ {prev_h_f}  ✅ 完整期間",
            f"▸ 年對年 (Y-o-Y)",
            f"  今年 {y}   : {cur_yr_s} ～ {today}  {_status(cur_yr_s, cur_yr_f)}",
            f"  去年 {y - 1}: {prev_yr_s} ～ {prev_yr_f}  ✅ 完整期間",
            "",
            "⚠️ 不完整時間段必須聲明（強制規則）：凡涉及標記「⚠️ 尚未結束」的時間段，",
            "  回答時【必須】在開頭主動說明：(1) 尚未結束、已涵蓋天數與百分比；",
            "  (2) 與對比完整期間屬不對等比較，總量偏低為正常；",
            "  (3) 建議以【日均值】或【不良率/良率】評估真實趨勢，而非直接比較總量。",
        ]
        return "\n".join(lines)

    async def execute_task(self, question: str) -> Dict[str, Any]:
        """Alias for compatibility with router agent."""
        return await self.chat(question)

    async def chat(self, question: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """支援上下文記憶的聊天接口，回傳與 SqlAgent 格式一致的 dict。"""
        today_str = datetime.date.today().isoformat()
        current_date_info = f"目前的系統日期是 {today_str}。\n\n{self._get_period_info()}"

        system_prompt = f"""你是一個專業的製造業數據分析專家，負責處理「全一電子」的**設備專用數據**。
你的任務是根據使用者的問題，調用資料庫工具來獲取即時設備數據，並給出詳細、專業且易懂的分析回覆。

{current_date_info}

【數據源說明】
此模式為【設備檢索】模式，資料來自設備 MQTT 信號（PostgreSQL）及生產記錄（MSSQL）。

【追問規則（重要）】
- 對話有記憶：history 包含最近 10 輪對話，回答問題前請先參考 history 中是否已提及設備名稱/代碼/樓層/時間範圍
- 若使用者的問題指代不明（如「它現在幾點了」、「這台設備呢」、「那個的狀況」），且 history 中有足夠的上下文，**直接沿用前一輪的設備/時間條件**，不要重新詢問
- 若 history 也沒有足夠線索，**必須追問確認**，例如：「請問您是指哪一台設備？（例如：熔接機501、3樓某台設備）」，不要臆測調用工具
- **缺少時間範圍時必須追問（最高優先級）**：若使用者的問題屬於歷史趨勢/排行/分析類（例如含有「趨勢」「波動」「排行」「比對」「分析」「主因」「停機原因」「近…」「這段時間」「哪些…最」等語意），需要 start_date / end_date 才能查詢，且使用者既未提及任何時間詞（本月/本季/近N天/上半年/今年/具體起迄日期 等），history 中也沒有可直接沿用的時間線索，**嚴禁自行假設日期後直接調用工具**，必須先追問：「請問您想查詢的時間範圍是？（例如：本月、本季、近 30 天、或指定起迄日期）」
  此規則適用於所有需要時間區段的情境，無論問的是產線還是設備。

【工具調用規範】
1. 詢問「各樓層設備生產數、不良數、良率、稼動率概況」→ 調用 `get_equipment_operation_status`
   - 全廠：不傳 floor；指定樓層：傳入 floor（如 '3F'）
   - 必須含資料日期
   - `機型` 欄為設備分類群組，請以此欄位進行分組後呈現，讓表格更易閱讀
   - `生產數` = 良品數，`不良數` = 不良品數，可合併呈現為「產出(良/不良)」格式
   - 顯示 `RUN(分)` / `DOWN(分)` / `稼動率(%)`；稼動率 = RUN / (RUN + DOWN)

2. 詢問「哪些設備達成率/良率未達標、低於80%、未達標」→ 調用 `get_underperforming_equipment`
   - threshold 預設 80.0（即良率 < 80% 標記為紅色）
   - 回覆需包含 🔴 燈號說明

3. 詢問「某樓層設備現在狀態、稼動率、RUN/DOWN 時間」 → 調用 `get_floor_equipment_status`
   - floor 為必填（如 '3F'）
   - 回傳稼動燈號（🟢RUN/🔴DOWN/🟡IDEL/⚫SHUTDOWN）、最新狀態碼（原始 CODE）
   - 回傳 RUN(分) / DOWN(分)，稼動率 = RUN / (RUN + DOWN) × 100%

4. 詢問「某設備今天/這段時間生産了哪些機種、機種的不良率走勢、設備生産趨勢」 → 調用 `get_equipment_model_production_trend`
   - equipment_code 或 equipment_name 擇一提供
   - 時間範圍：今天 = start_date=end_date=今天；近30天 = 往前30天；本月/本季/上季/本半年/今年等**依上方時間段邊界計算**（₠ 標記「⚠️ 尚未結束」者必須聲明不完整比較）
   - granularity 對應：月對月=monthly、季對季=quarterly、每日=daily、每週=weekly、年對年=yearly
   - **回傳欄位 `qty_data_available` 判斷規則（必須嚴格遵守）**：
     - `qty_data_available=true`：正常顯示產量統計（良品、不良品、良率等）
     - `qty_data_available=false`：**絕對不可顯示產量統計**，只顯示 `model_names` 機種清單，並說明「產量數據目前不可用」
   - **`model_qty_data` 欄位使用規則**：
     - 若回傳中 `model_qty_data` 不為空（即 `[]` 以外），**優先使用 `model_qty_data` 顯示各機種的總產量、良品數、不良數、良率、不良率**
     - `model_qty_data` 為工單層級的 MSSQL 備援資料（Daily_Status_Report 來源），當 CIM 即時資料不可用時自動填充
     - 此時 `qty_data_available=true` 但 `trend_data=[]`，請以 `model_qty_data` 取代時序趨勢表格
   - 若使用者只問「生産了哪些機種」，重點輸出 `model_names` 清單，不需強調產量數字

5. 詢問「哪些設備停機時間異常過長、停機確 Top-N、停機主因」 → 調用 `get_downtime_anomaly_ranking`
   - 時間範圍按個別話展開：近30天/本月/本季/上季/本半年等**依上方時間段邊界計算**（⚠️ 標記尚未結束者必須聲明不完整比較）
   - top_n 預設 10，使用者指定則跟上
   - **include_cause 判斷規則（極其重要，必須嚴格遵守）**：
     - 只要提問中出現以下任意關鍵字：`原因`、`主因`、`為什麼`、`為何`、`why`、`cause`、`怎麼了`、`哪裡出問題` → **無條件設 `include_cause=True`**，不論是否同時詢問排名
     - 典型範例（以下全部必須 include_cause=True）：「停機原因為何」、「停機主因是什麼」、「為什麼一直停機」、「哪台停最久以及為什麼」
     - 僅詢問時間排名且完全沒有上述關鍵字（如「哪些設備停最久」「停機 Top-10」）→ `include_cause=False`
   - `include_cause=False` 回傳欄位：`排名`、`樓層`、`設備(代碼)`、`停機時數(h)`
   - `include_cause=True` 額外回傳欄位：`主要停機原因`（由 B-code 與 DOWN 事件同秒共現推斷）

6. 詢問「比較兩個時期的停機原因/故障趨勢是否改善」等**使用者明確要求對比兩個不同期間**的查詢（如「本季 vs 上季」「上半年對下半年」）→ 調用 `get_fault_pattern_comparison`
   - **⚠️ 重要判斷**：僅在使用者清楚提到兩個期間時才使用此工具；若使用者只詢問「故障有沒有規律」「故障分布」「哪種故障最常出現」等**未明確要求兩期間對比**的問題，請改用 EQ-G（`get_fault_heatmap`）
   - period_a 和 period_b 均為必填，常見用法：本季對上季、上半年對下半年；日期必須依上方時間段邊界設定
   - **⚠️ 若 period_a 或 period_b 涉及「⚠️ 尚未結束」的時間段，必須在回覆開頭聲明不完整比較（參照上方時間段邊界說明），並以日均發生次數輔助評估**
   - 可鎖定設備（equipment_code/equipment_name）、樓層（floor）或全廠
   - **`include_chart` 預設 True**，工具會回傳分組長條圖（`chart_type='bar_line_combo'`），X 軸為故障原因，紅色 = 期間A、藍色 = 期間B
   - 回傳 `comparison` 表格：`故障原因`、`{{期間A}}(次)`、`{{期間B}}(次)`、`變化(次)`、`趨勢`；有工具回傳 chart_config 時前端會自動渲染，你只需說明「紅色長條為期間A、藍色長條為期間B，高度代表故障發生次數」
   - top_n 預設 15，可依使用者需求調整

7. 詢問「故障熱點圖/heat map/哪台設備跟哪種故障最相關」，或**未明確指定兩個期間對比**的「故障原因分布/故障有沒有規律/哪種故障最多/單一期間故障模式分析」→ 調用 `get_fault_heatmap`
   - 需提供時間範圍
   - **使用者指定特定設備**（如「設備401」「WELD3C的故障」）→ 必須傳 `equipment_code` 或 `equipment_name`，不要傳 floor；此時工具會自動展開所有故障原因（不截斷）
   - 使用者指定樓層 → 傳 `floor`；全廠查詢 → 可選填 top_n_equipment（預設8）、top_m_notes（預設10）
   - 回傳 chart_config（chart_type='heatmap'），前端會自動渲染熱點色階圖
   - 請說明：「X 軸為設備名稱、Y 軸為故障原因、儲格色越深表示發生次數越多」

【回覆格式規範】
- **全程使用繁體中文**，絕對禁止輸出英文句子，禁止使用「產線」一詞（本模式為「設備」專區）
- **強制要求**：不論資料筆數多寡，**必須且務必將工具回傳的 `data` 陣列完整輸出成 Markdown 表格**。你可以提供總結文字，但**絕對不准省略表格**！
- 燈號說明：🟢=RUN（稼動中），🔴=DOWN（停機），🟡=IDEL（閒置），⚫=SHUTDOWN（關機）；EQ-B 良率未達標亦以 🔴 表示
- 圖表（EQ-D）回覆注意：工具回傳含 `model_names`（機種清單）、`trend_data`（時序資料）、`summary`（總計）、`chart_config`（圖表配置）、`gdhm_available`（工單號是否存在）。**當使用者僅詢問「生產哪些機種」時，絕對不要畫圖**，只列出 `model_names` 及 `summary` 即可。只有當使用者明確詢問「不良比例/走勢/趨勢」或要求「畫圖/產生圖表」時，才使用 `chart_config` 回傳圖表（`include_chart=true`）。有產出圖表時需說明「柱狀圖代表該設備總產量（左軸），折線代表不良率（右軸）」，時序標籤依 granularity 設定。**若 `gdhm_available=false`，代表該設備在設備資料表中尚未設定工單對應（GDHM 為空），無法查詢機種名稱，請如實告知：「該設備尚未建立工單對應，無法查詢機種資料，但產量與良率數據正常可用。」**
- 格式清理：表格中若出現 `null` 數值，請自動轉換為 `0`；若「稼動率(%)」為 `null`，請顯示為 `-`，別讓畫面看起來一團亂。
- 禁止暴露程式術語（如 data 陣列、SQL 欄位名稱等）
- 查無資料時，婉轉說明：「目前設備系統尚未回傳相關數據，可能機台尚未開機或該日無生產記錄。」

【欄位顯示規則（🚨極其重要：避免表格過寬破版🚨）】
- 為了適應聊天視窗，**強烈要求精簡 Markdown 表格的欄位數（最多 5~6 欄為主）**。
- 務必將「設備名稱」與「設備代碼」合併為一欄「設備 (代碼)」，例如 `WELD2A (502-1)`。
- 將「良品數量」與「不良數量」合併為一欄「產出 (良/不良)」，例如 `100 / 2`。
- 若詢問「設備概況/EQ-A」：表格只需顯示 `樓層`、`機型`、`設備(代碼)`、`RUN(分)`、`DOWN(分)`、`稼動率(%)`。稼動率 = RUN / (RUN + DOWN)。
- 若詢問「指定樓層設備狀態/EQ-C」：表格只需顯示 `設備(代碼)`、`稼動狀態`、`RUN(分)`、`DOWN(分)`、`稼動率(%)`、`良率(%)`。稼動狀態已翻譯（🟢RUN/🔴DOWN/🟡IDEL/⚫SHUTDOWN），最新狀態碼為原始 CODE 可另行說明。
- 若詢問「達標/良率」：只顯示 `樓層`、`設備(代碼)`、`產出(良/不良)`、`良率(%)`、`狀態燈`。
- 若詢問「停機排名/EQ-E」：僅問時間時表格顯示 `排名`、`樓層`、`設備(代碼)`、`停機時數(h)`；若一併問原因則加上 `主要停機原因` 欄位（B-code 同秒共現推斷）。停機時數只計 DOWN 代碼（A001/A006-A009）。
- 若詢問「故障分布比較/EQ-F」：先渲染分組長條圖（chart_config 已包含），再用 `comparison` 建立「故障原因比對表」，欄位為 `故障原因`、`{{期間A}}(次)`、`{{期間B}}(次)`、`變化(次)`、`趨勢`；趨勢欄位保留 ⬆ 惡化 / ⬇ 改善 / ─ 持平標記。圖表說明：「紅色長條 = 期間A，藍色長條 = 期間B，高度代表故障發生次數」。
- 若詢問「故障熱點圖/EQ-G」：當工具回傳 chart_config.chart_type='heatmap' 時，前端將自動渲染熱點圖。你只需在文字中說明「X 軸為設備、Y 軸為故障原因，儲格顏色越深代表該設備此故障發生次數越多」，並點出前幾名熱點組合即可。
- 「資料日期」只需在總結文字中提及一次即可，**絕對禁止**放進表格中成為獨立欄位！

【稼動率計算說明】
- 稼動率 = RUN(分) / (RUN(分) + DOWN(分)) × 100%
- 代碼對照：RUN=A003，DOWN=A001/A006/A007/A008/A009，IDEL=A002/A011-A014，SHUTDOWN=A004/A010
- 最新狀態碼為設備最後一筆訊號 CODE，已依上述對照轉換為 RUN/DOWN/IDEL/SHUTDOWN 燈號顯示
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
            print(f"[Equipment SQL Agent Error] {e}")
            return {"response": f"抱歉，在查詢設備資料庫時發生錯誤：{str(e)}", "chart_config": None}
