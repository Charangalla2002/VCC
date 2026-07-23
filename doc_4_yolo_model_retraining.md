# Documentation 4: Model Training Studio — Optimal "Training Succeeded" Settings (`doc_4_yolo_model_retraining.md`)

This guide details the complete, tested, production-ready configuration required to guarantee that model training jobs in the **VCC Model Training Studio** (Port `5174` / Service Port `8002`) execute cleanly and succeed without memory errors, pipe write issues, or process deadlocks.

---

## ⚙️ 1. Subprocess Execution & Worker Settings

| Setting / Variable | Configured Value | Engineering Purpose & Protection |
| :--- | :--- | :--- |
| **Subprocess Mode** | Isolated Process (`training_worker.py`) | Decouples PyTorch / Ultralytics GIL workload from FastAPI server on ports `8000`/`8002`. |
| **Worker Threads (`workers`)** | `0` (Windows CPU) | Eliminates PyTorch multiprocessing pipe inheritance errors and GIL deadlocks (`OSError 22`). |
| **Progress Bar (`TQDM_DISABLE`)** | `1` | Disables tqdm stdout/stderr progress bars to prevent Windows subprocess pipe corruption. |
| **Stream Handler Wrappers** | `safe_stdout_write` / `safe_stderr_write` | Prevents pipe closed exceptions from terminating training prematurely. |
| **Work Directory (`TRAIN_WORK_DIR`)** | `backend/training_data/work` | Explicit CWD pinning prevents dangling `runs/` folders in root workspace. |

---

## 📊 2. Dataset Preparation & Splitting Rules

| Setting / Variable | Configured Value | System Rule & Safeguard |
| :--- | :--- | :--- |
| **Minimum Labeled Images** | `5` (`VCC_MIN_LABELED_IMAGES`) | Enforces dataset validation before spawning training job to avoid zero-sample failures. |
| **Train/Validation Split** | `80%` Train / `20%` Validation | Automatically allocates dataset with guaranteed minimum 1 validation image. |
| **YAML Formatting** | Forward Slashes (`C:/.../split`) | Prevents PyYAML Windows backslash escape syntax errors. |
| **Image Resolution (`imgsz`)** | `480` (`VCC_TRAIN_IMGSZ`) | Optimal feature resolution balance for CPU execution speed and accuracy. |
| **Default Base Model** | `yolo11n.pt` (`TRAIN_BASE_MODEL`) | Lightweight backbone with high accuracy and fast iteration time. |

---

## 🎯 3. Deployment & Weight Publishing

| Parameter | Configuration | Description |
| :--- | :--- | :--- |
| **Output Path** | `TRAINED_MODEL_DIR` (Repository Root) | Writes custom weights as `yolo11s_custom_v1.pt` (auto-incrementing to `v2`, `v3`). |
| **Environment Variable** | `VCC_MODEL_PATH=yolo11s_custom_v1.pt` | Set in `.env` for zero-downtime hot-reload in detection service (`start_detection.py`). |

---

## 🚀 4. Verification Checklist for Successful Training

1. **Auto-Capture & Annotation**:
   - Enable **Auto-Capture** on Port `5174` or click **Capture Frame Now**.
   - Annotate at least **5 images** using the Roboflow-style bounding box labeler or **Smart Click Auto-Annotation**.
2. **Submit Training Job**:
   - Go to **Train Model** tab, set Epochs = `10`, Batch Size = `8`, and click **Start Training Job**.
3. **Monitor Real-Time Logs**:
   - The UI log terminal streams structured `@@VCC` progress lines showing epoch loss and progress.
4. **Publish & Deploy**:
   - Upon completion, `yolo11s_custom_v1.pt` is generated in project root.
