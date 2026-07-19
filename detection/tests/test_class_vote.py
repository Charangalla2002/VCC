"""
Tests for majority-vote vehicle classification.

The class recorded against a count used to be whatever the detector said on the
single frame the vehicle happened to cross the line. YOLO's class output flickers
between visually similar classes (bus/truck, car/van), so the persisted class was
effectively chosen at random from one instant. These tests pin the replacement:
the class is decided by the evidence gathered across the whole track.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from counter import LineCounter  # noqa: E402

BUS, TRUCK, CAR = 5, 7, 2
H = W = 1000


class FakeTrack:
    def __init__(self, tid, cy, cls, conf=0.9):
        self.id = tid
        self._cy = cy
        self.cls = cls
        self.conf = conf

    @property
    def xyxy(self):
        return [490, self._cy - 10, 510, self._cy + 10]


def _counter(**kw):
    line = {"id": 1, "name": "L1", "x1": 0.0, "y1": 0.5, "x2": 1.0, "y2": 0.5,
            "lane_id": 1, "direction": "both", "color": "#00d4ff"}
    return LineCounter(camera_id="c", lines=[line], **kw)


def test_single_bad_frame_at_the_crossing_does_not_decide_the_class():
    """
    The core regression. A vehicle seen as a bus for its whole life, misread as a
    truck on exactly the frame it crosses, must still be recorded as a bus.
    """
    c = _counter()
    for y in (200, 250, 300, 350, 400):
        c.process_tracks([FakeTrack(1, y, BUS, 0.85)], H, W)

    # The crossing frame flickers to TRUCK, with high confidence.
    events = c.process_tracks([FakeTrack(1, 600, TRUCK, 0.95)], H, W)

    assert len(events) == 1
    assert events[0].vehicle_class == "bus", (
        f"single-frame flicker decided the class: got {events[0].vehicle_class}"
    )


def test_persistent_class_wins_over_scattered_noise():
    c = _counter()
    # 12 bus readings interleaved with 3 spurious car readings.
    seq = [BUS] * 5 + [CAR] + [BUS] * 4 + [CAR] + [BUS] * 3 + [CAR]
    for i, cls in enumerate(seq):
        c.process_tracks([FakeTrack(2, 200 + i * 10, cls, 0.8)], H, W)

    events = c.process_tracks([FakeTrack(2, 600, CAR, 0.8)], H, W)
    assert events[0].vehicle_class == "bus"


def test_genuinely_changed_majority_is_respected():
    """
    The vote must not be inertia: if the detector overwhelmingly says truck, the
    result is truck, even if the first reading was a bus.
    """
    c = _counter()
    c.process_tracks([FakeTrack(3, 200, BUS, 0.5)], H, W)
    for i in range(10):
        c.process_tracks([FakeTrack(3, 250 + i * 15, TRUCK, 0.9)], H, W)

    events = c.process_tracks([FakeTrack(3, 600, TRUCK, 0.9)], H, W)
    assert events[0].vehicle_class == "truck"


def test_confidence_is_the_mean_for_the_winning_class():
    """Reported confidence should describe the decision, not one arbitrary frame."""
    c = _counter()
    for conf in (0.6, 0.8, 1.0):
        c.process_tracks([FakeTrack(4, 200 + int(conf * 100), BUS, conf)], H, W)

    events = c.process_tracks([FakeTrack(4, 600, BUS, 0.2)], H, W)
    # Four bus observations: 0.6, 0.8, 1.0 and the crossing frame's 0.2.
    assert events[0].confidence == pytest.approx((0.6 + 0.8 + 1.0 + 0.2) / 4)


def test_first_frame_crossing_falls_back_to_current_reading():
    """
    A track can cross on the very first frame it is seen (fast vehicle, or a track
    that appears mid-frame). With no history there is nothing to vote on, so the
    current reading must be used rather than 'unknown'.
    """
    c = _counter()
    c.process_tracks([FakeTrack(5, 400, BUS, 0.9)], H, W)   # seed prev centroid
    c._class_votes.clear()                                   # simulate no history
    events = c.process_tracks([FakeTrack(5, 600, BUS, 0.9)], H, W)
    assert events[0].vehicle_class == "bus"


def test_votes_are_not_inflated_by_multiple_lines():
    """
    Evidence must be recorded once per frame, not once per line. Recording inside
    the per-line loop would multiply every observation by the number of lines --
    harmless for a single class, but it corrupts the ratio between classes.
    """
    lines = [
        {"id": 1, "name": "A", "x1": 0.0, "y1": 0.5, "x2": 1.0, "y2": 0.5,
         "lane_id": 1, "direction": "both", "color": "#000"},
        {"id": 2, "name": "B", "x1": 0.0, "y1": 0.8, "x2": 1.0, "y2": 0.8,
         "lane_id": 2, "direction": "both", "color": "#000"},
        {"id": 3, "name": "C", "x1": 0.0, "y1": 0.9, "x2": 1.0, "y2": 0.9,
         "lane_id": 3, "direction": "both", "color": "#000"},
    ]
    c = LineCounter(camera_id="c", lines=lines)
    c.process_tracks([FakeTrack(6, 100, BUS, 0.9)], H, W)

    frames, _conf_sum = c._class_votes[6][BUS]
    assert frames == 1, f"one frame with 3 lines recorded {frames} votes"


def test_votes_are_evicted_when_a_track_retires():
    """Otherwise this grows without bound, and a recycled id inherits old votes."""
    c = _counter(retire_after_frames=2)
    c.process_tracks([FakeTrack(7, 300, BUS, 0.9)], H, W)
    assert 7 in c._class_votes

    for _ in range(5):
        c.process_tracks([], H, W)

    assert 7 not in c._class_votes, "class votes leaked past track retirement"


def test_recycled_track_id_does_not_inherit_the_previous_class():
    c = _counter(retire_after_frames=2)
    for y in (200, 250, 300):
        c.process_tracks([FakeTrack(8, y, BUS, 0.95)], H, W)
    for _ in range(5):
        c.process_tracks([], H, W)          # id 8 retires

    # A different vehicle later reuses id 8.
    c.process_tracks([FakeTrack(8, 300, CAR, 0.9)], H, W)
    events = c.process_tracks([FakeTrack(8, 600, CAR, 0.9)], H, W)
    assert events[0].vehicle_class == "car", "recycled id inherited the old class"


def test_vote_storage_is_bounded_by_class_count_not_track_length():
    """A vehicle lingering in frame must not grow this without bound."""
    c = _counter()
    for i in range(500):
        c.process_tracks([FakeTrack(9, 100 + (i % 20), BUS, 0.9)], H, W)

    assert len(c._class_votes[9]) == 1, "one class should occupy one entry"
    assert c._class_votes[9][BUS][0] == 500, "frame tally should accumulate"


def test_upward_crossing_also_uses_the_vote():
    """The 'up' branch is less exercised; it must resolve the vote too."""
    c = _counter()
    for y in (800, 750, 700):
        c.process_tracks([FakeTrack(10, y, BUS, 0.9)], H, W)

    events = c.process_tracks([FakeTrack(10, 300, TRUCK, 0.95)], H, W)
    assert len(events) == 1
    assert events[0].direction == "up"
    assert events[0].vehicle_class == "bus"




# ---------------------------------------------------------------------------
# Tracker / counter window alignment
# ---------------------------------------------------------------------------

def test_retirement_window_outlasts_the_tracker_buffer():
    """
    The counter must not forget a vehicle while the tracker can still resurrect
    it under the same id.

    ByteTrack keeps a lost track re-acquirable for `track_buffer` frames. If the
    counter retires that id first, its dedup entry is gone, so when the tracker
    brings the vehicle back the next crossing is counted a second time. Deriving
    one from the other is only safe if this ordering holds.
    """
    import importlib
    import config as cfg
    importlib.reload(cfg)

    assert cfg.RETIRE_AFTER_FRAMES > cfg.TRACK_BUFFER, (
        f"counter retires at {cfg.RETIRE_AFTER_FRAMES} frames but the tracker "
        f"can resurrect ids for {cfg.TRACK_BUFFER} — a resurrected track would "
        "be counted twice"
    )


def test_tracker_yaml_track_buffer_matches_config():
    """
    The YAML drives the tracker; config.TRACK_BUFFER drives the counter's window.
    They are two declarations of one number, so drift silently breaks the
    invariant above.
    """
    import yaml
    import config as cfg

    with open(cfg.TRACKER) as fh:
        tracker_cfg = yaml.safe_load(fh)

    assert tracker_cfg["track_buffer"] == cfg.TRACK_BUFFER, (
        f"{cfg.TRACKER} says track_buffer={tracker_cfg['track_buffer']} but "
        f"config.TRACK_BUFFER={cfg.TRACK_BUFFER}"
    )


def test_counter_defaults_to_the_configured_retirement_window():
    import config as cfg
    assert _counter().retire_after_frames == cfg.RETIRE_AFTER_FRAMES


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
