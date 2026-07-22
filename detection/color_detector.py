"""
color_detector.py — Advanced Vehicle Color Recognition Module.

Uses multi-stage Region of Interest (ROI) extraction, Glare/Shadow filtering,
K-Means dominant color clustering, and CIELAB / HSV color space distance matching
to accurately classify vehicle body colors: White, Black, Silver, Red, Blue,
Yellow, Green, Orange, Cyan, Purple, Pink.
"""
from __future__ import annotations

import cv2
import numpy as np


def detect_vehicle_color(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> str:
    """
    Detect dominant vehicle body paint color from a BGR image frame and bounding box.

    Parameters
    ----------
    frame : np.ndarray
        Input BGR image frame.
    bbox : tuple[float, float, float, float]
        Bounding box (x1, y1, x2, y2).

    Returns
    -------
    str
        Detected vehicle color ('White', 'Black', 'Silver', 'Red', 'Blue', 'Yellow', etc.).
    """
    try:
        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]

        # Clamp bounding box coordinates
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(fw, x2), min(fh, y2)

        w, h = x2 - x1, y2 - y1
        if w < 12 or h < 12:
            return "Unknown"

        # ---------------------------------------------------------------------
        # 1. Target Body Panel ROI Extraction (Excludes windshield, roof, road)
        # ---------------------------------------------------------------------
        # Top 25% is usually windshield/roof glass; bottom 15% is road/tires.
        # Sides (15% left/right) avoid neighboring lane background.
        roi_y1 = y1 + int(h * 0.25)
        roi_y2 = y1 + int(h * 0.82)
        roi_x1 = x1 + int(w * 0.15)
        roi_x2 = x1 + int(w * 0.85)

        crop = frame[roi_y1:roi_y2, roi_x1:roi_x2]
        if crop.size == 0:
            crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return "Unknown"

        # ---------------------------------------------------------------------
        # 2. Convert to Color Spaces (HSV and CIELAB)
        # ---------------------------------------------------------------------
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)

        s_chan = hsv[:, :, 1]
        v_chan = hsv[:, :, 2]

        # ---------------------------------------------------------------------
        # 3. Filter Specular Glare & Deep Undercarriage Shadows
        # ---------------------------------------------------------------------
        # Valid paint mask: exclude extreme glare (V > 248) and pitch black (V < 20)
        valid_mask = (v_chan >= 20) & (v_chan <= 248)
        if np.sum(valid_mask) < 25:
            valid_mask = np.ones((crop.shape[0], crop.shape[1]), dtype=bool)

        valid_bgr = crop[valid_mask]
        valid_hsv = hsv[valid_mask]
        valid_lab = lab[valid_mask]

        if len(valid_bgr) == 0:
            return "Unknown"

        # ---------------------------------------------------------------------
        # 4. K-Means Dominant Color Clustering (K=3)
        # ---------------------------------------------------------------------
        pixels_bgr = np.float32(valid_bgr)
        k = min(3, len(pixels_bgr))
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 0.2)
        
        _, labels_idx, centers_bgr = cv2.kmeans(
            pixels_bgr, k, None, criteria, 5, cv2.KMEANS_RANDOM_CENTERS
        )

        # Count pixels per cluster
        counts = np.bincount(labels_idx.flatten())
        sorted_indices = np.argsort(counts)[::-1]

        # Evaluate dominant clusters
        color_votes = []
        for idx in sorted_indices:
            weight = counts[idx] / len(pixels_bgr)
            if weight < 0.15:
                continue

            center_bgr = centers_bgr[idx].reshape(1, 1, 3).astype(np.uint8)
            c_hsv = cv2.cvtColor(center_bgr, cv2.COLOR_BGR2HSV)[0, 0]
            c_lab = cv2.cvtColor(center_bgr, cv2.COLOR_BGR2LAB)[0, 0]

            H, S, V = int(c_hsv[0]), int(c_hsv[1]), int(c_hsv[2])
            L, A, B = float(c_lab[0]), float(c_lab[1]), float(c_lab[2])

            # Classify cluster center using CIELAB & HSV thresholds
            c_name = _classify_color_sample(H, S, V, L, A, B)
            color_votes.append((c_name, weight))

        if not color_votes:
            # Fallback on global median
            med_hsv = np.median(valid_hsv, axis=0)
            med_lab = np.median(valid_lab, axis=0)
            return _classify_color_sample(
                int(med_hsv[0]), int(med_hsv[1]), int(med_hsv[2]),
                float(med_lab[0]), float(med_lab[1]), float(med_lab[2])
            )

        # ---------------------------------------------------------------------
        # 5. Dominant Chromatic / Achromatic Selection
        # ---------------------------------------------------------------------
        # Prefer chromatic colors if weight >= 0.20, otherwise dominant cluster
        for c_name, w in color_votes:
            if c_name not in ("White", "Black", "Silver") and w >= 0.20:
                return c_name

        return color_votes[0][0]

    except Exception:
        return "Unknown"


def _classify_color_sample(H: int, S: int, V: int, L: float, A: float, B: float) -> str:
    """
    Classify a single color sample from HSV (H: 0-180, S: 0-255, V: 0-255)
    and CIELAB (L: 0-255, A: 0-255, B: 0-255) values.
    """
    # OpenCV LAB ranges: L (0-255), A (0-255, 128=0), B (0-255, 128=0)
    a_shift = A - 128.0
    b_shift = B - 128.0
    chroma = np.sqrt(a_shift**2 + b_shift**2)

    # 1. Achromatic Classification (White / Black / Silver)
    if S < 45 or chroma < 16.0:
        if L >= 175 or V >= 190:
            return "White"
        elif L <= 60 or V <= 55:
            return "Black"
        else:
            return "Silver"

    # 2. Chromatic Classification (Red, Orange, Yellow, Green, Cyan, Blue, Purple, Pink)
    if (H <= 11 or H >= 165) and (S >= 40):
        return "Red"
    elif 12 <= H <= 24 and (S >= 45):
        return "Orange"
    elif 25 <= H <= 34 and (S >= 40):
        return "Yellow"
    elif 35 <= H <= 85 and (S >= 35):
        return "Green"
    elif 86 <= H <= 100 and (S >= 35):
        return "Cyan"
    elif 101 <= H <= 135 and (S >= 35):
        return "Blue"
    elif 136 <= H <= 155 and (S >= 35):
        return "Purple"
    elif 156 <= H <= 164 and (S >= 35):
        return "Pink"

    # Fallback based on Luminance if saturation is borderline
    if L >= 175:
        return "White"
    elif L <= 60:
        return "Black"
    
    return "Silver"
