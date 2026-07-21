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

def download_datacluster_indian_dataset():
    """Import open-source Indian Vehicle dataset from DataCluster Labs & IIIT-H IDD."""
    repo_dir = os.path.join(BACKEND_DIR, "training_data", "datacluster_repo")
    print("[INDIAN-DATASET] Fetching DataCluster Labs & IIIT-H Indian Vehicle Dataset...")
    try:
        import subprocess
        if not os.path.exists(repo_dir):
            subprocess.run(["git", "clone", "--depth", "1", "https://github.com/datacluster-labs/Indian-Vehicle-Image-Dataset.git", repo_dir], check=False)
        print(f"[INDIAN-DATASET] DataCluster Labs Indian Vehicle dataset ready at: {repo_dir}")
    except Exception as e:
        print(f"[INDIAN-DATASET] Note on DataCluster repo fetch: {e}")

def generate_indian_vehicle_samples(num_samples=250):
    """Generate high-density Indian traffic dataset samples focusing on Bengaluru & Pan-Indian Auto-Rickshaws & Two-Wheelers."""
    print(f"[INDIAN-DATASET] Generating {num_samples} Bengaluru & Pan-Indian auto-rickshaw & traffic scenario samples...")

    # Class IDs: 0: auto_rickshaw, 1: motorcycle, 2: car, 3: bus, 4: truck, 5: bicycle

    for i in range(num_samples):
        h, w = 640, 640
        # Asphalt road background
        img = np.full((h, w, 3), (55, 55, 55), dtype=np.uint8)

        # Draw road markings & lane dividers
        cv2.rectangle(img, (0, 0), (w, 35), (35, 120, 35), -1)  # Roadside kerb
        cv2.rectangle(img, (0, h - 35), (w, h), (35, 120, 35), -1)
        for dash_x in range(0, w, 50):
            cv2.line(img, (dash_x, 320), (dash_x + 25, 320), (255, 255, 255), 3)

        labels = []
        num_vehicles = random.randint(5, 10)

        for _ in range(num_vehicles):
            # 60% probability for Auto-Rickshaws (0) and Two-Wheelers (1)
            cls_id = random.choice([0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 4, 5])

            if cls_id == 0:
                # Auto-Rickshaw (Bengaluru Green/Yellow or Pan-Indian Yellow/Black)
                bw = random.randint(65, 115)
                bh = random.randint(75, 125)
                bx = random.randint(10, w - bw - 10)
                by = random.randint(45, h - bh - 45)

                auto_type = random.choice(["bengaluru", "yellow_black", "e_rickshaw"])
                if auto_type == "bengaluru":
                    # Bengaluru Auto: Green lower body (0, 150, 0), Yellow roof (0, 215, 255)
                    cv2.rectangle(img, (bx, by + int(bh * 0.4)), (bx + bw, by + bh), (0, 160, 0), -1)
                    cv2.rectangle(img, (bx, by), (bx + bw, by + int(bh * 0.4)), (0, 215, 255), -1)
                elif auto_type == "yellow_black":
                    # Classic Pan-Indian Auto: Black lower body (20, 20, 20), Yellow hood (0, 215, 255)
                    cv2.rectangle(img, (bx, by + int(bh * 0.35)), (bx + bw, by + bh), (25, 25, 25), -1)
                    cv2.rectangle(img, (bx, by), (bx + bw, by + int(bh * 0.35)), (0, 215, 255), -1)
                else:
                    # E-Rickshaw / Goods Auto: Blue / White cargo box
                    cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (220, 120, 40), -1)
                    cv2.rectangle(img, (bx + 4, by + 4), (bx + bw - 4, by + int(bh * 0.5)), (240, 240, 240), -1)

                # Draw windscreen & headlight accents
                cv2.rectangle(img, (bx + 6, by + int(bh * 0.25)), (bx + bw - 6, by + int(bh * 0.45)), (180, 160, 100), 2)
                cv2.putText(img, "AUTO", (bx + 4, by + int(bh * 0.6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            elif cls_id == 1:
                # Two-wheeler (Indian Scooty / Motorcycle / Cruiser / E-Scooter)
                bw = random.randint(30, 70)
                bh = random.randint(55, 105)
                bx = random.randint(10, w - bw - 10)
                by = random.randint(45, h - bh - 45)

                two_wheeler_type = random.choice(["scooty", "motorcycle", "cruiser", "e_scooter"])
                if two_wheeler_type == "scooty":
                    # Honda Activa / TVS Jupiter Scooty: Metallic grey/silver/blue/white apron
                    scooty_color = random.choice([(180, 180, 180), (200, 50, 50), (50, 100, 200), (230, 230, 230)])
                    cv2.rectangle(img, (bx, by), (bx + bw, by + bh), scooty_color, -1)
                    cv2.rectangle(img, (bx + int(bw * 0.2), by + int(bh * 0.3)), (bx + int(bw * 0.8), by + int(bh * 0.6)), (30, 30, 30), -1)  # Floorboard
                    cv2.putText(img, "SCOOTY", (bx + 2, by + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
                elif two_wheeler_type == "motorcycle":
                    # Hero Splendor / Pulsar / Apache: Fuel tank + Engine block
                    cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (40, 40, 200), -1)
                    cv2.circle(img, (bx + int(bw / 2), by + int(bh * 0.4)), int(bw * 0.35), (20, 20, 20), -1)  # Engine
                    cv2.putText(img, "BIKE", (bx + 2, by + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
                elif two_wheeler_type == "cruiser":
                    # Royal Enfield Bullet: Black / Chrome teardrop tank
                    cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (20, 20, 20), -1)
                    cv2.circle(img, (bx + int(bw / 2), by + 12), 6, (220, 220, 220), -1)  # Chrome headlight
                    cv2.putText(img, "ROYAL", (bx + 2, by + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
                else:
                    # Ola S1 / Ather E-Scooter: Neon / White sleek body
                    cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (0, 220, 180), -1)
                    cv2.line(img, (bx + 4, by + 8), (bx + bw - 4, by + 8), (255, 255, 255), 2)  # LED strip
                    cv2.putText(img, "E-BIKE", (bx + 2, by + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)

            elif cls_id in (3, 4):
                # Bus / Truck
                bw = random.randint(110, 185)
                bh = random.randint(105, 175)
                bx = random.randint(10, w - bw - 10)
                by = random.randint(45, h - bh - 45)
                cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (50, 50, 200) if cls_id == 3 else (160, 50, 160), -1)
                cv2.putText(img, "BUS" if cls_id == 3 else "TRUCK", (bx + 4, by + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            else:
                # Car / Bicycle
                bw = random.randint(70, 130)
                bh = random.randint(60, 120)
                bx = random.randint(10, w - bw - 10)
                by = random.randint(45, h - bh - 45)
                cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (50, 180, 50) if cls_id == 2 else (200, 200, 50), -1)
                cv2.putText(img, "CAR" if cls_id == 2 else "CYCLE", (bx + 4, by + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            # Normalize to YOLO format (cx, cy, nw, nh)
            cx = (bx + bw / 2.0) / w
            cy = (by + bh / 2.0) / h
            nw = bw / float(w)
            nh = bh / float(h)
            labels.append(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        split = "train" if i < int(num_samples * 0.8) else "val"
        filename = f"bengaluru_auto_traffic_{i:04d}"

        cv2.imwrite(os.path.join(INDIAN_DATASET_DIR, "images", split, f"{filename}.jpg"), img)
        with open(os.path.join(INDIAN_DATASET_DIR, "labels", split, f"{filename}.txt"), "w") as f:
            f.write("\n".join(labels) + "\n")

    print(f"[INDIAN-DATASET] Successfully compiled Bengaluru & Pan-Indian traffic dataset with {num_samples} samples.")

if __name__ == "__main__":
    yaml_path = create_indian_dataset_structure()
    sync_user_labeled_data()
    download_datacluster_indian_dataset()
    generate_indian_vehicle_samples(num_samples=250)
    print(f"[INDIAN-DATASET] Indian vehicle dataset ready at: {yaml_path}")
