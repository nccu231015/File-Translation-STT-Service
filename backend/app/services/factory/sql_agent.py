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
            {
                "type": "function",
                "function": {
                    "name": "get_production_overview",
                    "description": "取得日期的產線開工總覽：包含開工線數(kgcx)、正在生產的工單號碼(distinct)、機種(distinct)。",
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
                    "name": "get_workorder_quantity",
                    "description": "獲取工單的『目標生產數量』(WORK_ORDER_NUM) 與 『現在實際生產數量』(ACTUAL_PRO)。",
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
                    "name": "get_kpi_ranking",
                    "description": "獲取各類績效前10名排行。可用於：進度達標(top_achieving)、落後(lagging)、異常(abnormal)、停機時間(downtime)、達成率未標(unachieved)。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kpi_type": {
                                "type": "string", 
                                "enum": ["top_achieving", "lagging", "abnormal", "downtime", "unachieved"],
                                "description": "排行類型。"
                            },
                            "target_date": {"type": "string", "description": "例如 '2026-03-17'。"}
                        },
                        "required": ["kpi_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_line_defect_records",
                    "description": "查詢【產線/樓層-不良數明細】。用於回答：2026-03-06 的不良數是多少？有哪些紀錄？",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "例如 '2026-03-06'。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_line_downtime_records",
                    "description": "查詢【產線/樓層-停機時間明細】。用於回答：2026-03-06 的停機時間、工單與備註紀錄。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "例如 '2026-03-06'。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_defect_pareto_analysis",
                    "description": "對特定工單進行【不良品 Pareto 趨勢分析】。包含檢查工序、不良型態、位置備註與累積百分比。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "work_order": {"type": "string", "description": "工單號碼，如 'N511-2512150027'"},
                            "target_date": {"type": "string", "description": "查詢日期，例如 '2026-03-06'。"}
                        },
                        "required": ["work_order"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_downtime_cause_analysis",
                    "description": "對特定工單進行【停機時間統計、原因分析】。包含停機類別、責任單位、占比與累積占比。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "work_order": {"type": "string", "description": "工單號碼，如 'N511-2512150027'"},
                            "target_date": {"type": "string", "description": "查詢日期，例如 '2026-03-06'。"}
                        },
                        "required": ["work_order"]
                    }
                }
            }
        ]

    async def execute_task(self, question: str) -> str:
        """Alias for compatibility with router agent."""
        return await self.chat(question)

    async def chat(self, question: str, history: List[Dict[str, str]] = None) -> str:
        """
        支援上下文記憶的聊天接口。
        """
        current_date_info = f"目前的系統日期是 {datetime.date.today().isoformat()}。"
        
        system_prompt = f"""你是一個專業的製造業數據分析專家，服務於「全一電子」。
你的任務是根據使用者的問題，調用適當的 SQL 工具來獲取即時生產數據，並給出詳細、專業且易懂的分析回覆。

{current_date_info}

數據源提示：
- [Daily_Status_Report]：開工總覽、產量、績效排行與工單報表細節。
- [blpjl_new_copy1]：詳細的不良項目與異常碼統計。
- [tjsjjl_new_copy1]：專業停機紀錄統計表。

規範：
1. **數值與紀錄查詢**：
   - 詢問「產線/樓層-不良數、明細、紀錄」，請調用 `get_line_defect_records`。
   - 詢問「產線/樓層-停機時間、紀錄、明細」，請調用 `get_line_downtime_records`。
2. **深度分析專區**：
   - 詢問「不良品統計、趨勢分析、Pareto、位置分佈」，請調用 `get_defect_pareto_analysis`。
   - 詢問「停機時間統計、原因分析、責任單位」，請調用 `get_downtime_cause_analysis`。
3. **基礎概覽與排行**：查詢今日開工數使用 `get_production_overview`；查排名使用 `get_kpi_ranking`。
4. **禁止虛構**：資料源已鎖定，絕對不要自行撰寫 SQL 語句。
5. 所有結果請以 Markdown 表格呈現，並提供 50~100 字專業分析。
"""
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history[-10:]:
                messages.append({"role": h["role"], "content": h["content"]})
        
        messages.append({"role": "user", "content": question})

        try:
            # 參數名稱 tool_executor_obj 必須與 llm_service.py 定義一致
            response = await self.llm.chat_with_tools(
                messages=messages,
                tools=self._get_tool_schemas(),
                tool_executor_obj=self.tools
            )
            return self.llm.s2tw.convert(response)
        except Exception as e:
            print(f"[SQL Agent Error] {e}")
            return f"抱歉，在查詢資料庫時發生錯誤：{str(e)}"
