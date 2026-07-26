# ==============================================================================
# VCC (Vehicle Classification & Counting) Unified Production Dockerfile
# Optimized for Raspberry Pi (ARM64 / aarch64) and x86_64 CPU environments
# ==============================================================================

# ------------------------------------------------------------------------------
# STAGE 1: Frontend Build Stage
# ------------------------------------------------------------------------------
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package manifests
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source code
COPY frontend/ ./

# Set environment variables for static build
ENV VITE_API_URL=""
ENV VITE_STREAM_BASE_URL=""

# Build React application (dist/ contains main dashboard and training.html)
RUN npm run build

# ------------------------------------------------------------------------------
# STAGE 2: Python Runtime & Deployment Stage
# ------------------------------------------------------------------------------
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies (OpenCV, GStreamer, FFmpeg, Nginx, Supervisor)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    git \
    libgl1 \
    libglib2.0-0 \
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-tools \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirement files first for layer caching
COPY backend/requirements.txt /app/backend/requirements.txt
COPY detection/requirements.txt /app/detection/requirements.txt

# Install PyTorch CPU + Ultralytics + OpenCV Headless + all dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r /app/backend/requirements.txt && \
    pip install --no-cache-dir -r /app/detection/requirements.txt && \
    pip install --no-cache-dir opencv-python-headless pyyaml

# Copy application source code
COPY backend /app/backend
COPY detection /app/detection
COPY run_all.py start_detection.py setup_and_run.py /app/

# Copy pretrained model weights into /app
COPY yolo*.pt /app/

# Copy built frontend assets from STAGE 1
COPY --from=frontend-builder /app/frontend/dist /var/www/vcc/dist

# Copy Nginx and Supervisor configurations
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create runtime directories for data persistence
RUN mkdir -p /app/backend/training_data/images \
             /app/backend/training_data/labels \
             /app/backend/training_data/split \
             /app/backend/training_data/models \
             /app/uploads/videos \
             /var/log/supervisor

# Set Python path
ENV PYTHONPATH="/app/backend:/app/detection:/app" \
    VCC_MODEL_PATH="/app/yolo11n.pt" \
    VCC_FALLBACK_MODEL="/app/yolo11n.pt" \
    DATABASE_URL="sqlite+aiosqlite:////app/vcc.db"

# Expose ports
# 80 / 5173: Frontend Dashboard & Nginx Proxy
# 5174: Training Studio UI
# 8000: Backend API
# 8001: Detection Streamer
# 8002: Training Service API
EXPOSE 80 5173 5174 8000 8001 8002

# Health check to ensure Backend and Streamer are responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# Start supervisord process supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
