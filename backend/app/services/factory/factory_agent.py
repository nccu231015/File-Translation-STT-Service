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
        Route user question to the correct agent based on router decision.
        Returns: {"response": str, "chart_config": dict | None}
        """
        print(f"\n[Factory Agent] Received new question: '{user_question}'")

        # Routing context (follow-up handling) is managed by n8n;
        # Python router is used as a local fallback only.
        route_decision = await self.router.route_question(user_question)
        route_type = route_decision.get("route", "SQL_PROD")
        print(f"[Factory Agent] Router decision -> {route_type}")

        if route_type == "SQL_EQ":
            result = await self.equipment_sql_agent.chat(user_question, history=history)
        else:
            # SQL_PROD or any fallback
            result = await self.sql_agent.chat(user_question, history=history)

        if isinstance(result, dict):
            return result
        return {"response": str(result), "chart_config": None}
