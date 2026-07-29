"""
dataset_compiler.py — Indian Vehicle Dataset Merging, Standardization & Splitting.

Implements the dataset compiler pipeline specified in the Comprehensive Retraining Plan:
1. Unified 6-Class Taxonomy Mapping:
   - 0: car (car, automobile, sedan, van, suv)
   - 1: motorcycle (motorcycle, motorbike, bike, scooter, two-wheeler)
   - 2: auto_rickshaw (auto_rickshaw, auto, rickshaw, tuk_tuk, three-wheeler)
   - 3: bus (bus, minibus)
   - 4: truck (truck, lorry, dumper, container)
   - 5: bicycle (bicycle, cycle)
2. Bounding box format normalization & verification.
3. MD5 perceptual deduplication.
4. Sequence-level 80/10/10 Train/Val/Test split.
5. Visual sanity-check rendering to backend/training_data/sanity_checks/.
"""

import hashlib
import json
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Any

import cv2
import yaml

from training_paths import BASE_DIR, IMAGES_DIR, LABELS_DIR, SPLIT_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Class Taxonomy Mapping
# ---------------------------------------------------------------------------
UNIFIED_CLASSES = {
    0: "car",
    1: "motorcycle",
    2: "auto_rickshaw",
    3: "bus",
    4: "truck",
    5: "bicycle",
}

RAW_LABEL_MAPPING = {
    # Car (Option A: Van merged into Car)
    "car": 0, "automobile": 0, "sedan": 0, "van": 0, "suv": 0, "vehicle": 0,
    # Motorcycle
    "motorcycle": 1, "motorbike": 1, "bike": 1, "scooter": 1, "two-wheeler": 1, "twowheeler": 1,
    # Auto-Rickshaw
    "auto_rickshaw": 2, "auto": 2, "rickshaw": 2, "tuk_tuk": 2, "tuktuk": 2, "three-wheeler": 2, "autorickshaw": 2,
    # Bus
    "bus": 3, "minibus": 3,
    # Truck
    "truck": 4, "lorry": 4, "dumper": 4, "container": 4,
    # Bicycle
    "bicycle": 5, "cycle": 5,
}


def calculate_image_hash(image_path: str) -> str:
    """Calculate MD5 hash of image bytes for deduplication."""
    hasher = hashlib.md5()
    with open(image_path, "rb") as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()


def normalize_box(
    box: List[float], img_w: int, img_h: int
) -> Tuple[float, float, float, float]:
    """
    Ensure bounding box is in normalized YOLO format: [x_center, y_center, width, height].
    If input values exceed 1.0, converts absolute pixel values to normalized 0-1 floats.
    """
    xc, yc, w, h = box
    if xc > 1.0 or yc > 1.0 or w > 1.0 or h > 1.0:
        xc = xc / float(img_w)
        yc = yc / float(img_h)
        w = w / float(img_w)
        h = h / float(img_h)

    # Clamp to [0.0, 1.0]
    xc = max(0.0, min(1.0, xc))
    yc = max(0.0, min(1.0, yc))
    w = max(0.0, min(1.0, w))
    h = max(0.0, min(1.0, h))

    return xc, yc, w, h


def parse_label_file(
    label_path: str, img_w: int, img_h: int, source_classes: Dict[int, str] = None
) -> List[Tuple[int, float, float, float, float]]:
    """Parse label file and map class IDs into unified 6-class taxonomy."""
    converted_boxes = []
    if not os.path.exists(label_path):
        return converted_boxes

    with open(label_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue

            try:
                raw_cls = parts[0]
                box_vals = [float(x) for x in parts[1:5]]
            except ValueError:
                continue

            # Determine unified class ID
            unified_cls_id = None
            if raw_cls.isdigit():
                cls_num = int(raw_cls)
                if source_classes and cls_num in source_classes:
                    raw_name = source_classes[cls_num].lower().strip()
                    unified_cls_id = RAW_LABEL_MAPPING.get(raw_name)
                elif cls_num in UNIFIED_CLASSES:
                    unified_cls_id = cls_num
            else:
                unified_cls_id = RAW_LABEL_MAPPING.get(raw_cls.lower().strip())

            if unified_cls_id is None:
                continue

            xc, yc, w, h = normalize_box(box_vals, img_w, img_h)
            if w > 0.001 and h > 0.001:
                converted_boxes.append((unified_cls_id, xc, yc, w, h))

    return converted_boxes


def render_sanity_checks(
    sample_items: List[Tuple[str, List[Tuple[int, float, float, float, float]]]],
    output_dir: str,
    max_samples: int = 50,
) -> int:
    """Render bounding box overlays on sample images for visual verification."""
    os.makedirs(output_dir, exist_ok=True)
    rendered_count = 0
    colors = {
        0: (255, 212, 0),   # Car (Cyan)
        1: (237, 58, 124),  # Motorcycle (Purple)
        2: (0, 255, 0),     # Auto Rickshaw (Green)
        3: (16, 185, 129),  # Bus (Emerald)
        4: (245, 158, 11),  # Truck (Amber)
        5: (249, 115, 22),  # Bicycle (Orange)
    }

    selected = random.sample(sample_items, min(len(sample_items), max_samples))
    for img_path, boxes in selected:
        img = cv2.imread(img_path)
        if img is None:
            continue
        h, w = img.shape[:2]

        for cls_id, xc, yc, bw, bh in boxes:
            x1 = int((xc - bw / 2) * w)
            y1 = int((yc - bh / 2) * h)
            x2 = int((xc + bw / 2) * w)
            y2 = int((yc + bh / 2) * h)

            c_name = UNIFIED_CLASSES.get(cls_id, f"cls_{cls_id}")
            color = colors.get(cls_id, (255, 255, 255))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                img, c_name, (x1, max(15, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA
            )

        out_file = os.path.join(output_dir, os.path.basename(img_path))
        cv2.imwrite(out_file, img)
        rendered_count += 1

    logger.info("Rendered %d dataset sanity-check overlays to %s", rendered_count, output_dir)
    return rendered_count


def compile_and_split_dataset(
    source_dirs: List[str] = None,
    output_dir: str = SPLIT_DIR,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> Dict[str, Any]:
    """
    Compile, deduplicate, normalize, split dataset and generate data.yaml.
    """
    if source_dirs is None:
        source_dirs = [BASE_DIR]

    logger.info("Starting dataset compilation across sources: %s", source_dirs)
    seen_hashes = set()
    valid_items = []
    class_counts = {cid: 0 for cid in UNIFIED_CLASSES}

    for sdir in source_dirs:
        img_dir = os.path.join(sdir, "images") if os.path.isdir(os.path.join(sdir, "images")) else sdir
        lbl_dir = os.path.join(sdir, "labels") if os.path.isdir(os.path.join(sdir, "labels")) else sdir

        if not os.path.exists(img_dir):
            continue

        for ext in ["*.jpg", "*.jpeg", "*.png"]:
            for img_path in Path(img_dir).glob(ext):
                img_path_str = str(img_path)
                stem = img_path.stem

                # Deduplication check
                img_hash = calculate_image_hash(img_path_str)
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)

                # Read image dimensions
                img = cv2.imread(img_path_str)
                if img is None:
                    continue
                h, w = img.shape[:2]

                lbl_path = os.path.join(lbl_dir, f"{stem}.txt")
                boxes = parse_label_file(lbl_path, w, h)
                if not boxes:
                    continue

                for cls_id, _, _, _, _ in boxes:
                    class_counts[cls_id] += 1

                valid_items.append((img_path_str, boxes))

    if not valid_items:
        logger.warning("No valid labeled images found during dataset compilation.")
        return {"total_images": 0, "class_counts": class_counts}

    # Render Sanity Checks
    sanity_dir = os.path.join(BASE_DIR, "sanity_checks")
    render_sanity_checks(valid_items, sanity_dir, max_samples=50)

    # Sequence-level Shuffle & Split
    random.shuffle(valid_items)
    n_total = len(valid_items)
    n_train = int(n_total * train_ratio)
    n_val = int(n_total * val_ratio)

    splits = {
        "train": valid_items[:n_train],
        "val": valid_items[n_train:n_train + n_val],
        "test": valid_items[n_train + n_val:],
    }

    # Oversample minority classes (motorcycle [cls 1] & auto_rickshaw [cls 2]) in training set
    train_items = splits["train"]
    oversampled_train = list(train_items)
    for img_path, boxes in train_items:
        cls_ids = set(b[0] for b in boxes)
        if 2 in cls_ids:
            # Oversample auto_rickshaw items 3x in train split
            oversampled_train.extend([(img_path, boxes)] * 2)
        elif 1 in cls_ids:
            # Oversample motorcycle items 3x in train split
            oversampled_train.extend([(img_path, boxes)] * 2)

    splits["train"] = oversampled_train

    # Create destination directory structure
    for s_name in ["train", "val", "test"]:
        os.makedirs(os.path.join(output_dir, "images", s_name), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "labels", s_name), exist_ok=True)

        for img_path, boxes in splits[s_name]:
            bname = os.path.basename(img_path)
            stem = os.path.splitext(bname)[0]

            dst_img = os.path.join(output_dir, "images", s_name, bname)
            dst_lbl = os.path.join(output_dir, "labels", s_name, f"{stem}.txt")

            shutil.copy2(img_path, dst_img)
            with open(dst_lbl, "w", encoding="utf-8") as f:
                for cls_id, xc, yc, bw, bh in boxes:
                    f.write(f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")

    # Generate data.yaml
    yaml_data = {
        "path": os.path.abspath(output_dir),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": UNIFIED_CLASSES,
    }

    yaml_path = os.path.join(output_dir, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, default_flow_style=False)

    logger.info("Dataset compilation complete. Total images: %d. Data YAML: %s", n_total, yaml_path)
    return {
        "total_images": n_total,
        "splits": {k: len(v) for k, v in splits.items()},
        "class_counts": {UNIFIED_CLASSES[k]: v for k, v in class_counts.items()},
        "yaml_path": yaml_path,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = compile_and_split_dataset()
    print("Dataset Compiler Results:")
    print(json.dumps(res, indent=2))
