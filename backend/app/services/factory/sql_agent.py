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
            },
            {
                "type": "function",
                "function": {
                    "name": "get_defect_anomaly_report",
                    "description": "跨日不良異常分析：一次比對產線今日的不良數與過去 N 天的平均不良數，判斷是否發生異常飆高。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "目前的查詢日期，例如 '2026-03-24'。"},
                            "lookback_days": {"type": "integer", "description": "要回溯計算平均的天數，預設為 30。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_defect_rate_anomaly_report",
                    "description": "跨日『不良率』異常分析：跨表彙整總產出與不良數，一次比對產線今日的不良「率」與過去 N 天的平均不良「率」。適用於需要考慮總產量基準的情境。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "目前的查詢日期，例如 '2026-03-24'。"},
                            "lookback_days": {"type": "integer", "description": "要回溯計算平均的天數，預設為 7 或 30。"}
                        }
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
2. **明細紀錄與原因查詢**：
   - 詢問「不良紀錄明細、缺陷位置、Pareto」，請調用 `get_line_defect_records` 或 `get_defect_pareto_analysis`。
   - 詢問「停機紀錄明細、具體停機原因、責任單位分析」，請調用 `get_line_downtime_records` 或 `get_downtime_cause_analysis`。
3. **KPI 指標與異常排行 (關鍵)**：
   - 詢問「正在生產的工單清單、哪些機種開工、今日開工概況」，**必須**調用 `get_production_overview`。
   - 詢問「工單生產數量、目標數與實際數統計」，才調用 `get_workorder_quantity`。
   - 詢問「停機時間異常、誰停機最久、停機時間排行」，必須調用 `get_kpi_ranking(kpi_type='downtime')`。
   - 詢問「異常比例排行、誰不良最嚴重」，必須調用 `get_kpi_ranking(kpi_type='abnormal')`。
4. **異常趨勢與跨日比對**：
   - 當詢問「今天產線不良『數量』是否異常？」時，調用 `get_defect_anomaly_report`。
   - 當詢問「今天產線不良『率』是否異常？」或「把今天的平均不良率與最近7天的日均不良率作對比」時，**必須調用 `get_defect_rate_anomaly_report`**。
5. **查無資料處理機制 (極重要)**：如果工具回傳的結果為空 (長度為 0)、查無數據，或無法進行計算，**請直接簡潔回答「目前系統無相關資料可供查詢」即可**。絕對禁止回覆「內部工具代碼」、虛擬 Python 語法、內部函數名稱 (如 get_line_defect_records)，或向使用者解釋系統底層的「API 呼叫步驟」。
6. **禁止暴露系統內部邏輯**：永遠不要在回覆中向使用者展現你的思考過程、工具名稱、爬取步驟，不需要告訴使用者你打算怎麼拿到資料或怎麼算。
7. **禁止虛構**：資料源已鎖定，絕對不要自行撰寫 SQL 語句或瞎掰數據。
8. **回答風格**：有數據時，以 Markdown 表格呈現並提供專業解說。無數據時，簡短回答查無資料即可，不要過度解釋。
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
