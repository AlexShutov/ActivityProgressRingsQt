"""Общая модель выделения индикаторов (MIT).

Выделение (selection) — «подсветить один или несколько элементов, приглушив
остальные». Линейный индикатор уже умел это (случайный столбец через окна данных,
затемнение соседей, свечение выделенного); кольцевой — умел только расти на фокусе.
Этот модуль выносит в одно место то, что не зависит от формы элемента:

- :func:`SelectionController` — **драйвер выделения**: «какой элемент выделен по
  времени» (чередование «выбрать/пропустить» по окнам данных, случайный индекс,
  плавное нарастание/затухание) плюс параметры рендера (``dim`` — затемнение
  невыделенных, ``active_index`` — какой активен).
- Общие хелперы стратегий: ``count_selected``, ``has_adjacent_selected``,
  ``select_strategy_kind`` — «сколько выбрано и есть ли соседние», которыми
  пользуются и линейный, и кольцевой (у обоих был дублированный код).

Сам рост/свечение каждого элемента остаётся в его рендере (столбец растёт по
ширине, кольцо — по толщине), но решение «кого подсветить» и «насколько затемнить»
общее, поэтому новый индикатор не копирует тайминг-логику.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import random
from collections.abc import Callable, Sequence

from .easing import ease_out_cubic

# Порог «элемент активен» для затемнения/определения активного (соответствует
# прежнему ``FOCUS_EPSILON`` линейного рендерера: маленький допуск, чтобы
# численный ноль или остатки после затухания не считались активом).
SELECTION_ACTIVE_EPSILON = 1e-6
# Порог «элемент выбран» при подсчёте выбранных для стратегии (менее строгий,
# как было в ``selection_strategy``/``rings_strategy``).
SELECTION_COUNT_EPSILON = 1e-9
# Насколько гаснет невыделенный элемент при активном пульсе (тот же диапазон,
# что в линейном рендерере).
SELECTION_DIM_MIN = 0.35
SELECTION_DIM_RANGE = 1.0 - SELECTION_DIM_MIN


def clamp_fraction(value: float) -> float:
    """Доля фокуса, зажатая в ``[0, 1]``."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def count_selected(focus: Sequence[float], epsilon: float = SELECTION_COUNT_EPSILON) -> int:
    """Сколько элементов сейчас «выбрано» (фокус строго больше ``epsilon``)."""
    return sum(1 for f in focus if f > epsilon)


def has_adjacent_selected(focus: Sequence[float], count: int) -> bool:
    """Есть ли среди выбранных соседняя пара ``i`` и ``i+1``."""
    selected = [
        i
        for i in range(count)
        if i < len(focus) and focus[i] > SELECTION_COUNT_EPSILON
    ]
    return any(cur == prev + 1 for prev, cur in zip(selected, selected[1:], strict=False))


def select_strategy_kind(focus: Sequence[float], selection_on: bool) -> str:
    """Вид стратегии роста: ``"multiple"``, если выбранных больше одной, иначе ``"single"``.

    Оба индикатора выбирают одну и ту же стратегию по числу выбранных: одна (или
    ни одной) — одиночный рост, несколько — рост с урезанием соседних пар.
    """
    return "multiple" if selection_on and count_selected(focus) > 1 else "single"


class SelectionController:
    """Драйвер выделения + параметры рендера, не зависящие от формы элемента.

    Состояние — «какой элемент выделен в текущем окне данных». ``advance``
    открывает новое окно (чередуя «выбрать случайный элемент» / «пропустить»),
    ``focus`` возвращает по одному фокусу ``0..1`` на элемент для момента ``now``
    (плавное нарастание в начале окна, удержание, затухание при пропуске).
    ``dim`` — насколько затемнить невыделенные элементы, ``active_index`` — индекс
    подсвеченного.  Форма (столбец/кольцо) в этом классе не участвует.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        select_count: int = 2,
        transition_s: float = 0.6,
        ease: Callable[[float], float] = ease_out_cubic,
        rng: random.Random | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._select_count = max(1, int(select_count))
        self._transition_s = float(transition_s)
        self._ease = ease
        self._rng = rng if rng is not None else random.Random()
        self._active_indices: tuple[int, ...] = ()
        self._should_select = True
        self._window_start = 0.0
        self._window_is_select = False

    @property
    def enabled(self) -> bool:
        """Включено ли выделение (при ``False`` — элементы не подсвечиваются)."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def active_index(self) -> int | None:
        """Первый подсвеченный элемент (``None`` — нет выделения).

        Оставляем для совместимости с прежним одиночным API (и тестами): сами
        индикаторы подсвечивают сразу все ``active_indices``.
        """
        return self._active_indices[0] if self._active_indices else None

    @property
    def active_indices(self) -> tuple[int, ...]:
        """Индексы подсвеченных в текущем окне данных элементов."""
        return self._active_indices

    @property
    def is_select_window(self) -> bool:
        """Истина, если текущее окно данных «выбранное» (а не «пропуск»)."""
        return self._window_is_select

    @property
    def should_select(self) -> bool:
        """Флаг «в следующем окне выбрать» (чередуется с каждым окном)."""
        return self._should_select

    def advance(self, now: float, count: int) -> None:
        """Открывает новое окно данных: через раз выбрать случайные элементы/пропустить."""
        if count <= 0 or not self._enabled:
            self._active_indices = ()
            return
        if self._should_select:
            pick = min(self._select_count, count)
            self._active_indices = tuple(self._rng.sample(range(count), pick))
            self._window_is_select = True
        else:
            self._window_is_select = False  # предыдущий пульс гаснет в этом окне
        self._window_start = now
        self._should_select = not self._should_select

    def focus(self, now: float, count: int) -> list[float]:
        """Per-element фокус ``0..1`` в текущем окне данных.

        Если окно «выбранное» — ``select_count`` случайных элементов плавно нарастают
        и держатся (фокус ``1.0``) до конца окна; если «пропуск» — предыдущий пульс
        плавно гаснет и остаётся выключенным.  Так выделение меняется вместе с данными
        и держится весь показ, а не мигает.
        """
        focus = [0.0] * count
        if count <= 0 or not self._enabled or not self._active_indices:
            return focus
        transition = max(SELECTION_ACTIVE_EPSILON, self._transition_s)
        elapsed = now - self._window_start
        for index in self._active_indices:
            if index >= count:
                # Элементов стало меньше под активным пульсом — пропускаем (иначе OOB).
                continue
            if self._window_is_select:
                focus[index] = (
                    self._ease(elapsed / transition) if elapsed <= transition else 1.0
                )
            else:
                focus[index] = (
                    1.0 - self._ease(elapsed / transition) if elapsed <= transition else 0.0
                )
        return focus

    @staticmethod
    def selection_strength(focus: Sequence[float]) -> float:
        """Максимальный фокус по всем элементам (сила текущего пульса)."""
        return max(focus) if focus else 0.0

    @staticmethod
    def active_index_of(focus: Sequence[float], selection_on: bool) -> int | None:
        """Индекс элемента с наибольшим фокусом (если он активнее нуля)."""
        if not selection_on or not focus:
            return None
        peak = max(focus)
        return focus.index(peak) if peak > SELECTION_ACTIVE_EPSILON else None

    @staticmethod
    def dim(focus_value: float, selection_on: bool, selection_strength: float) -> float:
        """Яркость элемента/подписи: при idle полная, при пульсе затемняется всё,
        кроме подсвеченного элемента."""
        if selection_on and selection_strength > SELECTION_ACTIVE_EPSILON:
            if focus_value > SELECTION_ACTIVE_EPSILON:
                return 1.0
            return 1.0 - SELECTION_DIM_RANGE * selection_strength
        return 1.0
