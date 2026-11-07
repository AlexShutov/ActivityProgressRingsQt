"""Tests for rounded ends of the gauge-rings sector (MIT).

Verifies that ``render_gauge_rings`` honours ``start_corner_fraction`` /
``end_corner_fraction`` (dоля толщины 0..0.5): a rounded end (0.5) differs from a
square radial end (0.0) for partially filled rings, and out-of-range values are
clamped like the linear indicator's corner fractions.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from activityrings.rings import render_gauge_rings

GAUGES = [
    ("cpu", "CPU", (250, 55, 95), 0.62),
    ("gpu", "GPU", (145, 221, 82), 0.88),
    ("ram", "RAM", (56, 181, 240), 0.41),
]


def _frame_bytes(img) -> bytes:
    return img.convert("RGBA").tobytes()


def test_rounded_end_differs_from_square_end():
    rounded = render_gauge_rings(GAUGES, (200, 200), progress={}, start_corner_fraction=0.5)
    square = render_gauge_rings(GAUGES, (200, 200), progress={}, start_corner_fraction=0.0)
    assert _frame_bytes(rounded) != _frame_bytes(square)


def test_clamps_corner_fraction_to_full_round():
    over = render_gauge_rings(GAUGES, (200, 200), progress={}, start_corner_fraction=3.0)
    full = render_gauge_rings(GAUGES, (200, 200), progress={}, start_corner_fraction=0.5)
    assert _frame_bytes(over) == _frame_bytes(full)


def test_clamps_corner_fraction_to_square():
    under = render_gauge_rings(GAUGES, (200, 200), progress={}, end_corner_fraction=-2.0)
    square = render_gauge_rings(GAUGES, (200, 200), progress={}, end_corner_fraction=0.0)
    assert _frame_bytes(under) == _frame_bytes(square)


def test_default_is_full_round():
    default = render_gauge_rings(GAUGES, (200, 200), progress={})
    full = render_gauge_rings(GAUGES, (200, 200), progress={}, start_corner_fraction=0.5, end_corner_fraction=0.5)
    assert _frame_bytes(default) == _frame_bytes(full)