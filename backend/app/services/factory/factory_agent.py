from .router_agent import FactoryRouterAgent
from .sql_agent import SqlAgent
from .rag_agent import RagAgent

class FactoryAgentService:
    """
    智能問答的總調度員 (Orchestrator)。
    這是前端 API 所呼叫的唯一入口點。
    1. 接收 Request
    2. 交由 Router 判定是走 SQL 查詢或是 RAG 查詢
    3. 把結果整合並回傳給用戶
    """
    
    def __init__(self, llm_service):
        self.router = FactoryRouterAgent(llm_service)
        self.sql_agent = SqlAgent(llm_service)
        self.rag_agent = RagAgent(llm_service)
        
    async def chat(self, user_question: str) -> str:
        """
        處理使用者的每一句話
        1. Router 分析問題語意
        2. 動態呼叫對應的工具 (路由決策樹)
        3. 回傳文字解說
        """
        print(f"\n[Factory Agent] Received new question: '{user_question}'")
        
        # 取得路由路徑 (例如: {"route": "SQL"})
        route_decision = await self.router.route_question(user_question)
        
        route_type = route_decision.get("route", "UNKNOWN")
        print(f"[Factory Agent] Router decision -> {route_type}")
        
        if route_type == "SQL":
            # 委託給 SQL Agent 執行 A/B 類報表查詢工具
            response = await self.sql_agent.execute_task(user_question)
            return response
            
        elif route_type == "RAG":
            # 委託給 RAG Agent 檢索 C 類說明手冊
            response = await self.rag_agent.execute_task(user_question)
            return response
            
        else:
            return "無法解析您的問題。如果需要查詢稼動率，或是機台異常處理方法，請再說明得更詳細一點。"
