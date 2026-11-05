"""Pure focus-shift model for the Activity Rings overlay (MIT).

Deterministic and headless: given a schedule of focus windows it computes, for any
time ``t``, every ring's eased width and its gap-preserving radius. It imports no
Qt or Pillow, so the same code drives a live Qt view and an offscreen video render.

Geometry is anchored by :func:`layout`: the outermost band's OUTER edge is fixed at
``outer_r`` and the gap between adjacent band edges is constant. Focusing a ring
widens it (``FOCUS_SCALE``) and reflows the others around it so the gap is preserved
at every frame, not just at the endpoints.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

FOCUS_SCALE = 1.5
GAP_FRACTION = 0.075
TRANSITION_S = 0.6


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


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def layout(widths: Sequence[float], gap: float, outer_r: float) -> list[float]:
    """Centerline radii, outermost -> innermost, with a constant band-edge gap.

    The outermost band's outer edge is fixed at ``outer_r`` and every adjacent pair
    of bands keeps an exact ``gap`` between the inner edge of the outer band and the
    outer edge of the inner band. Returns one centerline radius per input ``width``.
    """
    radii: list[float] = []
    acc = 0.0
    for i, w in enumerate(widths):
        if w <= 0:
            raise ValueError(f"width must be positive, got {w!r}")
        r = outer_r - gap * i - acc - w / 2.0
        if r - w / 2.0 <= 0:
            raise ValueError(
                f"layout would pass the center at ring {i}: radius {r!r}, width {w!r}"
            )
        radii.append(r)
        acc += w
    return radii


@dataclass(frozen=True)
class FocusWindow:
    start: float
    end: float
    index: int


def default_schedule(
    period: float = 5.0,
    focus_duration: float = 2.0,
    n_rings: int = 3,
    cycles: int = 4,
) -> list[FocusWindow]:
    return [
        FocusWindow(i * period, i * period + focus_duration, i % n_rings)
        for i in range(cycles)
    ]


@dataclass(frozen=True)
class FocusFrame:
    widths: list[float]
    radii: list[float]
    factors: list[float]


class FocusTimeline:
    """Per-ring eased focus {width, radius} for any time ``t``.

    ``schedule`` is a list of :class:`FocusWindow`. A ring ramps base -> focused with
    :func:`ease_out_cubic` over ``transition_s`` starting at its window start, holds
    until the window end, then ramps back over ``transition_s`` after it. Radii are
    derived from the animated widths via :func:`layout`, so the reflow stays
    gap-preserving continuously.
    """

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
        self._schedule = list(schedule)
        self._ring_bases = list(ring_bases)
        self._outer_r = outer_r
        self._gap = gap if gap is not None else GAP_FRACTION * outer_r
        self._transition_s = transition_s
        self._scale = scale

    def base_widths(self) -> list[float]:
        return [r.width_frac * self._outer_r for r in self._ring_bases]

    def focus_factor(self, t: float) -> list[float]:
        factors = [0.0] * len(self._ring_bases)
        for window in self._schedule:
            if window.index < len(factors):
                f = self._factor_for_window(window, t)
                if f > factors[window.index]:
                    factors[window.index] = f
        return factors

    def _factor_for_window(self, window: FocusWindow, t: float) -> float:
        ts = self._transition_s
        if t < window.start:
            return 0.0
        if t <= window.start + ts:
            return ease_out_cubic((t - window.start) / ts)
        if t <= window.end:
            return 1.0
        if t <= window.end + ts:
            return 1.0 - ease_out_cubic((t - window.end) / ts)
        return 0.0

    def frame(self, t: float) -> FocusFrame:
        factors = self.focus_factor(t)
        widths = [
            b * (1.0 + f * (self._scale - 1.0))
            for b, f in zip(self.base_widths(), factors, strict=True)
        ]
        radii = layout(widths, self._gap, self._outer_r)
        return FocusFrame(widths=widths, radii=radii, factors=factors)


def progress_track(
    t: float,
    targets: Sequence[Sequence[float]],
    *,
    interval_s: float,
    tween_s: float,
    ease=ease_out_cubic,
) -> list[float]:
    """Current per-ring progress at global time ``t``.

    ``targets`` is indexed [interval_index][ring_index]; each interval lasts
    ``interval_s`` seconds and values ease from the previous interval's value to the
    current interval's value over ``tween_s`` seconds at the start of the interval.
    """
    if t < 0:
        return list(targets[0])
    tween_s = min(tween_s, interval_s)
    idx = int(t // interval_s)
    idx = min(idx, len(targets) - 1)
    t_in = t - idx * interval_s
    k = min(1.0, t_in / tween_s) if tween_s > 0 else 1.0
    prev = targets[idx - 1] if idx > 0 else targets[idx]
    curr = targets[idx]
    return [prev[r] + (curr[r] - prev[r]) * ease(k) for r in range(len(curr))]


def seed_progress_targets(
    n_intervals: int,
    n_rings: int,
    seed: int,
    uplim: float = 2.0,
) -> list[list[float]]:
    """Per-interval per-ring random progress targets (``uniform(0, uplim)``)."""
    rng = random.Random(seed)
    return [
        [rng.uniform(0.0, uplim) for _ in range(n_rings)] for _ in range(n_intervals)
    ]
