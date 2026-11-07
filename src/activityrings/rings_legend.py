"""Circular legend for the Activity Rings overlay (MIT).

Places one label per ring on a circle just outside the outermost ring's outer edge.
Each label sits in a rectangular backdrop (the ring's gauge colour at ~0.9 opacity)
with the same font as the linear indicator — the resolved font is passed in from the
outside, so the widgets stay decoupled from the dashed chart.

Placement resolves on a screen-coordinate circle around the ring centre: 0°=right,
90°=down, 180°=left, 270°=up.  A ring hugging the right edge leaves only the left arc
free, so the layout first excludes the "blind" angles where a label backdrop would fall
off-screen, keeps the largest contiguous remaining sector, splits it into one part per
ring, and drops each label at the midpoint of its part (polar coordinates).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from PIL import Image, ImageDraw, ImageFont

Color = tuple[int, int, int]

# Легенда лежит на окружности радиусом ``outer_ring_outer_edge + 1 см`` (мм).
RING_LEGEND_RADIUS_CLEARANCE_MM = 10.0
# Отступ от текста до края подложки (мм) — переводится в px через ``px_per_mm``.
RING_LEGEND_LABEL_PAD_MM = 0.3
# Непрозрачность подложки (~0.9 от 255).
RING_LEGEND_BACKDROP_ALPHA = 230
# Радиус скругления подложки как доля её высоты (мягкие углы вместо острых).
RING_LEGEND_BACKDROP_CORNER_FRACTION = 0.18
# Разрешение сканирования «слепой зоны»: число проб на каждый кольцевой сектор.
RING_LEGEND_SECTOR_SCAN_SAMPLES = 96

# Угловые «кандидатские» сектора (в градусах, экранные координаты) по стороне легенды.
_CANDIDATE_SECTOR_BY_PLACEMENT: dict[str, tuple[float, float]] = {
    "LEFT": (90.0, 270.0),
    "RIGHT": (-90.0, 90.0),
    "BOTH": (-180.0, 180.0),
}


class LegendPlacement(Enum):
    """Сторона, на которой рисуется легенда относительно круга."""

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    BOTH = "BOTH"


def parse_legend_placement(value: str | None) -> LegendPlacement | None:
    """Парсит ``"LEFT"/"RIGHT"/"BOTH"`` (без регистра) в ``LegendPlacement``.

    ``None``/пустая строка/неизвестное значение → ``None`` (вызывающий решает).
    """
    if not value:
        return None
    normalized = str(value).strip().upper()
    for placement in LegendPlacement:
        if placement.value == normalized:
            return placement
    return None


@dataclass(frozen=True)
class LegendLabel:
    """Позиция одной подписи легенды: текст, центр (в px) и цвет подложки."""

    text: str
    center: tuple[float, float]
    color: Color


class CircleLegendLayoutManager:
    """Раскладка и отрисовка круговой легенды колец.

    ``center`` — центр кольцевой группы в координатах целевого канваса; ``radius`` —
    радиус окружности легенды (уже включает ``RING_LEGEND_RADIUS_CLEARANCE_MM``).
    ``view_size`` — размеры канваса (px), за пределы которого подписи не выходят.
    ``font`` — уже настроенный ``PIL.ImageFont`` (тот же, что у линейного индикатора).
    ``text_color``/``backdrop_alpha`` — цвет текста и непрозрачность подложки;
    ``padding_px`` — отступ текста от края подложки; ``corner_radius_px`` — радиус
    скругления подложки; ``letter_spacing_px`` — межсимвольный трекинг (как у линейного).
    """

    def __init__(
        self,
        *,
        center: tuple[float, float],
        radius: float,
        view_size: tuple[int, int],
        placement: LegendPlacement,
        font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
        text_color: Color,
        backdrop_alpha: int = RING_LEGEND_BACKDROP_ALPHA,
        padding_px: float = 0.0,
        corner_radius_px: float = 0.0,
        letter_spacing_px: float = 0.0,
    ) -> None:
        self._center = (float(center[0]), float(center[1]))
        self._radius = float(radius)
        self._view_size = (int(view_size[0]), int(view_size[1]))
        self._placement = placement
        self._font = font
        self._text_color = (int(text_color[0]), int(text_color[1]), int(text_color[2]))
        self._backdrop_alpha = int(backdrop_alpha)
        self._padding_px = float(padding_px)
        self._corner_radius_px = float(corner_radius_px)
        self._letter_spacing_px = float(letter_spacing_px)

    # -- Измерение текста --------------------------------------------------
    def _measure_width(self, text: str) -> float:
        """Ширина ``text`` в px с учётом межсимвольного трекинга."""
        if self._letter_spacing_px > 0 and len(text) > 1:
            per_char = sum(float(self._font.getlength(ch)) for ch in text)
            return per_char + self._letter_spacing_px * (len(text) - 1)
        return float(self._font.getlength(text))

    def _measure_height(self, text: str) -> float:
        """Высота ``text`` в px (по bbox глифов)."""
        bbox = self._font.getbbox(text)
        return float(bbox[3] - bbox[1])

    def _measure(self, text: str) -> tuple[float, float]:
        """``(width, height)`` текста в px, с трекингом и без него."""
        return self._measure_width(text), self._measure_height(text)

    def _max_label_size(self, labels: Sequence[str]) -> tuple[float, float]:
        """Максимальная ``(width, height)`` среди всех подписей (консервативный габарит)."""
        sizes = [self._measure(text) for text in labels]
        if not sizes:
            return 0.0, 0.0
        return (
            max(size[0] for size in sizes) + 2.0 * self._padding_px,
            max(size[1] for size in sizes) + 2.0 * self._padding_px,
        )

    # -- Слепая зона / рабочий сектор -------------------------------------
    def _candidate_sector(self) -> tuple[float, float]:
        """Угловой интервал-кандидат для стороны легенды (градусы, экранные)."""
        return _CANDIDATE_SECTOR_BY_PLACEMENT[self._placement.value]

    def _label_center_at(self, angle_deg: float) -> tuple[float, float]:
        """Центр подписи на окружности легенды под углом ``angle_deg`` (экранные градусы)."""
        rad = math.radians(angle_deg)
        return (
            self._center[0] + self._radius * math.cos(rad),
            self._center[1] + self._radius * math.sin(rad),
        )

    def _box_fits_at(self, angle_deg: float, box_w: float, box_h: float) -> bool:
        """Помещается ли подложка ``box_w``×``box_h`` в ``view_size`` под углом."""
        px, py = self._label_center_at(angle_deg)
        half_w = box_w / 2.0
        half_h = box_h / 2.0
        return (
            px - half_w >= 0.0
            and px + half_w <= self._view_size[0]
            and py - half_h >= 0.0
            and py + half_h <= self._view_size[1]
        )

    def _usable_sector(self, labels: Sequence[str]) -> tuple[float, float]:
        """Наибольший непрерывный угловой сектор, где помещаются все подписи.

        Сканируем «кандидатский» интервал стороны, отмечаем углы, где подложка
        максимальной подписи влезает в канвас, и берём самый длинный непрерывный
        прогон (сама «слепая зона» — всё остальное).  Если ни один угол не влезает,
        возвращаем весь кандидатский интервал (перерисуем с возможным обрезом).
        """
        candidate_start, candidate_end = self._candidate_sector()
        span = candidate_end - candidate_start
        if span <= 0:
            return candidate_start, candidate_end
        box_w, box_h = self._max_label_size(labels)
        samples = max(RING_LEGEND_SECTOR_SCAN_SAMPLES, int(round(abs(span))))
        step = span / samples
        runs: list[tuple[float, float]] = []
        run_start: float | None = None
        run_end: float = 0.0
        for sample in range(samples + 1):
            angle = candidate_start + step * sample
            if self._box_fits_at(angle, box_w, box_h):
                if run_start is None:
                    run_start = angle
                run_end = angle
            elif run_start is not None:
                runs.append((run_start, run_end))
                run_start = None
        if run_start is not None:
            runs.append((run_start, run_end))
        if not runs:
            return candidate_start, candidate_end
        return max(runs, key=lambda run: run[1] - run[0])

    def layout(self, labels: Sequence[str], colors: Sequence[Color]) -> list[LegendLabel]:
        """Считает позиции подписей: сектор → разбиение на ``count`` частей → полярная точка.

        Каждая подпись попадает в середину своей части углового сектора, на окружность
        ``radius`` вокруг ``center`` (полярные координаты).  Порядок подписей сохраняется
        (первая подпись — первая часть сектора).
        """
        label_list = list(labels)
        color_list = list(colors)
        if not label_list:
            return []
        count = len(label_list)
        sector_start, sector_end = self._usable_sector(label_list)
        step = (sector_end - sector_start) / count
        result: list[LegendLabel] = []
        for index in range(count):
            angle = sector_start + step * (index + 0.5)
            color = color_list[index] if index < len(color_list) else (
                color_list[0] if color_list else self._text_color
            )
            result.append(
                LegendLabel(
                    text=label_list[index],
                    center=self._label_center_at(angle),
                    color=color,
                )
            )
        return result

    # -- Отрисовка ---------------------------------------------------------
    def _draw_text(self, draw, text: str, top: float, left: float, box_w: float) -> None:
        """Рисует ``text`` по центру подложки с межсимвольным трекингом."""
        text_w = self._measure_width(text)
        caret = left + (box_w - text_w) / 2.0
        if self._letter_spacing_px <= 0 or len(text) <= 1:
            draw.text((caret, top), text, font=self._font, fill=(*self._text_color, 255))
            return
        for ch in text:
            draw.text((caret, top), ch, font=self._font, fill=(*self._text_color, 255))
            caret += float(draw.textlength(ch, font=self._font)) + self._letter_spacing_px

    def render(
        self,
        canvas: Image.Image,
        labels: Sequence[str],
        colors: Sequence[Color],
    ) -> Image.Image:
        """Рисует подложки и текст легенды на ``canvas`` (RGBA) и возвращает его."""
        draw = ImageDraw.Draw(canvas)
        for label in self.layout(labels, colors):
            text_w, text_h = self._measure(label.text)
            box_w = text_w + 2.0 * self._padding_px
            box_h = text_h + 2.0 * self._padding_px
            left = label.center[0] - box_w / 2.0
            top = label.center[1] - box_h / 2.0
            corner = min(self._corner_radius_px, box_h / 2.0)
            text_top = top + (box_h - text_h) / 2.0
            draw.rounded_rectangle(
                (left, top, left + box_w, top + box_h),
                radius=corner,
                fill=(*label.color, self._backdrop_alpha),
            )
            self._draw_text(draw, label.text, text_top, left, box_w)
        return canvas
