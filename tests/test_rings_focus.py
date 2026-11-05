"""Unit tests for the pure Activity-Rings focus model (no Qt/Pillow).

Covers the constant-gap, outer-edge-anchored ``layout``, the 1.5x focus widening,
and the eased ``FocusTimeline`` schedule/factor behaviour.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from activityrings.rings_focus import (
    BASE_RINGS,
    FOCUS_SCALE,
    GAP_FRACTION,
    TRANSITION_S,
    FocusTimeline,
    default_schedule,
    ease_out_cubic,
    layout,
)


def _edges(radii: list[float], widths: list[float]) -> tuple[list[float], list[float]]:
    inner = [r - w / 2.0 for r, w in zip(radii, widths)]
    outer = [r + w / 2.0 for r, w in zip(radii, widths)]
    return inner, outer


# -- layout -----------------------------------------------------------------
def test_layout_fixes_outer_edge_and_keeps_gap():
    widths = [4.0, 3.0, 5.0, 2.0]
    gap = 1.5
    outer_r = 20.0
    radii = layout(widths, gap, outer_r)
    inner, outer = _edges(radii, widths)
    assert outer[0] == pytest.approx(outer_r)
    for j in range(len(widths) - 1):
        assert inner[j] - outer[j + 1] == pytest.approx(gap)


def test_layout_constant_gap_across_varying_widths():
    for widths, gap, outer_r in (
        ([5.0, 5.0, 5.0], 1.0, 25.0),
        ([9.0, 2.0, 6.0], 0.5, 20.0),
        ([1.0, 3.0, 2.0, 4.0], 2.0, 30.0),
    ):
        radii = layout(widths, gap, outer_r)
        inner, outer = _edges(radii, widths)
        assert outer[0] == pytest.approx(outer_r)
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
        default_schedule(cycles=1), outer_r=100.0, transition_s=TRANSITION_S
    )
    base = timeline.base_widths()
    plateau = timeline.frame(timeline._schedule[0].start + TRANSITION_S + 0.1)
    for i, (b, w) in enumerate(zip(base, plateau.widths)):
        expected = b * FOCUS_SCALE if i == 0 else b
        assert w == pytest.approx(expected)


def test_unfocused_rings_match_base_layout():
    timeline = FocusTimeline(default_schedule(cycles=1), outer_r=100.0)
    base = timeline.base_widths()
    pinned = layout(base, GAP_FRACTION * 100.0, 100.0)
    frame = timeline.frame(-1.0)
    assert frame.widths == pytest.approx(base)
    assert frame.radii == pytest.approx(pinned)


# -- schedule / timeline ----------------------------------------------------
def test_default_schedule_first_two_seconds_focuses_first_ring():
    schedule = default_schedule(period=5.0, focus_duration=2.0, n_rings=3)
    assert (schedule[0].start, schedule[0].end, schedule[0].index) == (0.0, 2.0, 0)
    assert (schedule[1].start, schedule[1].end, schedule[1].index) == (5.0, 7.0, 1)
    assert (schedule[2].start, schedule[2].end, schedule[2].index) == (10.0, 12.0, 2)
    assert (schedule[3].start, schedule[3].end, schedule[3].index) == (15.0, 17.0, 0)
    timeline = FocusTimeline(schedule, outer_r=100.0)
    assert timeline.focus_factor(1.0) == pytest.approx([1.0, 0.0, 0.0])
    assert timeline.focus_factor(3.0) == pytest.approx([0.0, 0.0, 0.0])
    assert timeline.focus_factor(6.0) == pytest.approx([0.0, 1.0, 0.0])
    assert timeline.focus_factor(11.0) == pytest.approx([0.0, 0.0, 1.0])


def test_transition_window_is_present_and_eased():
    timeline = FocusTimeline(default_schedule(cycles=1), outer_r=100.0)
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
        default_schedule(period=5.0, focus_duration=2.0, n_rings=3), outer_r=120.0
    )
    gap = timeline._gap
    for t in (0.0, 0.3, 0.6, 1.0, 2.3, 2.6, 3.5, 5.9):
        frame = timeline.frame(t)
        inner, outer = _edges(frame.radii, frame.widths)
        assert outer[0] == pytest.approx(120.0)
        for j in range(len(frame.radii) - 1):
            assert inner[j] - outer[j + 1] == pytest.approx(gap)


def test_frame_carries_per_ring_focus_factors():
    timeline = FocusTimeline(
        default_schedule(period=5.0, focus_duration=2.0, n_rings=3), outer_r=120.0
    )
    assert timeline.frame(-1.0).factors == pytest.approx([0.0, 0.0, 0.0])
    assert timeline.frame(1.0).factors == pytest.approx([1.0, 0.0, 0.0])
    assert timeline.frame(6.0).factors == pytest.approx([0.0, 1.0, 0.0])


def test_base_rings_are_move_exercise_stand():
    assert [r.key for r in BASE_RINGS] == ["move", "exercise", "stand"]
    assert [r.color for r in BASE_RINGS] == [
        (250, 55, 95),
        (145, 221, 82),
        (56, 181, 240),
    ]