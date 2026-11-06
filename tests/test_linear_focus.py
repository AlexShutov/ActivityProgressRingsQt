"""Unit tests for the pure Activity Linear Indicator focus model (no Qt/Pillow).

Covers the constant-gap, edge-anchored ``layout``, the 1.5x focus widening, and
the eased ``FocusTimeline`` schedule/factor behaviour, mirroring the Activity Rings
focus-model tests.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from activity_linear_indicator.linear_focus import (
    BASE_BARS,
    FOCUS_SCALE,
    GAP_FRACTION,
    TRANSITION_S,
    FocusTimeline,
    default_schedule,
    ease_out_cubic,
    layout,
    progress_track,
    seed_progress_targets,
)


def _edges(positions: list[float], widths: list[float]) -> tuple[list[float], list[float]]:
    inner = [p - w / 2.0 for p, w in zip(positions, widths, strict=True)]
    outer = [p + w / 2.0 for p, w in zip(positions, widths, strict=True)]
    return inner, outer


# -- layout -----------------------------------------------------------------
def test_layout_fixes_outer_edge_and_keeps_gap():
    widths = [4.0, 3.0, 5.0, 2.0]
    gap = 1.5
    outer_len = 20.0
    positions = layout(widths, gap, outer_len)
    inner, outer = _edges(positions, widths)
    assert outer[0] == pytest.approx(outer_len)
    for j in range(len(widths) - 1):
        assert inner[j] - outer[j + 1] == pytest.approx(gap)


def test_layout_constant_gap_across_varying_widths():
    for widths, gap, outer_len in (
        ([5.0, 5.0, 5.0], 1.0, 25.0),
        ([9.0, 2.0, 6.0], 0.5, 20.0),
        ([1.0, 3.0, 2.0, 4.0], 2.0, 30.0),
    ):
        positions = layout(widths, gap, outer_len)
        inner, outer = _edges(positions, widths)
        assert outer[0] == pytest.approx(outer_len)
        for j in range(len(widths) - 1):
            assert inner[j] - outer[j + 1] == pytest.approx(gap)


def test_layout_rejects_negative_or_zero_width():
    with pytest.raises(ValueError):
        layout([0.0, 1.0], 1.0, 10.0)


def test_layout_rejects_overlapping_geometry():
    with pytest.raises(ValueError):
        layout([8.0, 8.0], 0.1, 5.0)


# -- easing -----------------------------------------------------------------
def test_ease_out_cubic_monotonic_unit_interval():
    samples = [ease_out_cubic(i / 10.0) for i in range(11)]
    assert samples == sorted(samples)
    assert samples[0] == 0.0
    assert samples[-1] == 1.0
    assert ease_out_cubic(-1.0) == 0.0
    assert ease_out_cubic(2.0) == 1.0


# -- focus widening ---------------------------------------------------------
def test_focus_yields_width_1_5x_base():
    timeline = FocusTimeline(
        default_schedule(cycles=1), outer_len=100.0, transition_s=TRANSITION_S
    )
    base = timeline.base_widths()
    plateau = timeline.frame(timeline._schedule[0].start + TRANSITION_S + 0.1)
    for i, (b, w) in enumerate(zip(base, plateau.widths, strict=True)):
        expected = b * FOCUS_SCALE if i == 0 else b
        assert w == pytest.approx(expected)


def test_unfocused_bars_match_base_layout():
    timeline = FocusTimeline(default_schedule(cycles=1), outer_len=100.0)
    base = timeline.base_widths()
    pinned = layout(base, GAP_FRACTION * 100.0, 100.0)
    frame = timeline.frame(-1.0)
    assert frame.widths == pytest.approx(base)
    assert frame.positions == pytest.approx(pinned)


# -- schedule / timeline ----------------------------------------------------
def test_default_schedule_first_two_seconds_focuses_first_bar():
    schedule = default_schedule(period=5.0, focus_duration=2.0, n_bars=3)
    assert (schedule[0].start, schedule[0].end, schedule[0].index) == (0.0, 2.0, 0)
    assert (schedule[1].start, schedule[1].end, schedule[1].index) == (5.0, 7.0, 1)
    assert (schedule[2].start, schedule[2].end, schedule[2].index) == (10.0, 12.0, 2)
    timeline = FocusTimeline(schedule, outer_len=100.0)
    assert timeline.focus_factor(1.0) == pytest.approx([1.0, 0.0, 0.0])
    assert timeline.focus_factor(3.0) == pytest.approx([0.0, 0.0, 0.0])
    assert timeline.focus_factor(6.0) == pytest.approx([0.0, 1.0, 0.0])
    assert timeline.focus_factor(11.0) == pytest.approx([0.0, 0.0, 1.0])


def test_transition_window_is_present_and_eased():
    timeline = FocusTimeline(default_schedule(cycles=1), outer_len=100.0)
    ts = TRANSITION_S
    assert timeline.focus_factor(0.0) == pytest.approx([0.0, 0.0, 0.0])
    assert timeline.focus_factor(ts / 2.0)[0] == pytest.approx(ease_out_cubic(0.5))
    assert timeline.focus_factor(ts)[0] == pytest.approx(1.0)
    assert timeline.focus_factor(2.0 + ts)[0] == pytest.approx(0.0)
    assert timeline.focus_factor(2.0 + ts / 2.0)[0] == pytest.approx(
        1.0 - ease_out_cubic(0.5)
    )


def test_frame_stays_gap_preserving_throughout_transition():
    timeline = FocusTimeline(
        default_schedule(period=5.0, focus_duration=2.0, n_bars=3), outer_len=120.0
    )
    gap = timeline._gap
    for t in (0.0, 0.3, 0.6, 1.0, 2.3, 2.6, 3.5, 5.9):
        frame = timeline.frame(t)
        inner, outer = _edges(frame.positions, frame.widths)
        assert outer[0] == pytest.approx(120.0)
        for j in range(len(frame.positions) - 1):
            assert inner[j] - outer[j + 1] == pytest.approx(gap)


def test_frame_carries_per_bar_focus_factors():
    timeline = FocusTimeline(
        default_schedule(period=5.0, focus_duration=2.0, n_bars=3), outer_len=120.0
    )
    assert timeline.frame(-1.0).factors == pytest.approx([0.0, 0.0, 0.0])
    assert timeline.frame(1.0).factors == pytest.approx([1.0, 0.0, 0.0])
    assert timeline.frame(6.0).factors == pytest.approx([0.0, 1.0, 0.0])


def test_base_bars_are_move_exercise_stand():
    assert [b.key for b in BASE_BARS] == ["move", "exercise", "stand"]
    assert [b.color for b in BASE_BARS] == [
        (250, 55, 95),
        (145, 221, 82),
        (56, 181, 240),
    ]


# -- progress track ---------------------------------------------------------
def test_progress_track_at_t_zero_is_first_target():
    assert progress_track(0, [[0.0], [0.5]], interval_s=2, tween_s=0.3) == [0.0]


def test_progress_track_completes_tween_after_interval_boundary():
    assert progress_track(2.3, [[0.0], [0.5]], interval_s=2, tween_s=0.3) == [0.5]


def test_progress_track_intermediate_k_is_strictly_between():
    v = progress_track(2.15, [[0.0], [1.0]], interval_s=2, tween_s=0.3)[0]
    assert 0.0 < v < 1.0


def test_progress_track_eases_monotonically():
    interval = 2.0
    targets = [[0.0], [1.0], [2.0]]
    prev = None
    for i in range(61):
        v = progress_track(i * 0.1, targets, interval_s=interval, tween_s=0.6)[0]
        if prev is not None:
            assert v >= prev - 1e-9
        prev = v


def test_progress_track_clamps_tween_to_interval():
    targets = [[0.0], [1.0], [2.0]]
    v = progress_track(3.0, targets, interval_s=2.0, tween_s=5.0)[0]
    assert 0.0 < v < 1.0
    assert v == pytest.approx(ease_out_cubic(0.5))


def test_progress_track_negative_t_returns_first_target():
    assert progress_track(-1.0, [[0.5], [1.5]], interval_s=2, tween_s=0.3) == [0.5]


def test_seed_progress_targets_shape_and_bounds():
    targets = seed_progress_targets(5, 3, seed=42)
    assert len(targets) == 5
    for row in targets:
        assert len(row) == 3
        for v in row:
            assert 0.0 <= v <= 2.0
    assert seed_progress_targets(5, 3, seed=42) == targets
