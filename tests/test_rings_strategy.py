"""Unit tests for the Activity-Rings selection-growth strategies (no Qt/Pillow).

Covers the strategy choice (single vs multiple by selected count), the single
full-growth behaviour, the multiple non-adjacent == single rule, the multiple
adjacent gap-raised + growth-throttled rule, the boundary (min gap too large →
no growth), and the integration through ``SelectionRingsLayoutManager``.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from activityrings.rings_layout import SelectionRingsLayoutManager
from activityrings.rings_strategy import (
    SelectMultipleIndicators,
    SelectSingleIndicator,
    count_selected,
    min_gap_px_for,
    select_ring_strategy,
)

SCALE = 1.22
DESIGN_GAP = 28.0
OUTER_R = 209.0
BASE = [34.485, 34.485, 34.485]


def _plan(strategy, focus, *, gap=DESIGN_GAP, min_gap=50.0):
    return strategy.plan(
        count=len(BASE),
        base_widths=BASE,
        focus=focus,
        scale_full=SCALE,
        design_gap=gap,
        min_gap_px=min_gap,
        outer_r=OUTER_R,
    )


# -- count / choice ----------------------------------------------------------
def test_count_selected_counts_only_positive_focus():
    assert count_selected([0.0, 1.0, 0.0]) == 1
    assert count_selected([0.5, 0.5, 0.0]) == 2
    assert count_selected([0.0, 0.0, 0.0]) == 0
    assert count_selected([0.0, 1.0, 1.0]) == 2


def test_strategy_is_single_when_at_most_one_selected():
    assert isinstance(select_ring_strategy([0.0, 1.0, 0.0], True), SelectSingleIndicator)
    assert isinstance(select_ring_strategy([0.0, 0.0, 0.0], True), SelectSingleIndicator)
    assert isinstance(select_ring_strategy([1.0, 0.0, 0.0], False), SelectSingleIndicator)


def test_strategy_is_multiple_when_more_than_one_selected():
    assert isinstance(select_ring_strategy([1.0, 1.0, 0.0], True), SelectMultipleIndicators)


# -- single ------------------------------------------------------------------
def test_single_plan_grows_full_with_design_gap():
    plan = _plan(SelectSingleIndicator(), [1.0, 0.0, 0.0])
    assert plan.scales[0] == pytest.approx(SCALE)  # полный рост выбранного
    assert plan.scales[1] == pytest.approx(1.0)
    assert plan.scales[2] == pytest.approx(1.0)
    assert plan.gap == pytest.approx(DESIGN_GAP)


# -- multiple, non-adjacent behaves like single ------------------------------
def test_multiple_non_adjacent_behaves_like_single():
    plan = _plan(SelectMultipleIndicators(), [1.0, 0.0, 1.0])  # 0 и 2 — не соседние
    assert plan.scales == pytest.approx([SCALE, 1.0, SCALE])
    assert plan.gap == pytest.approx(DESIGN_GAP)


# -- multiple, adjacent: gap raised + growth throttled -----------------------
def test_multiple_adjacent_raises_gap_and_caps_growth():
    plan = _plan(SelectMultipleIndicators(), [1.0, 1.0, 0.0])
    # Зазор поднят к min_gap_px (место под свечение).
    assert plan.gap == pytest.approx(50.0)
    assert plan.gap >= 50.0
    # Рост урезан (меньше полного selection_scale), но есть.
    assert 1.0 < plan.scales[0] < SCALE
    assert 1.0 < plan.scales[1] < SCALE
    assert plan.scales[2] == pytest.approx(1.0)
    # Увеличенный зазор умещается в радиальный бюджет (внутреннее кольцо не проходит центр).
    widths = [b * s for b, s in zip(BASE, plan.scales, strict=True)]
    assert sum(widths) + plan.gap * (len(BASE) - 1) < OUTER_R


# -- multiple, adjacent boundary: min gap too large -> no growth -------------
def test_multiple_adjacent_boundary_min_gap_too_large_no_growth():
    plan = _plan(SelectMultipleIndicators(), [1.0, 1.0, 0.0], min_gap=500.0)
    # Не хватает места даже без роста — рост нулевой, зазор возвращается к design_gap.
    assert plan.scales == pytest.approx([1.0, 1.0, 1.0])
    assert plan.gap == pytest.approx(DESIGN_GAP)


# -- px_per_mm helper --------------------------------------------------------
def test_min_gap_px_for_uses_diagonal():
    # 11.3" панель 1920x440: diagonal_px ~1969.8 / 287.02 мм ~ 6.863 px/мм.
    px = min_gap_px_for((1920, 440))
    assert px == pytest.approx(3.0 * (1969.8 / (11.3 * 25.4)), rel=1e-2)
    assert px > 0


# -- integration through the selection layout manager ------------------------
def test_selection_manager_adjacent_raises_gap_and_throttles_width():
    mgr = SelectionRingsLayoutManager(outer_fraction=0.55, min_gap_px=50.0)
    res = mgr.measure(760.0, None, [1.0, 1.0, 0.0])
    base = mgr.base_widths(res.outer_radius)
    # Зазор поднят к min_gap_px (≥ 50 px).
    assert res.gap == pytest.approx(50.0)
    assert res.gap >= 50.0
    # Соседние выбранные кольца растут меньше полного selection_scale.
    assert base[0] < res[0].width < base[0] * mgr.selection_scale
    assert base[1] < res[1].width < base[1] * mgr.selection_scale
    # Невыбранное кольцо не растёт.
    assert res[2].width == pytest.approx(base[2])


def test_selection_manager_single_still_grows_full():
    mgr = SelectionRingsLayoutManager(outer_fraction=0.55, min_gap_px=50.0)
    res = mgr.measure(760.0, None, [1.0, 0.0, 0.0])
    base = mgr.base_widths(res.outer_radius)
    assert res[0].width == pytest.approx(base[0] * mgr.selection_scale)
    assert res.gap < 50.0  # одно выбранное — зазор не поднимается
