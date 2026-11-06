"""Apple-style Activity Progress Rings (MIT).

Headless, resolution-independent renderers and a pure focus-shift timeline for the three
concentric Activity Rings. ``rings`` draws frames over Pillow; ``rings_focus`` is the pure
focus model (constants, gap-preserving layout, eased per-ring focus factors) that also drives
the Qt preview in ``tools/qrings_preview.py``.

The package exposes its API lazily so importing it never pulls in Pillow; the pure focus model
is usable in a minimal environment and the Pillow renderer loads on first use.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

__all__ = [
    # pure focus model
    "BASE_RINGS",
    "FOCUS_SCALE",
    "GAP_FRACTION",
    "TRANSITION_S",
    "FocusFrame",
    "FocusTimeline",
    "FocusWindow",
    "RingBase",
    "default_schedule",
    # Pillow renderer (lazy)
    "RingSpec",
    "build_rings",
    "eased_progress_map",
    "gauge_ring_bases",
    "render_gauge_rings",
    "render_rings",
    "render_sequence",
]

_FOCUS_EXPORTS = frozenset(
    {
        "BASE_RINGS",
        "FOCUS_SCALE",
        "GAP_FRACTION",
        "TRANSITION_S",
        "FocusFrame",
        "FocusTimeline",
        "FocusWindow",
        "RingBase",
        "default_schedule",
    }
)
_PILLOW_EXPORTS = frozenset(
    {
        "RingSpec",
        "build_rings",
        "eased_progress_map",
        "gauge_ring_bases",
        "render_gauge_rings",
        "render_rings",
        "render_sequence",
    }
)


def __getattr__(name: str):
    if name in _FOCUS_EXPORTS:
        from activityrings.rings_focus import (  # pure, no Pillow
            BASE_RINGS,
            FOCUS_SCALE,
            GAP_FRACTION,
            TRANSITION_S,
            FocusFrame,
            FocusTimeline,
            FocusWindow,
            RingBase,
            default_schedule,
        )

        return {
            "BASE_RINGS": BASE_RINGS,
            "FOCUS_SCALE": FOCUS_SCALE,
            "GAP_FRACTION": GAP_FRACTION,
            "TRANSITION_S": TRANSITION_S,
            "FocusFrame": FocusFrame,
            "FocusTimeline": FocusTimeline,
            "FocusWindow": FocusWindow,
            "RingBase": RingBase,
            "default_schedule": default_schedule,
        }[name]
    if name in _PILLOW_EXPORTS:
        from activityrings.rings import (  # Pillow — imported lazily
            RingSpec,
            build_rings,
            eased_progress_map,
            gauge_ring_bases,
            render_gauge_rings,
            render_rings,
            render_sequence,
        )

        return {
            "RingSpec": RingSpec,
            "build_rings": build_rings,
            "eased_progress_map": eased_progress_map,
            "gauge_ring_bases": gauge_ring_bases,
            "render_gauge_rings": render_gauge_rings,
            "render_rings": render_rings,
            "render_sequence": render_sequence,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

