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
from common.easing import ease_out_cubic, lerp, lerp_color

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


def build_rings(
    outer_radius: float,
    width: float,
    targets: dict[str, float] | None = None,
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
        **render_kwargs,
    )


def _pt(center_x: float, center_y: float, radius: float, angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return center_x + radius * math.cos(rad), center_y + radius * math.sin(rad)


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
    caps: bool = True,
) -> None:
    """Draw a swept ring band (gradient) with cap dots centered on the band.

    The band spans ``[radius - width/2, radius + width/2]`` so the centerline is exactly
    ``radius``; cap dots are circles of radius ``width/2`` drawn at that same radius, so
    they sit centered on the band (never poke out).
    """
    from PIL import ImageDraw

    draw = ImageDraw.Draw(layer)
    sweep = 360.0 * max(0.0, min(frac, 1.0))
    if sweep <= 0:
        return
    radius_inner = radius - width / 2.0
    radius_outer = radius + width / 2.0
    end_angle = start_angle + sweep
    for i in range(segs):
        segment_frac = (i + 0.5) / segs
        angle_start = lerp(start_angle, end_angle, i / segs)
        angle_end = lerp(start_angle, end_angle, (i + 1) / segs) + 0.5  # overlap avoids seams
        col = lerp_color(color_start, color_end, segment_frac) + (alpha,)
        draw.polygon(
            _annulus(center_x, center_y, radius_inner, radius_outer, angle_start, angle_end),
            fill=col,
        )
    if caps:
        cap_radius = width / 2.0
        for angle_deg, cap_col in ((start_angle, color_start), (end_angle, color_end)):
            px, py = _pt(center_x, center_y, radius, angle_deg)
            draw.ellipse(
                [px - cap_radius, py - cap_radius, px + cap_radius, py + cap_radius],
                fill=cap_col + (alpha,),
            )


def _draw_backdrop(
    layer: Image.Image,
    center_x: float,
    center_y: float,
    radius: float,
    width: float,
    color: Color,
    alpha: int,
) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(layer)
    radius_inner = radius - width / 2.0
    radius_outer = radius + width / 2.0
    draw.polygon(
        _annulus(center_x, center_y, radius_inner, radius_outer, 0, 360, samples=64),
        fill=color + (alpha,),
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
    """
    w, h = size
    cx, cy = (w / 2.0, h / 2.0) if center is None else center
    radius = (min(w, h) / 2.0 * 0.84) if outer_radius is None else outer_radius

    canvas_w = int(w * ss)
    canvas_h = int(h * ss)
    drawer = IndicatorBackgroundDrawer(transparent=transparent)
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
            )
            for g in result.geometry
        ]
    else:
        rings = build_rings(radius * ss, radius * 0.18 * ss, targets or _DEFAULT_TARGETS)

    for spec in rings:
        r = spec.radius
        width = spec.width
        frac = float(progress.get(spec.key, spec.target) if progress else spec.target)
        frac = max(0.0, frac)

        if spec.backdrop_alpha:
            _draw_backdrop(img, px, py, r, width, spec.color, spec.backdrop_alpha)

        sil = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        _draw_arc_segments(
            sil, px, py, r, width, frac, spec.color, spec.color, spec.start_angle, segs
        )

        if spec.shadow:
            off = shadow_offset * ss
            sh = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            sh.paste((0, 0, 0, 120), (int(off), int(off)), sil)
            sh = sh.filter(ImageFilter.GaussianBlur(shadow_softness * ss))
            img.alpha_composite(sh)

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

