#!/bin/bash
# ==============================================================================
# VCC - Direct PC/WSL to Raspberry Pi Sync Script (No GitHub Required)
# ==============================================================================

if [ -z "$1" ]; then
    echo "Usage: ./sync_to_pi.sh <PI_IP_ADDRESS> [PI_USER] [PI_PATH]"
    echo "Example: ./sync_to_pi.sh 192.168.1.50 pi /home/pi/VCC"
    exit 1
fi

PI_IP="$1"
PI_USER="${2:-pi}"
PI_PATH="${3:-/home/pi/VCC}"

echo "======================================================================"
echo " Syncing VCC Project to Raspberry Pi ($PI_USER@$PI_IP:$PI_PATH)"
echo "======================================================================"

# Ensure target folder exists on Pi
ssh "${PI_USER}@${PI_IP}" "mkdir -p ${PI_PATH}"

# Stream tar directly over SSH
echo "[1/2] Syncing code files..."
tar --exclude='.git' \
    --exclude='node_modules' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.db' \
    --exclude='dist' \
    -czf - . | ssh "${PI_USER}@${PI_IP}" "tar -xzf - -C ${PI_PATH}"

echo "[2/2] Rebuilding and launching Docker containers on Raspberry Pi..."
ssh "${PI_USER}@${PI_IP}" "cd ${PI_PATH} && docker compose up -d --build"

echo "======================================================================"
echo " SUCCESS! Application updated and running on http://${PI_IP}/"
echo "======================================================================"
