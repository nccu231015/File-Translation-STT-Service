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
                    "name": "get_line_downtime_records",
                    "description": "獲取特定日期的產線停機詳細紀錄明細（包含備註與類別）。",
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
                    "name": "get_equipment_by_floor",
                    "description": "按樓層查詢生產設備分佈與資訊。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "floor": {"type": "string", "description": "樓層名稱，例如 '1F'、'2F-1'。"}
                        },
                        "required": ["floor"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_active_equipment",
                    "description": "獲取當前或特定日期有在生產（稼動）的機台代號清單。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {"type": "string", "description": "格式為 'YYYYMMDD'，如 '20260317'。不傳則預設今日。"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_daily_status",
                    "description": "取得特定設備(機台)在指定日期的運作狀態(RUN/DOWN/IDEL)統計明細與良率。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "equipment_code": {"type": "string", "description": "機台代號，例如 '94135B'"},
                            "target_date_dash": {"type": "string", "description": "日期，格式必須為 'YYYY-MM-DD'"}
                        },
                        "required": ["equipment_code", "target_date_dash"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_equipment_downtime_summary",
                    "description": "分析特定時間範圍內的設備故障趨勢、故障碼與停機次數排行。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date_num": {"type": "string", "description": "開始日期 'YYYYMMDD'"},
                            "end_date_num": {"type": "string", "description": "結束日期 'YYYYMMDD'"}
                        },
                        "required": ["start_date_num", "end_date_num"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_kpi_ranking",
                    "description": "獲取產線設備的績效排行(KPI Ranking)，用於找出業績最優或最差的機種。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kpi_type": {
                                "type": "string", 
                                "enum": ["top_achieving", "lagging", "abnormal", "downtime", "unachieved"],
                                "description": "排行類型：'top_achieving'(業績達標前10)、'lagging'(業績最落後前10)、'abnormal'(不良率最高前10)、'downtime'(停機最久前10)、'unachieved'(達成率未過半)。"
                            },
                            "target_date": {"type": "string", "description": "例如 '2026-03-17'。"}
                        },
                        "required": ["kpi_type"]
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
        history: [{'role': 'user', 'content': '...'}, {'role': 'assistant', 'content': '...'}]
        """
        # 今天的日期語境
        current_date_info = f"目前的系統日期是 {datetime.date.today().isoformat()}。"
        
        system_prompt = f"""你是一個專業的製造業數據分析專家，服務於「全一電子」。
你的任務是根據使用者的問題，調用適當的 SQL 工具來獲取即時生產數據，並給出詳細、專業且易懂的分析回覆。

{current_date_info}

規範：
1. 若數據中包含良率、稼動率、工單數量，請以「網格表格(Markdown)」呈現。
2. 當使用者詢問「最好」、「最差」、「業績分析」或「排名」時：
   - 如果 'get_production_overview' 的回傳數據不足，請主動嘗試使用 'get_kpi_ranking' 工具。
   - 應優先從數據中計算每個機種的出現頻次或加總產量，給出具體的數值排名，不要只列出清單。
3. 若查詢結果為空，請告知使用者該時段可能無生產記錄，或請調低查詢的時間精度。
4. 請始終保持回覆的專業性，並在對話中考慮 history 中提到的上下文。
5. 所有的回覆必須使用「繁體中文」。
6. 回答請保持精簡、準確，除非必要，否則不需要畫蛇添足提供一般性管理建議。
"""
        
        # 組合 Messages：System + History + Current Question
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            # 只取最近 10 則對話避免長度超出限制
            for h in history[-10:]:
                messages.append({
                    "role": h["role"],
                    "content": h["content"]
                })
        
        messages.append({"role": "user", "content": question})

        try:
            # 呼叫 LLM 進行工具決策與答案聚合
            answer = await self.llm.chat_with_tools(
                messages=messages,
                tools=self._get_tool_schemas(),
                tool_executor_obj=self.tools
            )
            
            # 使用 OpenCC 確保最終回傳為繁體
            return self.llm.s2tw.convert(answer)

        except Exception as e:
            print(f"[SQL Agent Error] {e}")
            return f"抱歉，在查詢資料庫時發生錯誤：{str(e)}"
