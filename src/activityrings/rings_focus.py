"""Pure focus-shift model for the Activity Rings overlay (MIT).

Deterministic and headless: given a schedule of focus windows it computes, for any
time ``t``, every ring's eased width and its gap-preserving radius. It imports no
Qt or Pillow, so the same code drives a live Qt view and an offscreen video render.

Geometry is anchored by :func:`layout`: the outermost band's OUTER edge is fixed at
``outer_r`` and the gap between adjacent band edges is constant. Focusing a ring
widens it (``FOCUS_SCALE``) and reflows the others around it so the gap is preserved
at every frame, not just at the endpoints. The shared logic lives in
:mod:`common.focus`; here we only specialise the width attribute name and the frame's
radius vector.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Re-export the shared model pieces so ``activityrings.rings_focus`` keeps its API.
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
    "BASE_RINGS",
    "FOCUS_SCALE",
    "GAP_FRACTION",
    "TRANSITION_S",
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
class RingBase:
    key: str
    label: str
    color: tuple[int, int, int]
    width_frac: float
    target: float
    start_angle: float = 270.0


BASE_RINGS: tuple[RingBase, ...] = (
    RingBase("move", "Move", (250, 55, 95), 0.165, 0.72),
    RingBase("exercise", "Exercise", (145, 221, 82), 0.165, 0.86),
    RingBase("stand", "Stand", (56, 181, 240), 0.165, 0.55),
)


@dataclass(frozen=True)
class FocusFrame:
    widths: list[float]
    radii: list[float]
    factors: list[float]


def default_schedule(
    period: float = 5.0,
    focus_duration: float = 2.0,
    n_rings: int = 3,
    cycles: int = 4,
) -> list[FocusWindow]:
    """Расписание фокус-окон (обёртка над ``common.focus.default_schedule``)."""
    return _generic_default_schedule(
        period=period, focus_duration=focus_duration, count=n_rings, cycles=cycles
    )


class FocusTimeline(FocusTimelineBase[FocusFrame]):
    """Per-ring eased focus {width, radius} for any time ``t``.

    ``schedule`` is a list of :class:`FocusWindow`. A ring ramps base -> focused with
    :func:`ease_out_cubic` over ``transition_s`` starting at its window start, holds
    until the window end, then ramps back over ``transition_s`` after it. Radii are
    derived from the animated widths via :func:`layout`, so the reflow stays
    gap-preserving continuously.
    """

    _width_attr = "width_frac"

    def __init__(
        self,
        schedule: Sequence[FocusWindow],
        *,
        outer_r: float,
        ring_bases: Sequence[RingBase] = BASE_RINGS,
        gap: float | None = None,
        transition_s: float = TRANSITION_S,
        scale: float = FOCUS_SCALE,
    ) -> None:
        super().__init__(
            schedule,
            outer=outer_r,
            bases=ring_bases,
            gap=gap,
            transition_s=transition_s,
            scale=scale,
        )

    def _make_frame(
        self, widths: list[float], radii: list[float], factors: list[float]
    ) -> FocusFrame:
        return FocusFrame(widths=widths, radii=radii, factors=factors)
