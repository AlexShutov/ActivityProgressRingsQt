"""Общая отрисовка фона позади индикаторов (MIT).

За основу взят линейный индикатор: по умолчанию непрозрачная сплошная заливка
``DEFAULT_BACKGROUND``, а ``transparent=True`` даёт прозрачный оверлей для укладки
поверх живой темы панели. Класс ``IndicatorBackgroundDrawer`` сводит цвет и политику
прозрачности в одно место и умеет заливать фон и в Pillow RGBA-изображение
(кольцевой индикатор), и в Qt QImage (линейный индикатор), чтобы фон всех
индикаторов рисовался одинаково.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

DEFAULT_BACKGROUND: tuple[int, int, int] = (16, 18, 24)


class IndicatorBackgroundDrawer:
    """Единая заливка фона позади индикатора (за основу — линейный индикатор).

    По умолчанию непрозрачный фон цвета ``DEFAULT_BACKGROUND``; при
    ``transparent=True`` фон прозрачный (это нужно кольцевому оверлею и линейному
    оверлею дашборда поверх живой темы). Поддерживает оба бэкенда: ``fill_image`` —
    Pillow RGBA, ``fill_qimage`` — Qt QImage.
    """

    def __init__(
        self,
        background: tuple[int, int, int] | None = DEFAULT_BACKGROUND,
        *,
        transparent: bool = False,
    ) -> None:
        # Стабильный цвет фона (не зависит от прозрачности): из него выводится и
        # заливка канвы, и полупрозрачная подложка-трек ``backdrop``.
        background_rgb = DEFAULT_BACKGROUND if background is None else tuple(background)
        self._rgb: tuple[int, int, int] = (
            int(background_rgb[0]),
            int(background_rgb[1]),
            int(background_rgb[2]),
        )
        self._transparent = bool(transparent)
        if transparent:
            self._rgba: tuple[int, int, int, int] = (0, 0, 0, 0)
        else:
            self._rgba = (*self._rgb, 255)

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        """RGBA-цвет фона (``(0,0,0,0)`` при прозрачном)."""
        return self._rgba

    @property
    def rgb(self) -> tuple[int, int, int]:
        """RGB-цвет фона (стабильный, независимо от прозрачности)."""
        return self._rgb

    @property
    def transparent(self) -> bool:
        """Истина, если фон прозрачный (оверлей)."""
        return self._transparent

    def backdrop(self, alpha: int) -> tuple[int, int, int, int]:
        """Полупрозрачная подложка (трек) — «более прозрачная версия фона».

        Единый нейтральный цвет для всех элементов виджета (по умолчанию — сам
        цвет фона), чтобы фон под каждой полосой/кольцом не был разноцветным.
        Кольца рисуют им задний фон каждого кольца; композитный дашборд передаёт
        тот же нейтральный ``palette["muted"]`` и в кольца, и в подложку линейного
        индикатора, поэтому фон обоих виджетов совпадает.
        """
        return (*self._rgb, int(alpha))

    def fill_image(self, image) -> None:
        """Заливает весь фон в Pillow RGBA-изображении ``image`` (in-place)."""
        from PIL import ImageDraw

        width, height = image.size
        ImageDraw.Draw(image).rectangle([0, 0, width, height], fill=self._rgba)

    def fill_qimage(self, image) -> None:
        """Заливает весь фон в Qt QImage ``image`` (in-place)."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor

        if self.transparent:
            image.fill(Qt.GlobalColor.transparent)
        else:
            image.fill(QColor(*self.rgb))
