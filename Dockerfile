# Use NVIDIA CUDA 12.1 DEVEL image (Required for Faster-Whisper/CUDA 12 and compiling Detectron2)
FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies (including build tools for Detectron2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3-dev \
    build-essential \
    ninja-build \
    ffmpeg \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create symlinks for python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

WORKDIR /app

# Install uv for faster package management
RUN pip install uv

# Copy pyproject.toml
COPY backend/pyproject.toml ./

# Install app dependencies
ENV UV_HTTP_TIMEOUT=500
RUN uv pip install --system -r pyproject.toml

# Copy Code
COPY backend/app ./app
COPY backend/.env.example ./.env

# --- Install PyTorch with CUDA 12.1 support ---
RUN uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# --- Install DocLayout-YOLO for Layout Detection ---
# Official installation method from: https://github.com/opendatalab/PDF-Extract-Kit
# Note: Must use pip directly (not uv) for --extra-index-url support
RUN pip install doclayout-yolo==0.0.2 --extra-index-url=https://pypi.org/simple

# --- Download DocLayout-YOLO Pre-trained Model ---
# Using official weights from HuggingFace
RUN mkdir -p /app/models/layout && \
    wget -q --show-progress \
    https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0/resolve/main/models/Layout/YOLO/doclayout_yolo_ft.pt \
    -O /app/models/layout/doclayout_yolo_ft.pt || \
    echo "WARNING: DocLayout-YOLO model download failed"

# Verify installation
RUN python -c "from doclayout_yolo import YOLOv10; print('✓ DocLayout-YOLO ready')"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
