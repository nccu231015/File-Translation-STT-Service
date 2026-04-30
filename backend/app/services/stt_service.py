import time
import threading
from faster_whisper import WhisperModel
import os


class STTService:
    def __init__(self, model_size="tiny"):
        self.model_size = model_size
        self.model = None
        self.lock = threading.Lock()  # Protect model inference

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
            else:
                try:
                    # Try CUDA first
                    self.model = WhisperModel(self.model_size, device="cuda", compute_type="float16")
                    print("Successfully loaded model on GPU (CUDA).", flush=True)
                except Exception as e:
                    print(f"Failed to load on GPU ({e}). Falling back to CPU (int8).")
                    self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

            print("[STT] Model pre-warm complete. Ready to transcribe.", flush=True)

    def transcribe(self, audio_path: str):
        """
        Transcribes the given audio file using faster-whisper.
        """
        start_time = time.time()
        t0 = time.monotonic()

        # Diagnostic breadcrumbs (helps locate hangs: model load vs lock vs transcribe vs segment iteration)
        def _elapsed_ms() -> float:
            return (time.monotonic() - t0) * 1000.0

        def _diag(msg: str) -> None:
            if os.getenv("STT_DIAGNOSTIC_LOG", "true").lower() in ("0", "false", "no", "off"):
                return
            print(f"[STT-TRACE] +{_elapsed_ms():.0f}ms {msg}", flush=True)

        try:
            sz = os.path.getsize(audio_path) if os.path.exists(audio_path) else -1
        except OSError:
            sz = -1
        _diag(f"transcribe_start path={audio_path} size_bytes={sz}")

        _diag("_ensure_model_loaded: enter (may block on lock if another thread loads model)")
        self._ensure_model_loaded()
        _diag("_ensure_model_loaded: done")

        if not self.model:
            raise RuntimeError("STT Model not initialized")

        force_cpu = os.getenv("FORCE_CPU", "false").lower() == "true"
        _diag(f"model_ready force_cpu={force_cpu}")

        print(f"Starting transcription for {audio_path}...", flush=True)

        segment_list = []
        text_list = []
        count = 0

        _diag("acquiring Whisper inference lock (another request may hold this)")
        with self.lock:
            _diag("inference lock acquired; calling faster_whisper.transcribe (VAD runs here)")
            segments, info = self.model.transcribe(audio_path, beam_size=1, vad_filter=True)
            _diag(
                "transcribe returned iterator; iterating segments "
                "(first forward pass often starts on first iteration)"
            )
            print(f"Detected language '{info.language}' with probability {info.language_probability}", flush=True)

            for segment in segments:
                count += 1
                if count == 1:
                    _diag(f"first_segment received end={segment.end:.2f}s")
                if count % 10 == 0:
                    print(f"Processed {count} segments...", flush=True)
                    _diag(f"segment_progress count={count}")
                text_list.append(segment.text)
                segment_list.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text
                })

        _diag(f"segment_loop_done total_segments={count}")
        full_text = "".join(text_list).strip()
        print(f"Transcription complete. Total segments: {count}", flush=True)

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
