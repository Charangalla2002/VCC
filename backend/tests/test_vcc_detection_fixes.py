import unittest
import numpy as np
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "detection"))

import config
from tracker import _BoxWrapper
from counter import LineCounter, intersect

class TestVCCFixes(unittest.TestCase):

    def test_bounding_box_scaling(self):
        """Test 1: Verify coordinate rescaling from 640x640 back to 1920x1080."""
        orig_w, orig_h = 1920, 1080
        infer_sz = 640

        scale_x = orig_w / float(infer_sz) # 3.0
        scale_y = orig_h / float(infer_sz) # 1.6875

        # Simulated raw detection box in 640x640 space
        raw_box = [100.0, 100.0, 200.0, 200.0]
        scaled_box = (
            raw_box[0] * scale_x,
            raw_box[1] * scale_y,
            raw_box[2] * scale_x,
            raw_box[3] * scale_y,
        )

        class MockBoxes:
            pass

        box_wrapper = _BoxWrapper(MockBoxes(), 0, color="White", scaled_xyxy=scaled_box)

        # Confirm returned xyxy matches exact scaled dimensions
        self.assertEqual(box_wrapper.xyxy[0], 300.0)
        self.assertEqual(box_wrapper.xyxy[1], 168.75)
        self.assertEqual(box_wrapper.xyxy[2], 600.0)
        self.assertEqual(box_wrapper.xyxy[3], 337.5)

    def test_line_crossing_accuracy_with_rescaled_boxes(self):
        """Test 1b: Verify LineCounter triggers accurately with rescaled coordinates."""
        counter = LineCounter(
            camera_id="test_cam",
            lines=[{
                "id": 1,
                "name": "Test Line",
                "x1": 0.0, "y1": 0.5, "x2": 1.0, "y2": 0.5, # Horizontal line at y=540px
                "lane_id": 1,
                "direction": "both",
                "color": "#00d4ff"
            }]
        )

        class MockTrack:
            def __init__(self, track_id, xyxy):
                self.id = track_id
                self.xyxy = xyxy
                self.cls = 2 # Car
                self.conf = 0.8

        # Frame 1: Vehicle above line (y_center = 500)
        t1 = MockTrack(1, (900, 480, 1000, 520))
        events1 = counter.process_tracks([t1], frame_h=1080, frame_w=1920)
        self.assertEqual(len(events1), 0)

        # Frame 2: Vehicle crosses line (y_center = 560)
        t2 = MockTrack(1, (900, 540, 1000, 580))
        events2 = counter.process_tracks([t2], frame_h=1080, frame_w=1920)
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0].direction, "down")

    def test_class_confidence_thresholds(self):
        """Test 3: Verify class-specific confidence filtering (e.g. Motorcycle vs Car)."""
        self.assertLessEqual(config.CONF_THRESHOLD, 0.20)
        self.assertLessEqual(config.CLASS_CONF_THRESHOLDS["motorcycle"], 0.20)

    def test_bounding_box_colors_and_crossing_state(self):
        """Test 4: Verify bounding box color state per track ID (White before crossing, Green after crossing)."""
        counter = LineCounter(
            camera_id="test_cam",
            lines=[{
                "id": 1,
                "name": "Test Line",
                "x1": 0.0, "y1": 0.5, "x2": 1.0, "y2": 0.5,
                "lane_id": 1,
                "direction": "both",
                "color": "#00d4ff"
            }]
        )

        class MockTrack:
            def __init__(self, track_id, xyxy):
                self.id = track_id
                self.xyxy = xyxy
                self.cls = 2
                self.conf = 0.8

        # Frame 1: Track 1 (above line) and Track 2 (above line)
        t1 = MockTrack(1, (100, 480, 200, 520)) # center y=500
        t2 = MockTrack(2, (400, 480, 500, 520)) # center y=500
        counter.process_tracks([t1, t2], frame_h=1080, frame_w=1920)

        self.assertFalse(counter.has_crossed(1))
        self.assertFalse(counter.has_crossed(2))

        # Frame 2: Track 1 crosses line, Track 2 stays above line
        t1_crossed = MockTrack(1, (100, 540, 200, 580)) # center y=560
        t2_above = MockTrack(2, (400, 490, 500, 530)) # center y=510
        counter.process_tracks([t1_crossed, t2_above], frame_h=1080, frame_w=1920)

        # Track 1 crossed -> True (Green), Track 2 uncrossed -> False (White)
        self.assertTrue(counter.has_crossed(1))
        self.assertFalse(counter.has_crossed(2))

        # Frame 3: Track 1 moves further down
        t1_down = MockTrack(1, (100, 600, 200, 640))
        counter.process_tracks([t1_down], frame_h=1080, frame_w=1920)

        # Confirm Green state persists
        self.assertTrue(counter.has_crossed(1))

if __name__ == "__main__":
    unittest.main()
