"""Unit tests for the shared selection model in ``common.selection`` (MIT).

Covers the ``SelectionController`` driver (какой элемент подсветить по окнам данных),
the shape-agnostic render params (``dim``/``selection_strength``/``active_index_of``)
and the strategy helpers (``count_selected``/``has_adjacent_selected``/
``select_strategy_kind``) that both the linear and the ring indicator share.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import random

import pytest

from common.selection import (
    SELECTION_ACTIVE_EPSILON,
    SELECTION_COUNT_EPSILON,
    SELECTION_DIM_MIN,
    SELECTION_DIM_RANGE,
    SelectionController,
    clamp_fraction,
    count_selected,
    has_adjacent_selected,
    select_strategy_kind,
)


# -- helpers ----------------------------------------------------------------
def test_clamp_fraction_bounds():
    assert clamp_fraction(-1.0) == 0.0
    assert clamp_fraction(0.5) == 0.5
    assert clamp_fraction(2.0) == 1.0


def test_count_selected_uses_tight_epsilon():
    assert count_selected([1.0, 0.5, 0.0, 1e-10]) == 2
    assert count_selected([0.0, 0.0]) == 0
    assert count_selected([2.0, 3.0]) == 2


def test_count_selected_uses_count_epsilon_to_exclude_sub_epsilon():
    # При 1e-10 < SELECTION_COUNT_EPSILON (1e-9) элемент не считается выбранным.
    assert SELECTION_COUNT_EPSILON == 1e-9
    assert count_selected([1e-10]) == 0
    assert count_selected([1e-8]) == 1


def test_has_adjacent_selected_detects_pairs():
    assert has_adjacent_selected([1.0, 1.0, 0.0], 3) is True
    assert has_adjacent_selected([1.0, 0.0, 1.0], 3) is False
    assert has_adjacent_selected([1.0, 0.0, 0.0], 3) is False


def test_select_strategy_kind_picks_multiple_over_single():
    assert select_strategy_kind([1.0, 0.0, 0.0], True) == "single"
    assert select_strategy_kind([1.0, 1.0, 0.0], True) == "multiple"
    assert select_strategy_kind([1.0, 1.0, 0.0], False) == "single"


# -- driver: advance / focus ------------------------------------------------
def test_controller_advance_alternates_select_and_skip_windows():
    controller = SelectionController(rng=random.Random(7))
    controller.advance(0.0, 3)
    assert controller.is_select_window is True
    assert controller.active_index in (0, 1, 2)
    controller.advance(5.0, 3)
    assert controller.is_select_window is False
    controller.advance(10.0, 3)
    assert controller.is_select_window is True


def test_controller_disabled_clears_active():
    controller = SelectionController(enabled=False, rng=random.Random(1))
    controller.advance(0.0, 3)
    assert controller.active_index is None
    assert controller.focus(0.0, 3) == [0.0, 0.0, 0.0]


def test_controller_zero_count_clears_active():
    controller = SelectionController(rng=random.Random(2))
    controller.advance(0.0, 0)
    assert controller.active_index is None


def test_controller_select_window_focus_rises_then_holds():
    controller = SelectionController(transition_s=0.6, rng=random.Random(3))
    controller.advance(0.0, 3)
    idx = controller.active_index
    assert controller.focus(0.3, 3)[idx] == pytest.approx(0.875)  # ease-out(0.5)
    assert controller.focus(1.0, 3)[idx] == 1.0  # удержание до конца окна


def test_controller_skip_window_focus_fades_to_zero():
    controller = SelectionController(transition_s=0.6, rng=random.Random(4))
    controller.advance(0.0, 3)
    idx = controller.active_index
    controller.advance(1.0, 3)  # «пропуск»: прошлый пульс гаснет
    assert controller.focus(1.3, 3)[idx] == pytest.approx(0.125)  # ease-out(0.5)
    assert controller.focus(2.0, 3)[idx] == 0.0


def test_controller_focus_survives_count_shrink():
    controller = SelectionController(rng=random.Random(5))
    controller.advance(0.0, 3)
    if controller.active_index is not None and controller.active_index >= 1:
        # Стало меньше колец под активным → актив сбрасывается, без OOB-краша.
        focus = controller.focus(0.1, 1)
        assert len(focus) == 1
        assert focus[0] == 0.0


def test_controller_selection_strength_is_peak():
    assert SelectionController.selection_strength([0.2, 0.9, 0.1]) == pytest.approx(0.9)
    assert SelectionController.selection_strength([]) == 0.0


def test_controller_active_index_of_picks_peak():
    assert SelectionController.active_index_of([0.9, 0.1], True) == 0
    assert SelectionController.active_index_of([0.1, 0.9], True) == 1
    assert SelectionController.active_index_of([0.0, 0.0], True) is None
    assert SelectionController.active_index_of([0.9, 0.1], False) is None


# -- render param: dim -------------------------------------------------------
def test_controller_dim_keeps_active_full_dims_inactive():
    assert SelectionController.dim(1.0, True, 1.0) == 1.0
    assert SelectionController.dim(0.0, True, 1.0) == pytest.approx(
        1.0 - SELECTION_DIM_RANGE
    )
    assert SelectionController.dim(0.0, False, 1.0) == 1.0
    assert SelectionController.dim(0.0, True, 0.0) == 1.0


def test_dim_constants_are_coherent():
    assert SELECTION_DIM_MIN == 0.35
    assert SELECTION_DIM_RANGE == pytest.approx(1.0 - SELECTION_DIM_MIN)
    assert SELECTION_ACTIVE_EPSILON == 1e-6