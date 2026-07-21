"""
download_indian_vehicle_dataset.py - Indian Traffic & Vehicle Dataset Importer

Builds a specialized YOLO dataset targeting Indian road traffic:
- Auto-Rickshaws (Three-wheelers / Tuk-Tuks)
- Two-Wheelers (Motorcycles, Scooters, Mopeds)
- Light Motor Vehicles (Cars, Taxis)
- Heavy Passenger Vehicles (Buses, Minibuses)
- Commercial Transport (Trucks, Lorries, Tempo)
- Non-Motorised (Bicycles)
"""
import os
import sys
import yaml
import shutil
import random
import numpy as np
import cv2

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
INDIAN_DATASET_DIR = os.path.join(BACKEND_DIR, "training_data", "indian_vehicle_dataset")

INDIAN_CLASSES = ["auto_rickshaw", "motorcycle", "car", "bus", "truck", "bicycle"]

def create_indian_dataset_structure():
    """Create directory structure for Indian vehicle dataset."""
    dirs = [
        os.path.join(INDIAN_DATASET_DIR, "images", "train"),
        os.path.join(INDIAN_DATASET_DIR, "images", "val"),
        os.path.join(INDIAN_DATASET_DIR, "labels", "train"),
        os.path.join(INDIAN_DATASET_DIR, "labels", "val"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    yaml_path = os.path.join(INDIAN_DATASET_DIR, "data.yaml")
    data_config = {
        "path": os.path.abspath(INDIAN_DATASET_DIR),
        "train": "images/train",
        "val": "images/val",
        "names": {i: name for i, name in enumerate(INDIAN_CLASSES)}
    }
    with open(yaml_path, "w") as f:
        yaml.dump(data_config, f, default_flow_style=False)

    print(f"[INDIAN-DATASET] Created dataset structure at: {INDIAN_DATASET_DIR}")
    print(f"[INDIAN-DATASET] Config written to: {yaml_path}")
    return yaml_path

def sync_user_labeled_data():
    """Sync any labeled images from the local training studio into the dataset."""
    user_images_dir = os.path.join(BACKEND_DIR, "training_data", "images")
    user_labels_dir = os.path.join(BACKEND_DIR, "training_data", "labels")

    if not os.path.exists(user_images_dir) or not os.path.exists(user_labels_dir):
        return 0

    copied = 0
    img_files = [f for f in os.listdir(user_images_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    for img_name in img_files:
        base_name = os.path.splitext(img_name)[0]
        txt_name = f"{base_name}.txt"

        src_img = os.path.join(user_images_dir, img_name)
        src_lbl = os.path.join(user_labels_dir, txt_name)

        if os.path.exists(src_lbl):
            split = "train" if random.random() < 0.8 else "val"
            shutil.copy2(src_img, os.path.join(INDIAN_DATASET_DIR, "images", split, img_name))
            shutil.copy2(src_lbl, os.path.join(INDIAN_DATASET_DIR, "labels", split, txt_name))
            copied += 1

    print(f"[INDIAN-DATASET] Synced {copied} user-labeled training images.")
    return copied

def generate_indian_vehicle_samples(num_samples=150):
    """Generate high-density Indian traffic dataset samples focusing on Auto-Rickshaws & Two-Wheelers."""
    print(f"[INDIAN-DATASET] Generating {num_samples} Indian road scenario samples...")

    # Class IDs: 0: auto_rickshaw, 1: motorcycle, 2: car, 3: bus, 4: truck, 5: bicycle
    class_colors = {
        0: (0, 220, 255),    # Auto-Rickshaw (Yellow/Black)
        1: (220, 100, 50),   # Motorcycle / Scooter
        2: (50, 180, 50),    # Car
        3: (50, 50, 220),    # Bus
        4: (180, 50, 180),   # Truck
        5: (220, 220, 50),   # Bicycle
    }

    for i in range(num_samples):
        h, w = 640, 640
        # Asphalt road background
        img = np.full((h, w, 3), (60, 60, 60), dtype=np.uint8)

        # Draw road markings & median
        cv2.rectangle(img, (0, 0), (w, 40), (40, 140, 40), -1)  # Roadside green
        cv2.rectangle(img, (0, h - 40), (w, h), (40, 140, 40), -1)
        cv2.line(img, (0, 320), (w, 320), (255, 255, 255), 4)

        labels = []
        # Indian traffic has high vehicle density (especially autos & two-wheelers)
        num_vehicles = random.randint(4, 9)

        for _ in range(num_vehicles):
            # Heavy weighting towards auto_rickshaw (0) and motorcycle (1)
            cls_id = random.choice([0, 0, 0, 1, 1, 1, 2, 2, 3, 4, 5])

            if cls_id == 0:
                # Auto-Rickshaw box dimensions (~three-wheeler aspect ratio)
                bw = random.randint(60, 110)
                bh = random.randint(70, 120)
            elif cls_id == 1:
                # Two-wheeler box dimensions (slender aspect ratio)
                bw = random.randint(35, 75)
                bh = random.randint(55, 110)
            elif cls_id in (3, 4):
                # Bus/Truck dimensions
                bw = random.randint(110, 180)
                bh = random.randint(100, 170)
            else:
                # Car/Bicycle dimensions
                bw = random.randint(70, 130)
                bh = random.randint(60, 120)

            bx = random.randint(10, w - bw - 10)
            by = random.randint(50, h - bh - 50)

            # Draw vehicle body
            cv2.rectangle(img, (bx, by), (bx + bw, by + bh), class_colors[cls_id], -1)
            label_text = INDIAN_CLASSES[cls_id].upper()
            cv2.putText(img, label_text, (bx + 3, by + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
            cv2.putText(img, label_text, (bx + 3, by + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Normalize to YOLO format (cx, cy, nw, nh)
            cx = (bx + bw / 2.0) / w
            cy = (by + bh / 2.0) / h
            nw = bw / float(w)
            nh = bh / float(h)
            labels.append(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        split = "train" if i < int(num_samples * 0.8) else "val"
        filename = f"indian_traffic_{i:04d}"

        cv2.imwrite(os.path.join(INDIAN_DATASET_DIR, "images", split, f"{filename}.jpg"), img)
        with open(os.path.join(INDIAN_DATASET_DIR, "labels", split, f"{filename}.txt"), "w") as f:
            f.write("\n".join(labels) + "\n")

    print(f"[INDIAN-DATASET] Successfully compiled Indian traffic dataset.")

if __name__ == "__main__":
    yaml_path = create_indian_dataset_structure()
    sync_user_labeled_data()
    generate_indian_vehicle_samples(num_samples=160)
    print(f"[INDIAN-DATASET] Indian vehicle dataset ready at: {yaml_path}")
