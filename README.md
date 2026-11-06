# DashboardWidgets

Apple-style Dashboard Widgets, two sibling packages under one MIT roof:

- **`activityrings`** — Apple-style Activity Progress Rings: three concentric, eased,
  shadowed rings with a pure focus-shift timeline, rendered headless (Pillow). See
  `src/activityrings/`.
- **`activity_linear_indicator`** — the Activity Linear Indicator: a gap-preserving
  vertical stack of bars with a `QLinearGradient` fill, rounded caps, a soft drop
  shadow, and a **selection** glow outline (active outline colour) — rendered with a
  Qt (PySide6) `LinearItem` offscreen. Value/focus switching is eased (never jumping).
  See `src/activity_linear_indicator/`.

Both share a pure focus-shift model (`linear_focus` / `rings_focus`): a schedule of
focus windows drives per-item eased width/thickness and a gap-preserving reflow; a
`progress_track` eases value changes over time. The same code drives a live Qt view and
an offscreen video render.

## What's here

- **`src/activityrings/`** — `rings.py` (Pillow renderer) + `rings_focus.py` (pure
  focus model). `tools/rings_preview.py` / `tools/qrings_preview.py` write
  `docs/rings/` and `docs/rings_focus/`.
- **`src/activity_linear_indicator/`** — `linear.py` (Qt `LinearItem` + offscreen
  `QGraphicsScene` → `QImage`) + `linear_focus.py` (pure focus model).
  `tools/qlinear_preview.py` writes `docs/linear/` + `docs/linear_focus/`.
- **`tests/`** — pytest unit tests for both focus models.

## Quickstart

```bash
python -m pip install -e .          # both packages (Pillow + PySide6)
python tools/qlinear_preview.py     # write docs/linear/ (+ focus stills)
python tools/qrings_preview.py      # write docs/rings_focus/ (focus demo)
python -m pytest tests/             # run the focus-model tests
```

## License

MIT. The Qt overlay preview is intentional standalone code; it does not embed any
GPL-3.0 `trcc` internals.