import json
import asyncio
from typing import Dict, Any, List

class FactoryRouterAgent:
    """
    智能問答的請求路由器。
    透過 LLM 快速判定用戶提出的問題應交由哪一個子系統處理：
    1. SQL 查詢服務 (A、B 類數據查詢)
    2. RAG 知識庫服務 (C 類原因排查/手冊問答)
    """
    
    def __init__(self, llm_service):
        self.llm = llm_service

    async def route_question(self, question: str) -> Dict[str, str]:
        """
        Decide which agent should handle the question.
        Returns JSON: {"route": "SQL_EQ" | "SQL_PROD", "reason": "..."}
        """
        system_prompt = """你是一個製造業智能問答系統的請求路由器。
請分析使用者的問題，決定應交由哪一個子 Agent 處理：

1. 設備 Agent (route: "SQL_EQ")：
   負責處理一切與「設備本身」相關的問題。例如：
   - 「某台設備現在稼動狀態？」
   - 「哪些設備停機時間最長？」
   - 「熔接機501 近半年生産了哪些機種？」
   - 「設備 RUN/DOWN/稼動率/良率」
   - 「故障熱點圖、停機原因排行、兩期間故障比對」
   - 「某樓層所有設備狀態」

2. 產線 Agent (route: "SQL_PROD")：
   負責處理一切與「產線生產」相關的問題。例如：
   - 「今日產線開工狀況？」
   - 「N511 工單的生產進度？」
   - 「哪些工單落後？」
   - 「機種不良率趨勢」
   - 「某樓層開工幾條、生産什麼機種」
   - 「產量與不良率月對月/季對季走勢」

判斷規則：
- 問題核心是「特定機台/設備代碼/設備稼動/停機/故障」→ SQL_EQ
- 問題核心是「工單/產線/良率趨勢/生產進度/開工條數」→ SQL_PROD
- 無法判斷時預設 SQL_PROD

請嚴格回傳以下 JSON 格式：
{
    "route": "SQL_EQ" 或 "SQL_PROD",
    "reason": "你的判斷理由"
}"""
        
        try:
            messages = [{"role": "user", "content": f"問題：{question}"}]
            result = await self.llm.chat_json(messages, system_prompt=system_prompt)
            
            # 確保回傳結構完整
            if "route" not in result:
                result["route"] = "SQL" # 預設 fallback
            
            print(f"[Router Agent] Decision: {result['route']} | Reason: {result.get('reason')}")
            return result
            
        except Exception as e:
            print(f"[Router Agent] Error: {e}")
            return {"route": "SQL_PROD", "reason": "Error routing, fallback to SQL_PROD"}
