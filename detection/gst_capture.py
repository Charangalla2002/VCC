"""
gst_capture.py -- Native GStreamer RTSP capture using PyGObject (gi) bindings.

Bypasses OpenCV's VideoCapture layer entirely. Uses direct GStreamer C-API via PyGObject
for native TCP RTSP transport, bus error/EOS signals, appsink frame pulling, and per-camera
GLib main loops.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt to import GStreamer PyGObject bindings
# ---------------------------------------------------------------------------

GST_AVAILABLE = False
_GST_VERSION_STRING = "N/A"

try:
    import os
    import sys

    # Windows DLL path configuration if MSVC GStreamer runtime is present
    gst_root = r"C:\Users\Charan Galla\AppData\Local\Programs\gstreamer\1.0\msvc_x86_64"
    gst_bin = os.path.join(gst_root, "bin")
    gst_typelibs = os.path.join(gst_root, "lib", "girepository-1.0")

    detection_dir = os.path.dirname(os.path.abspath(__file__))
    local_bin = os.path.join(detection_dir, "bin")

    if os.path.isdir(gst_bin):
        os.environ["PATH"] = gst_bin + os.pathsep + local_bin + os.pathsep + os.environ.get("PATH", "")
        os.environ["GI_TYPELIB_PATH"] = gst_typelibs

        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(gst_bin)
                os.add_dll_directory(local_bin)
            except Exception:
                pass

    import gi  # type: ignore[import]
    gi.require_version("Gst", "1.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import Gst, GLib  # type: ignore[import]

    Gst.init(None)
    _GST_VERSION_STRING = Gst.version_string()
    GST_AVAILABLE = True
    logger.info("Native GStreamer PyGObject bindings loaded: %s", _GST_VERSION_STRING)

except Exception as exc:
    logger.warning("GStreamer PyGObject bindings not available in Python environment: %s", exc)
    GST_AVAILABLE = False


def gst_version_string() -> str:
    return _GST_VERSION_STRING


# ---------------------------------------------------------------------------
# Native GStreamer RTSP Capture Class
# ---------------------------------------------------------------------------

class GStreamerCapture:
    """
    Native GStreamer RTSP/File Capture using PyGObject (Gst/GLib bindings directly).
    """

    CONNECTING = "CONNECTING"
    OK = "OK"
    STALLED = "STALLED"

    def __init__(self, source: str, sequential: bool = False, latency: int = 200, stall_timeout: float = 8.0) -> None:
        if not GST_AVAILABLE:
            raise RuntimeError(
                "Native GStreamer PyGObject bindings (gi.repository.Gst) are required.\n"
                "Please ensure system packages are installed:\n"
                "  sudo apt-get update && sudo apt-get install -y python3-gi gir1.2-gstreamer-1.0 "
                "gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav"
            )

        self.source = str(source)
        self.sequential = sequential
        self.latency = latency
        self.stall_timeout = stall_timeout

        self.lock = threading.Lock()
        self.latest_frame: Optional[np.ndarray] = None
        self.ret = False
        self.frame_seq = 0
        self._last_read_seq = -1

        self.opened_at = time.monotonic()
        self.last_frame_ts: Optional[float] = None
        self.is_stalled = False

        self._loop: Optional[GLib.MainLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._pipeline: Any = None
        self._appsink: Any = None

    def _build_pipeline_string(self) -> str:
        src = self.source
        if src.startswith("rtsp://"):
            return (
                f"rtspsrc location=\"{src}\" protocols=tcp latency={self.latency} ! "
                f"rtph264depay ! h264parse ! avdec_h264 ! "
                f"videoconvert ! video/x-raw,format=BGR ! "
                f"appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false"
            )
        elif src.endswith((".mp4", ".avi", ".mkv", ".mov")) or os.path.exists(src):
            return (
                f"filesrc location=\"{src}\" ! decodebin ! videoconvert ! "
                f"video/x-raw,format=BGR ! "
                f"appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false"
            )
        else:
            return (
                f"uridecodebin uri=\"{src}\" ! videoconvert ! "
                f"video/x-raw,format=BGR ! "
                f"appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false"
            )

    def _on_bus_message(self, bus: Any, message: Any) -> bool:
        msg_type = message.type
        if msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error("[%s] GStreamer Bus Error: %s (debug: %s)", self.source, err.message, debug)
            with self.lock:
                self.ret = False
                self.is_stalled = True
            if self._loop and self._loop.is_running():
                self._loop.quit()

        elif msg_type == Gst.MessageType.EOS:
            logger.info("[%s] GStreamer Bus EOS received.", self.source)
            with self.lock:
                self.ret = False
                self.is_stalled = True
            if self._loop and self._loop.is_running():
                self._loop.quit()

        return True

    def _on_new_sample(self, appsink: Any) -> Gst.FlowReturn:
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK

        caps = sample.get_caps()
        structure = caps.get_structure(0)
        _, width = structure.get_int("width")
        _, height = structure.get_int("height")

        buf = sample.get_buffer()
        result, map_info = buf.map(Gst.MapFlags.READ)
        if not result:
            return Gst.FlowReturn.OK

        try:
            frame = np.frombuffer(map_info.data, dtype=np.uint8).copy().reshape((height, width, 3))
            with self.lock:
                self.latest_frame = frame
                self.ret = True
                self.frame_seq += 1
                self.last_frame_ts = time.monotonic()
        finally:
            buf.unmap(map_info)

        return Gst.FlowReturn.OK

    def _check_stall(self) -> bool:
        now = time.monotonic()
        with self.lock:
            if self.last_frame_ts is not None and (now - self.last_frame_ts) > self.stall_timeout:
                logger.warning("[%s] Stall watchdog: no new frame for %.1fs — marking STALLED", self.source, now - self.last_frame_ts)
                self.is_stalled = True
                self.ret = False
        return True

    def _run_main_loop(self) -> None:
        try:
            self._loop = GLib.MainLoop()
            GLib.timeout_add_seconds(1, self._check_stall)
            self._loop.run()
        except Exception as exc:
            logger.error("[%s] GStreamer MainLoop exception: %s", self.source, exc)
        finally:
            with self.lock:
                self.ret = False

    def start(self, timeout_sec: float = 15.0) -> bool:
        pipeline_str = self._build_pipeline_string()
        logger.info("[%s] Starting Native GStreamer pipeline: %s", self.source, pipeline_str)

        try:
            self._pipeline = Gst.parse_launch(pipeline_str)
        except Exception as exc:
            logger.error("[%s] GStreamer parse_launch failed: %s", self.source, exc)
            return False

        self._appsink = self._pipeline.get_by_name("sink")
        if self._appsink is None:
            logger.error("[%s] Could not find 'sink' element in pipeline", self.source)
            return False

        self._appsink.connect("new-sample", self._on_new_sample)

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        self._loop_thread = threading.Thread(target=self._run_main_loop, daemon=True, name=f"gst-loop-{id(self)}")
        self._loop_thread.start()

        ret = self._pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("[%s] GStreamer set_state(PLAYING) failed", self.source)
            self.release()
            return False

        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_sec:
            with self.lock:
                if self.is_stalled:
                    self.release()
                    return False
                if self.latest_frame is not None:
                    return True
            time.sleep(0.05)

        logger.warning("[%s] Pipeline start timeout after %.1fs — no frames received, marking failed", self.source, timeout_sec)
        self.release()
        return False

    def isOpened(self) -> bool:
        with self.lock:
            return self.ret or (self.latest_frame is not None and not self.is_stalled)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        ret, frame, _ = self.read_with_freshness()
        return ret, frame

    def read_with_freshness(self) -> Tuple[bool, Optional[np.ndarray], bool]:
        with self.lock:
            if self.latest_frame is None or self.is_stalled:
                return False, None, False
            is_new = self.frame_seq != self._last_read_seq
            self._last_read_seq = self.frame_seq
            return True, self.latest_frame.copy(), is_new

    def health(self) -> str:
        with self.lock:
            if self.is_stalled:
                return self.STALLED
            if self.last_frame_ts is None:
                if (time.monotonic() - self.opened_at) < 15.0:
                    return self.CONNECTING
                return self.STALLED
            if (time.monotonic() - self.last_frame_ts) >= self.stall_timeout:
                return self.STALLED
            return self.OK

    def release(self) -> None:
        with self.lock:
            self.is_stalled = True
            self.ret = False

        if self._pipeline is not None:
            try:
                self._pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
            self._pipeline = None

        if self._loop is not None and self._loop.is_running():
            try:
                self._loop.quit()
            except Exception:
                pass
            self._loop = None

        if self._loop_thread is not None and self._loop_thread.is_alive():
            if self._loop_thread != threading.current_thread():
                self._loop_thread.join(timeout=3.0)
            self._loop_thread = None

        logger.info("[%s] GStreamer pipeline released cleanly.", self.source)
