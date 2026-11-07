"""Общий функционал для всех индикаторов (MIT).

Переиспользуемые части, вынесенные из ``activityrings`` и
``activity_linear_indicator``, чтобы новый индикатор не копировал их:

- ``easing`` — числовые хелперы (clamp, ease-out, линейная интерполяция и цвет);
- ``focus`` — общая focus-модель (раскладка с постоянным зазором, таймлайн,
  расписание, прогресс-трек);
- ``background`` — единый фон позади индикатора (``IndicatorBackgroundDrawer``);
- ``selection`` — общая модель выделения (драйвер «какой элемент подсвечен»,
  затемнение, стратегия).

Ни один из модулей не тянет Qt/Pillow на импорте, поэтому ``common`` остаётся
лёгким и headless-пригодным (как и focus-модели индикаторов).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from .background import DEFAULT_BACKGROUND, IndicatorBackgroundDrawer
from .easing import clamp, ease_out_cubic, lerp, lerp_color
from .focus import (
    FOCUS_SCALE,
    GAP_FRACTION,
    TRANSITION_S,
    FocusTimelineBase,
    FocusWindow,
    default_schedule,
    layout,
    progress_track,
    seed_progress_targets,
)
from .selection import (
    SELECTION_ACTIVE_EPSILON,
    SELECTION_DIM_MIN,
    SELECTION_DIM_RANGE,
    SelectionController,
    clamp_fraction,
    count_selected,
    has_adjacent_selected,
    select_strategy_kind,
)

__all__ = [
    # numbers / easing
    "clamp",
    "ease_out_cubic",
    "lerp",
    "lerp_color",
    # focus model
    "FOCUS_SCALE",
    "GAP_FRACTION",
    "TRANSITION_S",
    "FocusTimelineBase",
    "FocusWindow",
    "default_schedule",
    "layout",
    "progress_track",
    "seed_progress_targets",
    # background
    "DEFAULT_BACKGROUND",
    "IndicatorBackgroundDrawer",
    # selection
    "SELECTION_ACTIVE_EPSILON",
    "SELECTION_DIM_MIN",
    "SELECTION_DIM_RANGE",
    "SelectionController",
    "clamp_fraction",
    "count_selected",
    "has_adjacent_selected",
    "select_strategy_kind",
]
