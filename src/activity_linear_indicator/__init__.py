"""Activity Linear Indicator (MIT).

Headless, resolution-independent bars with a pure focus-shift timeline and a Qt
(PySide6) overlay renderer, mirroring the Activity Rings package. ``linear_focus`` is
the pure focus model (constants, gap-preserving layout, eased per-bar focus factors);
``linear`` is the Qt ``LinearItem`` that paints the bars with a gradient fill, soft
drop shadow, animated (eased) value/focus switching, and a selection glow outline in
the active outline colour.

The package exposes its API lazily so importing it never pulls in Qt; the pure focus
model is usable in a minimal environment and the Qt renderer loads on first use.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

__all__ = [
    # pure focus model
    "BASE_BARS",
    "FOCUS_SCALE",
    "GAP_FRACTION",
    "TRANSITION_S",
    "BarBase",
    "FocusFrame",
    "FocusTimeline",
    "FocusWindow",
    "default_schedule",
    # Qt renderer (lazy)
    "DEFAULT_BACKGROUND",
    "DEFAULT_FOCUS_COLOR",
    "LinearItem",
    "apply_focus_frame",
    "build_focus_bars",
    "render",
    "render_bars_frame",
]

_FOCUS_EXPORTS = frozenset(
    {
        "BASE_BARS",
        "FOCUS_SCALE",
        "GAP_FRACTION",
        "TRANSITION_S",
        "BarBase",
        "FocusFrame",
        "FocusTimeline",
        "FocusWindow",
        "default_schedule",
    }
)
_QT_EXPORTS = frozenset(
    {
        "DEFAULT_BACKGROUND",
        "DEFAULT_FOCUS_COLOR",
        "LinearItem",
        "apply_focus_frame",
        "build_focus_bars",
        "render",
        "render_bars_frame",
    }
)


def __getattr__(name: str):
    if name in _FOCUS_EXPORTS:
        from activity_linear_indicator.linear_focus import (  # pure, no Qt
            BASE_BARS,
            FOCUS_SCALE,
            GAP_FRACTION,
            TRANSITION_S,
            BarBase,
            FocusFrame,
            FocusTimeline,
            FocusWindow,
            default_schedule,
        )

        return {
            "BASE_BARS": BASE_BARS,
            "FOCUS_SCALE": FOCUS_SCALE,
            "GAP_FRACTION": GAP_FRACTION,
            "TRANSITION_S": TRANSITION_S,
            "BarBase": BarBase,
            "FocusFrame": FocusFrame,
            "FocusTimeline": FocusTimeline,
            "FocusWindow": FocusWindow,
            "default_schedule": default_schedule,
        }[name]
    if name in _QT_EXPORTS:
        from activity_linear_indicator.linear import (  # Qt — imported lazily
            DEFAULT_BACKGROUND,
            DEFAULT_FOCUS_COLOR,
            LinearItem,
            apply_focus_frame,
            build_focus_bars,
            render,
            render_bars_frame,
        )

        return {
            "DEFAULT_BACKGROUND": DEFAULT_BACKGROUND,
            "DEFAULT_FOCUS_COLOR": DEFAULT_FOCUS_COLOR,
            "LinearItem": LinearItem,
            "apply_focus_frame": apply_focus_frame,
            "build_focus_bars": build_focus_bars,
            "render": render,
            "render_bars_frame": render_bars_frame,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
