"""Layout managers for the Activity Rings overlay (MIT).

Mirrors the dashboard adapter layout-manager idea (:mod:`adapter.layout`): a base
class holds the shared configuration (outer-radius fraction, edge margin, dynamic
gap) and two subclasses implement the two modes selected by the class attribute
:attr:`BaseRingsLayoutManager.is_selection_enabled`:

- ``StaticRingsLayoutManager`` (``is_selection_enabled=False``): every ring shares the
  same thickness; radii come from ``rings_focus.layout`` with the dynamic gap.  All
  rings sit inside the panel with ``edge_margin`` to the outer edge.
- ``SelectionRingsLayoutManager`` (``is_selection_enabled=True``): rings keep a
  CONSTANT thickness (no growth on selection — the old width increase shrank
  neighbours and looked bad); the flag only tells the renderer to highlight the
  active ring and dim the rest.  Radii also come from ``layout()``, so the constant
  band-edge gap is preserved at every frame.

The outermost band's OUTER edge is anchored at ``outer_radius``, which is clamped so
it keeps ``edge_margin`` (~2 mm) to the panel edge.  ``FocusTimeline`` computes the
per-ring eased ``focus`` factors; a layout manager turns those factors into the final
{radius, width} geometry.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .rings_focus import BASE_RINGS, RingBase, layout


@dataclass(frozen=True)
class RingGrowthPlan:
    """План роста колец: per-ring ``scales`` и эффективный ``gap``.

    Сейчас рост отключён (кольца не меняют толщину при выделении), поэтому все
    ``scales`` равны ``1.0``; ``gap`` — зазор между краями соседних колец.
    """

    scales: list[float]
    gap: float


@dataclass(frozen=True)
class RingGeometry:
    """A single ring band: centerline ``radius``, ``width`` and its visual metadata."""

    key: str
    label: str
    radius: float
    width: float
    color: tuple[int, int, int]
    target: float
    start_angle: float
    backdrop_alpha: int = 38
    shadow: bool = True


@dataclass(frozen=True)
class RingsLayoutResult:
    """Measured layout: per-ring geometry plus the anchored outer radius and gap."""

    geometry: Sequence[RingGeometry]
    outer_radius: float
    gap: float

    def __getitem__(self, index: int) -> RingGeometry:
        return self.geometry[index]

    def __len__(self) -> int:
        return len(self.geometry)


class BaseRingsLayoutManager:
    """Shared config + dynamic gap; subclasses implement ``measure``."""

    is_selection_enabled: bool = False

    def __init__(
        self,
        *,
        outer_fraction: float = 0.84,
        edge_margin: float = 14.0,
        gap_min: float = 8.0,
        gap_max: float = 28.0,
        gap_ratio: float = 0.2,
        min_slot: float = 8.0,
        ring_bases: Sequence[RingBase] = BASE_RINGS,
        backdrop_alpha: int = 38,
        ring_gap_px: float | None = None,
        inner_radius: float | None = None,
    ) -> None:
        self._outer_fraction = outer_fraction
        self._edge_margin = edge_margin
        self._gap_min = gap_min
        self._gap_max = gap_max
        self._gap_ratio = gap_ratio
        self._min_slot = min_slot
        self._ring_bases = list(ring_bases)
        self._backdrop_alpha = backdrop_alpha
        # Фиксированный зазор между краями соседних колец (px). ``None`` → выводится
        # из ``gap_for`` (динамический зазор). Задаётся явно, когда нужен точный
        # «~1мм» между кольцами (см. ``render_gauge_rings``/композит).
        self._ring_gap_px = ring_gap_px
        # Радиус внутренней границы САМОГО внутреннего (малого) кольца (px).
        # ``None`` → кольца занимают внешнюю полосу (``GAUGE_BAND_DEPTH_FRACTION``);
        # задаётся явно (напр. 5мм), чтобы кольца были толстыми и почти на весь круг.
        self._inner_radius = inner_radius

    @property
    def outer_fraction(self) -> float:
        return self._outer_fraction

    @property
    def edge_margin(self) -> float:
        return self._edge_margin

    @property
    def gap_min(self) -> float:
        return self._gap_min

    @property
    def gap_max(self) -> float:
        return self._gap_max

    def outer_radius(self, short_side: float) -> float:
        """Anchor radius for the outermost band's OUTER edge, keeping ``edge_margin``.

        Capped at ``short_side/2 - edge_margin`` so the outermost band never touches
        the panel edge, whether or not the outermost ring is selected.
        """
        return min(
            short_side / 2.0 * self._outer_fraction,
            short_side / 2.0 - self._edge_margin,
        )

    def gap_for(self, short_side: float, count: int) -> float:
        """Dynamic gap between bands, scaled from the slot (count + screen size)."""
        if count <= 1:
            return 0.0
        slot = short_side / max(1, count)
        gap = slot * self._gap_ratio
        return min(self._gap_max, max(self._gap_min, gap))

    def _resolve_gap(self, short_side: float, count: int, base: float) -> float:
        """Collapse the gap to zero rather than let thin bands crowd the center."""
        if self._ring_gap_px is not None:
            return self._ring_gap_px
        gap = self.gap_for(short_side, count)
        if base < self._min_slot and count > 1:
            gap = 0.0
        return gap

    def base_widths(self, outer_r: float) -> list[float]:
        """Per-ring band width at 1x focus (fraction of the anchor radius)."""
        return [base.width_frac * outer_r for base in self._ring_bases]

    def _measure(
        self, short_side: float, count: int, focus: Sequence[float] | None
    ) -> RingsLayoutResult:
        """Shared geometry path for both subclasses.

        ``base`` — базовые толщины колец; ``plan`` от стратегии выделения даёт
        per-ring ``scales`` (рост) и эффективный ``gap``; радиусы приходят из
        ``rings_focus.layout`` (outer-edge anchored, constant edge gap).
        """
        ring_bases = self._ring_bases[:count]
        outer_r = self.outer_radius(short_side)
        f = list(focus) if focus is not None else [0.0] * count
        if self._inner_radius is not None:
            # Заполняем радиальный диапазон [inner_radius, outer_r] кольцами равной
            # толщины (внутреннее кольцо начинается на ``inner_radius``).
            design_gap = self._resolve_gap(short_side, count, 0.0)
            span = outer_r - self._inner_radius
            band_sum = max(0.0, span - design_gap * (count - 1))
            per = band_sum / max(1, count)
            base = [per] * count
        else:
            base = self.base_widths(outer_r)[:count]
            design_gap = self._resolve_gap(short_side, count, min(base) if base else 0.0)
        plan = self._growth_plan(base, f, design_gap, outer_r, count)
        widths = [b * plan.scales[i] for i, b in enumerate(base)]
        radii = layout(widths, plan.gap, outer_r)
        geometry = tuple(
            RingGeometry(
                base.key,
                base.label,
                radii[i],
                widths[i],
                base.color,
                base.target,
                base.start_angle,
                backdrop_alpha=self._backdrop_alpha,
                shadow=True,
            )
            for i, base in enumerate(ring_bases)
        )
        return RingsLayoutResult(geometry, outer_r, plan.gap)

    def _growth_plan(
        self,
        base: Sequence[float],
        focus: Sequence[float],
        design_gap: float,
        outer_r: float,
        count: int,
    ) -> RingGrowthPlan:
        """План роста: статичный режим не растёт и держит ``design_gap``."""
        return RingGrowthPlan(scales=[1.0] * count, gap=design_gap)

    def _widths(self, outer_r: float, count: int, focus: Sequence[float] | None) -> list[float]:
        raise NotImplementedError

    def measure(
        self,
        short_side: float,
        count: int | None = None,
        focus: Sequence[float] | None = None,
    ) -> RingsLayoutResult:
        n = len(self._ring_bases) if count is None else int(count)
        if n <= 0:
            return RingsLayoutResult((), self.outer_radius(short_side), 0.0)
        return self._measure(short_side, n, focus)


class StaticRingsLayoutManager(BaseRingsLayoutManager):
    """Equal-thickness rings; the stack fills the panel within the margins."""

    is_selection_enabled = False

    def _widths(self, outer_r: float, count: int, focus: Sequence[float] | None) -> list[float]:
        return self.base_widths(outer_r)[:count]


class SelectionRingsLayoutManager(BaseRingsLayoutManager):
    """Кольца НЕ меняют толщину при выделении; флаг включает подсветку/затемнение.

    Рост убран (увеличение толщины выделенного кольца сжимало соседей и выглядело
    плохо) — все кольца держат постоянную толщину, как в статичной раскладке.  Зато
    ``is_selection_enabled = True``, чтобы рендерер подсвечивал активное кольцо и
    затемнял остальные.  Конструктор базового класса уже даёт постоянные ``scales``
    в ``_growth_plan``, поэтому переопределять его не нужно.
    """

    is_selection_enabled = True
