# ActivityProgressRingsQt

Apple-style Activity Progress Rings: three concentric, eased, shadowed rings with a pure
focus-shift timeline, rendered headless (Pillow) and as a Qt/PySide6 overlay preview.

## What's here

- **`src/activityrings/rings.py`** — resolution-independent Pillow renderer (`render_rings`,
  `render_sequence`, `eased_progress_map`). Feed any rectangle/canvas; the same frames serve an
  embedded LCD overlay or a full HDMI screen.
- **`src/activityrings/rings_focus.py`** — the pure focus-shift model (MIT, no Qt/Pillow):
  constant-gap, outer-edge-anchored layout; each ring ramps to `FOCUS_SCALE` on its focus window;
  `FocusTimeline.frame(t)` returns `{widths, radii, factors}` so a view can animate and highlight
  the focused ring.
- **`tools/rings_preview.py`** — Pillow-only preview that writes `docs/rings/` (GIF + stills).
  Usage: `python tools/rings_preview.py`.
- **`tools/qrings_preview.py`** — Qt-rendered focus preview via `QGraphicsScene` → `QImage`
  (offscreen). Writes `docs/rings_focus/` (frames + `focus_*.png` stills + `activity_focus.mp4`
  / `.gif`). The focused ring gets a thin configurable outline (green by default). Usage:
  `python tools/qrings_preview.py` (focus demo) or `--sweep` (original cascade sweep).
- **`tests/`** — pytest unit tests for the focus model (`rings_focus`) and the layout/easing
  invariants.

## Quickstart

```bash
python -m pip install -e .          # Pillow renderer
python -m pip install -e ".[qt]"    # add PySide6 for the Qt preview
python tools/rings_preview.py       # write docs/rings/
python tools/qrings_preview.py      # write docs/rings_focus/ (focus demo)
python -m pytest tests/             # run the focus-model tests
```

## License

MIT. The Qt overlay preview is intentional standalone code; it does not embed any GPL-3.0
`trcc` internals.