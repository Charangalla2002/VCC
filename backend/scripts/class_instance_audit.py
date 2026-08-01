import os
import glob
from pathlib import Path
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT_DIR = os.path.join(BASE_DIR, "training_data", "split")

UNIFIED_CLASSES = {
    0: "car",
    1: "motorcycle",
    2: "auto_rickshaw",
    3: "bus",
    4: "truck",
    5: "bicycle",
}

def audit_split_instances(split_dir: str):
    print("=== TASK 1.1: Class Instance Count Audit across Train/Val/Test Splits ===")
    
    splits = ["train", "val", "test"]
    raw_counts = defaultdict(lambda: defaultdict(int))
    
    for split in splits:
        labels_dir = os.path.join(split_dir, "labels", split)
        if not os.path.exists(labels_dir):
            print(f"Warning: Directory {labels_dir} does not exist.")
            continue
            
        label_files = glob.glob(os.path.join(labels_dir, "*.txt"))
        for l_file in label_files:
            with open(l_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    try:
                        cls_id = int(parts[0])
                        raw_counts[split][cls_id] += 1
                    except ValueError:
                        pass

    # Sum totals across all splits
    total_raw = defaultdict(int)
    for split in splits:
        for cid in UNIFIED_CLASSES:
            total_raw[cid] += raw_counts[split][cid]
            
    car_count = max(1, total_raw[0])
    
    # Print formatted Markdown table
    print("\n### Bounding Box Instance Count Audit Table\n")
    print("| Class ID | Class Name | Train Instances | Val Instances | Test Instances | Total Raw Instances | 3x Oversampled Est. | % of Car Instance Count | Status |")
    print("|---|---|---|---|---|---|---|---|---|")
    
    oversampling = {0: 1, 1: 3, 2: 3, 3: 1, 4: 1, 5: 1}
    
    for cid, cname in UNIFIED_CLASSES.items():
        tr = raw_counts["train"][cid]
        va = raw_counts["val"][cid]
        te = raw_counts["test"][cid]
        tot = total_raw[cid]
        os_est = tot * oversampling.get(cid, 1)
        pct = (tot / car_count) * 100.0
        
        status = "OK"
        if pct < 30.0:
            status = "IMPAIRMENT: Below 30% of Car Count"
            
        print(f"| {cid} | `{cname}` | {tr} | {va} | {te} | {tot} | {os_est} | {pct:.1f}% | {status} |")

if __name__ == "__main__":
    audit_split_instances(SPLIT_DIR)
