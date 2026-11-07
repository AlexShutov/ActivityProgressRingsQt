"""Общая focus-модель для всех индикаторов (MIT).

Детерминированная и headless-модель «выделения» индикатора: по расписанию окон
фокуса она считает для любого момента ``t`` утолщение каждого элемента и его
координату с сохранением постоянного зазора между соседними элементами. Не
импортирует Qt/Pillow, поэтому один и тот же код ведёт live-вью и офскрин-рендер.

Геометрия якорится функцией :func:`layout`: внешняя грань самого внешнего элемента
фиксируется на ``anchor``, зазор между соседними гранями постоянен. Фокус
утолщает элемент (``FOCUS_SCALE``) и перекладывает соседей вокруг него так, что
зазор сохраняется на каждом кадре. Модель одинакова для колец (centerline-радиусы)
и полос (centerline-позиции) — отличается только имя атрибута ширины на базе и
наименование вектора раскладки в итоговом кадре.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from .easing import ease_out_cubic, lerp

FOCUS_SCALE = 1.5
GAP_FRACTION = 0.075
TRANSITION_S = 0.6

_FrameT = TypeVar("_FrameT")


def layout(widths: Sequence[float], gap: float, anchor: float) -> list[float]:
    """Centerline-позиции, внешний элемент -> внутренний, с постоянным зазором.

    Внешняя грань первого элемента зафиксирована на ``anchor``, и каждая соседняя
    пара элементов держит ровный ``gap`` между внутренней гранью предыдущего и
    внешней гранью следующего. Возвращает по одной centerline-координате на входную
    ``width`` (одномерный аналог радиусов колец / позиций полос).
    """
    positions: list[float] = []
    acc = 0.0
    for i, w in enumerate(widths):
        if w <= 0:
            raise ValueError(f"width must be positive, got {w!r}")
        pos = anchor - gap * i - acc - w / 2.0
        if pos - w / 2.0 <= 0:
            raise ValueError(
                f"layout would run off the anchor at item {i}: position {pos!r}, width {w!r}"
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
    count: int = 3,
    cycles: int = 4,
) -> list[FocusWindow]:
    """Расписание фокус-окон по умолчанию (по одному на элемент, ``count`` штук)."""
    return [
        FocusWindow(i * period, i * period + focus_duration, i % count)
        for i in range(cycles)
    ]


class FocusTimelineBase(Generic[_FrameT]):
    """Общая база focus-таймлайна для любого индикатора (кольца/полосы/...).

    Подкласс задаёт:
     - ``_width_attr`` — имя атрибута ширины на базе (``"width_frac"`` для колец,
       ``"thickness_frac"`` для полос);
     - ``_make_frame(widths, offsets, factors)`` — как упаковать результат в свой
       ``FocusFrame`` (с нужным именем вектора раскладки).
    """

    _width_attr: str = "width_frac"

    def __init__(
        self,
        schedule: Sequence[FocusWindow],
        *,
        outer: float,
        bases: Sequence,
        gap: float | None = None,
        transition_s: float = TRANSITION_S,
        scale: float = FOCUS_SCALE,
    ) -> None:
        self._schedule = list(schedule)
        self._bases = list(bases)
        self._outer = outer
        self._gap = gap if gap is not None else GAP_FRACTION * outer
        self._transition_s = transition_s
        self._scale = scale

    def base_widths(self) -> list[float]:
        return [getattr(b, self._width_attr) * self._outer for b in self._bases]

    def focus_factor(self, t: float) -> list[float]:
        factors = [0.0] * len(self._bases)
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

    def frame(self, t: float) -> _FrameT:
        factors = self.focus_factor(t)
        widths = [
            b * (1.0 + f * (self._scale - 1.0))
            for b, f in zip(self.base_widths(), factors, strict=True)
        ]
        offsets = layout(widths, self._gap, self._outer)
        return self._make_frame(widths, offsets, factors)

    def _make_frame(
        self, widths: list[float], offsets: list[float], factors: list[float]
    ) -> _FrameT:
        raise NotImplementedError


def progress_track(
    t: float,
    targets: Sequence[Sequence[float]],
    *,
    interval_s: float,
    tween_s: float,
    ease=ease_out_cubic,
) -> list[float]:
    """Текущее значение прогресса на элемент в момент глобального времени ``t``.

    ``targets`` имеет индекс [interval_index][element_index]; каждый интервал длится
    ``interval_s`` секунд, значения перетекают из предыдущего интервала в текущий за
    ``tween_s`` секунд в начале интервала.
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
    return [lerp(prev[i], curr[i], ease(k)) for i in range(len(curr))]


def seed_progress_targets(
    n_intervals: int,
    n_items: int,
    seed: int,
    uplim: float = 2.0,
) -> list[list[float]]:
    """Псевдослучайные целевые значения прогресса (``uniform(0, uplim)``)."""
    rng = random.Random(seed)
    return [
        [rng.uniform(0.0, uplim) for _ in range(n_items)] for _ in range(n_intervals)
    ]
