"""Unit tests for the circular ring legend layout manager (MIT).

Validates the side parsing and that ``CircleLegendLayoutManager`` places one label per
ring on the correct side of the ring centre, keeps every label backdrop inside the
view (the "blind zone" exclusion) and renders onto an RGBA canvas.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from PIL import Image

from activityrings.rings_legend import (
    CircleLegendLayoutManager,
    LegendPlacement,
    parse_legend_placement,
)
from common.font import FontResolver, FontSpec

# «Правый край» (как в композите «кольца справа»): LEFT-легенда должна уместиться.
EDGE_VIEW = (1920, 440)
EDGE_CENTER = (1700.0, 220.0)
EDGE_RADIUS = 275.0
# «По центру» — обе стороны свободны, для RIGHT/BOTH.
CENTER_VIEW = (1920, 440)
CENTER = (960.0, 220.0)
CENTER_RADIUS = 200.0

LABELS = ["CPU", "GPU", "RAM", "LOAD"]
COLORS = [(250, 55, 95), (145, 221, 82), (56, 181, 240), (251, 246, 119)]


def _font():
    return FontResolver().resolve(FontSpec("Spacetron", 26))


def _manager(placement: LegendPlacement, *, center, radius, view):
    return CircleLegendLayoutManager(
        center=center,
        radius=radius,
        view_size=view,
        placement=placement,
        font=_font(),
        text_color=(255, 255, 255),
        padding_px=2.0,
        corner_radius_px=4.0,
        letter_spacing_px=3.0,
    )


def test_parse_legend_placement():
    assert parse_legend_placement("left") == LegendPlacement.LEFT
    assert parse_legend_placement("Right") == LegendPlacement.RIGHT
    assert parse_legend_placement("both") == LegendPlacement.BOTH
    assert parse_legend_placement(None) is None
    assert parse_legend_placement("") is None
    assert parse_legend_placement("sideways") is None


def test_legend_layout_one_position_per_label():
    mgr = _manager(LegendPlacement.LEFT, center=EDGE_CENTER, radius=EDGE_RADIUS, view=EDGE_VIEW)
    positions = mgr.layout(LABELS, COLORS)
    assert len(positions) == len(LABELS)
    assert [p.text for p in positions] == LABELS
    assert all(isinstance(p.color, tuple) for p in positions)


def test_legend_left_placement_keeps_labels_left_of_ring_and_in_view():
    mgr = _manager(LegendPlacement.LEFT, center=EDGE_CENTER, radius=EDGE_RADIUS, view=EDGE_VIEW)
    for label in mgr.layout(LABELS, COLORS):
        assert label.center[0] <= EDGE_CENTER[0]
        assert 0 <= label.center[0] <= EDGE_VIEW[0]
        assert 0 <= label.center[1] <= EDGE_VIEW[1]


def test_legend_left_backdrops_fit_inside_view():
    mgr = _manager(LegendPlacement.LEFT, center=EDGE_CENTER, radius=EDGE_RADIUS, view=EDGE_VIEW)
    for label in mgr.layout(LABELS, COLORS):
        text_w, text_h = mgr._measure(label.text)
        box_w, box_h = text_w + 2 * 2.0, text_h + 2 * 2.0
        left = label.center[0] - box_w / 2.0
        top = label.center[1] - box_h / 2.0
        assert left >= 0 and top >= 0
        assert left + box_w <= EDGE_VIEW[0] and top + box_h <= EDGE_VIEW[1]


def test_legend_right_placement_keeps_labels_right_of_ring():
    mgr = _manager(LegendPlacement.RIGHT, center=CENTER, radius=CENTER_RADIUS, view=CENTER_VIEW)
    for label in mgr.layout(LABELS, COLORS):
        assert label.center[0] >= CENTER[0]
        assert 0 <= label.center[0] <= CENTER_VIEW[0]
        assert 0 <= label.center[1] <= CENTER_VIEW[1]


def test_legend_renders_backdrops_and_text():
    mgr = _manager(LegendPlacement.LEFT, center=EDGE_CENTER, radius=EDGE_RADIUS, view=EDGE_VIEW)
    canvas = Image.new("RGBA", EDGE_VIEW, (0, 0, 0, 0))
    out = mgr.render(canvas, LABELS, COLORS)
    assert out is canvas
    # Где-то появились непрозрачные пиксели подложек (легенда реально нарисована).
    assert canvas.getchannel("A").getbbox() is not None


def test_legend_empty_labels_is_noop():
    mgr = _manager(LegendPlacement.LEFT, center=EDGE_CENTER, radius=EDGE_RADIUS, view=EDGE_VIEW)
    canvas = Image.new("RGBA", EDGE_VIEW, (0, 0, 0, 0))
    assert mgr.layout([], []) == []
    assert mgr.render(canvas, [], []) is canvas
    assert canvas.getchannel("A").getbbox() is None
