"""Unit tests for the Activity-Rings layout managers (no Qt/Pillow).

Covers the dynamic gap (count + screen size), the edge-margin clamp on the anchored
outer radius, the static equal-width layout, the selection growth (focused ring grows
thickness, neighbours keep their width), the gap-preserving reflow, and that
``is_selection_enabled`` discriminates the two modes.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from activityrings.rings_focus import BASE_RINGS, layout
from activityrings.rings_layout import (
    BaseRingsLayoutManager,
    RingGeometry,
    RingsLayoutResult,
    SelectionRingsLayoutManager,
    StaticRingsLayoutManager,
)


def _edges(radii: list[float], widths: list[float]) -> tuple[list[float], list[float]]:
    inner = [r - w / 2.0 for r, w in zip(radii, widths, strict=True)]
    outer = [r + w / 2.0 for r, w in zip(radii, widths, strict=True)]
    return inner, outer


def _radii(res: RingsLayoutResult) -> list[float]:
    return [g.radius for g in res.geometry]


def _widths(res: RingsLayoutResult) -> list[float]:
    return [g.width for g in res.geometry]


# -- outer radius / edge margin ---------------------------------------------
def test_outer_radius_respects_edge_margin():
    mgr = StaticRingsLayoutManager()
    for short in (200.0, 440.0, 760.0, 1400.0):
        assert mgr.outer_radius(short) <= short / 2.0 - mgr.edge_margin + 1e-9


def test_outer_radius_uses_fraction_when_roomy():
    short = 760.0
    mgr = StaticRingsLayoutManager(outer_fraction=0.84)
    assert mgr.outer_radius(short) == pytest.approx(short / 2.0 * 0.84)


def test_outer_radius_obeys_fraction_override():
    short = 440.0
    mgr = StaticRingsLayoutManager(outer_fraction=0.5)
    assert mgr.outer_radius(short) == pytest.approx(short / 2.0 * 0.5)


# -- dynamic gap -------------------------------------------------------------
def test_gap_decreases_with_count():
    mgr = StaticRingsLayoutManager()
    short = 760.0
    gap_3 = mgr.gap_for(short, 3)
    gap_6 = mgr.gap_for(short, 6)
    gap_12 = mgr.gap_for(short, 12)
    assert gap_3 > gap_6 > gap_12


def test_gap_clamped_to_bounds():
    mgr = StaticRingsLayoutManager()
    assert mgr.gap_for(10.0, 3) == pytest.approx(mgr.gap_min)
    assert mgr.gap_for(100000.0, 2) == pytest.approx(mgr.gap_max)


def test_gap_single_ring_is_zero():
    assert StaticRingsLayoutManager().gap_for(760.0, 1) == 0.0


# -- static layout -----------------------------------------------------------
def test_static_equal_widths_and_anchored_outer_edge():
    mgr = StaticRingsLayoutManager()
    short = 760.0
    res = mgr.measure(short, None)
    widths = _widths(res)
    assert widths == pytest.approx([widths[0]] * len(widths))
    inner, outer = _edges(_radii(res), widths)
    assert outer[0] == pytest.approx(res.outer_radius)
    assert outer[0] <= short / 2.0 - mgr.edge_margin + 1e-9
    for j in range(len(widths) - 1):
        assert inner[j] - outer[j + 1] == pytest.approx(res.gap)


def test_static_radii_match_focus_layout():
    mgr = StaticRingsLayoutManager()
    short = 760.0
    res = mgr.measure(short, None)
    outer_r = res.outer_radius
    widths = mgr.base_widths(outer_r)
    assert res.gap == pytest.approx(mgr.gap_for(short, len(widths)))
    assert _radii(res) == pytest.approx(layout(widths, res.gap, outer_r))


def test_static_three_rings():
    res = StaticRingsLayoutManager().measure(760.0, None)
    assert len(res) == len(BASE_RINGS)
    assert [g.key for g in res.geometry] == [b.key for b in BASE_RINGS]


# -- selection layout --------------------------------------------------------
def test_selection_grows_focused_ring():
    mgr = SelectionRingsLayoutManager()
    res = mgr.measure(760.0, None, [1.0, 0.0, 0.0])
    base = mgr.base_widths(res.outer_radius)
    assert res[0].width == pytest.approx(base[0] * mgr.selection_scale)
    assert res[1].width == pytest.approx(base[1])
    assert res[2].width == pytest.approx(base[2])


def test_selection_neighbors_keep_width_when_inner_focused():
    mgr = SelectionRingsLayoutManager()
    res = mgr.measure(760.0, None, [0.0, 1.0, 0.0])
    base = mgr.base_widths(res.outer_radius)
    assert res[1].width == pytest.approx(base[1] * mgr.selection_scale)
    assert res[0].width == pytest.approx(base[0])
    assert res[2].width == pytest.approx(base[2])


def test_selection_outer_ring_stays_within_margin():
    mgr = SelectionRingsLayoutManager()
    short = 760.0
    res = mgr.measure(short, None, [1.0, 0.0, 0.0])
    outer_edge = res[0].radius + res[0].width / 2.0
    assert outer_edge == pytest.approx(res.outer_radius)
    assert outer_edge <= short / 2.0 - mgr.edge_margin + 1e-9


def test_selection_preserves_gap_through_reflow():
    mgr = SelectionRingsLayoutManager()
    for focus in ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.5, 0.5, 0.5]):
        res = mgr.measure(760.0, None, focus)
        inner, outer = _edges(_radii(res), _widths(res))
        assert outer[0] == pytest.approx(res.outer_radius)
        for j in range(len(_widths(res)) - 1):
            assert inner[j] - outer[j + 1] == pytest.approx(res.gap)


def test_selection_zero_focus_matches_base_widths():
    mgr = SelectionRingsLayoutManager()
    res = mgr.measure(760.0, None, [0.0, 0.0, 0.0])
    base = mgr.base_widths(res.outer_radius)
    assert _widths(res) == pytest.approx(base)


# -- gap collapse on tiny screen --------------------------------------------
def test_gap_collapses_on_tiny_screen():
    mgr = StaticRingsLayoutManager()
    short = 60.0
    res = mgr.measure(short, None)
    assert res.gap == 0.0
    inner, outer = _edges(_radii(res), _widths(res))
    for j in range(len(_widths(res)) - 1):
        assert inner[j] - outer[j + 1] == pytest.approx(0.0)


# -- mode flag ---------------------------------------------------------------
def test_is_selection_enabled_discriminates():
    assert BaseRingsLayoutManager.is_selection_enabled is False
    assert StaticRingsLayoutManager.is_selection_enabled is False
    assert SelectionRingsLayoutManager.is_selection_enabled is True
    assert StaticRingsLayoutManager().is_selection_enabled is False
    assert SelectionRingsLayoutManager().is_selection_enabled is True


# -- result container --------------------------------------------------------
def test_result_indexing_and_len():
    res = StaticRingsLayoutManager().measure(760.0, None)
    assert len(res) == 3
    assert isinstance(res[0], RingGeometry)
    assert res[0].key == "move"


# -- integration with render_rings ------------------------------------------
def test_render_rings_with_selection_manager_produces_image():
    from activityrings.rings import render_rings

    mgr = SelectionRingsLayoutManager()
    img = render_rings(size=(760, 760), layout_manager=mgr, focus=[1.0, 0.0, 0.0])
    assert img is not None
    assert img.mode == "RGB"
    assert img.size == (760, 760)
