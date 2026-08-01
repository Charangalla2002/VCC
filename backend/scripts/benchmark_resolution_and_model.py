import os
import time
import logging
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT_DIR = os.path.join(BASE_DIR, "training_data", "split")
DATA_YAML = os.path.join(SPLIT_DIR, "data.yaml")

def benchmark_configs():
    print("=== TASK 1.5 & 1.6: Resolution & Model Variant Benchmark ===")
    
    if not os.path.exists(DATA_YAML):
        print(f"Error: {DATA_YAML} not found.")
        return

    test_configs = [
        ("yolo12n.pt", 640),
        ("yolo12n.pt", 960),
        ("yolo12s.pt", 640),
    ]

    print("\n| Model Variant | Inference Resolution | mAP50 | mAP50-95 | Inference Time (ms/img) | Estimated FPS | RPi Viability |")
    print("|---|---|---|---|---|---|---|")

    for model_name, imgsz in test_configs:
        try:
            model = YOLO(model_name)
            t0 = time.time()
            metrics = model.val(data=DATA_YAML, split="val", imgsz=imgsz, verbose=False)
            t1 = time.time()
            
            map50 = getattr(metrics.box, "map50", 0.0)
            map50_95 = getattr(metrics.box, "map", 0.0)
            
            # Extract inference speed
            speed_dict = getattr(metrics, "speed", {})
            infer_ms = speed_dict.get("inference", 200.0)
            fps = 1000.0 / max(1.0, infer_ms)
            
            rpi_status = "VIABLE (Target > 15 FPS)" if fps >= 15.0 else "⚠️ CPU HEAVY (Pi drops < 15 FPS)"
            
            print(f"| `{model_name}` | {imgsz}x{imgsz} | {map50:.4f} | {map50_95:.4f} | {infer_ms:.1f} ms | {fps:.1f} FPS | {rpi_status} |")
        except Exception as e:
            print(f"| `{model_name}` | {imgsz}x{imgsz} | N/A | N/A | N/A | N/A | Error: {e} |")

if __name__ == "__main__":
    benchmark_configs()
