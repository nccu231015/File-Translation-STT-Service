# Use NVIDIA CUDA base image for GPU support
FROM nvidia/cuda:12.6.0-cudnn-runtime-ubuntu22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
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

# --- Install PyTorch with CUDA 12.6 support ---
RUN uv pip install --system torch torchvision --index-url https://download.pytorch.org/whl/cu126

# --- Install LayoutParser with EfficientDet ---
RUN uv pip install --system opencv-python-headless && \
    uv pip install --system "layoutparser[effdet]" && \
    uv pip install --system timm

# --- Pre-download PubLayNet EfficientDet model (official 5-class model) ---
RUN mkdir -p /root/.cache/layoutparser/models && \
    (wget -q --timeout=30 "https://www.dropbox.com/s/ukbw5s673633hsw/publaynet-tf_efficientdet_d0.pth.tar?dl=1" \
         -O /tmp/publaynet-tf_efficientdet_d0.pth.tar || \
     wget -q "https://ghproxy.com/https://www.dropbox.com/s/ukbw5s673633hsw/publaynet-tf_efficientdet_d0.pth.tar?dl=1" \
         -O /tmp/publaynet-tf_efficientdet_d0.pth.tar) && \
    (tar -xf /tmp/publaynet-tf_efficientdet_d0.pth.tar -C /root/.cache/layoutparser/models/ 2>/dev/null || \
     cp /tmp/publaynet-tf_efficientdet_d0.pth.tar /root/.cache/layoutparser/models/publaynet-tf_efficientdet_d0.pth) && \
    rm -f /tmp/publaynet-tf_efficientdet_d0.pth.tar || \
    echo "WARNING: PubLayNet model download/extraction failed"

# Verify installation
RUN python -c "import layoutparser as lp; import torch; print(f'✓ LayoutParser + EfficientDet ready (CUDA: {torch.cuda.is_available()})')"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
