"""Unit tests for the shared ``common`` package (MIT).

Covers the reusable math helpers, the shared focus-model pieces and the unified
``IndicatorBackgroundDrawer`` (used by both the rings and the linear indicator so the
background behind them is drawn identically).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from common.background import DEFAULT_BACKGROUND, IndicatorBackgroundDrawer
from common.easing import clamp, ease_out_cubic, lerp, lerp_color
from common.focus import (
    FOCUS_SCALE,
    GAP_FRACTION,
    TRANSITION_S,
    default_schedule,
    layout,
    progress_track,
    seed_progress_targets,
)


# -- easing -----------------------------------------------------------------
def test_clamp_bounds_value():
    assert clamp(-1.0) == 0.0
    assert clamp(0.5) == 0.5
    assert clamp(2.0) == 1.0
    assert clamp(0.5, lo=-1.0, hi=2.0) == 0.5


def test_ease_out_cubic_monotonic_unit_interval():
    samples = [ease_out_cubic(i / 10.0) for i in range(11)]
    assert samples == sorted(samples)
    assert samples[0] == 0.0
    assert samples[-1] == 1.0
    assert ease_out_cubic(-1.0) == 0.0
    assert ease_out_cubic(2.0) == 1.0


def test_lerp_and_lerp_color():
    assert lerp(0.0, 10.0, 0.5) == pytest.approx(5.0)
    assert lerp(0.0, 10.0, 0.0) == 0.0
    assert lerp(0.0, 10.0, 1.0) == 10.0
    assert lerp_color((0, 0, 0), (255, 255, 255), 0.5) == (127, 127, 127)


# -- focus model (shared) ---------------------------------------------------
def test_focus_core_layout_anchors_outer_edge_and_keeps_gap():
    widths = [4.0, 3.0, 5.0, 2.0]
    gap = 1.5
    anchor = 20.0
    positions = layout(widths, gap, anchor)
    inner = [p - w / 2.0 for p, w in zip(positions, widths, strict=True)]
    outer = [p + w / 2.0 for p, w in zip(positions, widths, strict=True)]
    assert outer[0] == pytest.approx(anchor)
    for j in range(len(widths) - 1):
        assert inner[j] - outer[j + 1] == pytest.approx(gap)


def test_default_schedule_and_progress_track():
    schedule = default_schedule(period=5.0, focus_duration=2.0, count=3)
    assert (schedule[0].start, schedule[0].end, schedule[0].index) == (0.0, 2.0, 0)
    assert progress_track(0, [[0.0], [0.5]], interval_s=2, tween_s=0.3) == [0.0]
    assert progress_track(2.3, [[0.0], [0.5]], interval_s=2, tween_s=0.3) == [0.5]


def test_seed_progress_targets_shape_and_bounds():
    targets = seed_progress_targets(5, 3, seed=42)
    assert len(targets) == 5
    for row in targets:
        assert len(row) == 3
        for v in row:
            assert 0.0 <= v <= 2.0
    assert seed_progress_targets(5, 3, seed=42) == targets


def test_focus_constants_are_sane():
    assert FOCUS_SCALE == 1.5
    assert 0.0 < GAP_FRACTION < 1.0
    assert TRANSITION_S > 0.0


# -- background -------------------------------------------------------------
def test_drawer_default_is_opaque_shared_background():
    drawer = IndicatorBackgroundDrawer()
    assert drawer.rgba == (16, 18, 24, 255)
    assert drawer.rgb == DEFAULT_BACKGROUND
    assert not drawer.transparent


def test_drawer_transparent_overlay():
    drawer = IndicatorBackgroundDrawer(transparent=True)
    assert drawer.rgba == (0, 0, 0, 0)
    assert drawer.transparent


def test_drawer_custom_opaque_color():
    drawer = IndicatorBackgroundDrawer((1, 2, 3))
    assert drawer.rgba == (1, 2, 3, 255)
    assert not drawer.transparent


def test_drawer_backdrop_is_uniform_transparent_version_of_background():
    """Подложка-трек — единый цвет фона с заданной альфой, независимо от прозрачности."""
    drawer = IndicatorBackgroundDrawer()
    assert drawer.backdrop(38) == (*DEFAULT_BACKGROUND, 38)
    assert drawer.backdrop(40) == (*DEFAULT_BACKGROUND, 40)

    custom = IndicatorBackgroundDrawer((138, 147, 166))
    assert custom.backdrop(38) == (138, 147, 166, 38)

    overlay = IndicatorBackgroundDrawer(transparent=True)
    assert overlay.backdrop(38) == (*DEFAULT_BACKGROUND, 38)
    assert overlay.rgba == (0, 0, 0, 0)


def test_drawer_fill_image_pillow():
    from PIL import Image

    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    IndicatorBackgroundDrawer().fill_image(img)
    assert img.getpixel((0, 0)) == (16, 18, 24, 255)

    img2 = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
    IndicatorBackgroundDrawer(transparent=True).fill_image(img2)
    assert img2.getpixel((0, 0)) == (0, 0, 0, 0)


def test_drawer_fill_qimage_qt():
    from PySide6.QtGui import QImage

    img = QImage(8, 8, QImage.Format_ARGB32_Premultiplied)
    IndicatorBackgroundDrawer().fill_qimage(img)
    assert img.pixelColor(0, 0).getRgb() == (16, 18, 24, 255)

    img2 = QImage(8, 8, QImage.Format_ARGB32_Premultiplied)
    IndicatorBackgroundDrawer(transparent=True).fill_qimage(img2)
    assert img2.pixelColor(0, 0).getRgb() == (0, 0, 0, 0)
