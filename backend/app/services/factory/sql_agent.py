from typing import Dict, Any, List
from .sql_tools import FactorySqlTools

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
            {
                "type": "function",
                "function": {
                    "name": "get_production_overview",
                    "description": "取得日期的產線開工總覽：包含開工線數、正在生產的工單號碼、機種。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "查詢日期，例如 '2026-03-17'。不傳代表今日。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_workorder_quantity",
                    "description": "獲取工單目標生產數量(WORK_ORDER_NUM)與現在實際生產數量(ACTUAL_PRO)。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "查詢日期，例如 '2026-03-17'。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_line_defect_records",
                    "description": "獲取特定日期的產線不良品詳細紀錄明細。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "例如 '2026-03-17'。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_defect_pareto_analysis",
                    "description": "針對特定工單進行不良品 Pareto 分析（含佔比與累積百分比）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "work_order": {"type": "string", "description": "工單號碼，如 'N511-2512150027'"},
                            "target_date": {"type": "string", "description": "例如 '2026-03-17'。"}
                        },
                        "required": ["work_order"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_downtime_cause_analysis",
                    "description": "針對特定工單進行停機原因分析（含類別、責任單位、占比）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "work_order": {"type": "string", "description": "工單號碼，如 'N511-2512150027'"},
                            "target_date": {"type": "string", "description": "例如 '2026-03-17'。"}
                        },
                        "required": ["work_order"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_daily_status",
                    "description": "取得設備(Postgres)的狀態(RUN/DOWN/IDEL)統計明細與良率。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "equipment_code": {"type": "string", "description": "機台代號，例如 '94135B'"},
                            "target_date_dash": {"type": "string", "description": "日期，格式必須為 'YYYY-MM-DD'"}
                        },
                        "required": ["equipment_code", "target_date_dash"]
                    }
                }
            }
        ]

    async def execute_task(self, question: str) -> str:
        """
        處理 SQL 類問題：
        1. 呼叫 LLM (附帶 Tools Schema) 判斷要使用哪個工具。
        2. 若 LLM 選擇呼叫工具，則執行本地的 self.tools.x_func()。
        3. 將取得的資料回傳給 LLM 組合最終答案。
        """
        print(f"[SQL Agent] Planning SQL extraction for: {question}")
        
        # TODO: 結合 Ollama/OpenAI 的 Function Calling
        # 這裡會：
        #   resp = await self.llm.chat_with_tools([message], tools=self._get_tool_schemas())
        #   if resp.has_tool_call:
        #       tool_args = resp.tool_call.arguments
        #       data = getattr(self.tools, resp.tool_call.name)(**tool_args)
        #       ...
        
        return "這是一個模擬的回傳：3F 產線今日的稼動率為 85%。"
