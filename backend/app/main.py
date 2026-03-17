import os
import shutil
import tempfile
import httpx
import json
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

    # 2. Factory Databases Health Check
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
# Note: allow_credentials must be False when using allow_origins=["*"].
# This app uses JWT Bearer tokens (not cookies), so credentials mode is not needed.
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
    """
    Proxy to LDAP login API. On success, enriches response with employee
    data from MySQL (title, rank, canViewRecords).
    """
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

    # ── Enrich with MySQL employee data ────────────────────────────────────
    emp = await get_employee(sso_username)
    if emp:
        title = emp.get("DUTYNAME", "")
        dept  = emp.get("DEPTNAME", data.get("dpt", ""))
        name  = emp.get("EMPNAME", data.get("name", ""))
    else:
        # MySQL lookup failed — fall back to SSO data, no manager rights
        print(f"[Login] Employee {sso_username} not found in MySQL, using SSO data.", flush=True)
        title = ""
        dept  = data.get("dpt", "")
        name  = data.get("name", "")

    rank = get_rank(title)
    can_view = has_view_permission(rank)

    print(
        f"[Login] {sso_username} | {name} | {dept} | {title} | rank={rank} | canView={can_view}",
        flush=True,
    )

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
    """
    Return a list of employees whose records the given manager can view.
    Only employees in the same department with a lower authority rank are returned.
    Raises 403 if the requester does not have view permission.
    """
    requester = await get_employee(empid)
    if not requester:
        raise HTTPException(status_code=404, detail="Employee not found")

    rank = get_rank(requester.get("DUTYNAME", ""))
    if not has_view_permission(rank):
        raise HTTPException(status_code=403, detail="No permission to view employee records")

    dept = requester.get("DEPTNAME", "")
    subordinates = await get_subordinates(empid, dept, rank)

    return {
        "requester": {
            "empid": empid,
            "name": requester.get("EMPNAME", ""),
            "dept": dept,
            "title": requester.get("DUTYNAME", ""),
            "rank": rank,
        },
        "employees": subordinates,
    }


class SaveRecordRequest(BaseModel):
    empid: str
    type: str           # 'voice' | 'translation'
    file_name: str
    summary: Optional[str] = ""
    decisions: Optional[str] = ""
    action_items: Optional[str] = ""


@app.post("/api/employee-records")
async def create_employee_record(body: SaveRecordRequest):
    """
    Called by the frontend after completing a voice/translation process.
    Stores text metadata so managers can preview it later.
    """
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
    """
    Return the usage records of a specific employee.
    Called by managers viewing the records browser.
    """
    records = await get_employee_records(empid)
    return {"empid": empid, "records": records}


@app.get("/")
async def read_root():
    return {"message": "STT & Translation API Service is Running"}


@app.post("/stt")
async def transcribe_audio(
    file: UploadFile = File(...), 
    mode: str = Form("chat")  # Options: "chat", "meeting"
):
    """
    Receives an audio file, transcribes it.
    - If mode="chat": Sends text to LLM for immediate chat response.
    - If mode="meeting": Analyzes text for meeting minutes (Summary, Decision, Actions) and returns file.
    """
    # Create a temporary file to save the uploaded audio
    try:
        print(f"Received file: {file.filename}, Mode: {mode}, Content-Type: {file.content_type}")
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name

        # Transcribe (Run in threadpool to allow PDF/Chat to run simultaneously)
        from fastapi.concurrency import run_in_threadpool
        print(f"Mode: {mode} - Transcribing audio...", flush=True)
        stt_result = await run_in_threadpool(stt_service.transcribe, temp_file_path)

        # Clean up audio file
        os.remove(temp_file_path)

        user_text = stt_result["text"]
        print(f"Transcription Result (First 100 chars): {user_text[:100]}...")

        if not user_text.strip():
            return {"transcription": stt_result, "llm_response": "（未偵測到語音內容）"}

        # --- CHAT MODE ---
        if mode == "chat":
            print("Mode: Chat - Sending to LLM...")
            llm_response = await llm_service.chat(user_text)
            return {"transcription": stt_result, "llm_response": llm_response}

        # --- MEETING MODE ---
        elif mode == "meeting":
            print("Mode: Meeting - Analyzing Transcript in background...", flush=True)
            analysis = await run_in_threadpool(llm_service.analyze_meeting_transcript, user_text)
            
            # 2. Translate analysis to English (for bilingual meeting minutes)
            print("[Meeting] Translating analysis to English...", flush=True)
            en_analysis = await run_in_threadpool(
                llm_service.translate_analysis,
                analysis,
            )

            # --- Bilingual Frontend Formatting ---
            frontend_summary = ""
            if analysis.get('meeting_objective') or en_analysis.get('meeting_objective'):
                frontend_summary += f"【會議目的 | Meeting Objective】\n"
                if analysis.get('meeting_objective'):
                    frontend_summary += f"{analysis.get('meeting_objective')}\n"
                if en_analysis.get('meeting_objective'):
                    frontend_summary += f"{en_analysis.get('meeting_objective')}\n"
                frontend_summary += "\n"
            
            # Handle discussion_summary if it's a list (some LLMs output lists)
            disc_sum = analysis.get('discussion_summary', analysis.get('summary', ''))
            en_disc_sum = en_analysis.get('discussion_summary', en_analysis.get('summary', ''))
            
            frontend_summary += f"【討論摘要 | Discussion Summary】\n"
            if isinstance(disc_sum, list):
                try:
                    disc_text = ""
                    for item in disc_sum:
                        if isinstance(item, dict):
                            disc_text += f"- {item.get('topic', '')}: {item.get('description', '')}\n"
                        else:
                            disc_text += f"- {str(item)}\n"
                    frontend_summary += f"{disc_text}\n"
                except:
                    frontend_summary += f"{str(disc_sum)}\n"
            elif disc_sum:
                frontend_summary += f"{disc_sum}\n"
                
            if isinstance(en_disc_sum, list):
                try:
                    en_disc_text = ""
                    for item in en_disc_sum:
                        if isinstance(item, dict):
                            en_disc_text += f"- {item.get('topic', '')}: {item.get('description', '')}\n"
                        else:
                            en_disc_text += f"- {str(item)}\n"
                    frontend_summary += f"{en_disc_text}\n"
                except:
                    frontend_summary += f"{str(en_disc_sum)}\n"
            elif en_disc_sum:
                frontend_summary += f"{en_disc_sum}\n"

            # Combine Decisions
            safe_decisions = analysis.get('decisions', [])
            if not isinstance(safe_decisions, list):
                if isinstance(safe_decisions, str):
                    safe_decisions = [safe_decisions]
                else:
                    safe_decisions = []
                    
            frontend_decisions = []
            en_decisions = en_analysis.get('decisions', [])
            if not isinstance(en_decisions, list):
                en_decisions = [en_decisions] if isinstance(en_decisions, str) else []
            
            max_len = max(len(safe_decisions), len(en_decisions))
            for i in range(max_len):
                zh_d = str(safe_decisions[i]) if i < len(safe_decisions) else ""
                en_d = str(en_decisions[i]) if i < len(en_decisions) else ""
                if zh_d and en_d:
                    frontend_decisions.append(f"{zh_d}\n{en_d}")
                elif zh_d:
                    frontend_decisions.append(zh_d)
                elif en_d:
                    frontend_decisions.append(f"{en_d}")

            # Combine Action Items
            safe_action_items = analysis.get('action_items', [])
            if not isinstance(safe_action_items, list):
                safe_action_items = []
                
            frontend_actions = []
            en_actions = en_analysis.get('action_items', [])
            if not isinstance(en_actions, list):
                en_actions = [en_actions] if isinstance(en_actions, str) else []
                
            max_len = max(len(safe_action_items), len(en_actions))
            for i in range(max_len):
                zh_a = safe_action_items[i] if i < len(safe_action_items) else ""
                en_a = en_actions[i] if i < len(en_actions) else ""
                
                # If they are dicts, we could stringify them, but the frontend expects either string or {task, owner, deadline}
                # Let's convert them to string to ensure safe rendering of bilingual content
                def _fmt_action(a):
                    if isinstance(a, dict):
                        return f"[{a.get('owner', 'No Owner')}] {a.get('task', '')} ({a.get('deadline', '')})"
                    return str(a)
                
                zh_str = _fmt_action(zh_a) if zh_a else ""
                en_str = _fmt_action(en_a) if en_a else ""
                
                if zh_str and en_str:
                    frontend_actions.append(f"{zh_str}\n{en_str}")
                elif zh_str:
                    frontend_actions.append(zh_str)
                elif en_str:
                    frontend_actions.append(f"{en_str}")

            # 3. Generate bilingual Word document
            minutes_service = MeetingMinutesDocxService()
            docx_bytes = minutes_service.generate_minutes(
                file_name=file.filename,
                # Chinese content
                meeting_objective=analysis.get('meeting_objective', ''),
                discussion_summary=disc_sum,
                decisions=safe_decisions,
                action_items=safe_action_items,
                attendees=analysis.get('attendees', []),
                schedule_notes=analysis.get('schedule_notes', ''),
                # English translations
                en_meeting_objective=en_analysis.get('meeting_objective', ''),
                en_discussion_summary=en_analysis.get('discussion_summary', ''),
                en_decisions=en_decisions,
                en_action_items=en_actions,
                en_schedule_notes=en_analysis.get('schedule_notes', ''),
            )
            
            output_filename = f"meeting_minutes_{os.path.splitext(file.filename)[0]}.docx"
            
            # Return base64 encoded Word file for frontend download
            import base64
            docx_base64 = base64.b64encode(docx_bytes).decode('utf-8')
            
            frontend_analysis = {
                "summary": frontend_summary.strip(),
                "decisions": frontend_decisions,
                "action_items": frontend_actions
            }

            # 3. Generate bilingual transcript (segments → translate → docx)
            print("[Meeting] Generating bilingual transcript...", flush=True)
            segments = stt_result.get("segments", [])
            detected_lang = stt_result.get("language", "zh")

            # Determine language labels for document headers
            is_chinese = detected_lang.lower().startswith("zh")
            src_label = "中文" if is_chinese else "英文"
            tgt_label = "英文" if is_chinese else "繁體中文"

            bilingual_segments = await run_in_threadpool(
                llm_service.translate_segments,
                segments,
                detected_lang,
            )

            transcript_service = TranscriptDocxService()
            transcript_bytes = transcript_service.generate(
                file_name=file.filename,
                segments=bilingual_segments,
                src_lang=src_label,
                tgt_lang=tgt_label,
            )
            transcript_filename = f"bilingual_transcript_{os.path.splitext(file.filename)[0]}.docx"
            transcript_base64 = base64.b64encode(transcript_bytes).decode("utf-8")

            return {
                "transcription": stt_result,
                "analysis": frontend_analysis,
                "file_download": {
                    "filename": output_filename,
                    "content_base64": docx_base64,
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                },
                "transcript_download": {
                    "filename": transcript_filename,
                    "content_base64": transcript_base64,
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                }
            }
        
        else:
             raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")

    except Exception as e:
        # Ensure cleanup
        if "temp_file_path" in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pdf-translation")
async def translate_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_lang: str = Form(None), # Optional, default None to let service auto-detect
    debug: str = Form("false") # Receive as string to handle "true", "True", "on" manually
):
    """
    Receives a PDF file, extracts text, translates it, and returns the translated PDF file.
    If debug=True, returns PDF with bounding boxes instead of translation.
    """
    # Manual boolean conversion for robustness
    debug_mode = str(debug).lower() in ("true", "1", "t", "yes", "on")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    temp_input_path = None
    # No verify path here yet as it comes from service result
    
    try:
        # Save uploaded PDF temp
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
            shutil.copyfileobj(file.file, temp_input)
            temp_input_path = temp_input.name

        # Process
        print(f"Processing PDF: {file.filename}, Target Lang: {target_lang}, Debug: {debug_mode}")
        
        # Async execution allows non-blocking I/O during long LLM translation
        result_list = await pdf_service.process_pdf(
            temp_input_path, 
            force_target_lang=target_lang,
            debug_mode=debug_mode
        )
        
        # The service returns a list with one item containing the file_path
        output_pdf_path = result_list[0]["file_path"]
        
        # Convert translated PDF into DOCX
        output_docx_path = output_pdf_path.replace(".pdf", ".docx")
        with_docx = False
        try:
            from pdf2docx import Converter
            print(f"[PDF2DOCX] Converting {output_pdf_path} to DOCX...")
            cv = Converter(output_pdf_path)
            cv.convert(output_docx_path, start=0, end=None)
            cv.close()
            with_docx = True
            print("[PDF2DOCX] Conversion success")
        except Exception as e:
            print(f"[PDF2DOCX] Failed to convert to docx: {e}")
        
        # Encode to Base64
        import base64
        with open(output_pdf_path, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode('utf-8')
            
        docx_b64 = None
        if with_docx and os.path.exists(output_docx_path):
            with open(output_docx_path, 'rb') as f:
                docx_b64 = base64.b64encode(f.read()).decode('utf-8')
        
        # Add cleanup tasks
        background_tasks.add_task(os.remove, temp_input_path)
        background_tasks.add_task(os.remove, output_pdf_path)
        if with_docx and os.path.exists(output_docx_path):
            background_tasks.add_task(os.remove, output_docx_path)

        return {
            "pdf_base64": pdf_b64,
            "docx_base64": docx_b64
        }

    except Exception as e:
        # Immediate cleanup if failure
        if temp_input_path and os.path.exists(temp_input_path):
            os.remove(temp_input_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat_text(payload: dict):
    """
    Direct text chat endpoint.
    Expects JSON: {"text": "user message"}
    """
    try:
        user_text = payload.get("text")
        if not user_text:
            raise HTTPException(status_code=400, detail="Text field is required")

        llm_response = await llm_service.chat(user_text)
        return {"llm_response": llm_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/factory-chat")
async def factory_chat(payload: dict):
    """
    Factory Data Q&A Interface (Integrated SQL + RAG)
    Supports session-based conversation history via Redis.
    """
    from app.services.factory.factory_redis import factory_store
    try:
        user_text = payload.get("text")
        session_id = payload.get("session_id")  # Optional: continue existing session
        print(f"\n[Factory Chat] Request: '{user_text}' (session={session_id})", flush=True)

        if not user_text:
            raise HTTPException(status_code=400, detail="Text field is required")

        # Create new session if none provided
        if not session_id:
            session = await factory_store.create_session(user_text)
            session_id = session["session_id"]

        # Delegate to Factory Agent for routing and execution
        response = await factory_agent.chat(user_text)

        # Save the Q&A pair to session
        await factory_store.append_messages(session_id, user_text, response)

        print(f"[Factory Chat] Success: Response length {len(response)}", flush=True)
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
