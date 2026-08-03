"""
tracker.py — Async YOLO + ByteTrack inference and event posting.

Architecture
------------
* ``load_model()``      — loads the primary model; falls back to FALLBACK_MODEL
                          with a ``logging.warning`` if primary is unavailable.
* ``run_camera()``      — async task per camera: grabs frames, runs .track(),
                          feeds the LineCounter, posts events to the backend,
                          and pushes annotated frames to a per-camera Queue.
* ``main()``            — gathers all camera tasks concurrently.

Run directly::

    python tracker.py
"""

from __future__ import annotations

import asyncio
import os
import logging

import time
from typing import Any

import cv2
import httpx
import numpy as np
from dotenv import load_dotenv

load_dotenv()                          # load .env before importing config

import config
from counter import CrossingEvent, LineCounter, create_counters_from_config
from gst_capture import GStreamerCapture, GST_AVAILABLE, gst_version_string
from color_detector import detect_vehicle_color

from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# Global shared thread pool for YOLO inference
INFER_EXECUTOR = ThreadPoolExecutor(
    max_workers=config.MAX_INFER_WORKERS,
    thread_name_prefix="vcc-yolo-worker"
)


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

def sync_model_classes(model: Any) -> None:
    """Dynamically sync config.VEHICLE_CLASS_MAP with loaded model names."""
    if hasattr(model, "names") and isinstance(model.names, dict):
        new_map = {}
        for cls_id, name in model.names.items():
            name_str = str(name).lower()
            if any(k in name_str for k in ["auto", "rickshaw", "tuk", "three", "autorickshaw", "auto_rickshaw", "auto-rickshaw"]):
                new_map[cls_id] = "auto_rickshaw"
            elif any(k in name_str for k in ["motorcycle", "motorbike", "bike", "scooter"]):
                new_map[cls_id] = "motorcycle"
            elif any(k in name_str for k in ["car", "automobile"]):
                new_map[cls_id] = "car"
            elif "bus" in name_str:
                new_map[cls_id] = "bus"
            elif "truck" in name_str:
                new_map[cls_id] = "truck"
            elif "bicycle" in name_str or "cycle" in name_str:
                new_map[cls_id] = "bicycle"
        
        if new_map:
            config.VEHICLE_CLASS_MAP = new_map
            logger.info("Synchronized VEHICLE_CLASS_MAP from model: %s", new_map)


def load_model() -> Any:
    """
    Load a YOLO model from ``config.MODEL_PATH``.

    If that path cannot be loaded (file not found, corrupted, etc.) a
    ``logging.warning`` is emitted and the function retries with
    ``config.FALLBACK_MODEL``. If that also fails the exception propagates.
    """
    from ultralytics import YOLO

    primary = config.MODEL_PATH
    try:
        model = YOLO(primary)
        logger.info("[RUNTIME VERIFICATION] Live Detection Engine loaded model: '%s' (Classes: %s)", primary, getattr(model, "names", {}))
        sync_model_classes(model)
        return model
    except Exception as exc:
        logger.warning(
            "Could not load primary model '%s' (%s). "
            "Falling back to '%s'.",
            primary,
            exc,
            config.FALLBACK_MODEL,
        )
        model = YOLO(config.FALLBACK_MODEL)
        logger.info("[RUNTIME VERIFICATION] Fallback model loaded: '%s' (Classes: %s)", config.FALLBACK_MODEL, getattr(model, "names", {}))
        sync_model_classes(model)
        return model


# ---------------------------------------------------------------------------
# Frame annotation helpers
# ---------------------------------------------------------------------------

def _is_network_source(src: str) -> bool:
    """True for stream URLs (rtsp/http/udp/…), False for local file paths."""
    return "://" in src


def _hex_to_bgr(hex_str: str) -> tuple[int, int, int]:
    """Convert a '#RRGGBB' string to an OpenCV BGR tuple."""
    try:
        hex_str = hex_str.lstrip("#")
        return tuple(int(hex_str[i:i+2], 16) for i in (4, 2, 0))  # BGR order
    except Exception:
        return (255, 212, 0)  # Fallback to cyan (#00d4ff)


def _draw_lines(frame: np.ndarray, counter: LineCounter) -> None:
    """Draw all virtual counting lines on *frame* in-place."""
    h, w = frame.shape[:2]
    for line in counter.lines:
        try:
            x1, y1 = int(line["x1"] * w), int(line["y1"] * h)
            x2, y2 = int(line["x2"] * w), int(line["y2"] * h)
            color = _hex_to_bgr(line.get("color", "#00d4ff"))
            
            # Draw line segment
            cv2.line(frame, (x1, y1), (x2, y2), color, config.LINE_THICKNESS)
            # Draw small circles at endpoints
            cv2.circle(frame, (x1, y1), 5, (0, 0, 255), -1) # Red start A
            cv2.circle(frame, (x2, y2), 5, (0, 255, 0), -1) # Green end B
            
            # Draw line name label near midpoint
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.putText(
                frame,
                line["name"],
                (mx + 10, my - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA
            )
        except Exception:
            pass


def _draw_track(
    frame:     np.ndarray,
    box:       tuple[float, float, float, float],
    track_id:  int,
    label:     str,
    has_crossed: bool = False,
    color_label: str | None = None,
) -> None:
    """Draw a bounding box and label for a single tracked vehicle.
    Default color: White (un-crossed).
    Crossed color: Green (after crossing line).
    """
    x1, y1, x2, y2 = (int(v) for v in box)

    # Bounding Box Color: White (255, 255, 255) before line crossing; Bright Green (0, 255, 0) after crossing
    colour = (0, 255, 0) if has_crossed else (255, 255, 255)

    thickness = config.BOX_THICKNESS + 1 if has_crossed else config.BOX_THICKNESS
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, thickness)

    counted_badge = " [COUNTED]" if has_crossed else ""
    if color_label and color_label != "Unknown":
        text = f"#{track_id}{counted_badge} {color_label} {label}"
    else:
        text = f"#{track_id}{counted_badge} {label}"

    (tw, th), _ = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, config.FONT_SCALE, 1
    )
    header_bg = (0, 160, 0) if has_crossed else (60, 60, 60)
    cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), header_bg, -1)
    cv2.putText(
        frame, text,
        (x1 + 2, y1 - 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        config.FONT_SCALE,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def _draw_counters(
    frame:   np.ndarray,
    counter: LineCounter,
) -> None:
    """Overlay down/up counts on the top-left corner of *frame* per line."""
    y_offset = 30
    for line in counter.lines:
        lid = line["id"]
        # Must not use len(counted_*_per_line[lid]): those sets evict retired track
        # ids, so their size falls as traffic clears. line_totals() is monotonic.
        down_cnt, up_cnt = counter.line_totals(lid)
        txt = f"{line['name']}: DOWN {down_cnt} | UP {up_cnt}"
        color = _hex_to_bgr(line.get("color", "#00d4ff"))
        cv2.putText(
            frame, txt,
            (10, y_offset),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )
        y_offset += 24




# ---------------------------------------------------------------------------
# HTTP posting helper
# ---------------------------------------------------------------------------

#: Consecutive failed reads before an uploaded video is declared finished.
#: A single failed decode mid-file must not truncate the run.
EOF_CONFIRM_READS = 5


async def _report_video_complete(
    client: httpx.AsyncClient,
    camera_id: str,
    status: str,
    detail: str | None = None,
) -> None:
    """
    Tell the backend an uploaded video finished processing.

    Best-effort: a failure here leaves the job showing as still processing, which
    is recoverable and far better than crashing the camera task after the events
    have already been recorded.
    """
    url = f"{config.API_BASE_URL}/api/videos/{camera_id}/complete"
    payload: dict[str, Any] = {"status": status}
    if detail:
        payload["detail"] = detail
    try:
        response = await client.post(
            url,
            json=payload,
            headers={"X-API-Key": config.SERVICE_API_KEY},
            timeout=5.0,
        )
        response.raise_for_status()
        logger.info("[%s] Reported video status '%s' to backend.", camera_id, status)
    except Exception as exc:
        logger.warning(
            "[%s] Could not report video completion (%s): %s", camera_id, status, exc
        )


async def _post_event(
    client: httpx.AsyncClient,
    event:  CrossingEvent,
    cam:    dict[str, Any],
) -> None:
    """
    POST a single ``CrossingEvent`` to the backend API.

    Headers
    -------
    X-API-Key : ``config.SERVICE_API_KEY``
    """
    url     = f"{config.API_BASE_URL}/api/events"
    payload = {
        "camera_id":     int(event.camera_id),
        "location_id":   int(cam.get("location_id", 1)),
        "lane_id":       int(getattr(event, "lane_id", cam.get("lane_id", 1))),
        "vehicle_class": event.vehicle_class,
        "vehicle_color": getattr(event, "vehicle_color", "Unknown"),
        "confidence":    round(event.confidence, 4),
        "crossing_dir":  event.direction,
        "timestamp":     event.timestamp.isoformat(),
        "track_id":      event.track_id,
    }

    headers = {"X-API-Key": config.SERVICE_API_KEY}

    try:
        response = await client.post(url, json=payload, headers=headers, timeout=5.0)
        response.raise_for_status()
        logger.debug("Event posted: track=%d dir=%s", event.track_id, event.direction)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Backend rejected event (HTTP %d): %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.warning("Could not reach backend: %s", exc)


# ---------------------------------------------------------------------------
# Thin wrapper so each detection index behaves like a track object
# ---------------------------------------------------------------------------

class _BoxWrapper:
    """Thin shim that exposes a single-index slice of an ultralytics Boxes."""

    __slots__ = ("_boxes", "_idx", "color", "_scaled_xyxy")

    def __init__(self, boxes: Any, idx: int, color: str = "Unknown", scaled_xyxy: Any = None) -> None:
        self._boxes = boxes
        self._idx   = idx
        self.color  = color
        self._scaled_xyxy = scaled_xyxy

    @property
    def id(self) -> Any:
        ids = self._boxes.id
        if ids is None:
            return None
        return ids[self._idx]

    @property
    def xyxy(self) -> Any:
        if self._scaled_xyxy is not None:
            return self._scaled_xyxy
        return self._boxes.xyxy[self._idx]

    @property
    def cls(self) -> Any:
        return self._boxes.cls[self._idx]

    @property
    def conf(self) -> Any:
        return self._boxes.conf[self._idx]


# ---------------------------------------------------------------------------
# Dedicated Threaded RTSP Capture (OpenCV fallback when GStreamer unavailable)
# ---------------------------------------------------------------------------

import threading


class ThreadedRTSPCapture:
    """Background thread wrapping cv2.VideoCapture for RTSP.

    Used as a fallback when native GStreamer PyGObject bindings are not
    available (e.g. Windows with ABI-incompatible GStreamer MSVC runtime).
    """

    CONNECTING = "CONNECTING"
    OK = "OK"
    STALLED = "STALLED"

    def __init__(
        self,
        source_parsed: int | str,
        first_frame_timeout: float | None = None,
        stall_timeout: float | None = None,
        sequential: bool = False,
    ):
        self.source_parsed = source_parsed
        self.sequential = sequential
        self._taken = threading.Event()
        self._taken.set()
        if isinstance(source_parsed, str) and _is_network_source(source_parsed):
            rtsp_buf = int(os.getenv("VCC_RTSP_BUFFER_SIZE", "10240000"))
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;tcp|stimeout;5000000|buffer_size;{rtsp_buf}|max_delay;500000"
            )
            self.cap = cv2.VideoCapture(source_parsed, cv2.CAP_FFMPEG)
        else:
            self.cap = cv2.VideoCapture(source_parsed)
        self.latest_frame = None
        self.ret = False
        self.running = True
        self.frame_seq = 0
        self._last_read_seq = -1
        self._pending_set: list[tuple[int, float]] = []
        self.opened_at = time.monotonic()
        self.last_frame_ts: float | None = None
        self.first_frame_timeout = (
            first_frame_timeout
            if first_frame_timeout is not None
            else float(os.getenv("VCC_FIRST_FRAME_TIMEOUT", "20.0"))
        )
        self.stall_timeout = (
            stall_timeout
            if stall_timeout is not None
            else float(os.getenv("VCC_STALL_TIMEOUT", "5.0"))
        )
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def _cap_ref(self) -> Any:
        with self.lock:
            return self.cap

    def isOpened(self) -> bool:
        cap = self._cap_ref()
        try:
            return cap is not None and cap.isOpened()
        except Exception:
            return False

    def get(self, prop_id: int) -> float:
        cap = self._cap_ref()
        try:
            if cap is not None and cap.isOpened():
                return cap.get(prop_id)
        except Exception:
            pass
        return 0.0

    def set(self, prop_id: int, value: float) -> bool:
        with self.lock:
            if self.cap is None:
                return False
            self._pending_set.append((prop_id, value))
            self.opened_at = time.monotonic()
            self.last_frame_ts = None
        return True

    def _update_loop(self) -> None:
        try:
            while self.running:
                cap = self._cap_ref()
                if cap is None:
                    time.sleep(0.05)
                    continue
                try:
                    if not cap.isOpened():
                        time.sleep(0.05)
                        continue
                except Exception:
                    time.sleep(0.05)
                    continue

                with self.lock:
                    pending, self._pending_set = self._pending_set, []
                for prop_id, value in pending:
                    try:
                        cap.set(prop_id, value)
                    except Exception:
                        pass

                if self.sequential:
                    while self.running and not self._taken.wait(timeout=0.1):
                        pass
                    if not self.running:
                        break

                try:
                    ret, frame = cap.read()
                except Exception:
                    ret, frame = False, None

                if ret and frame is not None:
                    with self.lock:
                        if not self.running:
                            break
                        self.latest_frame = frame
                        self.ret = True
                        self.frame_seq += 1
                        self.last_frame_ts = time.monotonic()
                    if self.sequential:
                        self._taken.clear()
                else:
                    with self.lock:
                        self.ret = False
                    time.sleep(0.01)
        finally:
            self._close_cap()

    def read(self) -> tuple[bool, np.ndarray | None]:
        ret, frame, _is_new = self.read_with_freshness()
        return ret, frame

    def read_with_freshness(self) -> tuple[bool, np.ndarray | None, bool]:
        with self.lock:
            if self.latest_frame is None:
                return False, None, False
            is_new = self.frame_seq != self._last_read_seq
            self._last_read_seq = self.frame_seq
            ret = self.ret or self._health_locked() == self.OK
            frame = self.latest_frame.copy()
        if is_new and self.sequential:
            self._taken.set()
        return ret, frame, is_new

    def _health_locked(self) -> str:
        now = time.monotonic()
        if self.last_frame_ts is None:
            if (now - self.opened_at) < self.first_frame_timeout:
                return self.CONNECTING
            return self.STALLED
        if (now - self.last_frame_ts) >= self.stall_timeout:
            return self.STALLED
        return self.OK

    def health(self) -> str:
        with self.lock:
            return self._health_locked()

    def _close_cap(self) -> None:
        with self.lock:
            cap, self.cap = self.cap, None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

    def release(self) -> None:
        self.running = False
        thread = self.thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.warning(
                    "[%s] Thread join timed out after 5.0s during release",
                    getattr(self, "source_parsed", "unknown"),
                )
        self._close_cap()


def _capture_health(cap: Any) -> str:
    """
    Liveness of *cap* for captures that expose :meth:`ThreadedRTSPCapture.health`.

    Captures without it (``GStreamerCapture``) block on their own frame queue, so
    a falsy read from them already means the pipeline is dead -> ``STALLED``.
    """
    probe = getattr(cap, "health", None)
    if probe is None:
        return ThreadedRTSPCapture.STALLED
    try:
        return probe()
    except Exception:
        return ThreadedRTSPCapture.STALLED


def _release_capture_in_background(cap: Any, camera_id: str) -> None:
    """
    Release *cap* off the event loop, without waiting for it.

    ``release()`` joins the reader thread for up to 5 s.  Calling it inline from
    a ``finally`` block stalled every other camera and the MJPEG streamer for
    that long on each restart.  A plain daemon thread is used rather than
    ``run_in_executor`` because this runs during task cancellation, where
    awaiting anything re-raises ``CancelledError`` immediately and the loop may
    already be shutting down.
    """
    def _do_release() -> None:
        try:
            cap.release()
        except Exception:
            logger.debug("[%s] Capture release raised; ignoring.", camera_id)
        logger.info("[%s] Capture released.", camera_id)

    threading.Thread(
        target=_do_release, name=f"cap-release-{camera_id}", daemon=True
    ).start()



def handle_async_exception(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    """Global exception handler for asyncio event loop to prevent swallowed background task crashes."""
    msg = context.get("message")
    exc = context.get("exception")
    logger.error("[ASYNC EXCEPTION] %s", msg, exc_info=exc)
    print(f"[SYSTEM ASYNC EXCEPTION] {msg}: {exc}")


# ---------------------------------------------------------------------------
# Per-camera async task
# ---------------------------------------------------------------------------

async def run_camera(
    camera_config: dict[str, Any],
    counter:       LineCounter,
    frame_queues:  dict[str, asyncio.Queue],
) -> None:
    """
    Continuous inference loop for a single camera.
    """
    camera_id = camera_config["camera_id"]
    source    = camera_config["source"]

    try:
        source_parsed: int | str = int(source)
    except (ValueError, TypeError):
        source_parsed = source

    if isinstance(source_parsed, str) and not _is_network_source(source_parsed) and not os.path.isabs(source_parsed):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        resolved = os.path.abspath(os.path.join(repo_root, source_parsed))
        if os.path.exists(resolved):
            source_parsed = resolved

    is_file_source = isinstance(source_parsed, str) and not _is_network_source(source_parsed)
    if is_file_source:
        logger.info("[%s] File source detected — using sequential capture (no frame drops).", camera_id)

    single_pass = str(camera_config.get("source_type") or "live") == "upload"
    eof_streak = 0
    if single_pass:
        logger.info("[%s] Uploaded video — single-pass mode, will finish at EOF.", camera_id)

    logger.info("[%s] Opening source: %s", camera_id, source_parsed)

    loop = asyncio.get_running_loop()
    loop.set_exception_handler(handle_async_exception)

    try:
        model = await asyncio.wait_for(
            loop.run_in_executor(None, load_model),
            timeout=15.0
        )
    except asyncio.TimeoutError:
        logger.error("[%s] Camera pipeline startup / model load exceeded 15s — likely blocking call", camera_id)
        return

    async with httpx.AsyncClient() as http_client:
        cap = None
        if GST_AVAILABLE and isinstance(source_parsed, str):
            logger.info("[%s] Initializing Native GStreamer PyGObject capture pipeline (%s)...", camera_id, gst_version_string())
            gst_cap = GStreamerCapture(source_parsed, sequential=is_file_source)
            started = await loop.run_in_executor(None, gst_cap.start)
            if started:
                cap = gst_cap
                logger.info("[%s] Native GStreamer pipeline active and operational.", camera_id)
            else:
                logger.warning("[%s] Native GStreamer pipeline failed to start. Falling back to Threaded RTSP Capture...", camera_id)
                await loop.run_in_executor(None, gst_cap.release)

        if cap is None:
            logger.info("[%s] Opening source using Threaded RTSP Capture (OpenCV fallback)...", camera_id)
            cap = await loop.run_in_executor(
                None, lambda: ThreadedRTSPCapture(source_parsed, sequential=is_file_source)
            )

        retry_count = 0
        while not cap.isOpened() and not single_pass:
            retry_count += 1
            if retry_count <= 3 or retry_count % 10 == 0:
                logger.warning(
                    "[%s] Cannot open live camera '%s' (attempt %d). Retrying in 2.0 s...",
                    camera_id, source, retry_count,
                )
            await asyncio.sleep(2.0)
            await loop.run_in_executor(None, cap.release)
            if GST_AVAILABLE and isinstance(source_parsed, str):
                gst_cap = GStreamerCapture(source_parsed, sequential=is_file_source)
                started = await loop.run_in_executor(None, gst_cap.start)
                if started:
                    cap = gst_cap
                    continue
            cap = await loop.run_in_executor(
                None, lambda: ThreadedRTSPCapture(source_parsed, sequential=is_file_source)
            )

        if not cap.isOpened() and single_pass:
            logger.error(
                "[%s] Cannot open uploaded video source '%s'. Task exiting.",
                camera_id, source,
            )
            await _report_video_complete(http_client, camera_id, "failed")
            return

        # Inspect stream codec off the main thread
        try:
            fourcc = await loop.run_in_executor(None, lambda: int(cap.get(cv2.CAP_PROP_FOURCC)))
            codec_str = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip().lower()
            if codec_str in ["hevc", "h265", "265h"]:
                logger.info("[%s] Stream Codec: H.265 (HEVC) detected. Decoding via lossless TCP stream.", camera_id)
            elif codec_str in ["avc1", "h264", "264h"]:
                logger.info("[%s] Stream Codec: H.264 (AVC) detected. Decoding via lossless TCP stream.", camera_id)
            else:
                logger.info("[%s] Stream Codec: %s (FOURCC %d) detected. Decoding via lossless TCP stream.", camera_id, codec_str or "Unknown", fourcc)
        except Exception:
            pass

        logger.info("[%s] Capture open. Starting inference loop.", camera_id)

        # Announce that an uploaded video has actually started decoding. Without
        # this it would sit at 'pending' until EOF and then jump straight to
        # 'completed' -- and the UI only offers the live annotated preview while a
        # job reads 'processing', so the user would never see it work.
        if single_pass:
            await _report_video_complete(http_client, camera_id, "processing")
        
        # CPU Optimization: target FPS pacing
        target_fps = float(os.getenv("VCC_TARGET_FPS", "15.0"))
        target_delay = 1.0 / target_fps if target_fps > 0 else 0

        # Shared state for non-blocking decoupled display & inference backlog guard
        latest_tracks: list[Any] = []
        infer_in_flight: bool = False
        track_color_state: dict[int, dict[str, Any]] = {}

        async def _run_async_infer(frame_to_infer: np.ndarray, o_h: int, o_w: int):
            nonlocal infer_in_flight, latest_tracks
            try:
                infer_sz = config.INFER_IMGSZ
                if o_h != infer_sz or o_w != infer_sz:
                    infer_frame = cv2.resize(frame_to_infer, (infer_sz, infer_sz), interpolation=cv2.INTER_LINEAR)
                    scale_x = o_w / float(infer_sz)
                    scale_y = o_h / float(infer_sz)
                else:
                    infer_frame = frame_to_infer
                    scale_x = 1.0
                    scale_y = 1.0

                loop_cur = asyncio.get_running_loop()
                results = await loop_cur.run_in_executor(
                    INFER_EXECUTOR,
                    lambda f=infer_frame: model.track(
                        f,
                        persist    = True,
                        tracker    = config.TRACKER,
                        conf       = config.CONF_THRESHOLD,
                        iou        = config.IOU_THRESHOLD,
                        classes    = list(config.VEHICLE_CLASS_MAP.keys()),
                        verbose    = False,
                        imgsz      = infer_sz,
                    ),
                )

                new_tracks: list[Any] = []
                if results and results[0].boxes is not None:
                    boxes = results[0].boxes
                    for i in range(len(boxes)):
                        cls_raw = boxes.cls[i]
                        cls_id = int(cls_raw.item() if hasattr(cls_raw, "item") else cls_raw)
                        cls_name = config.VEHICLE_CLASS_MAP.get(cls_id, "car")

                        conf_raw = boxes.conf[i]
                        conf_val = float(conf_raw.item() if hasattr(conf_raw, "item") else conf_raw)
                        min_conf = config.CLASS_CONF_THRESHOLDS.get(cls_name, 0.35)
                        if conf_val < min_conf:
                            continue

                        box_slice = boxes.xyxy[i]
                        b_scaled = (
                            float(box_slice[0]) * scale_x,
                            float(box_slice[1]) * scale_y,
                            float(box_slice[2]) * scale_x,
                            float(box_slice[3]) * scale_y,
                        )

                        t_id = int(boxes.id[i]) if (boxes.id is not None and i < len(boxes.id)) else None
                        v_color = "Unknown"

                        if t_id is not None:
                            st = track_color_state.setdefault(t_id, {
                                "color": "Unknown",
                                "frames_since_detect": config.COLOR_DETECT_INTERVAL,
                                "best_conf": 0.0,
                                "best_bbox": None,
                            })
                            st["frames_since_detect"] += 1
                            if conf_val > st["best_conf"]:
                                st["best_conf"] = conf_val
                                st["best_bbox"] = b_scaled

                            if st["frames_since_detect"] >= config.COLOR_DETECT_INTERVAL:
                                target_bbox = st["best_bbox"] if st["best_bbox"] is not None else b_scaled
                                st["color"] = detect_vehicle_color(frame_to_infer, target_bbox)
                                st["frames_since_detect"] = 0
                                st["best_conf"] = 0.0
                                st["best_bbox"] = None
                            v_color = st["color"]
                        else:
                            v_color = detect_vehicle_color(frame_to_infer, b_scaled)

                        new_tracks.append(_BoxWrapper(boxes, i, color=v_color, scaled_xyxy=b_scaled))

                latest_tracks = new_tracks
                events = counter.process_tracks(new_tracks, o_h, frame_w=o_w)
                for ev in events:
                    asyncio.create_task(_post_event(http_client, ev, camera_config))
            except Exception as e:
                logger.error("[%s] Error in background inference worker: %s", camera_id, e)
            finally:
                infer_in_flight = False

        connecting_start_time: float | None = None
        connecting_logged = False
        fail_streak = 0
        backoff = RECONNECT_BASE_BACKOFF
        reconnect_timestamps: list[float] = []
        fps_frame_count = 0
        fps_start_time = time.monotonic()
        using_native_gst = GST_AVAILABLE and isinstance(source_parsed, str)

        try:
            while True:
                start_time = asyncio.get_event_loop().time()

                reader = getattr(cap, "read_with_freshness", None)
                if reader is not None:
                    ret, frame, is_new = await loop.run_in_executor(None, reader)
                else:
                    ret, frame = await loop.run_in_executor(None, cap.read)
                    is_new = ret

                if not ret:
                    health = _capture_health(cap)

                    if health == ThreadedRTSPCapture.CONNECTING:
                        if connecting_start_time is None:
                            connecting_start_time = time.monotonic()
                        elapsed_conn = time.monotonic() - connecting_start_time
                        if elapsed_conn > 8.0:
                            logger.warning(
                                "[%s] Stuck CONNECTING for %.1fs — forcing reconnect",
                                camera_id, elapsed_conn
                            )
                            await loop.run_in_executor(None, cap.release)
                            cap = await loop.run_in_executor(None, lambda: ThreadedRTSPCapture(source_parsed, sequential=is_file_source))
                            connecting_start_time = time.monotonic()
                            connecting_logged = False
                            continue
                        if not connecting_logged:
                            logger.info(
                                "[%s] Waiting for first frame from source...",
                                camera_id,
                            )
                            connecting_logged = True
                        await asyncio.sleep(0.2)
                        continue

                    connecting_start_time = None

                    gst_upload_eos = using_native_gst and single_pass and not cap.isOpened()
                    if is_file_source and (not using_native_gst or gst_upload_eos):
                        eof_streak += 1
                        if single_pass and eof_streak >= EOF_CONFIRM_READS:
                            logger.info(
                                "[%s] End of uploaded video — single pass complete. "
                                "Counted %d down / %d up.",
                                camera_id, counter.total_down, counter.total_up,
                            )
                            await _report_video_complete(http_client, camera_id, "completed")
                            return

                        if not single_pass:
                            if hasattr(cap, "set"):
                                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        await asyncio.sleep(0.05)
                        continue

                    fail_streak += 1
                    if fail_streak < 30 and cap.isOpened():
                        await asyncio.sleep(0.01)
                        continue

                    now_mono = time.monotonic()
                    reconnect_timestamps = [t for t in reconnect_timestamps if now_mono - t < 3600]
                    reconnect_timestamps.append(now_mono)
                    if len(reconnect_timestamps) >= 15:
                        logger.critical(
                            "[%s] CRITICAL: Reconnected %d times in the last 1 hour. "
                            "Check IP camera RTSP session cap / network instability.",
                            camera_id, len(reconnect_timestamps)
                        )

                    logger.warning(
                        "[%s] RTSP stream stalled after %d consecutive frame failures -- reconnecting in %.1f s...",
                        camera_id, fail_streak, backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, RECONNECT_MAX_BACKOFF)

                    await loop.run_in_executor(None, cap.release)

                    if using_native_gst:
                        gst_cap = GStreamerCapture(source_parsed)
                        started = await loop.run_in_executor(None, gst_cap.start)
                        if started:
                            cap = gst_cap
                            logger.info("[%s] Reconnected via native GStreamer.", camera_id)
                        else:
                            gst_cap.release()
                            logger.warning("[%s] GStreamer reconnect failed, trying FFMPEG.", camera_id)
                            cap = await loop.run_in_executor(None, lambda: ThreadedRTSPCapture(source_parsed, sequential=is_file_source))
                            using_native_gst = False
                    else:
                        cap = await loop.run_in_executor(None, lambda: ThreadedRTSPCapture(source_parsed, sequential=is_file_source))
                    connecting_logged = False
                    fail_streak = 0
                    continue

                if fail_streak:
                    logger.info("[%s] Capture recovered after %d failed attempts.", camera_id, fail_streak)
                    fail_streak = 0
                    backoff     = RECONNECT_BASE_BACKOFF
                eof_streak = 0
                connecting_logged = False

                if not is_new:
                    await asyncio.sleep(0.005)
                    continue

                orig_h, orig_w = frame.shape[:2]

                try:
                    import streamer
                    streamer.update_raw_frame(camera_id, frame)
                except Exception:
                    pass

                # Dispatch non-blocking background inference if no job is currently in flight
                if not infer_in_flight:
                    infer_in_flight = True
                    asyncio.create_task(_run_async_infer(frame, orig_h, orig_w))

                # ---- Immediate Non-Blocking Display Pushing (Native Capture FPS) ----
                annotated = frame.copy()
                _draw_lines(annotated, counter)
                _draw_counters(annotated, counter)

                for t in list(latest_tracks):
                    try:
                        tid_raw = t.id
                        if tid_raw is None:
                            continue
                        tid     = int(tid_raw.item() if hasattr(tid_raw, "item") else tid_raw)
                        box     = t.xyxy
                        cls_raw = t.cls
                        cls_id  = int(cls_raw.item() if hasattr(cls_raw, "item") else cls_raw)
                        label   = config.VEHICLE_CLASS_MAP.get(cls_id, "vehicle")
                        has_crossed = counter.has_crossed(tid)

                        _draw_track(
                            annotated,
                            (float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                            tid, label,
                            has_crossed=has_crossed,
                            color_label=getattr(t, "color", None)
                        )
                    except Exception:
                        pass

                q = frame_queues.get(camera_id)
                if q is not None:
                    if q.full():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        q.put_nowait(annotated)
                    except asyncio.QueueFull:
                        pass

                fps_frame_count += 1
                now_ts = time.monotonic()
                if (now_ts - fps_start_time) >= 30.0:
                    actual_fps = fps_frame_count / (now_ts - fps_start_time)
                    logger.info(
                        "[%s] Telemetry: Processing at %.2f FPS (Target: %.1f FPS, Active Tracks: %d)",
                        camera_id, actual_fps, target_fps, len(track_color_state),
                    )
                    fps_frame_count = 0
                    fps_start_time = now_ts



                # Sleep to maintain target FPS and yield CPU
                if target_delay > 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    sleep_time = target_delay - elapsed
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                    else:
                        await asyncio.sleep(0.005) # minimal yield to keep event loop responsive
                else:
                    await asyncio.sleep(0.005)


        except asyncio.CancelledError:
            logger.info("[%s] Camera task cancelled.", camera_id)
        except Exception as exc:
            logger.error("[%s] UNHANDLED EXCEPTION in inference loop: %s", camera_id, exc, exc_info=True)
        finally:
            # Non-blocking: release() joins the reader thread for up to 5 s and
            # this runs on the event loop during task cancellation.
            _release_capture_in_background(cap, camera_id)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def poll_settings_config() -> None:
    """
    Background task that polls GET /api/settings/config every 10 seconds.
    Updates config.CONF_THRESHOLD in-place.
    """
    url = f"{config.API_BASE_URL}/api/settings/config"
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    new_val = float(data["confidence_threshold"])
                    if config.CONF_THRESHOLD != new_val:
                        logger.info("Updating confidence threshold dynamically: %s -> %s", config.CONF_THRESHOLD, new_val)
                        config.CONF_THRESHOLD = new_val
        except Exception as exc:
            logger.warning("Failed to poll dynamic settings configuration (using last-known-good %s): %s", config.CONF_THRESHOLD, exc)
        await asyncio.sleep(10.0)


async def main() -> None:
    """Spin up one coroutine per configured camera and settings poll task."""
    counters     = create_counters_from_config()
    frame_queues = {
        cam["camera_id"]: asyncio.Queue(maxsize=config.FRAME_BUFFER_SIZE)
        for cam in config.CAMERAS
    }

    tasks = [
        asyncio.create_task(
            run_camera(cam, counters[cam["camera_id"]], frame_queues),
            name=f"camera-{cam['camera_id']}",
        )
        for cam in config.CAMERAS
    ]
    # Add settings config poll task
    tasks.append(asyncio.create_task(poll_settings_config(), name="settings-poll"))

    logger.info("Tracker started — %d tasks.", len(tasks))
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
