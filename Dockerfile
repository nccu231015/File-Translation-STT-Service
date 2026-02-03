# Use NVIDIA CUDA DEVEL image (Required for compiling Detectron2/CUDA extensions)
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

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

# --- Install PyTorch with CUDA 11.8 support (Matches Base Image) ---
# Detectron2 requires matching CUDA versions between System and PyTorch
RUN uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# --- Install Detectron2 from Source ---
# Using the main branch which supports PyTorch 2.x+
RUN python -m pip install 'git+https://github.com/facebookresearch/detectron2.git'

# --- Install LayoutParser with Detectron2 support ---
RUN uv pip install --system opencv-python-headless && \
    uv pip install --system "layoutparser[detectron2]"

# --- Pre-download Detectron2 PubLayNet Model (faster_rcnn_R_50_FPN_3x) ---
# Direct link from LayoutParser Model Zoo
RUN mkdir -p /root/.cache/layoutparser/models && \
    wget -q --timeout=60 "https://www.dropbox.com/s/dgy9c10wykk4lq4/model_final.pth?dl=1" \
         -O /root/.cache/layoutparser/models/faster_rcnn_R_50_FPN_3x.pth || \
    wget -q "https://ghproxy.com/https://www.dropbox.com/s/dgy9c10wykk4lq4/model_final.pth?dl=1" \
         -O /root/.cache/layoutparser/models/faster_rcnn_R_50_FPN_3x.pth || \
    echo "WARNING: Detectron2 model download failed"

# Verify installation
RUN python -c "import detectron2; import layoutparser as lp; print(f'✓ LayoutParser + Detectron2 ready')"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
