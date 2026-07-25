"""
training_worker.py - Isolated YOLO training subprocess.

Executed as ``python -u training_worker.py --epochs N --batch B --data /path/data.yaml
                    --output /path/model.pt --work-dir /path/train_runs``.

Communication with the parent (training_process.py) is via structured stdout
lines prefixed with ``@@VCC ``.  Everything else on stdout/stderr is treated as
an opaque log line by the parent.

This script intentionally imports ultralytics/torch **only here** — the parent
process never loads them, keeping the live-detection backend lightweight.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys


# ---------------------------------------------------------------------------
# Safe pipe wrapper — ultralytics' tqdm writes \r, ANSI codes, and bare \n to
# stderr.  On Windows, a text-mode subprocess pipe raises
# ``OSError: [Errno 22] Invalid argument`` for some of those writes.  This
# wrapper silently absorbs the error so the training loop keeps running.
# ---------------------------------------------------------------------------
class _SafePipeWriter(io.TextIOBase):
    """Drop-in replacement for sys.stderr that swallows broken-pipe / invalid-arg errors."""

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def write(self, s):
        try:
            return self._wrapped.write(s)
        except OSError:
            return len(s)  # pretend the write succeeded

    def flush(self):
        try:
            self._wrapped.flush()
        except OSError:
            pass

    def fileno(self):
        return self._wrapped.fileno()

    @property
    def encoding(self):
        return getattr(self._wrapped, "encoding", "utf-8")

    def isatty(self):
        return False


# Install the safe wrappers BEFORE any library import touches the streams.
sys.stderr = _SafePipeWriter(sys.stderr)
sys.stdout = _SafePipeWriter(sys.stdout)


EVENT_PREFIX = "@@VCC "


def _emit(event: dict) -> None:
    """Write a structured event line to stdout for the parent to consume."""
    sys.stdout.write(EVENT_PREFIX + json.dumps(event) + "\n")
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="VCC YOLO Training Worker")
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--data", type=str, required=True, help="Path to data.yaml")
    parser.add_argument("--output", type=str, required=True, help="Where to save the final .pt weights")
    parser.add_argument("--work-dir", type=str, required=True, help="Working directory for YOLO outputs")
    args = parser.parse_args()

    # ---- Resolve base model ------------------------------------------------
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(backend_dir)

    base_model_candidates = [
        os.path.join(repo_root, "yolo11n.pt"),
        os.path.join(repo_root, "yolo11s.pt"),
        "yolo11n.pt",
    ]
    base_model = "yolo11n.pt"
    for candidate in base_model_candidates:
        if os.path.isfile(candidate):
            base_model = candidate
            break

    print(f"Base model: {base_model}")
    print(f"Data YAML:  {args.data}")
    print(f"Epochs:     {args.epochs}")
    print(f"Batch size: {args.batch}")
    print(f"Output:     {args.output}")
    print(f"Work dir:   {args.work_dir}")

    # ---- Import ultralytics ------------------------------------------------
    try:
        # Suppress tqdm in data loaders to avoid pipe write issues
        os.environ["TQDM_DISABLE"] = "0"  # keep enabled but safe via wrapper

        from ultralytics import YOLO
        import torch
    except ImportError as e:
        print(f"ERROR: Could not import ultralytics/torch: {e}", file=sys.stderr)
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    imgsz = 640
    workers = 0 if os.name == "nt" or device == "cpu" else 2

    _emit({
        "event": "start",
        "base_model": os.path.basename(base_model),
        "device": device,
        "imgsz": imgsz,
        "workers": workers,
    })

    # ---- Train -------------------------------------------------------------
    model = YOLO(base_model)

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=imgsz,
        device=device,
        workers=workers,
        project=args.work_dir,
        name="vcc_train",
        exist_ok=True,
        verbose=True,
    )

    # ---- Export weights -----------------------------------------------------
    best_pt = os.path.join(args.work_dir, "vcc_train", "weights", "best.pt")
    last_pt = os.path.join(args.work_dir, "vcc_train", "weights", "last.pt")

    weights_src = best_pt if os.path.exists(best_pt) else last_pt

    if os.path.exists(weights_src):
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        shutil.copy2(weights_src, args.output)
        print(f"Model weights saved to: {args.output}")
        _emit({"event": "complete", "output": args.output})
    else:
        print("ERROR: No trained weights found after training.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
