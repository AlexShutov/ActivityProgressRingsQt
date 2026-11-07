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

# Легенда лежит на окружности радиусом ``outer_ring_outer_edge + 0.5 см`` (мм).
# 0.5 см — зазор по радиусу от внешнего края кольца до ближнего (кольцевого) края
# подложки; меньше уже не стоит, чтобы широкая подпись снова не легла на кольца.
RING_LEGEND_RADIUS_CLEARANCE_MM = 5.0
# Отступ от текста до края подложки (мм) — переводится в px через ``px_per_mm``.
# ~2 мм со всех сторон, чтобы жирный кегль «дышал» внутри подложки.
RING_LEGEND_LABEL_PAD_MM = 2.0
# Непрозрачность подложки (~0.5 от 255) — полупрозрачная, чтобы кольца просвечивали.
RING_LEGEND_BACKDROP_ALPHA = 128
# Радиус скругления подложки как доля её ВЫСОТЫ (мягкие углы вместо острых).
RING_LEGEND_BACKDROP_CORNER_FRACTION = 0.25
# Разрешение сканирования «слепой зоны»: число проб на каждый кольцевой сектор.
RING_LEGEND_SECTOR_SCAN_SAMPLES = 96

# Угловой «верх» экранной координатной системы (deg): 270° = up.  Легенда читается
# по часовой стрелке — от верхнего конца дуги к нижнему, поэтому вычисляем, какой из
# концов сектора ближе к «верху», и от него начинаем раскладывать подписи.
_LEGEND_UP_ANGLE_DEG = 270.0

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
    """Позиция одной подписи легенды: подпись, значение, центр (в px) и цвет подложки.

    ``label`` — короткая подпись датчика; ``value`` — строка значения (например
    ``"73%"``); ``text`` — готовый к отрисовке текст ``label: value`` (либо ``label``,
    если значения нет).  Значение хранится отдельно, чтобы ширина зоны значений
    считалась по нему фиксированно и подложка не «прыгала» при изменении числа.
    """

    label: str
    value: str | None = None
    center: tuple[float, float] = (0.0, 0.0)
    color: Color = (255, 255, 255)

    @property
    def text(self) -> str:
        """Отображаемый текст: ``label: value`` (или просто ``label`` без значения)."""
        return f"{self.label}: {self.value}" if self.value else self.label


class CircleLegendLayoutManager:
    """Раскладка и отрисовка круговой легенды колец.

    ``center`` — центр кольцевой группы в координатах целевого канваса; ``radius`` —
    радиус окружности легенды (уже включает ``RING_LEGEND_RADIUS_CLEARANCE_MM``).
    ``view_size`` — размеры канваса (px), за пределы которого подписи не выходят.
    ``font`` — уже настроенный ``PIL.ImageFont`` (тот же, что у линейного индикатора).
    ``text_color``/``backdrop_alpha`` — цвет текста и непрозрачность подложки;
    ``padding_px`` — отступ текста от края подложки; радиус скругления подложки
    рассчитывается ВНУТРИ как доля её высоты (``RING_LEGEND_BACKDROP_CORNER_FRACTION``);
    ``letter_spacing_px`` — межсимвольный трекинг;
    ``text_stroke_px`` — ширина утолщающей обводки глифа («жирность», как у линейного).
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
        letter_spacing_px: float = 0.0,
        text_stroke_px: float = 0.0,
    ) -> None:
        self._center = (float(center[0]), float(center[1]))
        self._radius = float(radius)
        self._view_size = (int(view_size[0]), int(view_size[1]))
        self._placement = placement
        self._font = font
        self._text_color = (int(text_color[0]), int(text_color[1]), int(text_color[2]))
        self._backdrop_alpha = int(backdrop_alpha)
        self._padding_px = float(padding_px)
        self._letter_spacing_px = float(letter_spacing_px)
        self._text_stroke_px = float(text_stroke_px)

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
        """Габарит текста С обводкой: ``(width, height)`` подложки, в которой он лежит.

        Обводка (``text_stroke_px``) расширяет глиф наружу — добавляем её к ширине и
        высоте, чтобы утолщённый (жирный) текст уместился в подложке без обрезки.
        """
        return (
            self._measure_width(text) + self._text_stroke_px,
            self._measure_height(text) + self._text_stroke_px,
        )

    def _value_zone_px(self, values: Sequence[str]) -> float:
        """Фиксированная ширина зоны значения: ``": "`` + максимум среди строк значений.

        Благодаря резерву под значения ширина подложки почти не зависит от текущего
        числа (меняется только при смене числа разрядов самого широкого значения),
        поэтому подпись не «прыгает» при обновлении показателя.
        """
        if not values:
            return 0.0
        separator = self._measure_width(": ")
        widest = max((self._measure_width(value) for value in values if value), default=0.0)
        return separator + widest

    def _box_size(
        self, label: str, value: str | None, value_zone_px: float
    ) -> tuple[float, float]:
        """Габарит подложки ``(width, height)`` для одной подписи.

        Ширина = подпись + зарезервированная зона значения + обводка + 2·паддинг —
        фиксированная, чтобы подложка не менялась при изменении значения.  Высота —
        одна строка (максимум из высот подписи и значения) + обводка + 2·паддинг.
        """
        stroke = self._text_stroke_px
        label_h = self._measure_height(label) + stroke
        height = label_h
        width = self._measure_width(label) + stroke
        if value is not None:
            height = max(height, self._measure_height(value) + stroke)
            width += value_zone_px
        return width + 2.0 * self._padding_px, height + 2.0 * self._padding_px

    def _max_box_size(
        self, labels: Sequence[str], values: Sequence[str] | None
    ) -> tuple[float, float]:
        """Максимальный ``(width, height)`` подложки среди всех подписей (для слепой зоны)."""
        value_zone_px = self._value_zone_px(values) if values else 0.0
        sizes = [
            self._box_size(label, values[index] if values else None, value_zone_px)
            for index, label in enumerate(labels)
        ]
        if not sizes:
            return 0.0, 0.0
        return max(size[0] for size in sizes), max(size[1] for size in sizes)

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
        """Помещается ли подложка ``box_w``×``box_h`` под углом (в границах канваса).

        Подложка пристыкована КОЛЬЦЕВОЙ стороной к полярной точке (см. ``render``):
        для левой дуги растёт влево от неё, для правой — вправо.  Благодаря этому
        даже широкая подпись не заносит внутренний край подложки на кольцевую группу —
        край всегда не дальше полярной точки (радиус ``radius`` > внешнего края колец).
        """
        px, py = self._label_center_at(angle_deg)
        left = px - box_w if px <= self._center[0] else px
        top = py - box_h / 2.0
        return (
            left >= 0.0
            and left + box_w <= self._view_size[0]
            and top >= 0.0
            and top + box_h <= self._view_size[1]
        )

    def _usable_sector(
        self, labels: Sequence[str], values: Sequence[str] | None = None
    ) -> tuple[float, float]:
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
        box_w, box_h = self._max_box_size(labels, values)
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

    def _angular_displacement_to_up(self, angle_deg: float) -> float:
        """Кратчайшее угловое расстояние (в градусах) от ``angle_deg`` до «верха» (270°)."""
        diff = (angle_deg - _LEGEND_UP_ANGLE_DEG) % 360.0
        return min(diff, 360.0 - diff)

    def layout(
        self,
        labels: Sequence[str],
        colors: Sequence[Color],
        values: Sequence[str] | None = None,
    ) -> list[LegendLabel]:
        """Считает позиции подписей: сектор → разбиение на ``count`` частей → полярная точка.

        Каждая подпись попадает в середину своей части углового сектора, на окружность
        ``radius`` вокруг ``center`` (полярные координаты).

        Порядок чтения — по часовой стрелке, сверху вниз: первая подпись (вход —
        ``outer -> inner``, т.е. первая = НАРУЖНОЕ кольцо) кладётся у верхнего конца
        дуги, последняя (внутреннее кольцо) — у нижнего.  Для этого определяем, какой
        из концов сектора ближе к «верху» (270°), и от него ведём раскладку вниз.
        ``values`` — строки значений (параллельно ``labels``), попадают в подпись
        как ``label: value``.
        """
        label_list = list(labels)
        color_list = list(colors)
        if not label_list:
            return []
        value_list = list(values) if values else None
        count = len(label_list)
        sector_start, sector_end = self._usable_sector(label_list, value_list)
        # Свип от верхнего конца дуги к нижнему: если «верх» — это ``start``, идём к
        # ``end`` (direction +1), иначе от ``end`` к ``start`` (direction -1).
        if self._angular_displacement_to_up(sector_start) <= self._angular_displacement_to_up(
            sector_end
        ):
            sweep_from, sweep_direction = sector_start, 1.0
        else:
            sweep_from, sweep_direction = sector_end, -1.0
        step = abs(sector_end - sector_start) / count
        result: list[LegendLabel] = []
        for index in range(count):
            angle = sweep_from + sweep_direction * step * (index + 0.5)
            color = color_list[index] if index < len(color_list) else (
                color_list[0] if color_list else self._text_color
            )
            value = value_list[index] if value_list else None
            result.append(
                LegendLabel(
                    label=label_list[index],
                    value=value,
                    center=self._label_center_at(angle),
                    color=color,
                )
            )
        return result

    # -- Отрисовка ---------------------------------------------------------
    def _draw_text(self, draw, text: str, top: float, start_x: float) -> None:
        """Рисует ``text`` слева направо, начиная с ``start_x`` (трекинг + обводка).

        Выравнивание по левому краю (а не по центру) необходимо, чтобы подпись была
        пристыкована к левому краю подложки с паддингом и не «прыгала» при изменении
        значения: зарезервированная зона значения держит ширину подложки постоянной.
        """
        caret = start_x
        fill = (*self._text_color, 255)
        stroke_width = int(round(self._text_stroke_px))
        if self._letter_spacing_px <= 0 or len(text) <= 1:
            draw.text(
                (caret, top), text, font=self._font, fill=fill,
                stroke_width=stroke_width, stroke_fill=fill,
            )
            return
        for ch in text:
            draw.text(
                (caret, top), ch, font=self._font, fill=fill,
                stroke_width=stroke_width, stroke_fill=fill,
            )
            caret += float(draw.textlength(ch, font=self._font)) + self._letter_spacing_px

    def render(
        self,
        canvas: Image.Image,
        labels: Sequence[str],
        colors: Sequence[Color],
        values: Sequence[str] | None = None,
    ) -> Image.Image:
        """Рисует подложки и текст легенды на ``canvas`` (RGBA) и возвращает его.

        Ширина каждой подложки фиксированная (подпись + зарезервированная зона
        значения), поэтому она не меняется при обновлении числа; текст пристыкован
        к левому краю с паддингом.
        """
        draw = ImageDraw.Draw(canvas)
        positions = self.layout(labels, colors, values)
        value_zone_px = self._value_zone_px(values) if values else 0.0
        for label in positions:
            box_w, box_h = self._box_size(label.label, label.value, value_zone_px)
            # Подложка пристыкована КОЛЬЦЕВОЙ стороной к полярной точке, а не
            # центрирована на ней: для левой дуги правый край = полярная точка и
            # подложка растёт влево (от колец), для правой — наоборот.  Тем самым
            # ширина (лейбл + значение) не заносит край подложки на кольцевую группу.
            left = (
                label.center[0] - box_w
                if label.center[0] <= self._center[0]
                else label.center[0]
            )
            top = label.center[1] - box_h / 2.0
            # Радиус скругления — 0.25 высоты подложки (доля, а не жёсткие px).
            corner = box_h * RING_LEGEND_BACKDROP_CORNER_FRACTION
            glyph_h = self._measure_height(label.text)
            # Центрируем текст по вертикали, а по горизонтали он лево-выровнен.
            text_top = top + (box_h - glyph_h) / 2.0
            draw.rounded_rectangle(
                (left, top, left + box_w, top + box_h),
                radius=corner,
                fill=(*label.color, self._backdrop_alpha),
            )
            self._draw_text(draw, label.text, text_top, left + self._padding_px)
        return canvas
