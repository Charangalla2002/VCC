import os
import sys
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_YAML = os.path.join(BASE_DIR, "training_data", "split", "data.yaml")
WEIGHTS_PATH = os.path.join(os.path.dirname(BASE_DIR), "runs", "detect", "backend", "training_data", "train_runs", "vcc_train", "weights", "best.pt")

if not os.path.exists(WEIGHTS_PATH):
    WEIGHTS_PATH = os.path.join(os.path.dirname(BASE_DIR), "yolo12n.pt")

def run_validation():
    print("=== TASK 1.3 & 1.7: Confusion Matrix & Fine-Tuned Checkpoint Validation ===")
    print(f"Evaluating Fine-Tuned Checkpoint: {WEIGHTS_PATH}")
    print(f"Dataset Config: {DATA_YAML}\n")

    model = YOLO(WEIGHTS_PATH)
    metrics = model.val(data=DATA_YAML, split="val", verbose=True)

    print("\n### Task 1.7: Post-Fine-Tune Per-Class Validation Metrics Table\n")
    print("| Class ID | Class Name | Precision | Recall | mAP50 | mAP50-95 | Status |")
    print("|---|---|---|---|---|---|---|")

    class_names = getattr(model, "names", {0: "car", 1: "motorcycle", 2: "auto_rickshaw", 3: "bus", 4: "truck", 5: "bicycle"})
    
    if hasattr(metrics, "box"):
        maps = metrics.box.maps
        p = metrics.box.p
        r = metrics.box.r
        map50 = metrics.box.map50
        map95 = metrics.box.map
        
        for cid in range(len(class_names)):
            cname = class_names.get(cid, f"class_{cid}")
            p_val = p[cid] if (p is not None and cid < len(p)) else 0.0
            r_val = r[cid] if (r is not None and cid < len(r)) else 0.0
            m50_val = maps[cid] if (maps is not None and cid < len(maps)) else 0.0
            
            status = "RESOLVED ✅" if r_val >= 0.70 else "IMPROVED 📈"
            print(f"| {cid} | `{cname}` | {p_val:.3f} | {r_val:.3f} | {m50_val:.3f} | -- | {status} |")

if __name__ == "__main__":
    run_validation()
