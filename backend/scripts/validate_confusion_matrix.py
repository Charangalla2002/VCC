import os
import sys
import logging
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT_DIR = os.path.join(BASE_DIR, "training_data", "split")
DATA_YAML = os.path.join(SPLIT_DIR, "data.yaml")
PROD_MODEL = os.path.join(os.path.dirname(BASE_DIR), "yolo12n.pt")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("confusion_matrix_val")

def run_validation():
    print("=== TASK 1.3: Empirical Confusion Matrix & Validation Benchmark ===")
    
    if not os.path.exists(DATA_YAML):
        print(f"Error: {DATA_YAML} not found. Run dataset compilation first.")
        return

    model_path = PROD_MODEL if os.path.exists(PROD_MODEL) else "yolo12n.pt"
    print(f"Loading model: {model_path}")
    model = YOLO(model_path)

    print(f"Evaluating model on dataset split: {DATA_YAML}")
    try:
        metrics = model.val(data=DATA_YAML, split="val", verbose=True)
        print("\n=== PER-CLASS METRICS SUMMARY ===")
        print(f"mAP50: {getattr(metrics.box, 'map50', 0.0):.4f}")
        print(f"mAP50-95: {getattr(metrics.box, 'map', 0.0):.4f}")
        print(f"Mean Precision: {getattr(metrics.box, 'mp', 0.0):.4f}")
        print(f"Mean Recall: {getattr(metrics.box, 'mr', 0.0):.4f}")
        
        if hasattr(metrics.box, "maps"):
            print("\nPer-class mAP50-95:", metrics.box.maps)
    except Exception as e:
        print(f"Validation failed: {e}")

if __name__ == "__main__":
    run_validation()
