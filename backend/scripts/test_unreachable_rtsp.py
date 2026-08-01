import os
import sys
import time
import logging
sys.path.append("detection")
from gst_capture import GStreamerCapture, GST_AVAILABLE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("unreachable_test")

def test_unreachable_stream():
    logger.info("=== TASK 7b: Unreachable RTSP Bus Error & Watchdog Test ===")
    if not GST_AVAILABLE:
        logger.error("Native GStreamer PyGObject bindings not available!")
        return

    unreachable_url = "rtsp://192.168.254.254:554/live.sdp"  # Non-existent IP address
    logger.info("Connecting to unreachable RTSP source: %s", unreachable_url)

    t0 = time.monotonic()
    cap = GStreamerCapture(unreachable_url, latency=200, stall_timeout=8.0)
    started = cap.start(timeout_sec=5.0)

    elapsed = time.monotonic() - t0
    logger.info("Pipeline start returned: %s in %.2f seconds", started, elapsed)
    logger.info("Capture Health State: %s", cap.health())

    if not started and elapsed < 8.0:
        logger.info("TEST 7b PASSED ✅: Bus error / timeout caught cleanly in %.2fs (< 8s) without freeze!", elapsed)
    else:
        logger.warning("TEST 7b RESULT: Started=%s, Elapsed=%.2fs", started, elapsed)

    cap.release()

if __name__ == "__main__":
    test_unreachable_stream()
