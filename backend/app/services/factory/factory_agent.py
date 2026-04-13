from typing import List, Dict
from .router_agent import FactoryRouterAgent
from .sql_agent import SqlAgent
from .equipment_sql_agent import EquipmentSqlAgent

class FactoryAgentService:
    """
    智能問答的總調度員 (Orchestrator)。
    這是前端 API 所呼叫的唯一入口點。
    1. 接收 Request
    2. 交由 Router 判定是走 SQL 查詢或是 RAG 查詢
    3. 判斷前綴把 SQL 請求再分流為產線 SQL Agent 或 設備 SQL Agent
    4. 把結果整合並回傳給用戶
    Returns: {"response": str, "chart_config": dict | None}
    """
    
    def __init__(self, llm_service):
        self.router = FactoryRouterAgent(llm_service)
        self.sql_agent = SqlAgent(llm_service)
        self.equipment_sql_agent = EquipmentSqlAgent(llm_service)
        
    async def chat(self, user_question: str, history: List[Dict] = None) -> dict:
        """
        處理使用者的每一句話
        Returns: {"response": str, "chart_config": dict | None}
        """
        print(f"\n[Factory Agent] Received new question: '{user_question}'")
        
        # 判斷問題前綴
        is_equipment = "【設備】" in user_question
        
        # 移除前綴讓後續 Router 判斷意圖時不會被死板的關鍵字干擾
        clean_question = user_question.replace("【設備】", "").replace("【產線】", "").strip()
        
        # 取得路由路徑 (例如: {"route": "SQL"})
        route_decision = await self.router.route_question(clean_question)
        
        route_type = route_decision.get("route", "UNKNOWN")
        print(f"[Factory Agent] Router decision -> {route_type} (Is Equipment: {is_equipment})")
        
        if route_type == "SQL":
            if is_equipment:
                # 委託給 Equipment SQL Agent (PostgreSQL 設備數據)
                result = await self.equipment_sql_agent.chat(clean_question, history=history)
            else:
                # 委託給 Production SQL Agent (MSSQL 產線數據)
                result = await self.sql_agent.chat(clean_question, history=history)
            
            # Normalise: both agents now return dict, but guard for string fallback
            if isinstance(result, dict):
                return result
            return {"response": str(result), "chart_config": None}
            
        elif route_type == "RAG":
            # RAG route removed; fall back to production SQL agent
            result = await self.sql_agent.chat(clean_question, history=history)
            if isinstance(result, dict):
                return result
            return {"response": str(result), "chart_config": None}
            
        else:
            return {
                "response": "無法解析您的問題。如果需要查詢稼動率，或是機台異常處理方法，請再說明得更詳細一點。",
                "chart_config": None
            }
