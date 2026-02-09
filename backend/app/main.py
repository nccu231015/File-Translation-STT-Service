import os
import shutil
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Response, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.services.stt_service import stt_service
from app.services.llm_service import llm_service
from app.services.pdf_service import pdf_service
from app.services.meeting_minutes_docx import MeetingMinutesDocxService
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

# Trigger reload for env update


# Middleware to help Ngrok bypass browser warning
@app.middleware("http")
async def add_ngrok_header(request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            llm_response = llm_service.chat(user_text)
            return {"transcription": stt_result, "llm_response": llm_response}

        # --- MEETING MODE ---
        elif mode == "meeting":
            print("Mode: Meeting - Analyzing Transcript in background...", flush=True)
            analysis = await run_in_threadpool(llm_service.analyze_meeting_transcript, user_text)
            
            # 1. Prepare frontend summary and safe lists FIRST
            # Combine objective and summary for the simplified frontend view
            frontend_summary = ""
            if analysis.get('meeting_objective'):
                frontend_summary += f"【會議目的】\n{analysis.get('meeting_objective')}\n\n"
            
            # Handle discussion_summary if it's a list (some LLMs output lists)
            disc_sum = analysis.get('discussion_summary', analysis.get('summary', ''))
            if isinstance(disc_sum, list):
                try:
                    disc_text = ""
                    for item in disc_sum:
                        if isinstance(item, dict):
                            disc_text += f"- {item.get('topic', '')}: {item.get('description', '')}\n"
                        else:
                            disc_text += f"- {str(item)}\n"
                    frontend_summary += f"【討論摘要】\n{disc_text}"
                except:
                    frontend_summary += f"【討論摘要】\n{str(disc_sum)}"
            else:
                frontend_summary += f"【討論摘要】\n{disc_sum}"

            # Ensure lists are strictly lists to avoid bug where strings are iterated by char
            safe_decisions = analysis.get('decisions', [])
            if not isinstance(safe_decisions, list):
                if isinstance(safe_decisions, str):
                    safe_decisions = [safe_decisions]
                else:
                    safe_decisions = []
            
            safe_action_items = analysis.get('action_items', [])
            if not isinstance(safe_action_items, list):
                safe_action_items = []

            # 2. Generate Word document using SAFE structured data
            minutes_service = MeetingMinutesDocxService()
            docx_bytes = minutes_service.generate_minutes(
                file_name=file.filename,
                meeting_objective=analysis.get('meeting_objective', ''),
                discussion_summary=disc_sum,  # Pass original structure, formatter handles it
                decisions=safe_decisions,     # Pass SAFE list
                action_items=safe_action_items, # Pass SAFE list
                attendees=analysis.get('attendees', []),
                schedule_notes=analysis.get('schedule_notes', '')
            )
            
            output_filename = f"meeting_minutes_{os.path.splitext(file.filename)[0]}.docx"
            
            # Return base64 encoded Word file for frontend download
            import base64
            docx_base64 = base64.b64encode(docx_bytes).decode('utf-8')
            
            frontend_analysis = {
                "summary": frontend_summary,
                "decisions": safe_decisions,
                "action_items": safe_action_items
            }

            return {
                "transcription": stt_result,
                "analysis": frontend_analysis,
                "file_download": {
                    "filename": output_filename,
                    "content_base64": docx_base64,
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
    debug: bool = Form(False) # Debug mode flag
):
    """
    Receives a PDF file, extracts text, translates it, and returns the translated PDF file.
    If debug=True, returns PDF with bounding boxes instead of translation.
    """
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
        print(f"Processing PDF: {file.filename}, Target Lang: {target_lang}, Debug: {debug}")
        
        # Async execution allows non-blocking I/O during long LLM translation
        result_list = await pdf_service.process_pdf(
            temp_input_path, 
            force_target_lang=target_lang,
            debug_mode=debug
        )
        
        # The service returns a list with one item containing the file_path
        output_pdf_path = result_list[0]["file_path"]
        
        # Determine filename for download
        filename_only = os.path.splitext(file.filename)[0]
        download_filename = f"{filename_only}_translated.pdf"
        
        # Add cleanup tasks
        background_tasks.add_task(os.remove, temp_input_path)
        background_tasks.add_task(os.remove, output_pdf_path)

        return FileResponse(
            output_pdf_path, 
            media_type="application/pdf", 
            filename=download_filename
        )

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

        llm_response = llm_service.chat(user_text)
        return {"llm_response": llm_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



