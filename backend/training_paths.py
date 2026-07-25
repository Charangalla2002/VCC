"""
training_paths.py - Shared, dependency-free path & URL constants for the
training subsystem.

Every constant lives here so that **scheduler.py**, **training_process.py**,
and **routers/training.py** can all import the same values without pulling in
heavy ML dependencies (ultralytics, torch, etc.).

This module is intentionally stdlib-only.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

#: Root of the ``backend/`` package (this file lives inside it).
BACKEND_DIR: str = os.path.dirname(os.path.abspath(__file__))

#: Top-level training data folder shared across capture, labeling & training.
BASE_DIR: str = os.path.join(BACKEND_DIR, "training_data")

#: Captured JPEG frames saved by the scheduler and the capture endpoint.
IMAGES_DIR: str = os.path.join(BASE_DIR, "images")

#: YOLO-format ``.txt`` label files (one per image).
LABELS_DIR: str = os.path.join(BASE_DIR, "labels")

#: Train / val split folders prepared before launching the worker.
SPLIT_DIR: str = os.path.join(BASE_DIR, "split")

#: Directory where newly trained ``.pt`` model weights are written.
TRAINED_MODEL_DIR: str = os.path.join(BASE_DIR, "models")

#: Working directory used by the training subprocess.
TRAIN_WORK_DIR: str = os.path.join(BASE_DIR, "train_runs")

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

#: Base URL of the detection / MJPEG streamer (Port 8001).
STREAM_BASE_URL: str = os.getenv("VCC_STREAM_BASE_URL", "http://localhost:8001")

# ---------------------------------------------------------------------------
# Numeric thresholds
# ---------------------------------------------------------------------------

#: Minimum number of labeled images before training can start.
MIN_LABELED_IMAGES: int = int(os.getenv("VCC_MIN_LABELED_IMAGES", "10"))

#: If total labeled images ≥ this, the auto-capture scheduler may trigger a
#: training run automatically.
VCC_AUTO_TRAIN_THRESHOLD: int = int(os.getenv("VCC_AUTO_TRAIN_THRESHOLD", "50"))

# ---------------------------------------------------------------------------
# Subprocess / log constants
# ---------------------------------------------------------------------------

#: Prefix emitted on stdout by the training worker for structured events.
EVENT_PREFIX: str = "@@VCC "

#: Maximum number of log lines kept in the in-memory ring buffer.
TRAIN_LOG_LIMIT: int = 500

#: Seconds to wait between SIGTERM and SIGKILL when cancelling a training run.
TRAIN_CANCEL_GRACE_SECONDS: float = 10.0

# ---------------------------------------------------------------------------
# Ensure critical directories exist on first import.
# ---------------------------------------------------------------------------
for _d in (IMAGES_DIR, LABELS_DIR, SPLIT_DIR, TRAINED_MODEL_DIR, TRAIN_WORK_DIR):
    os.makedirs(_d, exist_ok=True)
