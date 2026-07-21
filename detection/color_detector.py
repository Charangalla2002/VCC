"""
color_detector.py — Real-time vehicle color recognition module.

Analyzes the HSV color space of a cropped vehicle bounding box region
to classify dominant vehicle colors: Red, Orange, Yellow, Green, Cyan, Blue,
Purple, Pink, White, Black, Silver.
"""
from __future__ import annotations

import cv2
import numpy as np

# HSV Color Boundaries (H: 0-180, S: 0-255, V: 0-255)
COLOR_BOUNDS = [
    # (name, lower_hsv1, upper_hsv1, lower_hsv2, upper_hsv2)
    ("Red",    (0, 70, 50),     (10, 255, 255),  (170, 70, 50),  (180, 255, 255)),
    ("Orange", (11, 100, 100),  (24, 255, 255),  None,           None),
    ("Yellow", (25, 75, 75),    (34, 255, 255),  None,           None),
    ("Green",  (35, 50, 40),    (85, 255, 255),  None,           None),
    ("Cyan",   (86, 50, 50),    (100, 255, 255), None,           None),
    ("Blue",   (101, 60, 40),   (135, 255, 255), None,           None),
    ("Purple", (136, 50, 50),   (155, 255, 255), None,           None),
    ("Pink",   (156, 50, 50),   (169, 255, 255), None,           None),
]

def detect_vehicle_color(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> str:
    """
    Detect dominant vehicle color from a BGR image frame and bounding box (x1, y1, x2, y2).

    Returns
    -------
    str
        Detected color string (e.g. 'Red', 'Yellow', 'Black', 'White', 'Silver', 'Blue').
    """
    try:
        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]

        # Clamp coordinates
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(fw, x2), min(fh, y2)

        w, h = x2 - x1, y2 - y1
        if w < 10 or h < 10:
            return "Unknown"

        # Crop inner central region to focus on vehicle body (avoiding road & background bleeding)
        margin_w = int(w * 0.20)
        margin_h = int(h * 0.20)

        crop = frame[y1 + margin_h : y2 - margin_h, x1 + margin_w : x2 - margin_w]
        if crop.size == 0:
            crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return "Unknown"

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        s_channel = hsv[:, :, 1]
        v_channel = hsv[:, :, 2]

        mean_v = np.mean(v_channel)
        mean_s = np.mean(s_channel)

        # Achromatic check (White / Black / Silver)
        if mean_v < 45:
            return "Black"
        if mean_s < 35:
            if mean_v > 195:
                return "White"
            return "Silver"

        # Chromatic colors check
        max_pixels = 0
        best_color = "Silver"
        total_pixels = crop.shape[0] * crop.shape[1]

        for item in COLOR_BOUNDS:
            name = item[0]
            l1, u1 = np.array(item[1]), np.array(item[2])
            mask = cv2.inRange(hsv, l1, u1)

            if item[3] is not None and item[4] is not None:
                l2, u2 = np.array(item[3]), np.array(item[4])
                mask2 = cv2.inRange(hsv, l2, u2)
                mask = cv2.bitwise_or(mask, mask2)

            cnt = cv2.countNonZero(mask)
            if cnt > max_pixels:
                max_pixels = cnt
                best_color = name

        if (max_pixels / float(total_pixels)) < 0.12:
            if mean_v > 180:
                return "White"
            elif mean_v < 70:
                return "Black"
            else:
                return "Silver"

        return best_color
    except Exception:
        return "Unknown"
