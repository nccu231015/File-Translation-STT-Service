import os
import shutil
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from app.services.stt_service import stt_service
from app.services.llm_service import llm_service
from app.services.pdf_service import pdf_service
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

        # Transcribe
        stt_result = stt_service.transcribe(temp_file_path)

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
            print("Mode: Meeting - Analyzing Transcript...")
            analysis = llm_service.analyze_meeting_transcript(user_text)
            
            # Create a formatted TXT file response
            output_filename = f"meeting_minutes_{os.path.splitext(file.filename)[0]}.txt"
            
            transcript_section = f"--- 逐字稿 ---\n{user_text}\n"
            
            output_content = (
                f"=== 會議記錄 ===\n"
                f"檔案名稱: {file.filename}\n"
                f"處理模式: 會議錄製\n\n"
                f"{transcript_section}\n"
                f"--- 重點摘要 ---\n{analysis.get('summary', '無')}\n\n"
                f"--- 決策事項 ---\n" + "\n".join([f"- {d}" for d in analysis.get("decisions", [])]) + "\n\n"
                f"--- 待辦清單 ---\n" + "\n".join([f"- {a}" for a in analysis.get("action_items", [])])
            )
            
            # Save to a temp location if needed, or just return content directly?
            # Current frontend expects 'filename' and 'content' for download or display?
            # Let's match the structure of PDF response slightly for consistency if needed,
            # or return a specific structure for the new frontend.
            
            return {
                "transcription": stt_result,
                "analysis": analysis,
                "file_download": {
                    "filename": output_filename,
                    "content": output_content
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
    file: UploadFile = File(...),
    target_lang: str = Form(None) # Optional, default None to let service auto-detect
):
    """
    Receives a PDF file, extracts text, translates it, and returns the text content.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    try:
        # Save uploaded PDF temp
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_input:
            shutil.copyfileobj(file.file, temp_input)
            temp_input_path = temp_input.name

        # Process
        print(f"Processing PDF: {file.filename}, Target Lang: {target_lang}")
        pages_data = pdf_service.process_pdf(temp_input_path, force_target_lang=target_lang)

        # Cleanup input
        os.remove(temp_input_path)

        # Build full text content and extract summary
        full_text = ""
        summary = ""

        # Check if we have summary in the response (our new structure puts it in the first item)
        if pages_data and "summary" in pages_data[0]:
            summary = pages_data[0]["summary"]
            print(f"Got Summary for {file.filename}")

            # Add summary to LLM context
            llm_service.add_document_context(file.filename, summary)

        for page in pages_data:
            # page['page'] might be string "Full Document" now
            if page["page"] != "Full Document":
                full_text += f"=== PAGE {page['page']} ===\n"

            for para in page["paragraphs"]:
                full_text += para + "\n\n"

        return {
            "filename": f"{os.path.splitext(file.filename)[0]}_translated.txt",
            "content": full_text,
            "summary": summary,
        }

    except Exception as e:
        # Cleanup
        if "temp_input_path" in locals() and os.path.exists(temp_input_path):
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



