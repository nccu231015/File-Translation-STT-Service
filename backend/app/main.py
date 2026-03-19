import os
import shutil
import tempfile
import httpx
import json
import base64
import datetime
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
from app.services.factory.factory_agent import FactoryAgentService
from app.services.factory.factory_redis import factory_store
from pydantic import BaseModel
from typing import Optional
import uuid
import traceback
from fastapi.concurrency import run_in_threadpool
from pdf2docx import Converter
from app.services.factory.sql_tools import FactorySqlTools

app = FastAPI()
factory_agent = FactoryAgentService(llm_service)

@app.on_event("startup")
async def startup_event():
    """初始化服務：確保資料庫連線與 Table 就緒"""
    print("\n[Startup] Application is starting...", flush=True)
    
    # 1. Employee DB (MySQL)
    try:
        await ensure_records_table()
        print("[EmployeeDB] ✓ employee_records table ready")
    except Exception as e:
        print(f"[EmployeeDB Error] {e}")

    # 2. Factory Session Store (Redis/Memory)
    try:
        await factory_store.connect()
        print("[FactoryStore] ✓ Session store initialized")
    except Exception as e:
        print(f"[FactoryStore Error] {e}")

    # 3. Factory Databases Health Check
    try:
        factory_tools = FactorySqlTools()
        db_status = factory_tools.test_connections()
        print(f"[HealthCheck] MSSQL: {db_status['mssql']}, Postgres: {db_status['postgres']}")
    except Exception as e:
        print(f"[HealthCheck Error] {e}")

# Middleware
@app.middleware("http")
async def add_ngrok_header(request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

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
            resp = await client.post(LDAP_URL, data={"username": body.username, "password": body.password})
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LDAP service unavailable: {e}")

    if str(data.get("chkIdentity", "false")).lower() != "true":
        raise HTTPException(status_code=401, detail=data.get("msg", "登入失敗"))

    sso_username = data.get("username", body.username)
    emp = await get_employee(sso_username)
    if emp:
        title, dept, name = emp.get("DUTYNAME", ""), emp.get("DEPTNAME", data.get("dpt", "")), emp.get("EMPNAME", data.get("name", ""))
    else:
        title, dept, name = "", data.get("dpt", ""), data.get("name", "")

    rank = get_rank(title)
    can_view = has_view_permission(rank)
    return {"username": sso_username, "name": name, "dpt": dept, "title": title, "rank": rank, "canViewRecords": can_view}

@app.get("/api/records/{empid}")
async def get_records(empid: str):
    """
    獲取員工紀錄清單。
    如果是經理權限，則獲取下屬清單；如果是普通員工，獲取個人歷史紀錄。
    """
    requester = await get_employee(empid)
    if not requester:
        # 嘗試直接獲取該員紀錄
        records = await get_employee_records(empid)
        return {"empid": empid, "employees": [], "records": records}
    
    rank = get_rank(requester.get("DUTYNAME", ""))
    if has_view_permission(rank):
        # 經理視角：獲取下屬列表
        dept = requester.get("DEPTNAME", "")
        subordinates = await get_subordinates(empid, dept, rank)
        return {"requester_rank": rank, "employees": subordinates}
    else:
        # 個人視角：獲取個人紀錄
        records = await get_employee_records(empid)
        return {"empid": empid, "records": records}

@app.post("/api/employee-records")
async def create_employee_record(body: dict):
    # 兼容舊版與新版 Request Body
    record_id = await save_employee_record(
        empid=body.get("empid"),
        record_type=body.get("type", "voice"),
        file_name=body.get("file_name", "unknown"),
        summary=body.get("summary", ""),
        decisions=body.get("decisions", ""),
        action_items=body.get("action_items", ""),
    )
    if record_id is None: raise HTTPException(status_code=500, detail="Failed to save record")
    return {"id": record_id, "success": True}

@app.get("/")
async def read_root():
    return {"message": "Factory AI & STT Service is Running"}

@app.post("/stt")
async def transcribe_audio(file: UploadFile = File(...), mode: str = Form("chat")):
    temp_file_path = ""
    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name
        stt_result = await run_in_threadpool(stt_service.transcribe, temp_file_path)
        if os.path.exists(temp_file_path): os.remove(temp_file_path)
        
        user_text = stt_result["text"]
        if mode == "chat":
            llm_response = await llm_service.chat(user_text)
            return {"transcription": stt_result, "llm_response": llm_response}
        elif mode == "meeting":
            # Step 1: Analyze meeting transcript
            analysis = await run_in_threadpool(llm_service.analyze_meeting_transcript, user_text)
            
            # Step 2: Translate analysis to English (for bilingual minutes)
            try:
                en_analysis = await run_in_threadpool(llm_service.translate_analysis, analysis)
            except Exception as te:
                print(f"[STT] translate_analysis failed: {te}")
                en_analysis = {}
            
            # Step 3: Generate meeting minutes DOCX
            try:
                minutes_svc = MeetingMinutesDocxService()
                minutes_bytes = await run_in_threadpool(
                    minutes_svc.generate_minutes,
                    file.filename,
                    analysis.get("meeting_objective", ""),
                    analysis.get("discussion_summary", ""),
                    analysis.get("decisions", []),
                    analysis.get("action_items", []),
                    analysis.get("attendees", []),
                    analysis.get("schedule_notes", ""),
                    None,
                    en_analysis.get("meeting_objective", ""),
                    en_analysis.get("discussion_summary", ""),
                    en_analysis.get("decisions", []),
                    en_analysis.get("action_items", []),
                    en_analysis.get("schedule_notes", ""),
                )
                file_download = {
                    "filename": f"meeting_minutes_{file.filename}.docx",
                    "content_base64": base64.b64encode(minutes_bytes).decode("utf-8"),
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                }
            except Exception as de:
                print(f"[STT] MeetingMinutesDocx generation failed: {de}")
                file_download = None
            
            # Step 4: Translate segments for bilingual transcript
            transcript_download = None
            try:
                segments = stt_result.get("segments", [])
                detected_lang = stt_result.get("language", "zh")
                if segments:
                    translated_segments = await run_in_threadpool(
                        llm_service.translate_segments, segments, detected_lang
                    )
                    transcript_svc = TranscriptDocxService()
                    is_chinese = detected_lang.lower().startswith("zh")
                    transcript_bytes = await run_in_threadpool(
                        transcript_svc.generate,
                        file.filename,
                        translated_segments,
                        "中文" if is_chinese else "English",
                        "English" if is_chinese else "中文（繁體）",
                    )
                    transcript_download = {
                        "filename": f"transcript_{file.filename}.docx",
                        "content_base64": base64.b64encode(transcript_bytes).decode("utf-8"),
                        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    }
            except Exception as te2:
                print(f"[STT] TranscriptDocx generation failed: {te2}")
            
            # Step 5: Construct bilingual display fields for frontend
            composite_summary = ""
            zh_obj = analysis.get("meeting_objective", "").strip()
            en_obj = en_analysis.get("meeting_objective", "").strip()
            if zh_obj or en_obj:
               composite_summary += f"【會議目的 | Meeting Objective】\n{zh_obj}\n{en_obj}\n\n"
               
            zh_sum = analysis.get("discussion_summary", analysis.get("summary", "")).strip()
            en_sum = en_analysis.get("discussion_summary", en_analysis.get("summary", "")).strip()
            if zh_sum or en_sum:
               composite_summary += f"【討論摘要 | Discussion Summary】\n{zh_sum}\n{en_sum}"

            zh_decisions = analysis.get("decisions", [])
            en_decisions = en_analysis.get("decisions", [])
            composite_decisions = []
            max_len = max(len(zh_decisions), len(en_decisions))
            for i in range(max_len):
                zh_d = zh_decisions[i] if i < len(zh_decisions) else ""
                en_d = en_decisions[i] if i < len(en_decisions) else ""
                composite_decisions.append(f"{zh_d}\n{en_d}".strip())

            zh_actions = analysis.get("action_items", [])
            en_actions = en_analysis.get("action_items", [])
            composite_actions = []
            max_len_actions = max(len(zh_actions), len(en_actions))
            for i in range(max_len_actions):
                zh_a = zh_actions[i] if i < len(zh_actions) else {}
                en_a = en_actions[i] if i < len(en_actions) else {}
                
                if isinstance(zh_a, str):
                    zh_task = zh_a
                    en_task = en_a if isinstance(en_a, str) else en_a.get("task", "")
                    composite_actions.append(f"{zh_task}\n{en_task}".strip())
                else:
                    task = f"{zh_a.get('task', '')}\n{en_a.get('task', '')}".strip()
                    composite_actions.append({
                        "task": task, 
                        "owner": zh_a.get('owner', ''), 
                        "deadline": zh_a.get('deadline', '')
                    })

            result = {
                "transcription": stt_result,
                "analysis": {
                    "summary": composite_summary.strip() or zh_sum,
                    "decisions": composite_decisions,
                    "action_items": composite_actions,
                }
            }
            if 'translated_segments' in locals() and translated_segments:
                result["translated_segments"] = translated_segments
            if file_download:
                result["file_download"] = file_download
            if transcript_download:
                result["transcript_download"] = transcript_download
            return result

        return {"transcription": stt_result}
    except Exception as e:
        if temp_file_path and os.path.exists(temp_file_path): os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/pdf-translation")
async def translate_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...), target_lang: str = Form(None), debug: str = Form("false")):
    debug_mode = str(debug).lower() in ("true", "1", "t", "yes", "on")
    temp_input_path = ""
    docx_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
            shutil.copyfileobj(file.file, temp_input)
            temp_input_path = temp_input.name
            
        result_list = await pdf_service.process_pdf(temp_input_path, force_target_lang=target_lang, debug_mode=debug_mode)
        output_pdf_path = result_list[0]["file_path"]
        
        with open(output_pdf_path, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
            
        # Docx generation
        docx_b64 = None
        if not debug_mode:
            try:
                docx_path = output_pdf_path.replace(".pdf", ".docx")
                
                def _convert():
                    cv = Converter(output_pdf_path)
                    cv.convert(docx_path)
                    cv.close()
                    
                await run_in_threadpool(_convert)
                with open(docx_path, 'rb') as f:
                    docx_b64 = base64.b64encode(f.read()).decode('utf-8')
                background_tasks.add_task(os.remove, docx_path)
            except Exception as docx_err:
                print(f"[PDF] Docx conversion failed: {docx_err}")
                if os.path.exists(docx_path): os.remove(docx_path)
                
        background_tasks.add_task(os.remove, temp_input_path)
        background_tasks.add_task(os.remove, output_pdf_path)
        
        return {"pdf_base64": pdf_b64, "docx_base64": docx_b64}
    except Exception as e:
        if temp_input_path and os.path.exists(temp_input_path): os.remove(temp_input_path)
        if docx_path and os.path.exists(docx_path): os.remove(docx_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_text(payload: dict):
    text = payload.get("question", payload.get("text", ""))
    response = await llm_service.chat(text)
    return {"response": response}

@app.post("/factory-chat")
async def factory_chat(payload: dict, background_tasks: BackgroundTasks):
    """工廠數據聊天接口：整合 Session 歷史與 SQL 查詢"""
    try:
        user_text = payload.get("text")
        session_id = payload.get("session_id")
        if not user_text: raise HTTPException(status_code=400, detail="Text field is required")
        
        history = []
        if session_id:
            session = await factory_store.get_session(session_id)
            if session: history = session.get("messages", [])
        
        # 確保有 Session ID（簡化邏輯，避免 Redis 二次查詢引發異常）
        if not session_id:
            try:
                session = await factory_store.create_session(user_text)
                session_id = session["session_id"]
            except Exception as se:
                session_id = str(uuid.uuid4())
                print(f"[Session Warning] Fallback session id generated: {se}")
            
        print(f"\n[Factory Chat] Processing request (session={session_id})", flush=True)
        response = await factory_agent.chat(user_text, history=history)
        
        # 安全地添加背景存檔任務
        try:
            background_tasks.add_task(factory_store.append_messages, session_id, user_text, str(response))
        except Exception as bg_e:
            print(f"[BG Task Error] Failed to queue session save: {bg_e}")

        print(f"[Factory Chat] Success: {len(str(response))} chars", flush=True)
        
        # FastAPI 本身具備優異的 JSON 序列化能力，直接回傳字典即可
        return {
            "response": str(response),
            "session_id": str(session_id)
        }
        
    except Exception as e:
        print(f"[Factory API Error] {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/factory-sessions")
async def list_factory_sessions():
    try:
        sessions = await factory_store.list_sessions()
        return {"sessions": sessions}
    except Exception as e:
        print(f"[API Error] list_sessions: {e}")
        return {"sessions": []}

@app.get("/factory-sessions/{session_id}")
async def get_factory_session(session_id: str):
    session = await factory_store.get_session(session_id)
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.delete("/factory-sessions/{session_id}")
async def delete_factory_session(session_id: str):
    deleted = await factory_store.delete_session(session_id)
    if not deleted: raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}
