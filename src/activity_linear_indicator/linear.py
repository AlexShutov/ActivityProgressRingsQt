"""Qt-rendered Activity Linear Indicator (PySide6, offscreen).

A concrete ``LinearItem`` (``QGraphicsItem``) paints a horizontal bar with a
``QLinearGradient`` fill, fully-rounded caps, and a soft ``QGraphicsDropShadowEffect``.
A focused/selected bar gets a glowing LED-strip outline hugging its filled band — the
outline itself — with a soft colour glow (``QGraphicsDropShadowEffect``) that snaps to
the bar's outline colour instead of tinting the whole background. The colour is
overridable via the ``focus_color`` argument on ``build_focus_bars`` / ``render``.
``thickness`` and ``progress`` are PySide6 ``Property`` (float) so they can be animated;
the focus transition is NOT driven by live timers — frames are computed deterministically
from the pure ``activity_linear_indicator.linear_focus`` timeline and rendered via
``QGraphicsScene`` to ``QImage``, so the same code drives a live view and an offscreen
video render (mirroring the Activity Rings Qt preview).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os

from PySide6.QtCore import Property, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
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

from common.background import DEFAULT_BACKGROUND, IndicatorBackgroundDrawer

from .linear_focus import BASE_BARS, GAP_FRACTION, FocusFrame

DEFAULT_FOCUS_COLOR: tuple[int, int, int] = (0, 200, 90)


def qcolor(color: tuple[int, int, int]) -> QColor:
    return QColor(*color)


class LinearItem(QGraphicsObject):
    """A single Activity linear bar (gradient fill, rounded caps), centered at (0,0).

    ``thickness`` (stroke height) and ``progress`` (fill fraction) are animatable
    PySide6 properties; changing either updates the geometry and re-scales the drop
    shadow with ``thickness``. ``length`` is the fixed track length. The bar is laid
    out along X (``left_to_right`` or ``right_to_left``) and centered vertically at Y=0.
    """

    def __init__(
        self,
        length: float,
        thickness: float,
        color: tuple[int, int, int],
        progress: float = 0.0,
        *,
        focus_color: tuple[int, int, int] | None = None,
        direction: str = "left_to_right",
        backdrop_alpha: int = 38,
    ) -> None:
        super().__init__()
        if direction not in ("left_to_right", "right_to_left"):
            raise ValueError(
                f"direction must be 'left_to_right' or 'right_to_left', got {direction!r}"
            )
        self._len = float(length)
        self._t = float(thickness)
        self._color = qcolor(color)
        self._direction = direction
        self._progress = float(progress)
        self._backdrop_alpha = backdrop_alpha
        self._focus_color = qcolor(focus_color or DEFAULT_FOCUS_COLOR)
        self._focus_level = 0.0
        self._effect = QGraphicsDropShadowEffect()
        self._apply_shadow()
        self.setGraphicsEffect(self._effect)
        self.setCacheMode(QGraphicsItem.ItemCoordinateCache)

    def _apply_shadow(self) -> None:
        t = self._t
        f = self._focus_level
        # At rest: near-black soft shadow below. As the bar is focused, the shadow
        # becomes a soft glow of the outline colour: it spreads (more blur), the
        # offset sinks toward the bar (0,0), and the colour blends to the focus
        # colour instead of tinting the whole background.
        self._effect.setBlurRadius(max(1.0, t * (1.1 + 0.95 * f)))
        off = t * 0.35 * (1.0 - f)
        self._effect.setXOffset(off)
        self._effect.setYOffset(off)
        r = round(self._focus_color.red() * f)
        g = round(self._focus_color.green() * f)
        b = round(self._focus_color.blue() * f)
        self._effect.setColor(QColor(r, g, b, int(200 - 25 * f)))

    def _get_length(self) -> float:
        return self._len

    def _set_length(self, value: float) -> None:
        value = float(value)
        if value == self._len:
            return
        self.prepareGeometryChange()
        self._len = value
        self.update()

    length = Property(float, _get_length, _set_length)

    def _get_thickness(self) -> float:
        return self._t

    def _set_thickness(self, value: float) -> None:
        value = float(value)
        if value == self._t:
            return
        self.prepareGeometryChange()
        self._t = value
        self._apply_shadow()
        self.update()

    thickness = Property(float, _get_thickness, _set_thickness)

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, value: float) -> None:
        value = float(max(0.0, min(value, 2.0)))
        if value == self._progress:
            return
        self._progress = value
        self.update()

    progress = Property(float, _get_progress, _set_progress)

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

    def _get_direction(self) -> str:
        return self._direction

    direction = Property(str, _get_direction)

    def boundingRect(self) -> QRectF:
        pad = self._t
        return QRectF(
            -self._len / 2.0 - pad, -self._t / 2.0 - pad, self._len + 2 * pad, 3 * pad
        )

    def set_focus_color(self, color: tuple[int, int, int] | QColor) -> None:
        self._focus_color = QColor(color) if isinstance(color, QColor) else qcolor(color)
        self.update()

    def set_fill(self, fraction: float) -> None:
        self._progress = max(0.0, min(float(fraction), 2.0))
        self.update()

    def _tracks(self) -> tuple[QRectF, QRectF, QRectF, QRectF]:
        """(full track, base fill, overflow band, focus outline) rects, rounded caps."""
        t = self._t
        h = t / 2.0
        start = -self._len / 2.0
        end = self._len / 2.0
        track = QRectF(start, -h, self._len, t)
        frac = min(1.0, self._progress)
        fill_w = self._len * frac
        if self._direction == "right_to_left":
            fill = QRectF(end - fill_w, -h, fill_w, t)
            outline = fill
        else:
            fill = QRectF(start, -h, fill_w, t)
            outline = fill
        over_frac = min(1.0, max(0.0, self._progress - 1.0))
        over_w = self._len * over_frac
        if self._direction == "right_to_left":
            overflow = QRectF(start, -h, over_w, t)
        else:
            overflow = QRectF(end - over_w, -h, over_w, t)
        return track, fill, overflow, outline

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        track, fill, overflow, outline = self._tracks()
        radius = self._t / 2.0

        painter.setPen(Qt.NoPen)
        # Backdrop track: the low-alpha unfilled band (Apple's ~15% track).
        bcol = QColor(self._color)
        bcol.setAlpha(self._backdrop_alpha)
        painter.setBrush(QBrush(bcol))
        painter.drawRoundedRect(track, radius, radius)

        if overflow.width() > 0:
            painter.setBrush(QBrush(self._color.lighter(150)))
            painter.drawRoundedRect(overflow, radius, radius)

        if fill.width() > 0:
            g = QLinearGradient(self._len / 2.0, 0, -self._len / 2.0, 0)
            if self._direction == "right_to_left":
                g = QLinearGradient(-self._len / 2.0, 0, self._len / 2.0, 0)
            g.setColorAt(0.0, self._color.lighter(118))
            g.setColorAt(0.12, self._color)
            g.setColorAt(0.85, self._color.darker(96))
            g.setColorAt(1.0, self._color.lighter(118))
            painter.setBrush(QBrush(g))
            painter.drawRoundedRect(fill, radius, radius)

        if self._focus_level > 0.0:
            self._paint_focus(painter, outline, radius)

    def _paint_focus(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        """Closed LED-strip outline wrapping the focused bar's filled band.

        Traces the rounded-rect perimeter of the filled band so the outline hugs both
        edges and closes at the cap points. Drawn as a soft glow: three wide, faint
        gradient-width passes that spread outward, then a thin colour-transitioned
        core strip (``QLinearGradient``). Faded with focus level.
        """
        if rect.width() <= 0:
            return
        core = max(1.5, self._t * 0.03)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

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
        g = QLinearGradient(rect.left(), 0, rect.right(), 0)
        g.setColorAt(0.0, fc.lighter(140))
        g.setColorAt(0.12, fc)
        g.setColorAt(0.85, fc.darker(130))
        g.setColorAt(1.0, fc.lighter(140))
        pen = QPen(QBrush(g), core)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)


def build_focus_bars(
    center: QPointF,
    length: float,
    outer_len: float,
    focus_color: tuple[int, int, int] | None = None,
    *,
    direction: str = "left_to_right",
    bar_bases=BASE_BARS,
) -> list[LinearItem]:
    """True gap-preserving vertical stack: per-bar thicknesses + layout positions."""
    from .linear_focus import layout as _layout

    widths = [base.thickness_frac * outer_len for base in bar_bases]
    positions = _layout(widths, GAP_FRACTION * outer_len, outer_len)
    bars: list[LinearItem] = []
    for base, w, pos in zip(bar_bases, widths, positions, strict=True):
        item = LinearItem(
            length,
            w,
            base.color,
            base.target,
            focus_color=focus_color,
            direction=direction,
        )
        item.setPos(center.x(), pos)
        bars.append(item)
    return bars


def render(
    size: tuple[int, int],
    scene: QGraphicsScene,
    focus_color: tuple[int, int, int] | None = None,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
) -> QImage:
    w, h = size
    if focus_color is not None:
        for item in scene.items():
            if isinstance(item, LinearItem):
                item.set_focus_color(focus_color)
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    IndicatorBackgroundDrawer(background).fill_qimage(img)
    p = QPainter(img)
    scene.render(p)
    p.end()
    return img


def apply_focus_frame(bars: list[LinearItem], frame: FocusFrame) -> None:
    for item, width, pos, factor in zip(
        bars, frame.widths, frame.positions, frame.factors, strict=True
    ):
        item.thickness = width
        item.setPos(item.x(), pos)
        item.focus_level = factor


def ensure_offscreen_app() -> QApplication:
    """Create (once) an offscreen ``QApplication`` for headless rendering."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def render_bars_frame(
    size: tuple[int, int],
    *,
    bar_bases=BASE_BARS,
    length: float,
    outer_len: float,
    focus_color: tuple[int, int, int] | None = None,
    background: tuple[int, int, int] = DEFAULT_BACKGROUND,
    direction: str = "left_to_right",
) -> QImage:
    """Render a fresh set of bars (built from ``bar_bases``) to a ``QImage``.

    Owns its scratch ``QGraphicsScene`` and items, so it is safe as a one-shot still
    render. For animated sequences build a persistent scene (see the preview tool).
    """
    ensure_offscreen_app()
    center = QPointF(size[0] / 2.0, size[1] / 2.0)
    bars = build_focus_bars(
        center,
        length,
        outer_len,
        focus_color=focus_color,
        direction=direction,
        bar_bases=bar_bases,
    )
    scene = QGraphicsScene()
    scene.setSceneRect(0, 0, size[0], size[1])
    for bar in bars:
        scene.addItem(bar)
    return render(size, scene, focus_color=focus_color, background=background)
