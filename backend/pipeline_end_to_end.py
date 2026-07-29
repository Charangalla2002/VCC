import os
import sys
import json
import time
import shutil
import glob
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("end_to_end_pipeline")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "backend"))
sys.path.append(os.path.join(BASE_DIR, "detection"))

from dataset_compiler import compile_and_split_dataset

INCOMING_DIR = os.path.join(BASE_DIR, "datasets", "incoming")
TRAINING_DATA_DIR = os.path.join(BASE_DIR, "backend", "training_data")
SPLIT_DIR = os.path.join(TRAINING_DATA_DIR, "split")
PROD_MODEL_PATH = os.path.join(BASE_DIR, "yolo12n.pt")


def step_1_pull_datasets():
    logger.info("=== STEP 1: Pulling External Datasets via Kaggle API ===")
    os.makedirs(INCOMING_DIR, exist_ok=True)
    import kagglehub

    datasets_to_pull = [
        ("daudshah/vehicle-detection-dataset", "roboflow_vehicle"),
        ("dataclusterlabs/indian-vehicle-dataset", "datacluster"),
        ("deepakmittal/iitm-hetra", "iitm_hetra"),
    ]

    downloaded_paths = {}
    for kaggle_id, folder_name in datasets_to_pull:
        target_path = os.path.join(INCOMING_DIR, folder_name)
        if os.path.exists(target_path) and len(os.listdir(target_path)) > 0:
            logger.info("Dataset %s already present at %s", folder_name, target_path)
            downloaded_paths[folder_name] = target_path
            continue

        logger.info("Downloading %s...", kaggle_id)
        try:
            cache_path = kagglehub.dataset_download(kaggle_id)
            os.makedirs(target_path, exist_ok=True)
            shutil.copytree(cache_path, target_path, dirs_exist_ok=True)
            logger.info("Successfully copied %s to %s", kaggle_id, target_path)
            downloaded_paths[folder_name] = target_path
        except Exception as e:
            logger.error("Failed to download %s: %s", kaggle_id, e)

    return downloaded_paths


def step_2_backup_current_state():
    logger.info("=== STEP 2: Mandatory Pre-Merge Safety Backup ===")
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_data_dir = os.path.join(BASE_DIR, "backend", f"training_data_backup_{ts}")
    backup_model_path = os.path.join(BASE_DIR, f"yolo12n_current_backup_{ts}.pt")

    os.makedirs(backup_data_dir, exist_ok=True)
    if os.path.exists(os.path.join(TRAINING_DATA_DIR, "images")):
        shutil.copytree(os.path.join(TRAINING_DATA_DIR, "images"), os.path.join(backup_data_dir, "images"), dirs_exist_ok=True)
    if os.path.exists(os.path.join(TRAINING_DATA_DIR, "labels")):
        shutil.copytree(os.path.join(TRAINING_DATA_DIR, "labels"), os.path.join(backup_data_dir, "labels"), dirs_exist_ok=True)

    if os.path.exists(PROD_MODEL_PATH):
        shutil.copy2(PROD_MODEL_PATH, backup_model_path)
        logger.info("Model backup created: %s", backup_model_path)

    logger.info("Safety backup complete at %s", backup_data_dir)
    return backup_data_dir, backup_model_path


def step_3_standardize_and_merge(incoming_paths):
    logger.info("=== STEP 3: Taxonomy Standardization, Deduplication & Splitting ===")
    existing_img_count = len(list(Path(os.path.join(TRAINING_DATA_DIR, "images")).glob("*.*"))) if os.path.exists(os.path.join(TRAINING_DATA_DIR, "images")) else 0

    source_dirs = [TRAINING_DATA_DIR] + list(incoming_paths.values())
    logger.info("Merging across sources: %s", source_dirs)

    res = compile_and_split_dataset(source_dirs=source_dirs)

    merged_count = res.get("total_images", 0)
    logger.info("=== DATASET INTEGRITY VERIFICATION ===")
    logger.info("Existing Image Count: %d", existing_img_count)
    logger.info("Final Merged Dataset Count: %d", merged_count)
    logger.info("Class Counts Breakdown: %s", res.get("class_counts", {}))

    return res


def step_4_baseline_evaluation():
    logger.info("=== STEP 4: Baseline Model Evaluation ===")
    from ultralytics import YOLO
    if not os.path.exists(PROD_MODEL_PATH):
        logger.warning("Production model %s not found. Using yolo12n.pt base.", PROD_MODEL_PATH)

    model = YOLO(PROD_MODEL_PATH if os.path.exists(PROD_MODEL_PATH) else "yolo12n.pt")
    data_yaml = os.path.join(SPLIT_DIR, "data.yaml")

    if os.path.exists(data_yaml):
        logger.info("Evaluating baseline YOLOv12 on test split...")
        try:
            metrics = model.val(data=data_yaml, split="test", verbose=False)
            map50 = getattr(metrics.box, "map50", 0.0)
            map50_95 = getattr(metrics.box, "map", 0.0)
            logger.info("Baseline mAP50: %.4f, mAP50-95: %.4f", map50, map50_95)
            return {"map50": map50, "map50_95": map50_95}
        except Exception as e:
            logger.error("Baseline evaluation failed: %s", e)
    return {"map50": 0.0, "map50_95": 0.0}


def main():
    logger.info("Starting End-to-End YOLOv12 Retraining Pipeline...")
    inc_paths = step_1_pull_datasets()
    b_data, b_model = step_2_backup_current_state()
    compile_res = step_3_standardize_and_merge(inc_paths)
    base_metrics = step_4_baseline_evaluation()
    logger.info("Pipeline Step 1 to 4 Complete. Baseline Metrics: %s", base_metrics)


if __name__ == "__main__":
    main()
