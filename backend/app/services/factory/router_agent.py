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
        根據使用者的問題，決定路由方式與所需提取的實體(Entity)。
        返回 JSON 格式：{"route": "SQL" | "RAG", "reason": "...", "intent": "..."}
        """
        prompt = f"""請以路由管理員身份，分析以下使用者問題：
「{question}」

這是一個製造業的智能問答系統，我們有兩套知識來源：
1. SQL 查詢庫 (route: "SQL")：
   負責處理統計、計算、狀態與清單。例如：
   「今日 3F SMT 的稼動率？」、「94135B 這台機台的工單號碼？」、「哪些設備今天有停機？」

2. RAG 知識庫 (route: "RAG")：
   負責處理「為什麼 (Why)」與「如何做 (How)」。例如：
   「設備閃紅燈怎麼辦？」、「異常代碼 A006 是什麼故障？」、「馬達過熱該如何排除？」

若問題同時包含兩者（例如：為什麼今天3F產量沒達標？），若是想看數據選 SQL，想看維修指引選 RAG。

請嚴格以 JSON 格式回傳（不要加上 ```json 標籤）：
{{
    "route": "SQL" 或 "RAG",
    "reason": "你的判斷理由",
    "intent": "使用者想知道的核心資訊"
}}
"""
        
        # 假設調用 llm 服務
        try:
            # 這裡呼叫系統共用的 LLM
            # response = await self.llm.ask(prompt)
            # return json.loads(response)
            
            # TODO: 替換為實際的 LLM 呼叫
            print(f"[Router Agent] Routing question: {question}")
            return {"route": "SQL", "reason": "預設模擬", "intent": "測試"}
            
        except Exception as e:
            print(f"[Router Agent] Error during routing: {e}")
            return {"route": "UNKNOWN", "reason": str(e), "intent": "UNKNOWN"}
