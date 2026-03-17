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
        system_prompt = """你是一個製造業智能問答系統的請求路由器。
請分析使用者的問題，決定該交由哪一個子系統處理：

1. SQL 查詢服務 (route: "SQL")：
   負責處理結構化數據的統計、計算、狀態與清單。例如：
   - 「今日產線開工狀況？」
   - 「N511 工單的生產進度？」
   - 「哪些設備現在閃紅燈？」
   - 「查詢特定的良率、稼動率資料」

2. RAG 知識庫服務 (route: "RAG")：
   負責處理非結構化的「為什麼」與「如何做」知識。例如：
   - 「為什麼設備會閃紅燈？」
   - 「異常代碼 A006 的處理方法？」
   - 「產品表面刮傷的排除指引是什麼？」

判斷規則：
- 若涉及具體的數字、狀態、清單、日期統計 -> 選 SQL。
- 若涉及故障排除、成因分析、操作指引 -> 選 RAG。

請嚴格回傳以下 JSON 格式：
{
    "route": "SQL" 或 "RAG",
    "reason": "你的判斷理由",
    "intent": "使用者想知道的核心資訊"
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
            return {"route": "SQL", "reason": "Error routing, fallback to SQL", "intent": "unknown"}
