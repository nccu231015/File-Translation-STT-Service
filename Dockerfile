# Build Backend & Runtime
FROM python:3.11-slim

# Install system dependencies (ffmpeg is needed for audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast python package management
RUN pip install uv
ENV UV_HTTP_TIMEOUT=300

# Copy ONLY pyproject.toml FIRST
COPY backend/pyproject.toml ./

# Install dependencies
RUN uv sync

# Copy Backend Source Code
COPY backend/app ./app
COPY backend/.env.example ./.env

EXPOSE 8000

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "3600"]
