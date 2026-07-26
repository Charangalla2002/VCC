#!/bin/bash
# ==============================================================================
# VCC (Vehicle Classification & Counting) Raspberry Pi 5 Docker Deployment Script
# ==============================================================================

set -e

echo "======================================================================"
echo " VCC RASPBERRY PI DOCKER DEPLOYMENT SCRIPT"
echo "======================================================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "[1/4] Docker not found! Installing Docker for Raspberry Pi OS..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "[!] Docker installed successfully! Please log out and back in if running non-sudo."
else
    echo "[1/4] Docker is already installed."
fi

# Check Docker Compose plugin
if ! docker compose version &> /dev/null; then
    echo "[!] Docker Compose plugin missing. Installing plugin..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

echo "[2/4] Building VCC Docker image for ARM64 architecture..."
docker compose build --pull

echo "[3/4] Starting VCC multi-service container..."
docker compose up -d

echo "[4/4] Verifying container status..."
sleep 5
docker compose ps

echo "======================================================================"
echo " DEPLOYMENT COMPLETE!"
echo "======================================================================"
echo "➜ Dashboard URL:       http://$(hostname -I | awk '{print $1}')/"
echo "➜ Dashboard (Port 5173):http://$(hostname -I | awk '{print $1}'):5173/"
echo "➜ Training Studio UI:  http://$(hostname -I | awk '{print $1}'):5174/"
echo "➜ Backend API Docs:    http://$(hostname -I | awk '{print $1}'):8000/docs"
echo "======================================================================"
echo "To view live logs:    docker compose logs -f"
echo "To stop application:  docker compose down"
echo "======================================================================"
