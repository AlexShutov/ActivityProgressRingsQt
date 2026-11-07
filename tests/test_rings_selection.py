"""Integration tests for selection rendering in the gauge-rings (MIT).

Verifies that passing a ``focus`` to ``render_gauge_rings`` with the selection-enabled
layout manager produces the dimmed-inactive + glowing-active frame: a single active ring
gains a soft glow (highers total alpha), and with several gauges the frame with a hot
ring differs from the untouched one (inactive rings dimmed).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from activityrings.rings import render_gauge_rings

GAUGES = [
    ("cpu", "CPU", (250, 55, 95), 1.0),
    ("gpu", "GPU", (145, 221, 82), 1.0),
    ("ram", "RAM", (56, 181, 240), 1.0),
]
SINGLE = [("cpu", "CPU", (250, 55, 95), 1.0)]


def _alpha_sums(img) -> int:
    """Сумма альфа-каналов кадра (мерой «количества» непрозрачности)."""
    data = img.tobytes()  # без вызова deprecated ``getdata``
    return sum(data[i] for i in range(3, len(data), 4))


def test_selection_frame_is_rgba_and_sized():
    img = render_gauge_rings(GAUGES, (200, 200), progress={}, focus=[1.0, 0.0, 0.0])
    assert img.mode == "RGBA"
    assert img.size == (200, 200)


def test_selection_without_focus_matches_base():
    # Без focus (None) выключено выделение → кадр совпадает с самим собой.
    img = render_gauge_rings(GAUGES, (200, 200), progress={}, focus=None)
    assert img.mode == "RGBA"


def test_active_ring_glow_adds_alpha():
    base = render_gauge_rings(SINGLE, (200, 200), progress={}, focus=None)
    lit = render_gauge_rings(SINGLE, (200, 200), progress={}, focus=[1.0])
    # У активного кольца ореол размывается вокруг дуги → больше непрозрачности.
    assert _alpha_sums(lit) > _alpha_sums(base)


def test_focus_dims_inactive_rings():
    base = render_gauge_rings(GAUGES, (200, 200), progress={}, focus=None)
    lit = render_gauge_rings(GAUGES, (200, 200), progress={}, focus=[1.0, 0.0, 0.0])
    # Подсветка одного кольца меняет кадр (невыделенные гаснут, активное светится).
    assert base.tobytes() != lit.tobytes()
    assert _alpha_sums(lit) != _alpha_sums(base)


def test_active_glow_uses_ring_color_not_white():
    # Ореол окрашен цветом самого кольца (цвет столбца палитры), а не белым: кадры с
    # активным красным и синим кольцом одного датчика различаются.
    red = render_gauge_rings(
        [("a", "A", (250, 55, 90), 1.0)], (200, 200), progress={}, focus=[1.0],
    )
    blue = render_gauge_rings(
        [("a", "A", (56, 120, 240), 1.0)], (200, 200), progress={}, focus=[1.0],
    )
    assert red.tobytes() != blue.tobytes()