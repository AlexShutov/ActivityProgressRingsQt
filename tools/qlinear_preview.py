"""Qt-rendered Activity Linear Indicator preview with focus-shifting (PySide6, offscreen).

A concrete ``LinearItem`` (``QGraphicsItem``) paints each bar as a gap-preserving
vertical stack with a ``QLinearGradient`` fill, rounded caps and a soft
``QGraphicsDropShadowEffect``. A focused/selected bar gets a glowing LED-strip outline
hugging its filled band (the outline itself) with a soft colour glow that snaps to the
bar's outline colour instead of tinting the whole background. Green by default via
``DEFAULT_FOCUS_COLOR``, faded with each bar's focus level and tracking the bar through
the focus animation; overridable via the ``focus_color`` argument on
``build_focus_bars`` / ``render``. ``thickness`` and ``progress`` are PySide6
``Property`` (float) so they can be animated; the focus transition is NOT driven by live
timers — frames are computed deterministically from the pure
``activity_linear_indicator.linear_focus`` timeline and rendered via ``QGraphicsScene``
to ``QImage``, so the same code drives a live view and an offscreen video.

Run:  .venv-trcc/bin/python tools/qlinear_preview.py
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsScene

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from activity_linear_indicator.linear import (  # noqa: E402
    DEFAULT_BACKGROUND,
    DEFAULT_FOCUS_COLOR,
    apply_focus_frame,
    build_focus_bars,
    ensure_offscreen_app,
    render,
)
from activity_linear_indicator.linear_focus import (  # noqa: E402
    BASE_BARS,
    GAP_FRACTION,
    TRANSITION_S,
    FocusTimeline,
    default_schedule,
    progress_track,
)

OUT = REPO / "docs"
SIZE = 760
OUTER_H = SIZE * 0.4575
LENGTH = SIZE * 0.8
FPS = 24
PERIOD = 5.0
HOLD = 2.0
DURATION = 16.0


def _make_scene(focus_color=DEFAULT_FOCUS_COLOR) -> tuple[QGraphicsScene, list]:
    scene = QGraphicsScene()
    scene.setSceneRect(0, 0, SIZE, SIZE)
    bars = build_focus_bars(QPointF(SIZE / 2, SIZE / 2), LENGTH, OUTER_H, focus_color)
    for bar in bars:
        scene.addItem(bar)
    return scene, bars


def _build_timeline() -> FocusTimeline:
    return FocusTimeline(
        default_schedule(period=PERIOD, focus_duration=HOLD, n_bars=3, cycles=4),
        outer_len=OUTER_H,
        gap=GAP_FRACTION * OUTER_H,
        transition_s=TRANSITION_S,
    )


def _focused_still_times() -> list[tuple[str, float]]:
    schedule = default_schedule(period=PERIOD, focus_duration=HOLD, n_bars=3, cycles=4)
    return [(BASE_BARS[w.index].key, w.start + TRANSITION_S + 0.2) for w in schedule[:3]]


def render_progress_stills() -> int:
    """Value-change progress stills (early / mid / full) into ``docs/linear/``."""
    out = OUT / "linear"
    out.mkdir(parents=True, exist_ok=True)
    scene, bars = _make_scene()
    targets = [[0.15, 0.45, 0.75], [0.85, 0.30, 0.55], [0.30, 0.95, 0.20]]
    for name, t in (("still_early", 0.1), ("still_mid", 1.2), ("still_full", 2.3)):
        vals = progress_track(
            t, targets, interval_s=1.0, tween_s=0.6
        )
        for bar, v in zip(bars, vals, strict=True):
            bar.progress = v
        scene.update()
        render((SIZE, SIZE), scene, background=DEFAULT_BACKGROUND).save(
            str(out / f"{name}.png")
        )
    print(f"OK progress stills -> {out}")
    return 0


def render_focus_stills() -> int:
    """Selection stills (each bar focused) into ``docs/linear_focus/``."""
    out = OUT / "linear_focus"
    out.mkdir(parents=True, exist_ok=True)
    scene, bars = _make_scene()
    timeline = _build_timeline()
    for key, t in _focused_still_times():
        apply_focus_frame(bars, timeline.frame(t))
        scene.update()
        render((SIZE, SIZE), scene, background=DEFAULT_BACKGROUND).save(
            str(out / f"focus_{key}.png")
        )
    print(f"OK focus stills -> {out}")
    return 0


def main() -> int:
    ensure_offscreen_app()
    render_progress_stills()
    render_focus_stills()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
