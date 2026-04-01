from typing import Dict, Any, List
from .sql_tools import FactorySqlTools
import datetime

class EquipmentSqlAgent:
    """
    負責處理「設備檢索」上下文的工具調用，將自然語言轉為 4 種設備分析功能：
      EQ-A: 各樓層設備即時稼動狀態
      EQ-B: 良率未達標設備（紅色標記）
      EQ-C: 指定樓層設備稼動燈號與稼動率
      EQ-D: 特定設備生產機種不良率趨勢（Bar+Line）
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
                        "按樓層與設備類型分組，呈現良品數、不良數、良率、資料日期。"
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
                        "[設備] 查詢指定樓層的設備總數與稼動狀態。"
                        "按設備類型分組，顯示即時狀態燈號（🟢稼動中/🔴停機/🟡閒置/⚫關機）"
                        "與稼動率 = RUN / (RUN + DOWN)。"
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
        ]

    async def execute_task(self, question: str) -> Dict[str, Any]:
        """Alias for compatibility with router agent."""
        return await self.chat(question)

    async def chat(self, question: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """支援上下文記憶的聊天接口，回傳與 SqlAgent 格式一致的 dict。"""
        current_date_info = f"目前的系統日期是 {datetime.date.today().isoformat()}。"

        system_prompt = f"""你是一個專業的製造業數據分析專家，負責處理「全一電子」的**設備專用數據**。
你的任務是根據使用者的問題，調用資料庫工具來獲取即時設備數據，並給出詳細、專業且易懂的分析回覆。

{current_date_info}

【數據源說明】
此模式為【設備檢索】模式，資料來自設備 MQTT 信號（PostgreSQL）及生產記錄（MSSQL）。

【工具調用規範】
1. 詢問「各樓層設備稼動狀態、生產數、不良數」→ 調用 `get_equipment_operation_status`
   - 全廠：不傳 floor；指定樓層：傳入 floor（如 '3F'）
   - 必須含資料日期

2. 詢問「哪些設備達成率/良率未達標、低於80%、未達標」→ 調用 `get_underperforming_equipment`
   - threshold 預設 80.0（即良率 < 80% 標記為紅色）
   - 回覆需包含 🔴/🟢 燈號說明

3. 詢問「某樓層設備有幾台在稼動、設備稼動率、開工/停工狀態」→ 調用 `get_floor_equipment_status`
   - floor 為必填（如 '3F'）
   - 回覆需包含總台數、稼動台數、停機台數、稼動率

4. 詢問「某設備今天/這段時間生產了哪些機種、機種的不良率走勢、設備生產趨勢」→ 調用 `get_equipment_model_production_trend`
   - equipment_code 或 equipment_name 擇一提供
   - 時間範圍：今天 = start_date=end_date=今天；近30天 = 往前30天；本季/半年依此計算
   - granularity 對應：月對月=monthly、季對季=quarterly、每日=daily、每週=weekly、年對年=yearly

【回覆格式規範】
- **全程使用繁體中文**，絕對禁止輸出英文句子，禁止使用「產線」一詞（本模式為「設備」專區）
- **強制要求**：不論資料筆數多寡，**必須且務必將工具回傳的 `data` 陣列完整輸出成 Markdown 表格**。你可以提供總結文字，但**絕對不准省略表格**！
- 燈號說明：🟢=稼動/達標，🔴=停機/未達標，🟡=閒置，⚫=關機
- 圖表（EQ-D）回覆注意：**當使用者僅詢問「生產哪些機種」時，絕對不要畫圖（不要輸出 Echarts JSON）。只有當使用者明確詢問「不良比例/走勢/趨勢」或要求畫圖時，才能產生圖表 JSON。** 有產出圖表時需提及「柱狀圖代表各機種產量（左軸），折線代表不良率（右軸）」。
- 格式清理：表格中若出現 `null` 數值，請自動轉換為 `0`；若「稼動率(%)」為 `null`，請顯示為 `-`，別讓畫面看起來一團亂。
- 禁止暴露程式術語（如 data 陣列、SQL 欄位名稱等）
- 查無資料時，婉轉說明：「目前設備系統尚未回傳相關數據，可能機台尚未開機或該日無生產記錄。」

【欄位顯示規則】
- 使用者只詢問「稼動率」時：表格只顯示 樓層、設備代碼、設備名稱、RUN(分)、DOWN(分)、IDEL(分)、SHUTDOWN(分)、稼動率(%)、資料日期。不要出現良品數量、不良數量、良率。
- 使用者只詢問「良率」或「達成率」時：表格只顯示 樓層、設備代碼、設備名稱、良品數量、不良數量、良率(%)、狀態燈、資料日期。不要出現稼動率相關欄位。
- 使用者同時詢問兩者，或詢問「稼動狀態」、「整體狀態」時：顯示全部欄位。

【稼動率計算說明】
稼動率 = RUN(分) / (RUN(分) + DOWN(分)) × 100%
RUN = CODE='A003' 的信號區間加總；DOWN = CODE 為 A001/A006~A009 的區間加總
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
