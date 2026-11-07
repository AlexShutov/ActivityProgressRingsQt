"""Pure focus-shift model for the Activity Linear Indicator overlay (MIT).

Deterministic and headless: given a schedule of focus windows it computes, for any
time ``t``, every bar's eased thickness and its gap-preserving vertical position. It
imports no Qt or Pillow, so the same code drives a live Qt view and an offscreen
video render.

The bars are a one-dimensional analog of the concentric Activity Rings: instead of
centerline ``radius`` around a shared center, each bar has a ``thickness`` laid out
along a single axis, and :func:`layout` preserves a constant edge gap between
adjacent bars while anchoring the outer (first) bar's edge at ``outer_len``.
Focusing a bar widens it (``FOCUS_SCALE``) and reflows the others around it so the
gap is preserved at every frame, not just at the endpoints. The shared logic lives in
:mod:`common.focus`; here we only specialise the width attribute name and the frame's
position vector.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Re-export the shared model pieces so ``activity_linear_indicator.linear_focus``
# keeps its API (used by the renderer, the preview tool and the main dashboard).
from common.easing import ease_out_cubic  # noqa: F401
from common.focus import (  # noqa: F401
    FOCUS_SCALE,
    GAP_FRACTION,
    TRANSITION_S,
    FocusTimelineBase,
    FocusWindow,
    layout,
    progress_track,
    seed_progress_targets,
)
from common.focus import (
    default_schedule as _generic_default_schedule,
)

__all__ = [
    "BASE_BARS",
    "FOCUS_SCALE",
    "GAP_FRACTION",
    "TRANSITION_S",
    "BarBase",
    "FocusFrame",
    "FocusTimeline",
    "FocusWindow",
    "default_schedule",
    "ease_out_cubic",
    "layout",
    "progress_track",
    "seed_progress_targets",
]


@dataclass(frozen=True)
class BarBase:
    key: str
    label: str
    color: tuple[int, int, int]
    thickness_frac: float
    target: float


BASE_BARS: tuple[BarBase, ...] = (
    BarBase("move", "Move", (250, 55, 95), 0.165, 0.72),
    BarBase("exercise", "Exercise", (145, 221, 82), 0.165, 0.86),
    BarBase("stand", "Stand", (56, 181, 240), 0.165, 0.55),
)


@dataclass(frozen=True)
class FocusFrame:
    widths: list[float]
    positions: list[float]
    factors: list[float]


def default_schedule(
    period: float = 5.0,
    focus_duration: float = 2.0,
    n_bars: int = 3,
    cycles: int = 4,
) -> list[FocusWindow]:
    """Расписание фокус-окон (обёртка над ``common.focus.default_schedule``)."""
    return _generic_default_schedule(
        period=period, focus_duration=focus_duration, count=n_bars, cycles=cycles
    )


class FocusTimeline(FocusTimelineBase[FocusFrame]):
    """Per-bar eased focus {width, position} for any time ``t``.

    ``schedule`` is a list of :class:`FocusWindow`. A bar ramps base -> focused with
    :func:`ease_out_cubic` over ``transition_s`` starting at its window start, holds
    until the window end, then ramps back over ``transition_s`` after it. Positions
    are derived from the animated widths via :func:`layout`, so the reflow stays
    gap-preserving continuously.
    """

    _width_attr = "thickness_frac"

    def __init__(
        self,
        schedule: Sequence[FocusWindow],
        *,
        outer_len: float,
        bar_bases: Sequence[BarBase] = BASE_BARS,
        gap: float | None = None,
        transition_s: float = TRANSITION_S,
        scale: float = FOCUS_SCALE,
    ) -> None:
        super().__init__(
            schedule,
            outer=outer_len,
            bases=bar_bases,
            gap=gap,
            transition_s=transition_s,
            scale=scale,
        )

    def _make_frame(
        self, widths: list[float], positions: list[float], factors: list[float]
    ) -> FocusFrame:
        return FocusFrame(widths=widths, positions=positions, factors=factors)
