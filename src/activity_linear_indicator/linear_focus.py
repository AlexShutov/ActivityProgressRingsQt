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
gap is preserved at every frame, not just at the endpoints.
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


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def layout(widths: Sequence[float], gap: float, outer_len: float) -> list[float]:
    """Centerline positions, first bar -> last, with a constant edge gap.

    The first bar's outer edge is fixed at ``outer_len`` and every adjacent pair of
    bars keeps an exact ``gap`` between the inner edge of the preceding bar and the
    outer edge of the following bar. Returns one centerline position per input
    ``width`` (a one-dimensional analog of the rings' centerline radii).
    """
    positions: list[float] = []
    acc = 0.0
    for i, w in enumerate(widths):
        if w <= 0:
            raise ValueError(f"width must be positive, got {w!r}")
        pos = outer_len - gap * i - acc - w / 2.0
        if pos - w / 2.0 <= 0:
            raise ValueError(
                f"layout would run off the anchor at bar {i}: position {pos!r}, width {w!r}"
            )
        positions.append(pos)
        acc += w
    return positions


@dataclass(frozen=True)
class FocusWindow:
    start: float
    end: float
    index: int


def default_schedule(
    period: float = 5.0,
    focus_duration: float = 2.0,
    n_bars: int = 3,
    cycles: int = 4,
) -> list[FocusWindow]:
    return [
        FocusWindow(i * period, i * period + focus_duration, i % n_bars)
        for i in range(cycles)
    ]


@dataclass(frozen=True)
class FocusFrame:
    widths: list[float]
    positions: list[float]
    factors: list[float]


class FocusTimeline:
    """Per-bar eased focus {width, position} for any time ``t``.

    ``schedule`` is a list of :class:`FocusWindow`. A bar ramps base -> focused with
    :func:`ease_out_cubic` over ``transition_s`` starting at its window start, holds
    until the window end, then ramps back over ``transition_s`` after it. Positions
    are derived from the animated widths via :func:`layout`, so the reflow stays
    gap-preserving continuously.
    """

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
        self._schedule = list(schedule)
        self._bar_bases = list(bar_bases)
        self._outer_len = outer_len
        self._gap = gap if gap is not None else GAP_FRACTION * outer_len
        self._transition_s = transition_s
        self._scale = scale

    def base_widths(self) -> list[float]:
        return [b.thickness_frac * self._outer_len for b in self._bar_bases]

    def focus_factor(self, t: float) -> list[float]:
        factors = [0.0] * len(self._bar_bases)
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
        positions = layout(widths, self._gap, self._outer_len)
        return FocusFrame(widths=widths, positions=positions, factors=factors)


def progress_track(
    t: float,
    targets: Sequence[Sequence[float]],
    *,
    interval_s: float,
    tween_s: float,
    ease=ease_out_cubic,
) -> list[float]:
    """Current per-bar progress at global time ``t``.

    ``targets`` is indexed [interval_index][bar_index]; each interval lasts
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
    return [prev[i] + (curr[i] - prev[i]) * ease(k) for i in range(len(curr))]


def seed_progress_targets(
    n_intervals: int,
    n_bars: int,
    seed: int,
    uplim: float = 2.0,
) -> list[list[float]]:
    """Per-interval per-bar random progress targets (``uniform(0, uplim)``)."""
    rng = random.Random(seed)
    return [
        [rng.uniform(0.0, uplim) for _ in range(n_bars)] for _ in range(n_intervals)
    ]
