import os
import shutil
import tempfile
import httpx
import json
import base64
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Response, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.services.stt_service import stt_service
from app.services.llm_service import llm_service
from app.services.pdf_service import pdf_service
from app.services.meeting_minutes_docx import MeetingMinutesDocxService
from app.services.transcript_docx_service import TranscriptDocxService
from app.services.employee_db import (
    get_employee, get_subordinates,
    save_employee_record, get_employee_records,
    ensure_records_table,
)
from app.services.rank_service import get_rank, has_view_permission
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.services.factory.factory_agent import FactoryAgentService
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
factory_agent = FactoryAgentService(llm_service)

@app.on_event("startup")
async def startup_event():
    """Ensure helper DB tables exist and test factory DB connections on startup."""
    # 1. Employee DB (MySQL)
    await ensure_records_table()
    print("[EmployeeDB] ✓ employee_records table ready")

    # 2. Factory Session Store (Redis/Memory)
    from app.services.factory.factory_redis import factory_store
    await factory_store.connect()
    print("[FactoryStore] ✓ Redis/Memory store ready")

    # 3. Factory Databases Health Check
    try:
        from app.services.factory.sql_tools import FactorySqlTools
        factory_tools = FactorySqlTools()
        db_status = factory_tools.test_connections()
        
        if db_status["mssql"] == "ok":
            print("[MSSQL] ✓ Production DB Ready (172.16.2.68:1433)")
        else:
            print(f"[MSSQL] ✗ Connection Failed: {db_status['mssql']}")
            
        if db_status["postgres"] == "ok":
            print("[PostgreSQL] ✓ Equipment DB Ready (172.16.2.68:5432)")
        else:
            print(f"[PostgreSQL] ✗ Connection Failed: {db_status['postgres']}")
    except Exception as e:
        print(f"[HealthCheck Error] Failed during startup: {e}")

# Middleware to help Ngrok bypass browser warning
@app.middleware("http")
async def add_ngrok_header(request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/login")
async def login(body: LoginRequest):
    LDAP_URL = "http://api.jebsee.com.tw:8081/api/LDAPLogin"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                LDAP_URL,
                data={"username": body.username, "password": body.password},
            )
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LDAP service unavailable: {e}")

    if str(data.get("chkIdentity", "false")).lower() != "true":
        raise HTTPException(status_code=401, detail=data.get("msg", "登入失敗"))

    sso_username = data.get("username", body.username)
    emp = await get_employee(sso_username)
    if emp:
        title = emp.get("DUTYNAME", "")
        dept  = emp.get("DEPTNAME", data.get("dpt", ""))
        name  = emp.get("EMPNAME", data.get("name", ""))
    else:
        title = ""
        dept  = data.get("dpt", "")
        name  = data.get("name", "")

    rank = get_rank(title)
    can_view = has_view_permission(rank)
    return {
        "username": sso_username,
        "name": name,
        "dpt": dept,
        "title": title,
        "rank": rank,
        "canViewRecords": can_view,
    }

@app.get("/api/records/{empid}")
async def get_records_for_manager(empid: str):
    requester = await get_employee(empid)
    if not requester:
        raise HTTPException(status_code=404, detail="Employee not found")
    rank = get_rank(requester.get("DUTYNAME", ""))
    if not has_view_permission(rank):
        raise HTTPException(status_code=403, detail="No permission to view employee records")
    dept = requester.get("DEPTNAME", "")
    subordinates = await get_subordinates(empid, dept, rank)
    return {"employees": subordinates}

class SaveRecordRequest(BaseModel):
    empid: str
    type: str
    file_name: str
    summary: Optional[str] = ""
    decisions: Optional[str] = ""
    action_items: Optional[str] = ""

@app.post("/api/employee-records")
async def create_employee_record(body: SaveRecordRequest):
    record_id = await save_employee_record(
        empid=body.empid,
        record_type=body.type,
        file_name=body.file_name,
        summary=body.summary or "",
        decisions=body.decisions or "",
        action_items=body.action_items or "",
    )
    if record_id is None:
        raise HTTPException(status_code=500, detail="Failed to save record")
    return {"id": record_id, "success": True}

@app.get("/api/employee-records/{empid}")
async def fetch_employee_records(empid: str):
    records = await get_employee_records(empid)
    return {"empid": empid, "records": records}

@app.get("/")
async def read_root():
    return {"message": "STT & Translation API Service is Running"}

@app.post("/stt")
async def transcribe_audio(
    file: UploadFile = File(...), 
    mode: str = Form("chat")
):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
        from fastapi.concurrency import run_in_threadpool
        stt_result = await run_in_threadpool(stt_service.transcribe, temp_file_path)
        os.remove(temp_file_path)
        user_text = stt_result["text"]
        if mode == "chat":
            llm_response = await llm_service.chat(user_text)
            return {"transcription": stt_result, "llm_response": llm_response}
        elif mode == "meeting":
            analysis = await run_in_threadpool(llm_service.analyze_meeting_transcript, user_text)
            return {"transcription": stt_result, "analysis": analysis}
        raise HTTPException(status_code=400, detail="Invalid mode")
    except Exception as e:
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path): os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/pdf-translation")
async def translate_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_lang: str = Form(None),
    debug: str = Form("false")
):
    debug_mode = str(debug).lower() in ("true", "1", "t", "yes", "on")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    temp_input_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
            shutil.copyfileobj(file.file, temp_input)
            temp_input_path = temp_input.name
        result_list = await pdf_service.process_pdf(temp_input_path, force_target_lang=target_lang, debug_mode=debug_mode)
        output_pdf_path = result_list[0]["file_path"]
        with open(output_pdf_path, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
        background_tasks.add_task(os.remove, temp_input_path)
        background_tasks.add_task(os.remove, output_pdf_path)
        return {"pdf_base64": pdf_b64}
    except Exception as e:
        if temp_input_path and os.path.exists(temp_input_path): os.remove(temp_input_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_text(payload: dict):
    text = payload.get("question", "")
    response = await llm_service.chat(text)
    return {"response": response}

@app.post("/factory-chat")
async def factory_chat(payload: dict, background_tasks: BackgroundTasks):
    from app.services.factory.factory_redis import factory_store
    try:
        user_text = payload.get("text")
        session_id = payload.get("session_id")
        if not user_text: raise HTTPException(status_code=400, detail="Text field is required")
        history = []
        if session_id:
            session = await factory_store.get_session(session_id)
            if session: history = session.get("messages", [])
        else:
            session = await factory_store.create_session(user_text)
            session_id = session["session_id"]
        response = await factory_agent.chat(user_text, history=history)
        background_tasks.add_task(factory_store.append_messages, session_id, user_text, response)
        return {"response": response, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/factory-sessions")
async def list_factory_sessions():
    from app.services.factory.factory_redis import factory_store
    return {"sessions": await factory_store.list_sessions()}

@app.get("/factory-sessions/{session_id}")
async def get_factory_session(session_id: str):
    from app.services.factory.factory_redis import factory_store
    session = await factory_store.get_session(session_id)
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.get("/api/records/{empid}")
async def get_records(empid: str):
    return {"records": await get_employee_records(empid)}
