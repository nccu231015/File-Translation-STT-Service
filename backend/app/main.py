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
import asyncio
from fastapi.concurrency import run_in_threadpool
from pdf2docx import Converter
from app.services.factory.sql_tools import FactorySqlTools
import docx
from docx.shared import Pt
from docx.oxml.ns import qn
import asyncio
import subprocess
import platform
try:
    from docx2pdf import convert as docx2pdf_convert
except ImportError:
    docx2pdf_convert = None

app = FastAPI()
factory_agent = FactoryAgentService(llm_service)

@app.on_event("startup")
async def startup_event():
    """Initialization service: ensure DB connection and tables are ready"""
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
        raise HTTPException(status_code=401, detail=data.get("msg", "Login failed"))

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
    Get employee records list.
    Manager rank: gets subordinates list; Employee rank: gets personal history.
    """
    requester = await get_employee(empid)
    if not requester:
        # Try to get individual records directly
        records = await get_employee_records(empid)
        return {"empid": empid, "employees": [], "records": records}
    
    rank = get_rank(requester.get("DUTYNAME", ""))
    if has_view_permission(rank):
        # Manager view: get subordinates list
        dept = requester.get("DEPTNAME", "")
        subordinates = await get_subordinates(empid, dept, rank)
        return {"requester_rank": rank, "employees": subordinates}
    else:
        # Personal view: get personal records
        records = await get_employee_records(empid)
        return {"empid": empid, "records": records}

@app.post("/api/employee-records")
async def create_employee_record(body: dict):
    # Compatible with old and new Request Body versions
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
            # Step 1: Analyze meeting transcript (Traditional Chinese output)
            analysis = await run_in_threadpool(llm_service.analyze_meeting_transcript, user_text)

            # Step 2: Translate analysis to English (for bilingual minutes)
            try:
                en_analysis = await run_in_threadpool(llm_service.translate_analysis, analysis)
            except Exception as te:
                print(f"[STT] translate_analysis failed: {te}")
                en_analysis = {}

            # Step 3: Generate meeting minutes DOCX
            file_download = None
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

            # Step 4: Translate segments and generate bilingual transcript DOCX
            translated_segments = []
            transcript_download = None
            segments = stt_result.get("segments", [])
            detected_lang = stt_result.get("language", "zh")
            is_chinese = detected_lang.lower().startswith("zh")
            try:
                if segments:
                    translated_segments = await llm_service.translate_segments_async(
                        segments, detected_lang
                    )
                    transcript_svc = TranscriptDocxService()
                    transcript_bytes = await run_in_threadpool(
                        transcript_svc.generate,
                        file.filename,
                        translated_segments,
                        "Chinese" if is_chinese else "English",
                        "English" if is_chinese else "Chinese (Traditional)",
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
            
        # Docx generation and Table translation
        docx_b64 = None
        if not debug_mode:
            try:
                docx_path = output_pdf_path.replace(".pdf", ".docx")
                
                def _convert():
                    cv = Converter(output_pdf_path)
                    cv.convert(docx_path)
                    cv.close()
                    
                await run_in_threadpool(_convert)

                # ---- Stage 2: Process tables in Word (DOCX) ----
                def _process_docx_tables():
                    doc = docx.Document(docx_path)
                    to_translate = set()
                    
                    def collect_text(container):
                        if hasattr(container, 'tables'):
                            for table in container.tables:
                                for row in table.rows:
                                    for cell in row.cells:
                                        if hasattr(cell, 'paragraphs'):
                                            for para in cell.paragraphs:
                                                # Split lines to prevent LLM from being confused by lists/multiline structures
                                                for line in para.text.split('\n'):
                                                    cleaned = line.strip()
                                                    if cleaned and len(cleaned) > 1 and not cleaned.isdigit():
                                                        to_translate.add(cleaned)
                                        collect_text(cell)
                    
                    collect_text(doc)
                    return doc, list(to_translate)
                
                doc, content_list = await run_in_threadpool(_process_docx_tables)
                
                translation_cache = {}
                if content_list:
                    print(f"[PDF-DOCX] Batch translating {len(content_list)} table cell strings...", flush=True)
                    batch_size = 50
                    
                    async def process_batch(batch):
                        translated = await pdf_service._translate_batch_ollama(batch, target_lang=target_lang)
                        for orig, trans in zip(batch, translated):
                            if trans and "<SKIP>" not in trans:
                                translation_cache[orig] = trans

                    tasks = []
                    for i in range(0, len(content_list), batch_size):
                        tasks.append(process_batch(content_list[i : i + batch_size]))
                    
                    await asyncio.gather(*tasks)
                    
                    def _apply_docx_tables():
                        def apply_style(container):
                            if hasattr(container, 'tables'):
                                for table in container.tables:
                                    # Only unlock fixed row heights so rows can grow downward.
                                    # Do NOT change tblLayout to autofit — that causes columns to overflow page margins.
                                    for row in table.rows:
                                        try:
                                            trPr = row._tr.trPr
                                            if trPr is not None:
                                                for el in trPr.findall(qn('w:trHeight')):
                                                    trPr.remove(el)
                                        except Exception:
                                            pass
                                            
                                        for cell in row.cells:
                                            if hasattr(cell, 'paragraphs'):
                                                for para in cell.paragraphs:
                                                    lines = para.text.split('\n')
                                                    needs_update = False
                                                    new_lines = []
                                                    
                                                    # Apply translation line-by-line; fallback to original if missing
                                                    for line in lines:
                                                        cleaned = line.strip()
                                                        if cleaned in translation_cache:
                                                            new_lines.append(translation_cache[cleaned])
                                                            needs_update = True
                                                        else:
                                                            new_lines.append(line)
                                                    
                                                    if needs_update:
                                                        new_text = '\n'.join(new_lines)
                                                        if para.runs:
                                                            para.runs[0].text = new_text
                                                            for j in range(1, len(para.runs)): 
                                                                para.runs[j].text = ""
                                                        else:
                                                            para.add_run(new_text)
                                                        
                                                        # Clear indentation locks set by pdf2docx to allow English text to wrap naturally
                                                        para.paragraph_format.left_indent = None
                                                        para.paragraph_format.right_indent = None
                                                        
                                                        para.paragraph_format.line_spacing = 1.2
                                                        for run in para.runs:
                                                            if run.text:
                                                                run.font.name = 'Arial'
                                                                run.font.size = Pt(11)
                                                                run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
                                            apply_style(cell)
                        apply_style(doc)
                        doc.save(docx_path)
                        
                    await run_in_threadpool(_apply_docx_tables)
                    print(f"[PDF-DOCX] Applied {len(translation_cache)} translations to DOCX tables.", flush=True)

                with open(docx_path, 'rb') as f:
                    docx_b64 = base64.b64encode(f.read()).decode('utf-8')

                # ---- Stage 3: Convert DOCX to Final PDF ----
                def _docx_to_pdf():
                    try:
                        if platform.system() == "Windows":
                            if docx2pdf_convert:
                                docx2pdf_convert(docx_path, output_pdf_path)
                            else:
                                print("[PDF-DOCX] docx2pdf library not found on Windows.", flush=True)
                        else:
                            subprocess.run(['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', os.path.dirname(output_pdf_path), docx_path], check=True)
                    except Exception as e:
                        print(f"[PDF-DOCX] Docx to PDF failed: {e}", flush=True)

                await run_in_threadpool(_docx_to_pdf)
                
                # Reload the completely translated PDF
                if os.path.exists(output_pdf_path):
                    with open(output_pdf_path, 'rb') as f:
                        pdf_b64 = base64.b64encode(f.read()).decode('utf-8')

                background_tasks.add_task(os.remove, docx_path)
            except Exception as docx_err:
                print(f"[PDF] Docx translation/conversion failed: {docx_err}")
                import traceback
                traceback.print_exc()
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
    """Factory data chat interface: integrate session history with SQL querying"""
    try:
        user_text = payload.get("text")
        session_id = payload.get("session_id")
        if not user_text: raise HTTPException(status_code=400, detail="Text field is required")
        
        history = []
        if session_id:
            session = await factory_store.get_session(session_id)
            if session: history = session.get("messages", [])
        
        # Ensure session id exists (simplified logic for stability)
        if not session_id:
            try:
                session = await factory_store.create_session(user_text)
                session_id = session["session_id"]
            except Exception as se:
                session_id = str(uuid.uuid4())
                print(f"[Session Warning] Fallback session id generated: {se}")
            
        print(f"\n[Factory Chat] Processing request (session={session_id})", flush=True)
        response = await factory_agent.chat(user_text, history=history)
        
        # Safely add background archive task
        try:
            background_tasks.add_task(factory_store.append_messages, session_id, user_text, str(response))
        except Exception as bg_e:
            print(f"[BG Task Error] Failed to queue session save: {bg_e}")

        print(f"[Factory Chat] Success: {len(str(response))} chars", flush=True)
        
        # FastAPI handles JSON serialization automatically
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
