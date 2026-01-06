import mlx_whisper
import time


class STTService:
    def __init__(self, model_size="large-v3"):
        # mlx-whisper doesn't load a persistent object in the same way,
        # but we can set the default model here used for transcribing.
        # "mlx-community/whisper-large-v3-mlx" is the huggingface repo for mlx optimized weights
        self.model_path = f"mlx-community/whisper-{model_size}-mlx"
        print(f"STT Service initialized. Using MLX model: {self.model_path}")

    def transcribe(self, audio_path: str):
        """
        Transcribes the given audio file using MLX Whisper (GPU accelerated).
        """
        start_time = time.time()

        # mlx_whisper.transcribe automatically uses Metal (GPU) on Mac
        # Returns a dict with 'text' and 'segments'
        result = mlx_whisper.transcribe(
            audio_path, path_or_hf_repo=self.model_path, verbose=False
        )

        processing_time = time.time() - start_time

        # Format the result to match our previous structure if possible,
        # though mlx result structure is quite standard (similar to openai whisper)

        return {
            "text": result.get("text", "").strip(),
            "segments": result.get("segments", []),
            "language": result.get("language", "unknown"),
            "processing_time": processing_time,
        }


# Global instance
# You can change model_size to "base", "small", "medium", "large-v3"
# Since MLX is fast, "large-v3" might be usable, but "small" or "medium" is safer for speed.
stt_service = STTService(model_size="small")
