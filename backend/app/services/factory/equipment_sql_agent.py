from typing import Dict, Any, List
from .sql_tools import FactorySqlTools
import datetime

class EquipmentSqlAgent:
    """
    負責處理「設備檢索」上下文的 PostgreSQL 工具調用，將自然語言轉為特定設備分析。
    """
    
    def __init__(self, llm_service):
        self.llm = llm_service
        self.tools = FactorySqlTools()
        
    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        給 LLM 理解我們有哪些可用的工具 (設備專區)。
        這可以提供給相容 OpenAI Tool Calling 的模型使用。
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_active_equipment",
                    "description": "[設備檢索] 獲取當前有哪些設備正在跨線支援或正在稼動。可指定日期。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "查詢的日期字串，格式為 YYYY-MM-DD，若無提供可略。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_location",
                    "description": "[設備檢索] 根據設備名稱關鍵字搜尋設備的安裝位置/樓層。適用於『成型機在哪裡』、『XX機裝在哪』等位置查詢問題。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string", "description": "設備名稱關鍵字，例如 '成型機'、'真空泵'、'SMT' 等。"}
                        },
                        "required": ["keyword"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_by_floor",
                    "description": "[設備檢索] 根據安裝地點樓層獲取設備配置資料，例如查詢 1F 有哪些成型機。如果是 SMT，樓層為 '3F'。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {"type": "string", "description": "樓層名稱，例如 '1F', '3F', '4F' 等。"}
                        },
                        "required": ["floor"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_production_status",
                    "description": "[設備檢索] 獲取指定日期的所有生產設備的總結運行狀況，包含 RUN、DOWN 時間以及良率、進度等。【注意：此工具不含工單號碼，若需查工單號碼或生產機種，請改用 get_equipment_downtime_stats】",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "查詢的日期字串，格式為 YYYY-MM-DD。若無提供可用今天。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_failure_trend",
                    "description": "[設備檢索] 設備故障趨勢，依據時間範圍抓取各設備的故障次數與代碼，可用來分析「哪台設備故障最多次」或「某段時間的故障分布」。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {"type": "string", "description": "查詢的開始日期字串，包含這一天，格式為 YYYY-MM-DD。"},
                            "end_date": {"type": "string", "description": "查詢的結束日期字串，包含這一天，格式為 YYYY-MM-DD。"}
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_downtime_stats",
                    "description": "[設備檢索] 設備深入停機時間統計，包含 RUN/IDEL/DOWN/SHUTDOWN 各項具體數値、故障次數、良率、標準產能，以及【工單號碼 (WORK_ORDER_NO)】與生產機種資訊。若用戶需要查詢工單號碼、昨天/今天正在生產的機種，必須使用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {"type": "string", "description": "查詢的開始日期字串，包含這一天，格式為 YYYY-MM-DD。"},
                            "end_date": {"type": "string", "description": "查詢的結束日期字串，包含這一天，格式為 YYYY-MM-DD。"}
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_production_line_count",
                    "description": "查詢廠內產線數量（產線 ≠ 設備，產線是報工用的邏輯線別，設備是實體機台）。若問「某樓有幾條產線」，傳入 floor 參數；若問「全廠共幾條產線」或「各樓層分佈」，不傳 floor。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {"type": "string", "description": "樓層編號，例如 '1'、'3'、'4'。不傳此參數則回傳全廠分佈。"}
                        }
                    }
                }
            },
        ]

    async def execute_task(self, question: str) -> str:
        """Alias for compatibility with router agent."""
        return await self.chat(question)

    async def chat(self, question: str, history: List[Dict[str, str]] = None) -> str:
        """
        支援上下文記憶的聊天接口。
        """
        current_date_info = f"目前的系統日期是 {datetime.date.today().isoformat()}。"
        
        system_prompt = f"""你是一個專業的製造業數據分析專家，負責處理「全一電子」的**設備專用數據**。
你的任務是根據使用者的問題，調用 PostgreSQL 工具來獲取即時設備數據，並給出詳細、專業且易懂的分析回覆。

{current_date_info}

數據源提示：
此模式為【設備檢索】模式，資料庫聚焦在機台底層（如 SMT、成型機）的 MQTT 收集訊號，以及設備靜態配置。

規範：
1. **設備查詢調用**：
   - 詢問「XX設備/機台在哪裡」、「安裝位置」，調用 `get_equipment_location`（用設備名稱關鍵字模糊搜尋）。
   - 詢問設備配置、樓層機台（例：「1F 有哪些設備？」），調用 `get_equipment_by_floor`。
   - 詢問「工廠總共有幾條產線、各樓有幾條產線」（產線 ≠ 設備，產線是報工用的逻輯線别），調用 `get_production_line_count`。
   - 詢問設備一般生產狀態、稼動狀態、良率、進度，調用 `get_equipment_production_status`（注意：不含工單號碼）。
   - 詢問設備故障趨勢，調用 `get_equipment_failure_trend`。
   - 詢問設備深入停機各項時間統計 (RUN/IDEL/DOWN)、原因、**工單號碼、生產機種**，調用 `get_equipment_downtime_stats`。
   - 當用戶詢問『當前有哪些設備正在跨線支援/稼動』，調用 `get_active_equipment`。
   
2. **查無資料處理機制 (極重要)**：如果工具回傳的結果為空 (例如 `data` 陣列長度為 0)，**嚴格禁止暴露後端變數結構**。
   - 請婉轉地回答：「目前設備系統中查無相關數據。可能該樓層或指定時間區間內機台尚未回傳訊號，或無故障停機紀錄。」

3. **嚴格禁止憑對話記憶回答產線數據 (防幻覺最高指導)**：只要使用者提及特定的機台狀態或數據，**必須、立刻調用 SQL 工具向資料庫拉取最新數據**。若未去資料庫調用工具，不准給出具體數量結論。

4. **回答風格**：有數據時，以 Markdown 表格呈現並重點解說亮點（例如佔比最高的停機原因），並且使用親切口吻。請使用繁體中文。
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
            print(f"[Equipment SQL Agent Error] {e}")
            return f"抱歉，在查詢資料庫時發生錯誤：{str(e)}"
