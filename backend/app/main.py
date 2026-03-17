@app.post("/chat")
async def chat_text(payload: dict):
    """Simple text chat endpoint for testing LLM service."""
    print(f"[CHAT] Received question: {payload.get('question', '')[:50]}...", flush=True)
    text = payload.get("question", "")
    response = await llm_service.chat(text)
    return {"response": response}


@app.post("/factory-chat")
async def factory_chat(payload: dict, background_tasks: BackgroundTasks):
    """Factory Data Q&A Interface with session history."""
    from app.services.factory.factory_redis import factory_store
    try:
        user_text = payload.get("text")
        session_id = payload.get("session_id")
        
        if not user_text:
            raise HTTPException(status_code=400, detail="Text field is required")
        
        history = []
        if session_id:
            session = await factory_store.get_session(session_id)
            if session:
                history = session.get("messages", [])
        else:
            session = await factory_store.create_session(user_text)
            session_id = session["session_id"]
            
        print(f"\n[Factory Chat] Request (session={session_id})", flush=True)
        response = await factory_agent.chat(user_text, history=history)
        
        # 背景存檔，避免延遲
        background_tasks.add_task(factory_store.append_messages, session_id, user_text, response)
        
        print(f"[Factory Chat] Success: {len(response)} chars", flush=True)
        return {"response": response, "session_id": session_id}
    except Exception as e:
        print(f"[Factory API Error] {e}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/factory-sessions")
async def list_factory_sessions():
    """Returns a list of all factory chat sessions (newest first)."""
    from app.services.factory.factory_redis import factory_store
    sessions = await factory_store.list_sessions()
    return {"sessions": sessions}


@app.get("/factory-sessions/{session_id}")
async def get_factory_session(session_id: str):
    """Returns the full message history of a specific session."""
    from app.services.factory.factory_redis import factory_store
    session = await factory_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


@app.delete("/factory-sessions/{session_id}")
async def delete_factory_session(session_id: str):
    """Deletes a specific factory chat session."""
    from app.services.factory.factory_redis import factory_store
    deleted = await factory_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}
