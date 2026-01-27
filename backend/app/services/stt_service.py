import time
from faster_whisper import WhisperModel
import os

class STTService:
    def __init__(self, model_size="small"):
        self.model_size = model_size
        self.model = None
        
        force_cpu = os.getenv("FORCE_CPU", "false").lower() == "true"
        
        print(f"Initializing STT Service with faster-whisper (Model: {model_size})...")
        
        if force_cpu:
             print("FORCE_CPU is enabled. Skipping CUDA check.")
             self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        else:
            try:
                # Try CUDA first
                # compute_type="float16" is standard for CUDA
                self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
                print("Successfully loaded model on GPU (CUDA).")
            except Exception as e:
                print(f"Failed to load on GPU ({e}). Falling back to CPU (int8).")
                # Fallback to CPU with int8 quantization for speed
                self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
        print("STT Service initialized.")

    def transcribe(self, audio_path: str):
        """
        Transcribes the given audio file using faster-whisper.
        """
        start_time = time.time()
        
        if not self.model:
            raise RuntimeError("STT Model not initialized")

        # beam_size=1 to save memory, default is 5
        print(f"Starting transcription for {audio_path}...")
        segments, info = self.model.transcribe(audio_path, beam_size=1)
        
        # Convert generator to list to consume and get full text
        # faster-whisper segments usually include necessary spacing in the text itself
        segment_list = []
        text_list = []
        
        print(f"Detected language '{info.language}' with probability {info.language_probability}")

        count = 0
        for segment in segments:
            count += 1
            if count % 10 == 0:
                print(f"Processed {count} segments...")
            text_list.append(segment.text)
            segment_list.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text
            })
        
        full_text = "".join(text_list).strip()
        print(f"Transcription complete. Total segments: {count}")
        
        processing_time = time.time() - start_time
        
        return {
            "text": full_text,
            "segments": segment_list,
            "language": info.language,
            "processing_time": processing_time,
        }


# Global instance
# Using "small" model as default balancing speed/accuracy
stt_service = STTService(model_size="small")
