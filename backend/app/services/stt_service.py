import time
import threading
import subprocess
import tempfile
import os
import shutil
from contextlib import nullcontext

from faster_whisper import WhisperModel

from .gpu_live_monitor import MODULE_VOICE, gpu_work_scope


def _env_bool(key: str, default: bool = True) -> bool:
    v = os.getenv(key, str(default)).lower()
    return v in ("1", "true", "yes", "on")


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _is_zh_or_en(lang: str | None) -> bool:
    """
    First-pass languages we accept without relistening: English, Chinese (incl. Cantonese yue).
    Anything else (e.g. ja, ko) may re-sample from a later offset and optionally re-transcribe.
    """
    if not lang:
        return False
    b = str(lang).strip().lower().split("-", 1)[0]
    if b == "en":
        return True
    if b.startswith("zh"):
        return True
    if b == "yue":
        return True
    return False


class STTService:
    def __init__(self, model_size="tiny"):
        self.model_size = model_size
        self.model = None
        self._init_lock = threading.Lock()  # Protect model initialization only (not inference)
        # Set in _ensure_model_loaded: "cuda" or "cpu"
        self.whisper_device = "cpu"

        threading.Thread(
            target=self._ensure_model_loaded,
            daemon=True,
            name="whisper-prewarm",
        ).start()
        print(f"[STT] Pre-warming {model_size} model in background thread...", flush=True)

    def _ensure_model_loaded(self):
        with self._init_lock:
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
                    self.model = WhisperModel(self.model_size, device="cuda", compute_type="float16")
                    self.whisper_device = "cuda"
                    print("Successfully loaded model on GPU (CUDA).", flush=True)
                except Exception as e:
                    print(f"Failed to load on GPU ({e}). Falling back to CPU (int8).")
                    self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                    self.whisper_device = "cpu"

            print("[STT] Model pre-warm complete. Ready to transcribe.", flush=True)

    @staticmethod
    def _ffprobe_duration_seconds(path: str) -> float | None:
        try:
            out = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if out.returncode != 0:
                return None
            return float((out.stdout or "").strip())
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired) as e:
            print(f"[STT] ffprobe duration failed: {e}", flush=True)
            return None

    @staticmethod
    def _ffmpeg_extract_slice(src_path: str, dst_wav: str, start_sec: float, duration_sec: float) -> bool:
        try:
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(max(0.0, start_sec)),
                    "-i",
                    src_path,
                    "-t",
                    str(max(0.1, duration_sec)),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    dst_wav,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if r.returncode != 0:
                print(f"[STT] ffmpeg extract failed: {r.stderr or r.stdout}", flush=True)
                return False
            return os.path.exists(dst_wav) and os.path.getsize(dst_wav) > 0
        except FileNotFoundError:
            print("[STT] ffmpeg not found; cannot run delayed language sample.", flush=True)
            return False
        except subprocess.TimeoutExpired:
            print("[STT] ffmpeg extract timed out.", flush=True)
            return False

    def _run_transcribe_collect(self, audio_path: str, *, language: str | None = None):
        """Run whisper; return (segment_list, full_text, info)."""
        assert self.model is not None
        kwargs: dict = {"beam_size": 1, "vad_filter": True}
        if language:
            kwargs["language"] = language
        segments, info = self.model.transcribe(audio_path, **kwargs)
        text_list: list[str] = []
        segment_list: list[dict] = []
        count = 0
        print(
            f"[STT] Detected language '{info.language}' with probability {info.language_probability}",
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
        print(f"[STT] Transcription segment pass complete. Total segments: {count}", flush=True)
        return segment_list, full_text, info

    def transcribe(self, audio_path: str):
        """
        Auto language first. If not zh/en/yue, optionally re-sample from STT_LANG_RELISTEN_OFFSET_SEC
        (default 30s); if the sample is zh/en/yue, re-transcribe the full file with that language.
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

        relisten = _env_bool("STT_LANG_RELISTEN_ENABLED", True)
        offset_sec = _env_float("STT_LANG_RELISTEN_OFFSET_SEC", 30.0)
        window_sec = _env_float("STT_LANG_RELISTEN_WINDOW_SEC", 30.0)

        mgr = gpu_work_scope(MODULE_VOICE) if self.whisper_device == "cuda" else nullcontext()
        with mgr:
            print(f"[STT] Starting transcription for {audio_path}...", flush=True)

            segment_list, full_text, info = self._run_transcribe_collect(audio_path, language=None)

            lang0 = info.language

            if (
                relisten
                and not _is_zh_or_en(lang0)
                and shutil.which("ffmpeg")
                and shutil.which("ffprobe")
            ):
                duration = self._ffprobe_duration_seconds(audio_path)
                if duration is None or duration <= offset_sec + 1.0:
                    print(
                        f"[STT] relisten skipped: duration={duration}s (need > {offset_sec}s); "
                        f"keeping initial language={lang0!r}",
                        flush=True,
                    )
                else:
                    print(
                        f"[STT] First pass lang={lang0!r} is not zh/en/yue — sampling audio "
                        f"[{offset_sec}s .. {offset_sec + window_sec}s] to re-detect language.",
                        flush=True,
                    )
                    fd, slice_path = tempfile.mkstemp(suffix=".wav")
                    os.close(fd)
                    try:
                        ok = self._ffmpeg_extract_slice(
                            audio_path, slice_path, start_sec=offset_sec, duration_sec=window_sec
                        )
                        if ok:
                            _, _txt, info_slice = self._run_transcribe_collect(slice_path, language=None)
                            alt = info_slice.language
                            print(
                                f"[STT] Delayed sample language={alt!r} p={info_slice.language_probability}",
                                flush=True,
                            )
                            if _is_zh_or_en(alt):
                                forced = str(alt).lower().strip()
                                print(
                                    f"[STT] Re-transcribing FULL file with language={forced!r} "
                                    f"(first pass was {lang0!r}).",
                                    flush=True,
                                )
                                segment_list, full_text, info = self._run_transcribe_collect(
                                    audio_path, language=forced
                                )
                            else:
                                print(
                                    f"[STT] Delayed sample still not zh/en/yue ({alt!r}); "
                                    f"keeping first-pass transcript (lang={lang0!r}).",
                                    flush=True,
                                )
                        else:
                            print("[STT] relisten slice extract failed; keeping first-pass result.", flush=True)
                    finally:
                        try:
                            os.remove(slice_path)
                        except OSError:
                            pass
            elif relisten and not _is_zh_or_en(lang0):
                print(
                    "[STT] relisten skipped: ffmpeg/ffprobe missing; keeping initial language.",
                    flush=True,
                )

            processing_time = time.time() - start_time

            return {
                "text": full_text,
                "segments": segment_list,
                "language": info.language,
                "processing_time": processing_time,
            }


# Global instance
stt_service = STTService(model_size="tiny")
