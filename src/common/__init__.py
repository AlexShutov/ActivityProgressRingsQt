"""Общий функционал для всех индикаторов (MIT).

Переиспользуемые части, вынесенные из ``activityrings`` и
``activity_linear_indicator``, чтобы новый индикатор не копировал их:

- ``easing`` — числовые хелперы (clamp, ease-out, линейная интерполяция и цвет);
- ``focus`` — общая focus-модель (раскладка с постоянным зазором, таймлайн,
  расписание, прогресс-трек);
- ``background`` — единый фон позади индикатора (``IndicatorBackgroundDrawer``).

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
]
