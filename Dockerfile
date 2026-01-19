# Stage 1: Build Frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
# Copy package files
COPY frontend/package*.json ./
# Install dependencies
RUN npm install
# Copy source code
COPY frontend/ .
# Build
RUN npm run build

# Stage 2: Build Backend & Runtime
FROM python:3.11-slim

# Install system dependencies (ffmpeg is needed for audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend requirements/project files
COPY backend/pyproject.toml backend/uv.lock ./backend/
COPY README.md ./backend/

# Install uv and dependencies
# We install uv globally, then use it to install dependencies into system python
# (Since we are in a container, we don't strictly need a virtualenv)
RUN pip install uv
WORKDIR /app/backend
RUN uv sync --frozen --no-install-project

# Copy Backend Source Code
COPY backend/app ./app
COPY backend/.env.example ./.env

# Copy Built Frontend Assets from Stage 1
# Backend expects frontend dist at ../frontend/dist realtive to backend/
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose port
EXPOSE 8000

# Set Python path to include backend directory
ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1

# Command to run the application
# Using uv run to ensure we use the environment created by uv
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
