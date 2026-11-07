"""Unit tests for the data-driven "one ring per gauge" Activity-Rings wrapper.

Covers ``gauge_ring_bases`` (band geometry from gauge specs) and ``render_gauge_rings``
(renders N gauge rings, reusing the selection layout manager + rings renderer).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from activityrings.rings import GAUGE_BAND_DEPTH_FRACTION, gauge_ring_bases
from activityrings.rings_focus import RingBase

GAUGES = [
    ("cpu", "CPU", (250, 55, 95), 0.62),
    ("gpu", "GPU", (145, 221, 82), 0.88),
    ("ram", "RAM", (56, 181, 240), 0.41),
]


def test_gauge_ring_bases_one_ring_per_gauge():
    bases = gauge_ring_bases(GAUGES)
    assert len(bases) == 3
    assert bases[0].key == "cpu"
    assert bases[0].label == "CPU"
    assert bases[0].color == (250, 55, 95)
    assert bases[0].target == pytest.approx(0.62)


def test_gauge_ring_bases_width_frac_scales_with_count():
    assert gauge_ring_bases(GAUGES)[0].width_frac == pytest.approx(
        GAUGE_BAND_DEPTH_FRACTION / 3
    )
    assert gauge_ring_bases(GAUGES[:1])[0].width_frac == pytest.approx(
        GAUGE_BAND_DEPTH_FRACTION
    )


def test_gauge_ring_bases_respects_explicit_width_frac():
    bases = gauge_ring_bases(GAUGES, width_frac=0.1)
    assert all(b.width_frac == pytest.approx(0.1) for b in bases)


def test_gauge_ring_bases_returns_ring_base_instances():
    bases = gauge_ring_bases(GAUGES)
    assert all(isinstance(b, RingBase) for b in bases)


def test_render_gauge_rings_produces_overlay_frame():
    from activityrings.rings import render_gauge_rings

    img = render_gauge_rings(GAUGES, (760, 760), progress={"cpu": 0.6, "gpu": 0.8, "ram": 0.3})
    assert img is not None
    assert img.mode == "RGBA"  # прозрачный оверлей для укладки поверх темы
    assert img.size == (760, 760)


def test_render_gauge_rings_accepts_focus_and_ignores_unknown_target_keys():
    from activityrings.rings import render_gauge_rings

    img = render_gauge_rings(
        GAUGES,
        (400, 400),
        progress={},  # пусто → берутся targets из RingSpec
        focus=[1.0, 0.0, 0.0],
    )
    assert img.mode == "RGBA"


def test_render_gauge_rings_small_canvas_never_crashes():
    from activityrings.rings import render_gauge_rings

    img = render_gauge_rings(GAUGES, (48, 48))
    assert img.size == (48, 48)


def test_render_gauge_rings_outer_fraction_enlarges_rings():
    from activityrings.rings import render_gauge_rings

    progress = {key: 1.0 for key, _, _, _ in GAUGES}
    tight = render_gauge_rings(GAUGES, (760, 760), progress=progress, outer_fraction=0.96)
    reduced = render_gauge_rings(GAUGES, (760, 760), progress=progress, outer_fraction=0.5)
    # Большая доля → кольца крупнее → шире ненулевая область.
    assert tight.getbbox()[2] > reduced.getbbox()[2]
    assert tight.getbbox()[3] > reduced.getbbox()[3]
    assert tight.mode == "RGBA"


def test_ring_gap_px_override_controls_spacing():
    from activityrings.rings import gauge_ring_bases
    from activityrings.rings_layout import SelectionRingsLayoutManager

    count = len(GAUGES)
    bases = gauge_ring_bases(GAUGES)
    dynamic = SelectionRingsLayoutManager(
        ring_bases=bases, outer_fraction=0.96, edge_margin=14.0
    )
    tight = SelectionRingsLayoutManager(
        ring_bases=bases, outer_fraction=0.96, edge_margin=14.0, ring_gap_px=7.0
    )
    assert dynamic.measure(440, count).gap > tight.measure(440, count).gap  # 28 vs 7
    assert tight.measure(440, count).gap == pytest.approx(7.0)


def test_inner_radius_sizes_innermost_ring_and_thickens():
    from activityrings.rings import gauge_ring_bases
    from activityrings.rings_layout import SelectionRingsLayoutManager

    count = len(GAUGES)
    bases = gauge_ring_bases(GAUGES)
    narrow = SelectionRingsLayoutManager(
        ring_bases=bases, outer_fraction=0.96, edge_margin=14.0, ring_gap_px=7.0
    )
    filled = SelectionRingsLayoutManager(
        ring_bases=bases,
        outer_fraction=0.96,
        edge_margin=14.0,
        ring_gap_px=7.0,
        inner_radius=34.0,
    )
    res = filled.measure(440, count)
    # Внутренняя граница самого внутреннего кольца == заданному ``inner_radius``.
    innermost = res.geometry[-1]
    assert innermost.radius - innermost.width / 2 == pytest.approx(34.0)
    # Внешнее кольцо по-прежнему прижато к ``outer_r`` (внешний край).
    outermost = res.geometry[0]
    assert outermost.radius + outermost.width / 2 == pytest.approx(res.outer_radius)
    # Кольца толще, чем в узкой внешней полосе.
    narrow_res = narrow.measure(440, count)
    assert outermost.width > narrow_res.geometry[0].width
