"""
tests/test_counter.py — Unit tests for counter.LineCounter.

All tests are synchronous (counter.process_tracks is not async).
No external dependencies beyond the stdlib and the detection package itself.

Mock track objects
------------------
``_FakeTrack`` mimics the interface ``LineCounter.process_tracks`` expects:
    .id    → int
    .xyxy  → list[float]  [x1, y1, x2, y2]
    .cls   → int
    .conf  → float
"""

from __future__ import annotations

import os
import sys

# Allow importing from the parent detection/ directory without pip-installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from counter import CrossingEvent, LineCounter


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class _FakeTrack:
    """Minimal stand-in for an ultralytics single-detection wrapper."""

    def __init__(
        self,
        track_id: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        cls_id: int   = 2,      # 2 = car (COCO)
        conf:   float = 0.90,
    ) -> None:
        self.id   = track_id
        self.xyxy = [x1, y1, x2, y2]
        self.cls  = cls_id
        self.conf = conf


def _counter(
    direction: str   = "down",
    line_y:    float = 0.5,
    camera_id: str   = "test_cam",
) -> LineCounter:
    """Convenience factory for test counters."""
    return LineCounter(camera_id=camera_id, line_y=line_y, direction=direction)


FRAME_H = 1000          # standard test frame height
LINE_PX = FRAME_H * 0.5 # = 500


def _above(track_id: int, **kw) -> _FakeTrack:
    """Return a track whose centroid is clearly above the line (y=300)."""
    return _FakeTrack(track_id, 100, 200, 200, 400, **kw)   # centroid_y=300


def _below(track_id: int, **kw) -> _FakeTrack:
    """Return a track whose centroid is clearly below the line (y=700)."""
    return _FakeTrack(track_id, 100, 600, 200, 800, **kw)   # centroid_y=700


# ---------------------------------------------------------------------------
# Test 1 — downward crossing recorded when direction='down'
# ---------------------------------------------------------------------------

def test_crosses_down_direction_down():
    """
    Vehicle centroid moves top→bottom across the line.
    direction='down' → must produce exactly 1 event with direction='down'.
    """
    c = _counter(direction="down")

    # Frame 1: seed position above line
    evs = c.process_tracks([_above(1)], FRAME_H)
    assert evs == [], "No crossing yet — only one frame observed"

    # Frame 2: centroid crosses to below line
    evs = c.process_tracks([_below(1)], FRAME_H)

    assert len(evs) == 1
    assert evs[0].direction  == "down"
    assert evs[0].track_id   == 1
    assert evs[0].camera_id  == "test_cam"
    assert isinstance(evs[0], CrossingEvent)


# ---------------------------------------------------------------------------
# Test 2 — upward crossing is NOT recorded when direction='down'
# ---------------------------------------------------------------------------

def test_crosses_up_direction_down():
    """
    Vehicle centroid moves bottom→top across the line.
    direction='down' → must produce 0 events.
    """
    c = _counter(direction="down")

    c.process_tracks([_below(2)], FRAME_H)          # seed below line
    evs = c.process_tracks([_above(2)], FRAME_H)    # cross upward

    assert evs == [], f"Expected 0 events, got {evs}"


# ---------------------------------------------------------------------------
# Test 3 — same track crossing down twice is deduplicated
# ---------------------------------------------------------------------------

def test_dedup_same_direction():
    """
    Track #3 crosses downward twice.  The second crossing must produce no event
    because the track-id is already in ``counted_down``.
    """
    c = _counter(direction="down")

    # First crossing
    c.process_tracks([_above(3)], FRAME_H)
    evs1 = c.process_tracks([_below(3)], FRAME_H)
    assert len(evs1) == 1, "First crossing should be counted"

    # Simulate going back above and crossing down again
    c.process_tracks([_above(3)], FRAME_H)
    evs2 = c.process_tracks([_below(3)], FRAME_H)
    assert evs2 == [], "Second crossing of same track in same direction must be deduplicated"


# ---------------------------------------------------------------------------
# Test 4 — direction='both': downward crossing goes to counted_down only
# ---------------------------------------------------------------------------

def test_both_direction_down_first():
    """
    direction='both', track crosses downward.
    Result: track_id ∈ counted_down,  NOT ∈ counted_up.
    """
    c = _counter(direction="both")

    c.process_tracks([_above(4)], FRAME_H)
    evs = c.process_tracks([_below(4)], FRAME_H)

    assert len(evs) == 1
    assert evs[0].direction == "down"
    assert 4 in  c.counted_down_per_line[1]
    assert 4 not in c.counted_up_per_line[1]


# ---------------------------------------------------------------------------
# Test 5 — direction='both': down then up → 2 events, both directions counted
# ---------------------------------------------------------------------------

def test_both_direction_up_after_down():
    """
    direction='both', same track crosses down then later crosses up.
    Both crossings must be recorded — 2 total events.
    """
    c = _counter(direction="both")

    # Down crossing
    c.process_tracks([_above(5)], FRAME_H)
    evs_d = c.process_tracks([_below(5)], FRAME_H)
    assert len(evs_d) == 1 and evs_d[0].direction == "down"

    # Up crossing (same track)
    c.process_tracks([_below(5)], FRAME_H)           # re-seed below line
    evs_u = c.process_tracks([_above(5)], FRAME_H)  # cross upward

    assert len(evs_u) == 1 and evs_u[0].direction == "up"

    assert 5 in c.counted_down_per_line[1]
    assert 5 in c.counted_up_per_line[1]


# ---------------------------------------------------------------------------
# Test 6 — direction='both': counted_down does NOT block a subsequent up
# ---------------------------------------------------------------------------

def test_both_no_cross_block():
    """
    Critical independence test: the counted_down and counted_up sets are
    completely independent.  Being in counted_down MUST NOT prevent the
    same track from being counted going up.
    """
    c = _counter(direction="both")

    # Down crossing
    c.process_tracks([_above(6)], FRAME_H)
    c.process_tracks([_below(6)], FRAME_H)
    assert 6 in c.counted_down_per_line[1]

    # The up-dedup set is the ONLY gate on a future up crossing, and being
    # counted 'down' must not have populated it.  (This replaces the old
    # ``c._should_count_up(6)`` helper, which no longer exists — its entire
    # contract was "track is not already in the up dedup set".)
    assert 6 not in c.counted_up_per_line[1], (
        "counted_down membership must not block a future up crossing"
    )

    # Actually cross upward — must produce 1 up event
    c.process_tracks([_below(6)], FRAME_H)
    evs_u = c.process_tracks([_above(6)], FRAME_H)

    assert len(evs_u) == 1, f"Expected 1 up event, got {len(evs_u)}"
    assert evs_u[0].direction == "up"
    assert 6 in c.counted_up_per_line[1]


# ---------------------------------------------------------------------------
# Test 7 — brief wobble below line does not produce extra events
# ---------------------------------------------------------------------------

def test_brief_reversal():
    """
    Track #7 crosses the line going down, then wobbles slightly — its centroid
    drifts down a bit more but stays below the line.  Only 1 down event should
    ever be emitted; no second event or any up event.
    """
    c = _counter(direction="both")

    all_events: list[CrossingEvent] = []

    # Approach from above (centroid=375)
    c.process_tracks([_FakeTrack(7, 100, 300, 200, 450)], FRAME_H)

    # Cross the line going down (centroid=525 > 500)
    evs = c.process_tracks([_FakeTrack(7, 100, 450, 200, 600)], FRAME_H)
    all_events.extend(evs)                           # expect exactly 1 down

    # Wobble: stay below the line, centroid=510 (prev=525 → 510, no sign change)
    evs2 = c.process_tracks([_FakeTrack(7, 100, 460, 200, 560)], FRAME_H)
    all_events.extend(evs2)                          # expect 0 (no crossing)

    # Continue below (centroid=575)
    evs3 = c.process_tracks([_FakeTrack(7, 100, 500, 200, 650)], FRAME_H)
    all_events.extend(evs3)                          # expect 0

    down_events = [e for e in all_events if e.direction == "down"]
    up_events   = [e for e in all_events if e.direction == "up"]

    assert len(down_events) == 1, f"Expected 1 down event, got {down_events}"
    assert len(up_events)   == 0, f"Expected 0 up events, got {up_events}"


# ---------------------------------------------------------------------------
# Test 8 — multiple independent track IDs each counted separately
# ---------------------------------------------------------------------------

def test_multiple_tracks_independent():
    """
    Three different track IDs (10, 11, 12) each cross downward in the same
    frame transition.  All three must produce their own event.
    """
    c = _counter(direction="down")

    # Seed all three above the line
    c.process_tracks([_above(10), _above(11), _above(12)], FRAME_H)

    # All three cross below the line
    evs = c.process_tracks([_below(10), _below(11), _below(12)], FRAME_H)

    assert len(evs) == 3, f"Expected 3 events, got {len(evs)}"
    assert {e.track_id for e in evs} == {10, 11, 12}
    assert all(e.direction == "down" for e in evs)


# ---------------------------------------------------------------------------
# Test 9 — parallel movement (no vertical sign change) → 0 events
# ---------------------------------------------------------------------------

def test_parallel_movement():
    """
    Track #20 moves horizontally across the frame.  Its centroid Y stays
    constant above the line in every frame — no crossing event must be generated.
    """
    c = _counter(direction="both")

    # Centroid Y = 300 throughout (well above the 500 px line)
    for x_offset in range(0, 600, 50):
        track = _FakeTrack(20, x_offset, 200, x_offset + 100, 400)
        evs   = c.process_tracks([track], FRAME_H)
        assert evs == [], (
            f"Expected 0 events at x_offset={x_offset}, got {evs}"
        )

    assert 20 not in c.counted_down_per_line[1]
    assert 20 not in c.counted_up_per_line[1]


# ---------------------------------------------------------------------------
# Test 10 — dynamic custom drawn angled line crossing
# ---------------------------------------------------------------------------

def test_custom_angled_line_crossing():
    """
    Test segment intersection and direction cross product math for user-drawn
    freely angled line configurations.
    """
    # Custom diagonal line from (x=0.1, y=0.1) to (x=0.9, y=0.9)
    # Scaled by 1000x1000 frame: line goes from (100, 100) to (900, 900)
    c = LineCounter(
        camera_id="test_custom_cam",
        line_y=0.5,
        direction="both",
        counting_line="0.1,0.1,0.9,0.9"
    )

    FRAME_W = 1000
    FRAME_H = 1000

    # Case A: Vehicle crossing from top-right to bottom-left (crosses diagonal)
    # Movement vector: (600, 400) -> (400, 600)
    t1_frame1 = _FakeTrack(track_id=1, x1=550, y1=350, x2=650, y2=450) # Centroid (600, 400)
    t1_frame2 = _FakeTrack(track_id=1, x1=350, y1=550, x2=450, y2=650) # Centroid (400, 600)

    evs = c.process_tracks([t1_frame1], FRAME_H, frame_w=FRAME_W)
    assert evs == [], "No crossing yet"

    evs2 = c.process_tracks([t1_frame2], FRAME_H, frame_w=FRAME_W)
    assert len(evs2) == 1
    # cross product of line (800, 800) and movement (-200, 200) is:
    # 800 * 200 - 800 * (-200) = 160000 + 160000 = 320000 > 0 -> "down"
    assert evs2[0].direction == "down"
    assert 1 in c.counted_down_per_line[1]

    # Case B: Opposite crossing (from bottom-left to top-right)
    # Movement vector: (400, 600) -> (600, 400)
    t2_frame1 = _FakeTrack(track_id=2, x1=350, y1=550, x2=450, y2=650) # Centroid (400, 600)
    t2_frame2 = _FakeTrack(track_id=2, x1=550, y1=350, x2=650, y2=450) # Centroid (600, 400)

    evs = c.process_tracks([t2_frame1], FRAME_H, frame_w=FRAME_W)
    assert evs == [], "No crossing yet"

    evs2 = c.process_tracks([t2_frame2], FRAME_H, frame_w=FRAME_W)
    assert len(evs2) == 1
    assert evs2[0].direction == "up" # opposite sign -> "up"
    assert 2 in c.counted_up_per_line[1]


# ---------------------------------------------------------------------------
# Test 11 — brief occlusion must NOT drop the track's previous centroid
# ---------------------------------------------------------------------------

def test_occlusion_tolerance_preserves_prev_centroid():
    """
    A track that vanishes for a few frames (occlusion) and comes back must still
    be compared against its pre-occlusion centroid, so the crossing it made
    while hidden is still counted.
    """
    c = LineCounter(camera_id="occ_cam", line_y=0.5, direction="down",
                    retire_after_frames=5)

    c.process_tracks([_above(30)], FRAME_H)         # seed above the line

    for _ in range(4):                              # 4 < 5 → not yet retired
        assert c.process_tracks([], FRAME_H) == []
        assert 30 in c.prev_centroids, "occluded track must keep its centroid"

    evs = c.process_tracks([_below(30)], FRAME_H)   # reappears below the line
    assert len(evs) == 1 and evs[0].direction == "down"


# ---------------------------------------------------------------------------
# Test 12 — (a) prev_centroids is pruned; recycled id emits no phantom count
# ---------------------------------------------------------------------------

def test_retired_track_centroid_evicted_no_phantom_count():
    """
    Once a track has been absent past the retirement threshold its centroid is
    dropped.  A later vehicle that ByteTrack happens to give the same integer id
    must therefore NOT be compared against the old vehicle's position — that
    bogus long segment used to intersect the line and emit a phantom count.
    """
    c = LineCounter(camera_id="phantom_cam", line_y=0.5, direction="both",
                    retire_after_frames=3)

    c.process_tracks([_above(40)], FRAME_H)         # old vehicle, above line
    assert 40 in c.prev_centroids

    for _ in range(3):                              # absent long enough to retire
        c.process_tracks([], FRAME_H)

    assert 40 not in c.prev_centroids, "retired track must be evicted"
    assert 40 not in c._frames_missing

    # Same id recycled for a brand-new vehicle that appears below the line.
    evs = c.process_tracks([_below(40)], FRAME_H)
    assert evs == [], f"phantom count emitted for recycled id: {evs}"


# ---------------------------------------------------------------------------
# Test 13 — (b) dedup sets are pruned; a recycled id can be counted again
# ---------------------------------------------------------------------------

def test_retired_track_dedup_evicted_recycled_id_counts_again():
    """
    The dedup sets must not suppress an id forever.  After the original track
    retires, a new vehicle reusing that id is a different vehicle and must be
    counted on its own merits.
    """
    c = LineCounter(camera_id="recycle_cam", line_y=0.5, direction="down",
                    retire_after_frames=3)

    c.process_tracks([_above(41)], FRAME_H)
    assert len(c.process_tracks([_below(41)], FRAME_H)) == 1
    assert 41 in c.counted_down_per_line[1]

    for _ in range(3):
        c.process_tracks([], FRAME_H)

    assert 41 not in c.counted_down_per_line[1], "retired id must leave the dedup set"

    # New vehicle, recycled id, crosses down again → must be counted.
    c.process_tracks([_above(41)], FRAME_H)
    evs = c.process_tracks([_below(41)], FRAME_H)
    assert len(evs) == 1 and evs[0].direction == "down"
    assert c.total_down == 2, "both vehicles must be reflected in the running total"


# ---------------------------------------------------------------------------
# Test 14 — a still-visible vehicle is never retired, so never re-counted
# ---------------------------------------------------------------------------

def test_continuously_tracked_vehicle_never_recounted():
    """
    The core guarantee: while a track remains visible it is counted exactly once,
    no matter how many frames elapse — the absence bookkeeping must reset every
    frame the track is seen.
    """
    c = LineCounter(camera_id="persist_cam", line_y=0.5, direction="down",
                    retire_after_frames=3)

    c.process_tracks([_above(42)], FRAME_H)
    assert len(c.process_tracks([_below(42)], FRAME_H)) == 1

    # Stays visible below the line for far longer than the retirement window.
    for _ in range(10):
        assert c.process_tracks([_below(42)], FRAME_H) == []

    assert 42 in c.counted_down_per_line[1], "visible track must not be retired"

    # Crosses down a second time → still deduplicated.
    c.process_tracks([_above(42)], FRAME_H)
    assert c.process_tracks([_below(42)], FRAME_H) == []
    assert c.total_down == 1


# ---------------------------------------------------------------------------
# Test 15 — internal state stays bounded across many short-lived tracks
# ---------------------------------------------------------------------------

def test_internal_state_bounded_over_many_tracks():
    """
    Simulate long runtime: 200 vehicles, each visible for 2 frames.  Internal
    dicts/sets must not grow with the number of vehicles ever seen.
    """
    c = LineCounter(camera_id="bound_cam", line_y=0.5, direction="both",
                    retire_after_frames=3)

    for tid in range(100, 300):
        c.process_tracks([_above(tid)], FRAME_H)
        c.process_tracks([_below(tid)], FRAME_H)
        for _ in range(3):                       # let it retire
            c.process_tracks([], FRAME_H)

    assert len(c.prev_centroids) == 0
    assert len(c._frames_missing) == 0
    assert len(c.counted_down_per_line[1]) == 0
    assert c.total_down == 200, "running total must survive eviction"
