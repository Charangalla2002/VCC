import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# Load backend/.env to get DATABASE_URL. Anchored at this file rather than the
# cwd so the path holds no matter where the process is launched from.
load_dotenv(os.path.join(_REPO_ROOT, "backend", ".env"))

# db_dialect owns every PostgreSQL/SQLite difference, including resolving a
# relative sqlite:// path to an absolute one. Sharing it with the backend is what
# guarantees both processes open the same database file.
sys.path.append(os.path.join(_REPO_ROOT, "backend"))
from db_dialect import create_engine_from_url, normalize_database_url  # noqa: E402

# No argument — see backend/database.py: passing the ambient value explicitly
# bypasses the VCC_DATABASE_URL / project-.env precedence chain.
DATABASE_URL = normalize_database_url()

sys.path.append('detection')
import config
from tracker import run_camera
from counter import LineCounter
from streamer import start_server

# One engine for the process lifetime; the old code opened a fresh connection on
# every 5-second poll.
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine_from_url(DATABASE_URL)
    return _engine


async def fetch_cameras():
    """Read cameras + their counting lines. Works on PostgreSQL and SQLite alike."""
    try:
        async with _get_engine().connect() as conn:
            # Fetch counting lines
            lines_rows = (await conn.execute(text(
                "SELECT id, camera_id, name, x1, y1, x2, y2, lane_id, direction, color "
                "FROM counting_lines"
            ))).mappings().all()

            cam_lines_map = {}
            for lr in lines_rows:
                cid = str(lr["camera_id"])
                if cid not in cam_lines_map:
                    cam_lines_map[cid] = []
                cam_lines_map[cid].append({
                    "id": lr["id"],
                    "name": lr["name"],
                    "x1": lr["x1"], "y1": lr["y1"], "x2": lr["x2"], "y2": lr["y2"],
                    "lane_id": lr["lane_id"],
                    "direction": lr["direction"],
                    "color": lr["color"]
                })

            # Fetch cameras
            # source_type distinguishes a live feed from an uploaded video, which
            # is processed once and then reported rather than looped forever.
            # COALESCE so rows predating the column still behave as live cameras.
            rows = (await conn.execute(text(
                "SELECT id, name, rtsp_url, location_id, counting_line, "
                "COALESCE(source_type, 'live') AS source_type, "
                "processing_status "
                "FROM cameras"
            ))).mappings().all()

        cams = []
        for r in rows:
            # An uploaded video that has already been processed is a finished job,
            # not a camera. Its task exits at EOF, and without this the supervisor
            # would see a completed task and respawn it every poll -- reprocessing
            # the same file forever and multiplying its counts.
            if r["source_type"] == "upload" and r["processing_status"] in ("completed", "failed"):
                continue

            url = r["rtsp_url"]
            if not url:
                url = "0" # fallback to webcam if no url
            cid_str = str(r["id"])
            cams.append({
                "camera_id": cid_str,
                "name": r["name"],
                "source": url,
                "location_id": r["location_id"],
                "lane_id": int(os.getenv("VCC_DEFAULT_LANE_ID", "1")),
                "direction": os.getenv("VCC_DEFAULT_DIRECTION", "both"),
                "line_y": float(os.getenv("VCC_DEFAULT_LINE_Y", "0.5")),
                "counting_line": r["counting_line"],
                "counting_lines": cam_lines_map.get(cid_str, []),
                "source_type": r["source_type"],
                "processing_status": r["processing_status"],
            })
        return cams
    except Exception as e:
        print(f"[SYSTEM] Database error fetching cameras: {e}")
        return []

async def monitor_cameras_loop(active_tasks, queues, counters=None):
    """
    Reconcile running camera pipelines against the database every few seconds.

    Change classification matters here. Only the video *source* requires tearing
    down a pipeline -- that is the one thing we cannot swap without reopening the
    capture. Counting-line edits are applied in place via ``LineCounter.update_lines``.

    Previously any difference at all (including a colour change, because whole
    dicts were compared) cancelled the task. That reloaded the YOLO model, dropped
    the RTSP connection, and reset the counter -- which double-counted every vehicle
    still on screen, and made the operator's live view stutter every time they
    touched the editor.
    """
    if counters is None:
        counters = {}
    print("[SYSTEM] Starting dynamic camera coordinator loop...")
    while True:
        try:
            cameras = await fetch_cameras()
            db_cameras_map = {cam["camera_id"]: cam for cam in cameras}

            # 1. Stop tasks for cameras that were deleted, modified, or crashed
            for camera_id in list(active_tasks.keys()):
                current_task = active_tasks[camera_id]
                if current_task.done():
                    exc = None
                    try:
                        exc = current_task.exception()
                    except asyncio.CancelledError:
                        pass
                    if exc:
                        print(f"[SYSTEM] Camera {camera_id} task crashed with exception: {exc}")
                    else:
                        print(f"[SYSTEM] Camera {camera_id} task exited.")
                    active_tasks.pop(camera_id)
                    queues.pop(camera_id, None)
                    counters.pop(camera_id, None)
                    continue

                if camera_id not in db_cameras_map:
                    print(f"[SYSTEM] Camera {camera_id} deleted. Stopping pipeline...")
                    task = active_tasks.pop(camera_id)
                    task.cancel()
                    queues.pop(camera_id, None)
                    counters.pop(camera_id, None)
                else:
                    running_config = current_task.vcc_config
                    db_config = db_cameras_map[camera_id]

                    # Only a source change forces a restart.
                    if running_config["source"] != db_config["source"]:
                        print(f"[SYSTEM] Camera {camera_id} source changed. Restarting pipeline...")
                        task = active_tasks.pop(camera_id)
                        task.cancel()
                        queues.pop(camera_id, None)
                        counters.pop(camera_id, None)
                        continue

                    # Everything else is applied live, with no interruption.
                    counter = counters.get(camera_id)
                    if counter is not None:
                        new_lines = db_config.get("counting_lines") or []
                        if new_lines:
                            counter.update_lines(new_lines)
                        elif db_config.get("counting_line") != running_config.get("counting_line"):
                            # Legacy single-line column still in use for this camera.
                            print(
                                f"[SYSTEM] Camera {camera_id} legacy counting_line changed. "
                                "Restarting pipeline..."
                            )
                            task = active_tasks.pop(camera_id)
                            task.cancel()
                            queues.pop(camera_id, None)
                            counters.pop(camera_id, None)
                            continue

                    # Keep the attached config current so the next pass diffs correctly.
                    current_task.vcc_config = db_config


            # 2. Start tasks for new cameras
            for camera_id, cam in db_cameras_map.items():
                if camera_id not in active_tasks:
                    print(f"[SYSTEM] New camera {camera_id} ({cam['name']}) detected. Starting native pipeline...")
                    
                    # Create queue and counter
                    queues[camera_id] = asyncio.Queue(maxsize=config.FRAME_BUFFER_SIZE)
                    counter = LineCounter(
                        camera_id=camera_id,
                        line_y=cam["line_y"],
                        direction=cam["direction"],
                        counting_line=cam.get("counting_line"),
                        lines=cam.get("counting_lines", [])
                    )
                    
                    # Spawn task
                    task = asyncio.create_task(
                        run_camera(cam, counter, queues),
                        name=f"camera-{camera_id}"
                    )
                    task.vcc_config = cam  # Attach config to task for change-detection
                    active_tasks[camera_id] = task
                    # Retained so later line edits can be applied to the live counter
                    # instead of being forced through a pipeline restart.
                    counters[camera_id] = counter



        except Exception as e:
            print(f"[SYSTEM] Error in camera coordinator loop: {e}")
            
        await asyncio.sleep(5)

async def run():
    try:
        active_tasks = {}
        queues = {}
        counters = {}

        # Start the HTTP streamer server
        print("[SYSTEM] Starting MJPEG Streamer Server (Port 8001)...")
        streamer_task = asyncio.create_task(start_server(queues))

        # Run the dynamic coordinator
        await monitor_cameras_loop(active_tasks, queues, counters)
    except Exception as e:
        print(f"[SYSTEM] Critical error in detection main process: {e}")

if __name__ == "__main__":
    asyncio.run(run())
