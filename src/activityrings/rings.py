"""Apple-style Activity Rings: three concentric, eased, shadowed rings (MIT).

Headless raster over Pillow (no Qt / no window). The core is resolution-independent:
you give it a rectangular canvas, an explicit ``center`` and an ``outer_radius``, and
it draws the rings. That makes the SAME renderer usable for:

- the embedded 1920x440 panel overlay (render an RGB frame, trcc composites/encodes), and
- a full-size HDMI screen (live fullscreen loop, same frames, just a bigger canvas).

Animation is pure Python state (easing) + per-frame redraw, so it works identically
on a Pi without a GUI. Use ``eased_progress_map``/``render_sequence`` to drive a live
loop and ``render_rings`` for a single frame.

Rendering primitives:
- supersampled canvas + LANCZOS downsample for smooth (anti-aliased) ring edges;
- per-ring soft drop shadow (blurred silhouette, offset below);
- optional low-alpha backdrop ring (Apple's 15% track);
- sweep along a gradient start->end colour, with rounded end caps.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageFilter

from common.background import IndicatorBackgroundDrawer
from common.easing import ease_out_cubic, lerp

from .rings_focus import RingBase
from .rings_layout import BaseRingsLayoutManager, SelectionRingsLayoutManager

Color = tuple[int, int, int]

_DEFAULT_COLORS: dict[str, Color] = {
    "move": (250, 55, 95),  # red
    "exercise": (145, 221, 82),  # green
    "stand": (56, 181, 240),  # blue
}

_DEFAULT_TARGETS: dict[str, float] = {"move": 0.72, "exercise": 0.86, "stand": 0.55}

# Глубина (по радиусу) всей группы «кольцо на датчик» как доля ``outer_radius``:
# толщина одного кольца = ``GAUGE_BAND_DEPTH_FRACTION`` / число датчиков.
GAUGE_BAND_DEPTH_FRACTION = 0.4

# Выделение колец — собственная простая логика: подсвечивается ОДНО активное кольцо,
# остальные гаснут.  Актива — кольцо с ``focus > RING_ACTIVE_EPSILON``; невыделенные
# гаснут до ``RING_DIM_MIN``.  Здесь не считается число выбранных колец (в отличие от
# общего ``common.selection``, которым пользуется линейный индикатор).
RING_ACTIVE_EPSILON = 1e-6
RING_DIM_MIN = 0.35
# Параметры ореола вокруг активного кольца: размытие (px при 1x) и альфа дуги.
# Ореол рисуется КАК САМ СЕКТОР (начало+конец+бока), цветом кольца (цвет столбца
# палитры), без увеличения ширины — «весь сектор светится», а не только бока.
GLOW_SOFTNESS = 9.0
GLOW_ALPHA = 150

# Точки на одну дугу скругления конца сектора (чем больше — тем глаже филет).
CORNER_SAMPLES = 8


@dataclass(frozen=True)
class RingSpec:
    key: str
    label: str
    radius: float  # at 1x scale
    width: float  # at 1x scale
    color: Color = _DEFAULT_COLORS["move"]
    target: float = 1.0
    start_angle: float = -90.0  # 12 o'clock
    backdrop_alpha: int = 38  # ~15% track
    shadow: bool = True
    # Скругление концов сектора как ДОЛЯ толщины (0..0.5): ``start_corner_fraction``
    # — начало сектора, ``end_corner_fraction`` — конец.  0.5 → круглый конец капсулы,
    # 0 → плоская (радиальная) кромка.
    start_corner_fraction: float = 0.5
    end_corner_fraction: float = 0.5


def build_rings(
    outer_radius: float,
    width: float,
    targets: dict[str, float] | None = None,
    *,
    start_corner_fraction: float = 0.5,
    end_corner_fraction: float = 0.5,
) -> list[RingSpec]:
    """Three concentric rings from the outer radius inward (outer -> inner)."""
    targets = targets or _DEFAULT_TARGETS
    gap = outer_radius * 0.26
    specs = [
        RingSpec("move", "Move", outer_radius, width, _DEFAULT_COLORS["move"]),
        RingSpec("exercise", "Exercise", outer_radius - gap, width, _DEFAULT_COLORS["exercise"]),
        RingSpec("stand", "Stand", outer_radius - 2 * gap, width, _DEFAULT_COLORS["stand"]),
    ]
    return [
        RingSpec(
            key=spec.key,
            label=spec.label,
            radius=spec.radius,
            width=spec.width,
            color=spec.color,
            target=targets.get(spec.key, spec.target),
            start_angle=spec.start_angle,
            backdrop_alpha=spec.backdrop_alpha,
            shadow=spec.shadow,
            start_corner_fraction=start_corner_fraction,
            end_corner_fraction=end_corner_fraction,
        )
        for spec in specs
    ]


def gauge_ring_bases(
    gauges: Sequence[tuple[str, str, Color, float]],
    *,
    width_frac: float | None = None,
) -> list[RingBase]:
    """Строит концентрические кольца «кольцо на датчик» из описаний датчиков.

    ``gauges`` — последовательность ``(key, label, color, target)`` (целевая доля
    заполнения, обычно ``0..1``); одно кольцо на датчик, от внешнего к внутреннему.
    ``width_frac`` — толщина каждого кольца как доля ``outer_radius``; ``None`` —
    выводится из числа датчиков, чтобы вся группа колец заняла ``GAUGE_BAND_DEPTH``
    радиуса (для большого числа датчиков кольца становятся тоньше).
    """
    count = len(gauges)
    frac = _gauge_width_frac(count) if width_frac is None else max(0.0, float(width_frac))
    return [
        RingBase(
            key=str(key),
            label=str(label),
            color=color,
            width_frac=frac,
            target=float(target),
        )
        for key, label, color, target in gauges
    ]


def _gauge_width_frac(count: int) -> float:
    """Толщина одного кольца при ``count`` датчиках (доля ``outer_radius``)."""
    return float(GAUGE_BAND_DEPTH_FRACTION) / max(1, int(count))


def render_gauge_rings(
    gauges: Sequence[tuple[str, str, Color, float]],
    size: tuple[int, int],
    *,
    progress: dict[str, float] | None = None,
    focus: Sequence[float] | None = None,
    layout_manager: BaseRingsLayoutManager | None = None,
    outer_fraction: float = 0.84,
    edge_margin: float = 14.0,
    gap_px: float | None = None,
    inner_radius_px: float | None = None,
    track_color: Color | None = None,
    start_corner_fraction: float = 0.5,
    end_corner_fraction: float = 0.5,
    **render_kwargs,
) -> Image.Image:
    """Рендерит кадр «кольцо на датчик» (``gauges``) через ``render_rings``.

    Если ``layout_manager`` не задан, создаётся ``SelectionRingsLayoutManager`` с
    кольцами из ``gauges`` (выделение — strategя выбора колец). ``progress`` — доля
    заполнения на каждый ``key`` (``0..~2``); ``focus`` — per-ring факторы выбора.
    ``outer_fraction``/``edge_margin`` управляют размером колец (см.
    ``BaseRingsLayoutManager``): ``outer_fraction`` близко к 1 — кольца заполняют
    зону почти целиком, ``edge_margin`` — отступ от края зоны (px). ``gap_px`` —
    фиксированный зазор между краями соседних колец (px); ``None`` → динамический.
    ``inner_radius_px`` — радиус внутренней границы самого внутреннего кольца
    (px); ``None`` → кольца в узкой внешней полосе, задаётся явно (напр. 5мм),
    чтобы кольца были толстыми и почти на весь круг.
    """
    bases = gauge_ring_bases(gauges)
    manager = layout_manager
    if manager is None:
        manager = SelectionRingsLayoutManager(
            ring_bases=bases,
            outer_fraction=outer_fraction,
            edge_margin=edge_margin,
            ring_gap_px=gap_px,
            inner_radius=inner_radius_px,
        )
    return render_rings(
        progress=progress,
        size=size,
        layout_manager=manager,
        focus=focus,
        transparent=True,
        track_color=track_color,
        start_corner_fraction=start_corner_fraction,
        end_corner_fraction=end_corner_fraction,
        **render_kwargs,
    )


def _annulus(
    center_x: float,
    center_y: float,
    radius_inner: float,
    radius_outer: float,
    angle_start: float,
    angle_end: float,
    samples: int = 6,
) -> list[tuple[float, float]]:
    """Polygon points for an annulus sector between two radii (outer then inner)."""
    points: list[tuple[float, float]] = []
    for i in range(samples + 1):
        angle_deg = lerp(angle_start, angle_end, i / samples)
        rad = math.radians(angle_deg)
        points.append(
            (center_x + radius_outer * math.cos(rad), center_y + radius_outer * math.sin(rad))
        )
    for i in range(samples + 1):
        angle_deg = lerp(angle_start, angle_end, 1.0 - i / samples)
        rad = math.radians(angle_deg)
        points.append(
            (center_x + radius_inner * math.cos(rad), center_y + radius_inner * math.sin(rad))
        )
    return points


def _point_at_angle(
    center_x: float, center_y: float, radius: float, angle_rad: float
) -> tuple[float, float]:
    """Точка на окружности ``radius`` вокруг ``(center_x, center_y)`` под углом (рад)."""
    return (
        center_x + radius * math.cos(angle_rad),
        center_y + radius * math.sin(angle_rad),
    )


def _arc_points(
    center_x: float,
    center_y: float,
    radius: float,
    a_start: float,
    a_end: float,
    samples: int,
) -> list[tuple[float, float]]:
    """Точки дуги радиуса ``radius`` от ``a_start`` до ``a_end`` (рад)."""
    return [
        _point_at_angle(center_x, center_y, radius, lerp(a_start, a_end, i / samples))
        for i in range(samples + 1)
    ]


def _fillet_arc_points(
    center_radius: float,
    center_angle: float,
    corner_radius: float,
    p_boundary: tuple[float, float],
    p_line: tuple[float, float],
    center_x: float,
    center_y: float,
    samples: int,
) -> list[tuple[float, float]]:
    """Дуга скругления между границей полосы и радиальной кромкой конца сектора.

    Центр филета лежит на радиусе ``center_radius`` под углом ``center_angle`` (от
    центра полосы); ``p_boundary``/``p_line`` — точки касания с границей и кромкой.
    Возвращает точки короткой дуги от ``p_boundary`` к ``p_line``.
    """
    center_x_fillet = center_x + center_radius * math.cos(center_angle)
    center_y_fillet = center_y + center_radius * math.sin(center_angle)
    phi_boundary = math.atan2(p_boundary[1] - center_y_fillet, p_boundary[0] - center_x_fillet)
    phi_line = math.atan2(p_line[1] - center_y_fillet, p_line[0] - center_x_fillet)
    sweep = (phi_line - phi_boundary + math.pi) % (2.0 * math.pi) - math.pi
    return [
        (
            center_x_fillet + corner_radius * math.cos(phi_boundary + sweep * i / samples),
            center_y_fillet + corner_radius * math.sin(phi_boundary + sweep * i / samples),
        )
        for i in range(samples + 1)
    ]


def _rounded_band_points(
    center_x: float,
    center_y: float,
    radius: float,
    width: float,
    sweep_deg: float,
    start_deg: float,
    start_corner_fraction: float,
    end_corner_fraction: float,
    corner_samples: int = CORNER_SAMPLES,
) -> list[tuple[float, float]]:
    """Контур кольцевой полосы со скруглёнными концами сектора.

    Полоса лежит в ``[radius - width/2, radius + width/2]`` (центр — ``radius``).
    Концы скругляются как ДОЛЯ толщины (0..0.5): ``start_corner_fraction`` — угол
    ``start_deg`` (начало сектора), ``end_corner_fraction`` — конец.  При 0.5 оба
    филета сливаются в круглый конец-капсулу, при 0 — плоские радиальные кромки.
    Возвращает упорядоченные точки контура (Pillow ``draw.polygon``).
    """
    radius_inner = radius - width / 2.0
    radius_outer = radius + width / 2.0
    th0 = math.radians(start_deg)
    th1 = th0 + math.radians(sweep_deg)
    start_corner = min(max(0.0, start_corner_fraction), 0.5) * width
    end_corner = min(max(0.0, end_corner_fraction), 0.5) * width

    def corner(boundary_radius: float, corner_width: float, line_angle: float, at_start: bool):
        """Точки касания скругления границы ``boundary_radius`` и кромки ``line_angle``.

        Возвращает ``(boundary_angle, line_radius, centre_radius)``: угол касания на
        границе, радиус касания на кромке и радиус центра филета.  При ``corner_width``
        <= 0 угла нет — граница встречает кромку в ``boundary_radius``.
        """
        if corner_width <= 1e-9:
            return line_angle, boundary_radius, boundary_radius
        if boundary_radius >= radius:
            centre_radius = boundary_radius - corner_width
        else:
            centre_radius = boundary_radius + corner_width
        if centre_radius <= 1e-9:
            # Патологический случай (толщина больше радиуса): филет вырождается —
            # возвращаем плоскую кромку, как для corner_width <= 0.
            return line_angle, boundary_radius, boundary_radius
        delta = math.asin(min(1.0, max(0.0, corner_width / centre_radius)))
        boundary_angle = line_angle + (delta if at_start else -delta)
        return boundary_angle, centre_radius * math.cos(delta), centre_radius

    start_outer = corner(radius_outer, start_corner, th0, True)
    end_outer = corner(radius_outer, end_corner, th1, False)
    start_inner = corner(radius_inner, start_corner, th0, True)
    end_inner = corner(radius_inner, end_corner, th1, False)

    arc_samples = max(corner_samples, int(abs(sweep_deg) / 3.0))
    points = _arc_points(
        center_x, center_y, radius_outer, start_outer[0], end_outer[0], arc_samples,
    )
    if end_corner > 0:
        points += _fillet_arc_points(
            end_outer[2], end_outer[0], end_corner,
            _point_at_angle(center_x, center_y, radius_outer, end_outer[0]),
            _point_at_angle(center_x, center_y, end_outer[1], th1),
            center_x, center_y, corner_samples,
        )
    points.append(_point_at_angle(center_x, center_y, end_inner[1], th1))
    if end_corner > 0:
        points += _fillet_arc_points(
            end_inner[2], end_inner[0], end_corner,
            _point_at_angle(center_x, center_y, end_inner[1], th1),
            _point_at_angle(center_x, center_y, radius_inner, end_inner[0]),
            center_x, center_y, corner_samples,
        )
    points += _arc_points(
        center_x, center_y, radius_inner, end_inner[0], start_inner[0], arc_samples,
    )
    if start_corner > 0:
        points += _fillet_arc_points(
            start_inner[2], start_inner[0], start_corner,
            _point_at_angle(center_x, center_y, radius_inner, start_inner[0]),
            _point_at_angle(center_x, center_y, start_inner[1], th0),
            center_x, center_y, corner_samples,
        )
    points.append(_point_at_angle(center_x, center_y, start_outer[1], th0))
    if start_corner > 0:
        points += _fillet_arc_points(
            start_outer[2], start_outer[0], start_corner,
            _point_at_angle(center_x, center_y, start_outer[1], th0),
            _point_at_angle(center_x, center_y, radius_outer, start_outer[0]),
            center_x, center_y, corner_samples,
        )
    return points


def _draw_arc_segments(
    layer: Image.Image,
    center_x: float,
    center_y: float,
    radius: float,  # stroke CENTERLINE radius
    width: float,
    frac: float,
    color_start: Color,
    color_end: Color,
    start_angle: float,
    segs: int,
    alpha: int = 255,
    *,
    start_corner_fraction: float = 0.5,
    end_corner_fraction: float = 0.5,
) -> None:
    """Рисует кольцевую полосу с настраиваемым скруглением концов сектора.

    Полоса лежит в ``[radius - width/2, radius + width/2]`` (центральная линия —
    ``radius``).  ``start_corner_fraction``/``end_corner_fraction`` — скругление
    начала и конца сектора как доля толщины (0..0.5); 0.5 → круглый конец, 0 →
    плоская кромка.  ``segs`` сохраняется для совместимости API и задаёт сглаживание
    (число точек на дугу).  ``color_end`` резервирован под градиент; в текущих
    вызовах начало и конец одного цвета.
    """
    from PIL import ImageDraw

    draw = ImageDraw.Draw(layer)
    sweep = 360.0 * max(0.0, min(frac, 1.0))
    if sweep <= 0:
        return
    points = _rounded_band_points(
        center_x, center_y, radius, width, sweep, start_angle,
        start_corner_fraction, end_corner_fraction,
        corner_samples=max(3, int(segs / 8)),
    )
    draw.polygon(points, fill=color_start + (alpha,))


def _draw_backdrop(
    layer: Image.Image,
    center_x: float,
    center_y: float,
    radius: float,
    width: float,
    backdrop_color: tuple[int, int, int, int],
) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(layer)
    radius_inner = radius - width / 2.0
    radius_outer = radius + width / 2.0
    draw.polygon(
        _annulus(center_x, center_y, radius_inner, radius_outer, 0, 360, samples=64),
        fill=backdrop_color,
    )


def render_rings(
    progress: dict[str, float] | None = None,
    size: tuple[int, int] = (720, 720),
    *,
    center: tuple[float, float] | None = None,
    outer_radius: float | None = None,
    ss: int = 2,
    shadow_softness: float = 6.0,
    shadow_offset: float = 5.0,
    segs: int = 90,
    targets: dict[str, float] | None = None,
    layout_manager: BaseRingsLayoutManager | None = None,
    focus: Sequence[float] | None = None,
    transparent: bool = False,
    track_color: Color | None = None,
    start_corner_fraction: float = 0.5,
    end_corner_fraction: float = 0.5,
) -> Image.Image:
    """Render one frame of the three Activity Rings.

    ``progress`` maps ring key -> sweep fraction (0..~2, >1 wraps). When omitted it
    falls back to ``targets`` (default proportions). ``size`` may be any rectangle so
    the same renderer feeds a wide HDMI screen or a square preview; ``center`` defaults
    to canvas middle and ``outer_radius`` to 42% of the shorter side.

    Pass ``layout_manager`` (a :mod:`activityrings.rings_layout` manager) to drive the
    ring geometry from a layout manager; ``focus`` then holds the per-ring focus factors
    (0..1).  Its ``is_selection_enabled`` flag decides whether the focused ring grows in
    thickness (selection) or all rings keep their width (static).  Without a manager the
    existing fixed-geometry ``build_rings`` path is used, so behaviour is unchanged.

    ``transparent`` returns an RGBA overlay (transparent canvas) so the caller can
    alpha-composite the rings over a live theme; by default the frame is opaque RGB with
    a solid dark backdrop (standalone use).

    ``track_color`` — единый нейтральный цвет подложки (заднего фона) всех колец.
    По умолчанию (``None``) это сам ``DEFAULT_BACKGROUND``: фон каждого кольца — «более
    прозрачная версия фона», а не цвет самого кольца, поэтому фоны не разноцветные.
    Композит передаёт сюда ``palette["muted"]``, чтобы цвет трека совпадал с
    подложкой линейного индикатора.
    """
    w, h = size
    cx, cy = (w / 2.0, h / 2.0) if center is None else center
    radius = (min(w, h) / 2.0 * 0.84) if outer_radius is None else outer_radius

    canvas_w = int(w * ss)
    canvas_h = int(h * ss)
    drawer = IndicatorBackgroundDrawer(track_color, transparent=transparent)
    img = Image.new("RGBA", (canvas_w, canvas_h), drawer.rgba)
    px, py = cx * ss, cy * ss
    if layout_manager is not None:
        result = layout_manager.measure(min(w, h), None, focus)
        rings = [
            RingSpec(
                key=g.key,
                label=g.label,
                radius=g.radius * ss,
                width=g.width * ss,
                color=g.color,
                target=g.target,
                start_angle=g.start_angle,
                backdrop_alpha=g.backdrop_alpha,
                shadow=g.shadow,
                start_corner_fraction=start_corner_fraction,
                end_corner_fraction=end_corner_fraction,
            )
            for g in result.geometry
        ]
    else:
        rings = build_rings(
            radius * ss, radius * 0.18 * ss, targets or _DEFAULT_TARGETS,
            start_corner_fraction=start_corner_fraction,
            end_corner_fraction=end_corner_fraction,
        )

    # Выделение колец — своя простая логика: активное кольцо (``focus`` > порога)
    # светится цветом СВОЕГО сектора, остальные гаснут.  Число выбранных не считаем
    # и толщину не меняем (постоянная ширина у всех колец).
    focus_values: list[float] = list(focus) if focus is not None else []
    selection_on = bool(
        focus_values and layout_manager is not None and layout_manager.is_selection_enabled
    )

    for index, spec in enumerate(rings):
        r = spec.radius
        width = spec.width
        frac = float(progress.get(spec.key, spec.target) if progress else spec.target)
        frac = max(0.0, frac)

        if spec.backdrop_alpha:
            _draw_backdrop(
                img, px, py, r, width, drawer.backdrop(spec.backdrop_alpha)
            )

        ring_focus = (
            focus_values[index] if (selection_on and index < len(focus_values)) else 0.0
        )
        dim = (
            RING_DIM_MIN + (1.0 - RING_DIM_MIN) * ring_focus if selection_on else 1.0
        )
        arc_alpha = int(round(255.0 * dim))

        sil = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        _draw_arc_segments(
            sil, px, py, r, width, frac, spec.color, spec.color, spec.start_angle, segs,
            alpha=arc_alpha,
            start_corner_fraction=spec.start_corner_fraction,
            end_corner_fraction=spec.end_corner_fraction,
        )

        if spec.shadow:
            off = shadow_offset * ss
            sh = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            sh.paste((0, 0, 0, 120), (int(off), int(off)), sil)
            sh = sh.filter(ImageFilter.GaussianBlur(shadow_softness * ss))
            img.alpha_composite(sh)

        if selection_on and ring_focus > RING_ACTIVE_EPSILON:
            # Ореол = САМ сектор (полная ширина, скруглённые концы) в цвете кольца,
            # размытый позади чёткой дуги: светится весь сектор — и бока, и начало,
            # и конец.  Альфа следует за фокусом, поэтому при «пропуске» плавно гаснет.
            glow_alpha = int(round(GLOW_ALPHA * min(1.0, ring_focus)))
            glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            _draw_arc_segments(
                glow, px, py, r, width, frac,
                spec.color, spec.color, spec.start_angle, segs, alpha=glow_alpha,
                start_corner_fraction=spec.start_corner_fraction,
                end_corner_fraction=spec.end_corner_fraction,
            )
            img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(GLOW_SOFTNESS * ss)))

        img.alpha_composite(sil)

    resized = img.resize((w, h), Image.Resampling.LANCZOS)
    return resized if transparent else resized.convert("RGB")


def eased_progress_map(
    targets: dict[str, float],
    t: float,
    *,
    duration: float = 1.0,
    stagger: float = 0.18,
) -> dict[str, float]:
    """Per-ring eased sweep fraction at global time ``t`` (0..``duration``+stagger).

    Rings start staggered (move, then exercise, then stand) and ease out, giving the
    Apple-style cascade. Values >1 (e.g. move at 2x) still wrap.
    """
    out: dict[str, float] = {}
    order = list(targets)
    for i, key in enumerate(order):
        local = (t - i * stagger) / duration
        # ease_out_cubic already clamps, so local<0 -> 0 and local>1 -> 1.
        eased = ease_out_cubic(local)
        out[key] = targets[key] * eased
    return out


def render_sequence(
    targets: dict[str, float] | None = None,
    *,
    size: tuple[int, int] = (720, 720),
    seconds: float = 1.6,
    fps: int = 30,
    **kw,
) -> list[Image.Image]:
    """Pre-render an eased animation as a list of frames (for a GIF / live loop)."""
    targets = targets or _DEFAULT_TARGETS
    total = int(seconds * fps) + 1
    frames: list[Image.Image] = []
    for n in range(total):
        t = n / fps
        prog = eased_progress_map(targets, t, duration=seconds, stagger=0.18)
        frames.append(render_rings(progress=prog, size=size, **kw))
    return frames

