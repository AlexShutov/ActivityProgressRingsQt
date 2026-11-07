"""Стратегии роста выбранных колец в Activity Rings (MIT).

Аналог ``hardwarescreen.adapter.selection_strategy``, но для концентричных колец
(``activityrings.rings_focus.layout`` держит постоянный зазор между краями соседних
колец при любой раскладке).  Стратегия получает базовые толщины, фокусы, масштаб
выделения, design-зазор, минимальный зазор в px и внешний радиус, и возвращает:
- ``scales`` — масштаб роста каждого кольца (``1.0`` = без роста);
- ``gap`` — эффективный зазор между краями соседних колец для ``layout``.

- ``SelectSingleIndicator`` — прежнее поведение: каждое выбранное кольцо растёт на
  ``selection_scale``, зазор остаётся ``design_gap``.
- ``SelectMultipleIndicators`` — только когда выбранных больше одного.  Если выбранные
  кольца не являются соседними (нет пары ``i, i+1`` среди выбранных) — ведёт себя как
  ``SelectSingleIndicator``.  Если среди выбранных есть соседние — зазор поднимается до
  ``min_gap_px`` (место под свечение, чтобы свечения соседних выбранных не
  смешивались), а рост урезается настолько, чтобы увеличенный зазор поместился в
  радиальный бюджет ``outer_r``; если зазора ``min_gap_px`` не хватает даже без роста —
  рост этой пары нулевой и зазор возвращается к ``design_gap``.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from common.selection import (
    SELECTION_COUNT_EPSILON,
    clamp_fraction,
    count_selected,
    has_adjacent_selected,
)


@dataclass(frozen=True)
class RingGrowthPlan:
    """План роста колец: per-ring ``scales`` и эффективный ``gap`` для ``layout``."""

    scales: list[float]
    gap: float


def select_ring_strategy(focus: Sequence[float], selection_on: bool):
    """Возвращает стратегию по числу выбранных колец.

    Больше одной выбранной — ``SelectMultipleIndicators``; одна (или ни одной, в том
    числе при выключенном выделении) — ``SelectSingleIndicator``.
    """
    return (
        SelectMultipleIndicators()
        if selection_on and count_selected(focus) > 1
        else SelectSingleIndicator()
    )


def min_gap_px_for(
    size: tuple[int, int],
    *,
    diagonal_inches: float | None = None,
    min_gap_mm: float | None = None,
) -> float:
    """Минимальный зазор под свечение в пикселях для панели ``size``.

    ``px_per_mm`` выводится из физической диагонали панели (``diagonal_inches``) и её
    пиксельного разрешения при квадратных пикселях: ``px_per_mm = diagonal_px / mm``.
    """
    diagonal_inches = DEVICE_DIAGONAL_INCHES if diagonal_inches is None else diagonal_inches
    min_gap_mm = GLOW_MIN_GAP_MM if min_gap_mm is None else min_gap_mm
    width = max(1, int(size[0]))
    height = max(1, int(size[1]))
    diagonal_px = (width * width + height * height) ** 0.5
    diagonal_mm = diagonal_inches * MM_PER_INCH
    return min_gap_mm * (diagonal_px / diagonal_mm)


class RingSelectionStrategy:
    """Базовый интерфейс стратегии роста выбранных колец."""

    def plan(
        self,
        *,
        count: int,
        base_widths: Sequence[float],
        focus: Sequence[float],
        scale_full: float,
        design_gap: float,
        min_gap_px: float,
        outer_r: float,
    ) -> RingGrowthPlan:
        """Возвращает ``RingGrowthPlan`` (масштабы роста и эффективный зазор)."""
        raise NotImplementedError


class SelectSingleIndicator(RingSelectionStrategy):
    """Прежнее поведение: каждая выбранная растёт на ``selection_scale`` целиком."""

    def plan(
        self,
        *,
        count: int,
        base_widths: Sequence[float],
        focus: Sequence[float],
        scale_full: float,
        design_gap: float,
        min_gap_px: float,
        outer_r: float,
    ) -> RingGrowthPlan:
        scales = [1.0 + (scale_full - 1.0) * clamp_fraction(focus[i]) for i in range(count)]
        return RingGrowthPlan(scales, design_gap)


class SelectMultipleIndicators(RingSelectionStrategy):
    """Рост нескольких выбранных с подъёмом зазора и урезанием роста соседних."""

    def plan(
        self,
        *,
        count: int,
        base_widths: Sequence[float],
        focus: Sequence[float],
        scale_full: float,
        design_gap: float,
        min_gap_px: float,
        outer_r: float,
    ) -> RingGrowthPlan:
        scales = [1.0 + (scale_full - 1.0) * clamp_fraction(focus[i]) for i in range(count)]
        if not has_adjacent_selected(focus, count):
            return RingGrowthPlan(scales, design_gap)
        # Соседние выбранные: поднимаем зазор под свечение и урезаем рост, чтобы
        # увеличенный зазор поместился в радиальный бюджет ``outer_r`` (внутреннее
        # кольцо не должно пройти через центр).
        target_gap = max(design_gap, min_gap_px)
        sum_base = sum(base_widths)
        grow_weight = sum(
            base_widths[i] * clamp_fraction(focus[i])
            for i in range(count)
            if focus[i] > SELECTION_COUNT_EPSILON
        )
        room_after_gap = outer_r - sum_base - target_gap * (count - 1)
        if room_after_gap <= RADIAL_FIT_EPSILON or grow_weight <= 0.0:
            # Не хватает места даже без роста — не разводим кольца шире, зазор остаётся.
            return RingGrowthPlan([1.0] * count, design_gap)
        cap = 1.0 + min(
            scale_full - 1.0, (room_after_gap - RADIAL_FIT_EPSILON) / grow_weight
        )
        capped = [1.0 + (cap - 1.0) * clamp_fraction(focus[i]) for i in range(count)]
        return RingGrowthPlan(capped, target_gap)


# --- Константы ---
# Запас радиального бюджета, чтобы внутреннее кольцо не прошло ровно через центр
# (иначе ``rings_focus.layout`` бросает ``ValueError``).
RADIAL_FIT_EPSILON = 0.5
# Минимальный зазор между краями двух СМЕЖНЫХ выбранных колец: места под свечение,
# чтобы свечения соседних выбранных колец не смешивались.
GLOW_MIN_GAP_MM = 3.0
# Физическая диагональ панели (Trofeo Vision, маркетинговый «11.3») и перевод мм.
DEVICE_DIAGONAL_INCHES = 11.3
MM_PER_INCH = 25.4
# Номинальное разрешение панели (для дефолтного min_gap_px в layout-менеджере).
DEFAULT_PANEL_SIZE = (1920, 440)
# Дефолтный минимальный зазор в px для номинальной панели.
DEFAULT_RING_MIN_GAP_PX = min_gap_px_for(DEFAULT_PANEL_SIZE)
