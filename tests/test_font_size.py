# SPDX-License-Identifier: MIT
"""Unit tests for ``FontSizeCalculator`` (``common.font_size``).

Проверяем, что подбор максимального кегля уважает ограничения по ширине/высоте,
учитывает и ту и другую ось, не выдаёт кегль меньше ``min_size`` и монотонно
уменьшается для более длинных строк.  Это основа «максимально вмещающейся»
надписи в виджете линейного прогресса.
"""
from __future__ import annotations

from common.font import DEFAULT_FONT_FAMILY
from common.font_size import (
    DEFAULT_FONT_SIZE_MAX,
    DEFAULT_FONT_SIZE_MIN,
    FontSizeCalculator,
)


def _calculator() -> FontSizeCalculator:
    return FontSizeCalculator()


def test_fit_width_respects_limit():
    calc = _calculator()
    size = calc.fit_to_width("100%", DEFAULT_FONT_FAMILY, 69.0)
    assert DEFAULT_FONT_SIZE_MIN <= size <= DEFAULT_FONT_SIZE_MAX
    assert calc.measure_width("100%", DEFAULT_FONT_FAMILY, size) <= 69.0


def test_fit_height_respects_limit():
    calc = _calculator()
    size = calc.fit_to_height("100%", DEFAULT_FONT_FAMILY, 206.0)
    assert calc.measure_height("100%", DEFAULT_FONT_FAMILY, size) <= 206.0


def test_fit_keeps_smallest_of_width_and_height():
    calc = _calculator()
    wide = calc.fit("100%", DEFAULT_FONT_FAMILY, 1000.0, 40.0)
    tall = calc.fit("100%", DEFAULT_FONT_FAMILY, 1000.0, 200.0)
    assert wide <= tall
    assert calc.measure_height("100%", DEFAULT_FONT_FAMILY, wide) <= 40.0


def test_longer_text_yields_smaller_or_equal_size():
    calc = _calculator()
    short_size = calc.fit("A", DEFAULT_FONT_FAMILY, 69.0, 206.0)
    long_size = calc.fit("CPU", DEFAULT_FONT_FAMILY, 69.0, 206.0)
    assert long_size <= short_size


def test_min_size_is_lower_bound():
    calc = FontSizeCalculator(min_size=20, max_size=200)
    # Сверхширокая строка в узкой колонке не должна упасть ниже min_size.
    size = calc.fit_to_width("CPU GUI", DEFAULT_FONT_FAMILY, 12.0)
    assert size >= 20


def test_fit_with_fallback_family_still_returns_sane_int():
    # Неизвестное семейство уходит в откат на системный шрифт — измерение работает,
    # подбор возвращает целый кегль в допустимом диапазоне.
    calc = _calculator()
    size = calc.fit("100%", "NoSuchFamily", 69.0, 206.0)
    assert isinstance(size, int)
    assert DEFAULT_FONT_SIZE_MIN <= size <= DEFAULT_FONT_SIZE_MAX


def test_default_bounds_are_sane():
    assert 1 <= DEFAULT_FONT_SIZE_MIN < DEFAULT_FONT_SIZE_MAX
    calc = _calculator()
    assert calc.min_size == DEFAULT_FONT_SIZE_MIN
    assert calc.max_size == DEFAULT_FONT_SIZE_MAX


def test_letter_spacing_increases_width_and_shrinks_fit():
    base = FontSizeCalculator()
    tracked = FontSizeCalculator(letter_spacing_fraction=0.15)
    raw_w = base.measure_width("100%", DEFAULT_FONT_FAMILY, 40)
    tracked_w = tracked.measure_width("100%", DEFAULT_FONT_FAMILY, 40)
    assert tracked_w > raw_w
    raw_size = base.fit_to_width("100%", DEFAULT_FONT_FAMILY, 200.0)
    tracked_size = tracked.fit_to_width("100%", DEFAULT_FONT_FAMILY, 200.0)
    assert tracked_size <= raw_size
