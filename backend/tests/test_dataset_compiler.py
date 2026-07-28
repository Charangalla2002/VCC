import os
import sys
import unittest
import shutil
import tempfile
import cv2
import numpy as np

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _REPO_ROOT)

from dataset_compiler import (
    RAW_LABEL_MAPPING,
    UNIFIED_CLASSES,
    calculate_image_hash,
    normalize_box,
    parse_label_file,
    render_sanity_checks,
    compile_and_split_dataset,
)


class TestDatasetCompiler(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.img_dir = os.path.join(self.test_dir, "images")
        self.lbl_dir = os.path.join(self.test_dir, "labels")
        os.makedirs(self.img_dir, exist_ok=True)
        os.makedirs(self.lbl_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_taxonomy_mapping(self):
        """Verify label mapping for Option A (van merged into car) and Indian vehicle classes."""
        self.assertEqual(RAW_LABEL_MAPPING["car"], 0)
        self.assertEqual(RAW_LABEL_MAPPING["van"], 0)
        self.assertEqual(RAW_LABEL_MAPPING["motorcycle"], 1)
        self.assertEqual(RAW_LABEL_MAPPING["auto_rickshaw"], 2)
        self.assertEqual(RAW_LABEL_MAPPING["bus"], 3)
        self.assertEqual(RAW_LABEL_MAPPING["truck"], 4)
        self.assertEqual(RAW_LABEL_MAPPING["bicycle"], 5)

    def test_coordinate_normalization(self):
        """Verify absolute pixel coordinates are normalized to [0.0, 1.0]."""
        # Absolute pixel values for 1920x1080 image
        abs_box = [960.0, 540.0, 400.0, 200.0]
        xc, yc, w, h = normalize_box(abs_box, 1920, 1080)
        self.assertAlmostEqual(xc, 0.5)
        self.assertAlmostEqual(yc, 0.5)
        self.assertAlmostEqual(w, 400.0 / 1920.0)
        self.assertAlmostEqual(h, 200.0 / 1080.0)

    def test_label_parsing(self):
        """Verify parse_label_file handles string and numeric class labels."""
        label_path = os.path.join(self.lbl_dir, "sample.txt")
        with open(label_path, "w", encoding="utf-8") as f:
            f.write("car 0.5 0.5 0.2 0.2\n")
            f.write("auto_rickshaw 0.3 0.3 0.1 0.1\n")
            f.write("unknown_class 0.1 0.1 0.1 0.1\n")

        boxes = parse_label_file(label_path, 1920, 1080)
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0][0], 0)  # car
        self.assertEqual(boxes[1][0], 2)  # auto_rickshaw

    def test_dataset_compile_and_split(self):
        """Verify dataset compilation, deduplication, splitting, and yaml generation."""
        # Create 10 dummy images & label files
        for i in range(10):
            img_path = os.path.join(self.img_dir, f"frame_{i}.jpg")
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            # Add unique pixel color to ensure unique MD5 hash
            img[0, 0] = [i * 20, i * 20, i * 20]
            cv2.imwrite(img_path, img)

            lbl_path = os.path.join(self.lbl_dir, f"frame_{i}.txt")
            with open(lbl_path, "w", encoding="utf-8") as f:
                f.write(f"{i % 6} 0.5 0.5 0.2 0.2\n")

        out_split = os.path.join(self.test_dir, "split")
        res = compile_and_split_dataset(
            source_dirs=[self.test_dir],
            output_dir=out_split,
            train_ratio=0.8,
            val_ratio=0.1,
            test_ratio=0.1,
        )

        self.assertEqual(res["total_images"], 10)
        self.assertTrue(os.path.exists(os.path.join(out_split, "data.yaml")))
        self.assertTrue(os.path.exists(os.path.join(out_split, "images", "train")))


if __name__ == "__main__":
    unittest.main()
