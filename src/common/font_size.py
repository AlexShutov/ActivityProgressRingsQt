"""Подбор максимального размера шрифта под ограничения (MIT).

:class:`FontSizeCalculator` измеряет текст *тем же* резолвером, что и рисование
(``FontResolver``), и бинарным поиском находит наибольший кегль в px, при котором
текст помещается в заданные габариты.  Используется в виджете линейного прогресса:

- значение-процент (``"100%"``) — по ширине нижней зоны столбца, чтобы надпись
  «максимально вмещалась» и не наезжала на соседние столбцы;
- подписи-буквы сверху — один общий кегль для **всех** таких надписей (перебор
  по всем подписям делает сам виджет, здесь — только измерение и подбор).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from .font import FontResolver, FontSpec

# Гарантированный читаемый минимум и разумный потолок кегля (px) для перебора.
DEFAULT_FONT_SIZE_MIN = 12
DEFAULT_FONT_SIZE_MAX = 400


class FontSizeCalculator:
    """Максимальный кегль, при котором текст помещается в заданные габариты.

    ``fit_to_width``/``fit_to_height`` возвращают наибольший целый кегль в
    диапазоне ``[min_size, max_size]``, при котором измеренная ширина/высота текста
    не превышает лимит.  Если даже минимальный кегль не влезает — возвращается он.
    """

    def __init__(
        self,
        resolver: FontResolver | None = None,
        *,
        min_size: int = DEFAULT_FONT_SIZE_MIN,
        max_size: int = DEFAULT_FONT_SIZE_MAX,
        letter_spacing_fraction: float = 0.0,
    ) -> None:
        self._resolver = resolver if resolver is not None else FontResolver()
        self._min_size = max(1, int(min_size))
        self._max_size = max(self._min_size, int(max_size))
        # Межсимвольный интервал как доля кегля (0 — без трекинга).  Учитывается в
        # ``measure_width``, чтобы подбор кегля оставлял место и под трекинг.
        self._letter_spacing_fraction = max(0.0, float(letter_spacing_fraction))

    @property
    def min_size(self) -> int:
        """Нижняя граница перебора кегля (px)."""
        return self._min_size

    @property
    def max_size(self) -> int:
        """Верхняя граница перебора кегля (px)."""
        return self._max_size

    def measure_width(self, text: str, family: str, size: int) -> float:
        """Ширина ``text`` в px при ``family``/``size`` (0, если шрифт недоступен).

        Включает межсимвольный трекинг (``letter_spacing_fraction``), чтобы
        ``fit_to_width`` оставлял место и под интервалы между символами.
        """
        font = self._resolver.resolve(FontSpec(family, size))
        if font is None:
            return 0.0
        width = float(font.getlength(text))
        tracking = self._letter_spacing_fraction * size * max(0, len(text) - 1)
        return width + tracking

    def measure_height(self, text: str, family: str, size: int) -> float:
        """Высота ``text`` в px при ``family``/``size`` (0, если шрифт недоступен)."""
        font = self._resolver.resolve(FontSpec(family, size))
        if font is None:
            return 0.0
        box = font.getbbox(text)
        return float(box[3] - box[1])

    def fit_to_width(
        self,
        text: str,
        family: str,
        max_width: float,
        *,
        min_size: int | None = None,
        max_size: int | None = None,
    ) -> int:
        """Наибольший кегль, при котором ``text`` уже ``max_width``."""
        lo = self._min_size if min_size is None else max(self._min_size, int(min_size))
        hi = self._max_size if max_size is None else min(self._max_size, int(max_size))
        return self._search(
            text, family, max_width, lo, hi, measuring=self.measure_width
        )

    def fit_to_height(
        self,
        text: str,
        family: str,
        max_height: float,
        *,
        min_size: int | None = None,
        max_size: int | None = None,
    ) -> int:
        """Наибольший кегль, при котором ``text`` не выше ``max_height``."""
        lo = self._min_size if min_size is None else max(self._min_size, int(min_size))
        hi = self._max_size if max_size is None else min(self._max_size, int(max_size))
        return self._search(
            text, family, max_height, lo, hi, measuring=self.measure_height
        )

    def fit(
        self,
        text: str,
        family: str,
        max_width: float,
        max_height: float | None = None,
        *,
        min_size: int | None = None,
        max_size: int | None = None,
    ) -> int:
        """Наибольший кегль, при котором ``text`` влезает по ширине (**и** высоте)."""
        size_by_width = self.fit_to_width(
            text, family, max_width, min_size=min_size, max_size=max_size
        )
        if max_height is None:
            return size_by_width
        size_by_height = self.fit_to_height(
            text, family, max_height, min_size=min_size, max_size=max_size
        )
        return min(size_by_width, size_by_height)

    def _search(
        self,
        text: str,
        family: str,
        max_extent: float,
        low: int,
        high: int,
        *,
        measuring,
    ) -> int:
        """Бинарный поиск наибольшего кегля в ``[low, high]`` под ``max_extent``."""
        best = low
        while low <= high:
            mid = (low + high) // 2
            if measuring(text, family, mid) <= max_extent:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best
