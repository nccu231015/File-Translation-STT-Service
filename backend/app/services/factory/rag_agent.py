from typing import Dict, Any, List

class RagAgent:
    """
    負責處理 C 類問題：「根因分析」、「解決方案檢索」。
    當用戶詢問「XXX是為什麼」或「代碼A006怎麼處理」時，此模組會：
    1. 前往 OpenSearch (或其他 VectorDB) 尋找最相近的故事/手冊。
    2. 將檢索出的 Context 透過 LLM 濃縮成易讀的回覆。
    """
    
    def __init__(self, llm_service, vector_search_client=None):
        self.llm = llm_service
        self.search_client = vector_search_client
        
    async def retrieve_knowledge(self, query: str) -> List[Dict[str, Any]]:
        """
        將用戶的問題丟到向量庫去比對，取得知識片段 (Chunks)。
        """
        # TODO: 實作 OpenSearch / FAISS 的檢索邏輯
        print(f"[RAG Agent] Searching vector database for query: {query}")
        return [
            {"score": 0.95, "content": "「A006」代表皮帶鬆脫，維護方法為打開機殼後將張力調整至 50N。"},
            {"score": 0.88, "content": "異常碼「A011」表示信號中斷，需檢查網路連接線。"}
        ]

    async def execute_task(self, question: str) -> str:
        """
        完整的 RAG 流程：
        檢索 -> 重寫 Context -> 組合最終答案
        """
        print(f"[RAG Agent] Executing task for: {question}")
        chunks = await self.retrieve_knowledge(question)
        
        context_str = "\n".join([f"- {c['content']}" for c in chunks])
        
        prompt = f"""請擔任資深的工廠維修專家，參考以下【知識庫資訊】來回答使用者的【問題】：

【問題】：{question}

【知識庫資訊】：
{context_str}

【回答要求】：
- 若知識庫資訊無法回答問題，請誠實告知，不要自行腦補。
- 請以親切專業的繁體中文解釋。
"""
        # 假設 LLM 回傳
        # response = await self.llm.ask(prompt)
        # return response
        
        return "根據知識庫，這通常是皮帶鬆脫的問題，建議將張力調整至 50N。"
