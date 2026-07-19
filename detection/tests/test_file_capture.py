"""
Regression tests for sequential (file-source) capture.

A live camera should drop stale frames — the newest frame is the only useful one.
A video FILE is the opposite: every frame is content. The capture layer originally
used latest-frame-wins for both, so the reader decoded a whole clip in well under a
second into a single slot while inference ran at ~5 fps. Measured on a 90-frame
clip: 6 frames reached inference and the vehicle was never counted.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

cv2 = pytest.importorskip("cv2", reason="OpenCV not installed in this environment")
np = pytest.importorskip("numpy")


FRAMES = 40
W, H = 320, 240


@pytest.fixture(scope="module")
def clip():
    """A short synthetic clip with a frame-number marker burned into each frame."""
    path = os.path.join(tempfile.mkdtemp(), "clip.mp4")
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 15.0, (W, H))
    for i in range(FRAMES):
        frame = np.full((H, W, 3), 40, np.uint8)
        # Encode the index as a bright bar whose height is unique per frame, so a
        # dropped frame is detectable from pixels alone.
        cv2.rectangle(frame, (10, 10), (60, 10 + (i + 1) * 4), (255, 255, 255), -1)
        out.write(frame)
    out.release()
    assert os.path.getsize(path) > 0
    return path


def _drain(cap, limit, slow=0.0):
    """Read until the source is exhausted, counting only genuinely new frames."""
    import time

    seen = 0
    idle = 0
    while seen < limit and idle < 200:
        ret, frame, is_new = cap.read_with_freshness()
        if ret and is_new and frame is not None:
            seen += 1
            idle = 0
            if slow:
                time.sleep(slow)   # emulate inference latency
        else:
            idle += 1
            time.sleep(0.005)
    return seen


def test_sequential_capture_delivers_every_frame(clip):
    """
    The consumer is deliberately far slower than the decoder. In sequential mode
    back-pressure must hold the reader so no frame is skipped.
    """
    from tracker import ThreadedRTSPCapture

    cap = ThreadedRTSPCapture(clip, sequential=True)
    try:
        seen = _drain(cap, FRAMES, slow=0.01)
    finally:
        cap.release()

    assert seen == FRAMES, f"sequential capture dropped frames: {seen}/{FRAMES}"


def test_live_mode_still_drops_stale_frames(clip):
    """
    The live path must NOT gain back-pressure — for RTSP, buffering old frames is
    what causes latency drift. A slow consumer on a fast source should see fewer
    frames than the file contains.
    """
    from tracker import ThreadedRTSPCapture

    cap = ThreadedRTSPCapture(clip, sequential=False)
    try:
        seen = _drain(cap, FRAMES, slow=0.02)
    finally:
        cap.release()

    assert seen < FRAMES, (
        f"live mode delivered all {FRAMES} frames; latest-frame-wins should have "
        "dropped stale ones for a slow consumer"
    )


@pytest.mark.parametrize(
    "src,expected",
    [
        ("rtsp://10.0.0.5/stream", True),
        ("http://cam.local/feed.mjpg", True),
        ("udp://239.0.0.1:1234", True),
        ("/var/media/traffic.mp4", False),
        ("clip.mp4", False),
        ("C:\\videos\\traffic.avi", False),
    ],
)
def test_network_source_classification(src, expected):
    """File sources must be routed to sequential mode, network sources must not."""
    from tracker import _is_network_source

    assert _is_network_source(src) is expected


def test_release_unblocks_a_waiting_reader(clip):
    """
    In sequential mode the reader parks waiting for acknowledgement. release() must
    still tear it down promptly rather than deadlocking on that wait.
    """
    import time
    from tracker import ThreadedRTSPCapture

    cap = ThreadedRTSPCapture(clip, sequential=True)
    # Take one frame, then abandon it so the reader is parked awaiting the ack.
    _drain(cap, 1)
    time.sleep(0.2)

    t0 = time.monotonic()
    cap.release()
    elapsed = time.monotonic() - t0

    assert elapsed < 5.0, f"release() blocked for {elapsed:.1f}s on a parked reader"
    assert not cap.thread.is_alive(), "reader thread survived release()"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
