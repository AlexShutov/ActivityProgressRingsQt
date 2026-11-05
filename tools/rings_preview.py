"""Generate Activity-Rings previews (animated GIF + stills) for review (no panel).

Writes into <repo>/docs/rings/: activity.gif and stills at several moments. Pure
Pillow — no Qt, no hardware. Usage: .venv/bin/python tools/rings_preview.py
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
from pathlib import Path

from activityrings.rings import _DEFAULT_TARGETS, render_rings, render_sequence

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "rings"
SIZE = (760, 760)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = render_sequence(_DEFAULT_TARGETS, size=SIZE, seconds=1.6, fps=24)
    gif = frames[0]
    gif.save(OUT / "activity.gif", save_all=True, append_images=frames[1:], duration=40, loop=0)

    for frac, name in ((0.15, "still_early"), (0.5, "still_mid"), (1.0, "still_full")):
        prog = {k: v * frac for k, v in _DEFAULT_TARGETS.items()}
        render_rings(progress=prog, size=SIZE).save(OUT / f"{name}.png")

    # Wide-format sample to prove reuse on a 16:9 HDMI-like canvas.
    render_rings(_DEFAULT_TARGETS, size=(1200, 480)).save(OUT / "still_wide_hdmi.png")

    print(f"OK wrote {len(frames)} frames -> {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"  {p}  ({os.path.getsize(p)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
