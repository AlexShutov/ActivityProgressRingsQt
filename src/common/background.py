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
        if transparent:
            self._rgba: tuple[int, int, int, int] = (0, 0, 0, 0)
        else:
            rgb = DEFAULT_BACKGROUND if background is None else tuple(background)
            self._rgba = (rgb[0], rgb[1], rgb[2], 255)

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        """RGBA-цвет фона (``(0,0,0,0)`` при прозрачном)."""
        return self._rgba

    @property
    def rgb(self) -> tuple[int, int, int]:
        """RGB-цвет фона (для непрозрачных бэкендов)."""
        return self._rgba[:3]

    @property
    def transparent(self) -> bool:
        """Истина, если фон прозрачный (оверлей)."""
        return self._rgba[3] == 0

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
