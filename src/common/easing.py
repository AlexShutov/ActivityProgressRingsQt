"""Общие числовые хелперы индикаторов: интерполяция и easing (MIT).

Чистые функции без Qt/Pillow, которые используются во всех индикаторах и их
focus-моделях: кубическое ease-out, линейная интерполяция скаляров и цветов,
клампинг значений в диапазон. Вынесены в ``common``, чтобы новый индикатор не
копировал их заново.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

Color = tuple[int, int, int]


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Ограничивает ``value`` диапазоном ``[lo, hi]``."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def ease_out_cubic(t: float) -> float:
    """Классическое cubic ease-out на ``[0, 1]`` (клампится на входе)."""
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def lerp(a: float, b: float, t: float) -> float:
    """Линейная интерполяция ``a -> b`` при ``t`` из ``[0, 1]``."""
    return a + (b - a) * t


def lerp_color(color_start: Color, color_end: Color, t: float) -> Color:
    """Линейная интерполяция двух цветов покомпонентно (усечение в ``int``)."""
    return (
        int(lerp(color_start[0], color_end[0], t)),
        int(lerp(color_start[1], color_end[1], t)),
        int(lerp(color_start[2], color_end[2], t)),
    )
