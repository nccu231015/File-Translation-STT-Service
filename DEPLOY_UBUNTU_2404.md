# Deployment Guide for Ubuntu 24.04 (AI Host)

**Host Specs:**
- **OS:** Ubuntu 24.04.3 LTS (Noble Numbat)
- **Kernel:** Linux 6.8.0
- **Virtualization:** Nutanix AHV (KVM)

This guide covers setting up the environment for:
1.  **Frontend:** Node.js + PM2 (Next.js)
2.  **Backend:** Docker + NVIDIA Container Toolkit (FastAPI + GPU)

---

## 1. System Preparation (Run as Root/Sudo)

### Update System
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git build-essential
```

### Install Node.js v20 (LTS)
Ubuntu 24.04 default nodejs might be older or newer, let's allow `nodesource` to manage it for stability.
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Install PM2 (Process Manager)
```bash
sudo npm install -g pm2
```

---

## 2. Docker & NVIDIA Setup (Backend)

### Verify Docker Installation
Since you already have Docker v29.x installed, just verify user permissions:
```bash
# Check if current user is in docker group (to run without sudo)
groups | grep docker

# If not, add user to group and re-login
sudo usermod -aG docker $USER
newgrp docker
```

### Install NVIDIA Container Toolkit
**CRITICAL:** Even with Docker installed, you MUST install this toolkit to allow containers to access the GPU.

```bash
# 1. Configure the repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. Install the toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. Configure Docker runtime
sudo nvidia-ctk runtime configure --runtime=docker

# 4. Restart Docker to apply changes
sudo systemctl restart docker
```

---

## 3. Deploy Backend

Navigate to the project root (`File-Translation-STT-Service/`).

```bash
# 1. Build and Start Backend Container
# --build ensures we use the latest Dockerfile
sudo docker compose up -d --build

# 2. Verify Status
sudo docker compose ps
# Status should be "Up"

# 3. Verify GPU Access
sudo docker exec -it stt-translation-app nvidia-smi
# You should see the NVIDIA GPU details inside the container
```

---

## 4. Deploy Frontend

Navigate to the frontend directory (`File-Translation-STT-Service/frontend/`).

```bash
cd frontend

# 1. Install Dependencies
npm install

# 2. Build Next.js Application
# Note: Ensure NEXT_PUBLIC_API_URL points to your backend IP/Domain if external, 
# or localhost if accessed locally (but users access via browser, so usually needs public IP/Domain)
# For local testing on the server itself, localhost is fine.
npm run build

# 3. Start with PM2
pm2 start ecosystem.config.js

# 4. Save PM2 list (auto-resurrect on reboot)
pm2 save
pm2 startup
# (Run the command output by pm2 startup)
```

---

## 5. Troubleshooting

- **Backend errors:** Check logs with `sudo docker compose logs -f app`
- **Frontend errors:** Check logs with `pm2 logs`
- **GPU not found:** Ensure `nvidia-smi` works on the host machine first. If not, install host drivers: `sudo apt install -y nvidia-driver-535` (or appropriate version).
