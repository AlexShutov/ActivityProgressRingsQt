"""Qt-rendered Activity-Rings overlay preview with focus-shifting (PySide6, offscreen).

A concrete ``RingItem`` (``QGraphicsItem``) paints the three concentric rings with a
``QConicalGradient`` pen, ``RoundCap`` end caps and a soft ``QGraphicsDropShadowEffect``.
A focused ring gets a glowing LED-strip line hugging its swept band — the outline itself —
with a soft colour glow (``QGraphicsDropShadowEffect``) that also snaps to the ring's
outline colour instead of tinting the whole background. Green by default via
``DEFAULT_FOCUS_COLOR``, faded with each ring's focus level and tracking the ring through
the focus animation; the color is overridable via the ``focus_color`` argument on
``build_focus_rings`` / ``render``.
``radius`` and ``width`` are PySide6 ``Property`` (float) so they can be animated; the
focus transition is NOT driven by live timers — frames are computed deterministically from
the pure ``activityrings.rings_focus`` timeline and rendered via ``QGraphicsScene`` to
``QImage``, so the same code drives a live view and an offscreen video.

Run (default = focus demo):  .venv-trcc/bin/python tools/qrings_preview.py
Run (original sweep):        .venv-trcc/bin/python tools/qrings_preview.py --sweep
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from PySide6.QtCore import Property, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from activityrings.rings_focus import (  # noqa: E402
    BASE_RINGS,
    FOCUS_SCALE,
    GAP_FRACTION,
    TRANSITION_S,
    FocusTimeline,
    default_schedule,
    layout,
    progress_track,
    seed_progress_targets,
)

OUT = REPO / "docs" / "rings_focus"
SIZE = 760
OUTER_R = SIZE * 0.4575
FPS = 24
PRE_ROLL = 0.5
DURATION = 16.0
PERIOD = 5.0
HOLD = 2.0
DEFAULT_FOCUS_COLOR: tuple[int, int, int] = (0, 200, 90)
DEFAULT_BACKGROUND: tuple[int, int, int] = (16, 18, 24)


def qcolor(color: tuple[int, int, int]) -> QColor:
    return QColor(*color)


class RingItem(QGraphicsObject):
    """A single Activity ring (gradient QPen, RoundCap), centered at (0,0).

    ``radius`` (centerline) and ``width`` (stroke) are animatable PySide6 properties;
    changing either updates the geometry and re-scales the drop shadow with ``width``.
    """

    def __init__(
        self,
        radius: float,
        width: float,
        color: tuple[int, int, int],
        start_angle: float = 270.0,
        target: float = 1.0,
        focus_color: tuple[int, int, int] | None = None,
        *,
        direction: str = "clockwise",
    ) -> None:
        super().__init__()
        if direction not in ("clockwise", "counterclockwise"):
            raise ValueError(
                f"direction must be 'clockwise' or 'counterclockwise', got {direction!r}"
            )
        self._r = float(radius)
        self._w = float(width)
        self._color = qcolor(color)
        self._start = start_angle
        self._direction = direction
        self._target = target
        self._progress = float(target)
        self._rotation = 0.0
        self._sweep = 360.0 * target
        self._focus_color = qcolor(focus_color or DEFAULT_FOCUS_COLOR)
        self._focus_level = 0.0
        self._effect = QGraphicsDropShadowEffect()
        self._apply_shadow()
        self.setGraphicsEffect(self._effect)
        self.setCacheMode(QGraphicsItem.ItemCoordinateCache)

    def _apply_shadow(self) -> None:
        w = self._w
        f = self._focus_level
        # At rest: near-black soft shadow below. As the ring is focused, the shadow
        # becomes a soft glow of the outline colour: it spreads (more blur), the
        # offset sinks toward the ring (0,0), and the colour blends to the focus
        # colour instead of tinting the whole background.
        self._effect.setBlurRadius(max(1.0, w * (1.1 + 0.95 * f)))
        off = w * 0.35 * (1.0 - f)
        self._effect.setXOffset(off)
        self._effect.setYOffset(off)
        r = round(self._focus_color.red() * f)
        g = round(self._focus_color.green() * f)
        b = round(self._focus_color.blue() * f)
        self._effect.setColor(QColor(r, g, b, int(200 - 25 * f)))

    def _get_radius(self) -> float:
        return self._r

    def _set_radius(self, value: float) -> None:
        value = float(value)
        if value == self._r:
            return
        self.prepareGeometryChange()
        self._r = value
        self.update()

    radius = Property(float, _get_radius, _set_radius)

    def _get_width(self) -> float:
        return self._w

    def _set_width(self, value: float) -> None:
        value = float(value)
        if value == self._w:
            return
        self.prepareGeometryChange()
        self._w = value
        self._apply_shadow()
        self.update()

    width = Property(float, _get_width, _set_width)

    def set_focus_color(self, color: tuple[int, int, int] | QColor) -> None:
        self._focus_color = QColor(color) if isinstance(color, QColor) else qcolor(color)
        self.update()

    def _get_focus_level(self) -> float:
        return self._focus_level

    def _set_focus_level(self, value: float) -> None:
        value = float(max(0.0, min(value, 1.0)))
        if value == self._focus_level:
            return
        self._focus_level = value
        self._apply_shadow()
        self.update()

    focus_level = Property(float, _get_focus_level, _set_focus_level)

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, value: float) -> None:
        value = float(max(0.0, min(value, 2.0)))
        if value == self._progress:
            return
        self._progress = value
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def _get_rotation(self) -> float:
        return self._rotation

    def _set_rotation(self, value: float) -> None:
        value = float(value)
        if value == self._rotation:
            return
        self._rotation = value
        self.update()

    rotation = Property(float, _get_rotation, _set_rotation)

    def _get_direction(self) -> str:
        return self._direction

    direction = Property(str, _get_direction)

    def boundingRect(self) -> QRectF:
        m = self._r + self._w
        return QRectF(-m, -m, 2 * m, 2 * m)

    def set_sweep(self, fraction: float) -> None:
        frac = max(0.0, min(fraction, 1.0))
        self._sweep = 360.0 * frac
        self._progress = frac
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        sign = -1.0 if self._direction == "clockwise" else 1.0
        base = self._start + self._rotation
        base_sweep = 360.0 * min(1.0, self._progress)
        g = QConicalGradient(QPointF(0, 0), base)
        g.setColorAt(0.0, self._color.lighter(118))
        g.setColorAt(0.12, self._color)
        g.setColorAt(0.85, self._color.darker(96))
        g.setColorAt(1.0, self._color.lighter(118))
        pen = QPen(QBrush(g), self._w)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        rect = QRectF(-self._r, -self._r, 2 * self._r, 2 * self._r)
        painter.drawArc(rect, int(base * 16), int(sign * base_sweep * 16))
        if self._progress > 1.0:
            over_sweep = 360.0 * (self._progress - 1.0)
            op = QPen(self._color.lighter(150), self._w)
            op.setCapStyle(Qt.RoundCap)
            op.setJoinStyle(Qt.RoundJoin)
            painter.setPen(op)
            painter.drawArc(rect, int(base * 16), int(sign * over_sweep * 16))
        if self._focus_level > 0.0:
            self._paint_focus(painter)

    def _paint_focus(self, painter: QPainter) -> None:
        """Closed LED-strip outline wrapping the focused ring's band.

        Traces the full perimeter of the swept band: outer arc, rounded end cap, inner
        arc, rounded start cap, so the outline hugs both edges and closes at the boundary
        points. Drawn as a soft glow: three wide, faint gradient-width passes that spread
        outward, then a thin colour-transitioned core strip (``QConicalGradient``). Faded
        with focus level; tracks the ring as it widens/reflows through the focus animation.
        """
        core = max(1.5, self._w * 0.03)

        ri = self._r - self._w / 2.0
        ro = self._r + self._w / 2.0
        sign = -1.0 if self._direction == "clockwise" else 1.0
        base = self._start + self._rotation
        a0 = base
        a1 = base + sign * self._sweep
        cap_span = sign * 180.0

        outer_rect = QRectF(-ro, -ro, 2 * ro, 2 * ro)
        inner_rect = QRectF(-ri, -ri, 2 * ri, 2 * ri)

        # Rounded caps: half-discs (diameter w) centered on the band when it is cut.
        cap1 = self._arc_point(self._r, a1)
        cap0 = self._arc_point(self._r, a0)
        cap1_rect = QRectF(cap1.x() - self._w / 2.0, cap1.y() - self._w / 2.0, self._w, self._w)
        cap0_rect = QRectF(cap0.x() - self._w / 2.0, cap0.y() - self._w / 2.0, self._w, self._w)

        path = QPainterPath()
        path.arcMoveTo(outer_rect, a0)
        path.arcTo(outer_rect, a0, sign * self._sweep)
        path.arcTo(cap1_rect, a1, cap_span)
        path.arcTo(inner_rect, a1, -sign * self._sweep)
        path.arcTo(cap0_rect, a0 + 180.0, cap_span)
        path.closeSubpath()

        # Soft glow: wide, faint passes spreading outward from the outline line.
        for mult, alpha in ((7.0, 22), (4.5, 40), (2.8, 62)):
            c = QColor(self._focus_color)
            c.setAlpha(int(alpha * self._focus_level))
            pen = QPen(c, core * mult)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        # Core LED strip: a colour-transitioned line hugging the outline.
        fc = QColor(self._focus_color)
        fc.setAlpha(int(255 * self._focus_level))
        g = QConicalGradient(QPointF(0, 0), self._start)
        g.setColorAt(0.0, fc.lighter(140))
        g.setColorAt(0.12, fc)
        g.setColorAt(0.85, fc.darker(130))
        g.setColorAt(1.0, fc.lighter(140))
        pen = QPen(QBrush(g), core)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

    @staticmethod
    def _arc_point(radius: float, angle_deg: float) -> QPointF:
        """Point on a circle centered at the origin at ``angle_deg`` (Qt angle convention)."""
        a = math.radians(angle_deg)
        return QPointF(radius * math.cos(a), -radius * math.sin(a))


def build_focus_rings(
    center: QPointF,
    focus_color: tuple[int, int, int] | None = None,
    *,
    start_angle: float | None = None,
    direction: str = "clockwise",
) -> list[RingItem]:
    # True concentric base geometry: the gap-preserving centerline radii the timeline
    # produces for the base widths. The focus demo overrides these per frame anyway;
    # the progress/spin clip relies on them to keep the three rings concentric.
    widths = [base.width_frac * OUTER_R for base in BASE_RINGS]
    radii = layout(widths, GAP_FRACTION * OUTER_R, OUTER_R)
    rings: list[RingItem] = []
    for base, w, r in zip(BASE_RINGS, widths, radii, strict=True):
        item = RingItem(
            r,
            w,
            base.color,
            base.start_angle if start_angle is None else start_angle,
            base.target,
            focus_color=focus_color,
            direction=direction,
        )
        item.setPos(center)
        rings.append(item)
    return rings


def build_timeline() -> FocusTimeline:
    schedule = default_schedule(period=PERIOD, focus_duration=HOLD, n_rings=3, cycles=4)
    return FocusTimeline(
        schedule, outer_r=OUTER_R, gap=GAP_FRACTION * OUTER_R, transition_s=TRANSITION_S
    )


def render(
    size: int,
    scene: QGraphicsScene,
    focus_color: tuple[int, int, int] | None = None,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> QImage:
    if focus_color is not None:
        for item in scene.items():
            if isinstance(item, RingItem):
                item.set_focus_color(focus_color)
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(*background))
    p = QPainter(img)
    scene.render(p)
    p.end()
    return img


def apply_focus_frame(rings: list[RingItem], frame) -> None:
    for item, radius, width, factor in zip(
        rings, frame.radii, frame.widths, frame.factors, strict=True
    ):
        item.radius = radius
        item.width = width
        item.focus_level = factor


def render_focus_clip(
    scene: QGraphicsScene,
    rings: list[RingItem],
    timeline: FocusTimeline,
    out_dir: Path,
    *,
    start_t: float = -PRE_ROLL,
    end_t: float = DURATION,
    fps: int = FPS,
    focus_color: tuple[int, int, int] | None = None,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> tuple[list[QImage], float, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = int(round((end_t - start_t) * fps)) + 1
    frames: list[QImage] = []
    for i in range(n):
        t = start_t + i / fps
        apply_focus_frame(rings, timeline.frame(t))
        scene.update()
        img = render(SIZE, scene, focus_color=focus_color, background=background)
        frames.append(img)
        img.save(str(out_dir / f"frame_{i:03d}.png"))
    return frames, start_t, fps


def focused_still_times() -> list[tuple[str, float]]:
    schedule = default_schedule(period=PERIOD, focus_duration=HOLD, n_rings=3, cycles=4)
    return [(BASE_RINGS[w.index].key, w.start + TRANSITION_S + 0.2) for w in schedule[:3]]


def render_focus_demo(
    focus_color: tuple[int, int, int] | None = None,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
    out_dir: Path = OUT,
    *,
    start_angle: float | None = None,
    direction: str = "clockwise",
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication([])
    scene = QGraphicsScene()
    scene.setSceneRect(0, 0, SIZE, SIZE)
    center = QPointF(SIZE / 2.0, SIZE / 2.0)
    rings = build_focus_rings(
        center, focus_color=focus_color, start_angle=start_angle, direction=direction
    )
    for item in rings:
        scene.addItem(item)
    timeline = build_timeline()
    frames, start_t, fps = render_focus_clip(
        scene, rings, timeline, out_dir, focus_color=focus_color, background=background
    )
    for key, t in focused_still_times():
        apply_focus_frame(rings, timeline.frame(t))
        scene.update()
        render(SIZE, scene, focus_color=focus_color, background=background).save(
            str(out_dir / f"focus_{key}.png")
        )
    print(f"OK rendered {len(frames)} focus frames -> {out_dir}")
    print(f"pre-roll={PRE_ROLL}s start={start_t}s fps={fps} duration={DURATION}s")
    print(f"outer_r={OUTER_R:.2f} focus_scale={FOCUS_SCALE}")
    return 0


def render_focus_cases(
    out_dir: Path,
    *,
    focus_color: tuple[int, int, int] = DEFAULT_FOCUS_COLOR,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> list[tuple[str, float, str]]:
    """Render the four focus-animation cases (start top/bottom x cw/ccw).

    Each case renders its own focus sequence into ``out_dir/<name>/frame_%03d.png``
    where ``name`` is ``<start>_<dir>``. The caller composes them (eg. a 2x2 grid)
    into a single video. Start angles use the same Qt convention as ``drawArc``:
    ``90`` = top, ``270`` = bottom (this file's ``_arc_point`` mapping).
    """
    cases = [
        ("top_cw", 90.0, "clockwise"),
        ("top_ccw", 90.0, "counterclockwise"),
        ("bottom_cw", 270.0, "clockwise"),
        ("bottom_ccw", 270.0, "counterclockwise"),
    ]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if not QApplication.instance():
        QApplication([])
    for name, start_angle, direction in cases:
        case_dir = out_dir / name
        case_dir.mkdir(parents=True, exist_ok=True)
        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, SIZE, SIZE)
        center = QPointF(SIZE / 2.0, SIZE / 2.0)
        rings = build_focus_rings(
            center, focus_color=focus_color, start_angle=start_angle, direction=direction
        )
        for item in rings:
            scene.addItem(item)
        timeline = build_timeline()
        frames, _, _ = render_focus_clip(
            scene, rings, timeline, case_dir, focus_color=focus_color, background=background
        )
        print(f"OK rendered {len(frames)} frames for {name} (start={start_angle:.0f}, {direction})")
    return cases


def render_progress_clip(
    scene: QGraphicsScene,
    rings: list[RingItem],
    out_dir: Path,
    *,
    duration_ms: float = 300.0,
    value_interval_s: float = 2.0,
    fps: int = FPS,
    start_t: float = 0.0,
    end_t: float = DURATION,
    focus_color: tuple[int, int, int] | None = None,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
    seed: int = 0,
    uplim: float = 2.0,
) -> tuple[list[QImage], float, float]:
    """Render a value-change-tween progress clip.

    Per-ring progress comes from ``progress_track`` over seeded interval targets
    (``duration_ms``/1000 is the value-change tween length). The start point stays
    fixed at the ring's ``start_angle``; the tween moves each ring's leading arc edge
    around, so the arc grows/shrinks from the fixed origin instead of rigidly spinning.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    n = int(round((end_t - start_t) * fps)) + 1
    n_intervals = int(math.ceil(end_t / value_interval_s)) + 1
    targets = seed_progress_targets(n_intervals, len(rings), seed, uplim=uplim)
    frames: list[QImage] = []
    for i in range(n):
        t = start_t + i / fps
        vals = progress_track(
            t, targets, interval_s=value_interval_s, tween_s=duration_ms / 1000.0
        )
        for r, item in enumerate(rings):
            item.progress = vals[r]
        scene.update()
        img = render(SIZE, scene, focus_color=focus_color, background=background)
        frames.append(img)
        img.save(str(out_dir / f"frame_{i:03d}.png"))
    return frames, start_t, fps


def render_progress_cases(
    out_dir: Path,
    *,
    duration_ms: float = 300.0,
    value_interval_s: float = 2.0,
    fps: int = FPS,
    end_t: float = DURATION,
    focus_color: tuple[int, int, int] = DEFAULT_FOCUS_COLOR,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
    seed: int = 0,
) -> list[tuple[str, float, str]]:
    """Render the four progress-animation cases (start top/bottom x cw/ccw).

    Each case renders its own progress sequence into ``out_dir/<name>/frame_%03d.png``
    where ``name`` is ``<start>_<dir>``.
    """
    cases = [
        ("top_cw", 90.0, "clockwise"),
        ("top_ccw", 90.0, "counterclockwise"),
        ("bottom_cw", 270.0, "clockwise"),
        ("bottom_ccw", 270.0, "counterclockwise"),
    ]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if not QApplication.instance():
        QApplication([])
    for name, start_angle, direction in cases:
        case_dir = out_dir / name
        case_dir.mkdir(parents=True, exist_ok=True)
        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, SIZE, SIZE)
        center = QPointF(SIZE / 2.0, SIZE / 2.0)
        rings = build_focus_rings(
            center,
            focus_color=focus_color,
            start_angle=start_angle,
            direction=direction,
        )
        for item in rings:
            scene.addItem(item)
        frames, _, _ = render_progress_clip(
            scene,
            rings,
            case_dir,
            duration_ms=duration_ms,
            value_interval_s=value_interval_s,
            fps=fps,
            end_t=end_t,
            focus_color=focus_color,
            background=background,
            seed=seed,
        )
        print(
            f"OK rendered {len(frames)} progress frames for {name} "
            f"(start={start_angle:.0f}, {direction})"
        )
    return cases


def render_sweep_demo() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication([])
    scene = QGraphicsScene()
    scene.setSceneRect(0, 0, SIZE, SIZE)
    center = QPointF(SIZE / 2.0, SIZE / 2.0)
    rings = build_focus_rings(center)
    for item in rings:
        scene.addItem(item)
    duration = 1.6
    stagger = 0.18
    total = int(duration * FPS) + 1
    for n in range(total):
        t = n / FPS
        for i, item in enumerate(rings):
            local = (t - i * stagger) / duration
            item.set_sweep(BASE_RINGS[i].target * (1.0 - (1.0 - max(0.0, min(1.0, local))) ** 3))
        scene.update()
        render(SIZE, scene).save(str(OUT / f"sweep_{n:02d}.png"))
    print(f"OK rendered {total} sweep frames -> {OUT}")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--sweep":
        return render_sweep_demo()
    return render_focus_demo()


if __name__ == "__main__":
    raise SystemExit(main())
