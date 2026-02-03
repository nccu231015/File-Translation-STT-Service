# Use NVIDIA CUDA base image (Using 11.8 for best library compatibility)
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    ffmpeg \
    git \
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
RUN uv pip install --system -r pyproject.toml

# Copy Code
COPY backend/app ./app
COPY backend/.env.example ./.env

# --- Install PyTorch with CUDA 11.8 support ---
RUN uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# --- Install Detectron2 (Prebuilt for CUDA 11.8) ---
RUN python -m pip install detectron2 -f https://dl.fbaipublicfiles.com/detectron2/wheels/cu118/torch2.1/index.html

# --- Install LayoutParser with Detectron2 backend ---
RUN uv pip install --system opencv-python-headless && \
    uv pip install --system layoutparser

# Verify installation
RUN python -c "import layoutparser as lp; import detectron2; import torch; print(f'✓ LayoutParser + Detectron2 ready (CUDA: {torch.cuda.is_available()})')"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
