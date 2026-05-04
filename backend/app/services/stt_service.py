import time
import threading
from contextlib import nullcontext

from faster_whisper import WhisperModel
import os

from .gpu_live_monitor import MODULE_VOICE, gpu_work_scope


class STTService:
    def __init__(self, model_size="tiny"):
        self.model_size = model_size
        self.model = None
        self.lock = threading.Lock()  # Protect model inference
        # Set in _ensure_model_loaded: "cuda" or "cpu"
        self.whisper_device = "cpu"

        # ── Pre-warm: load the model eagerly in a background thread ──────────
        # This kicks off as soon as the module is imported (i.e. at Docker
        # startup), so the model is ready before the first user request arrives.
        # The daemon=True flag means the thread won't prevent the process from
        # exiting if something goes wrong.
        threading.Thread(
            target=self._ensure_model_loaded,
            daemon=True,
            name="whisper-prewarm",
        ).start()
        print(f"[STT] Pre-warming {model_size} model in background thread...", flush=True)

    def _ensure_model_loaded(self):
        with self.lock:
            if self.model:
                return

            force_cpu = os.getenv("FORCE_CPU", "false").lower() == "true"
            print(f"Initializing STT Service with faster-whisper (Model: {self.model_size})...")

            if force_cpu:
                print("FORCE_CPU is enabled. Skipping CUDA check.")
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                self.whisper_device = "cpu"
            else:
                try:
                    # Try CUDA first
                    self.model = WhisperModel(self.model_size, device="cuda", compute_type="float16")
                    self.whisper_device = "cuda"
                    print("Successfully loaded model on GPU (CUDA).", flush=True)
                except Exception as e:
                    print(f"Failed to load on GPU ({e}). Falling back to CPU (int8).")
                    self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                    self.whisper_device = "cpu"

            print("[STT] Model pre-warm complete. Ready to transcribe.", flush=True)

    def transcribe(self, audio_path: str):
        """
        Transcribes the given audio file using faster-whisper.
        """
        start_time = time.time()

        try:
            sz = os.path.getsize(audio_path) if os.path.exists(audio_path) else -1
        except OSError:
            sz = -1

        self._ensure_model_loaded()

        print(
            f"[STT] transcribe_start path={audio_path} size_bytes={sz} device={self.whisper_device}",
            flush=True,
        )

        if not self.model:
            raise RuntimeError("STT Model not initialized")

        mgr = gpu_work_scope(MODULE_VOICE) if self.whisper_device == "cuda" else nullcontext()
        with mgr:
            segment_list = []
            text_list = []
            count = 0

            print(f"[STT] Starting transcription for {audio_path}...", flush=True)

            with self.lock:
                segments, info = self.model.transcribe(audio_path, beam_size=1, vad_filter=True)
                print(
                    f"Detected language '{info.language}' with probability {info.language_probability}",
                    flush=True,
                )

                for segment in segments:
                    count += 1
                    if count % 10 == 0:
                        print(f"Processed {count} segments...", flush=True)
                    text_list.append(segment.text)
                    segment_list.append(
                        {
                            "start": segment.start,
                            "end": segment.end,
                            "text": segment.text,
                        }
                    )

            full_text = "".join(text_list).strip()
            print(f"[STT] Transcription complete. Total segments: {count}", flush=True)

            processing_time = time.time() - start_time

            return {
                "text": full_text,
                "segments": segment_list,
                "language": info.language,
                "processing_time": processing_time,
            }


# Global instance
# Changed to "tiny" model for maximum speed
stt_service = STTService(model_size="tiny")
