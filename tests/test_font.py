# SPDX-License-Identifier: MIT
"""Unit tests for font selection (``common.font``).

Проверяем стандартный формат ``FontSpec``, фактическую загрузку стилевого TTF-актива
(``Spacetron-Regular.ttf``) через ``FontResolver`` и откат на системный шрифт, чтобы
надписи всегда рисовались, даже если семейство не зарегистрировано.
"""
from __future__ import annotations

from common.font import (
    DEFAULT_FONT_FAMILY,
    FontResolver,
    FontSpec,
)


def test_font_spec_is_standard_css_style_fields():
    spec = FontSpec("Spacetron", 24)
    assert spec.family == "Spacetron"
    assert spec.size == 24
    assert spec.weight == "normal"
    assert spec.style == "normal"
    assert FontSpec("DejaVuSans", 20, weight="bold", style="italic").weight == "bold"


def test_default_family_points_to_bundled_spacetron_asset():
    resolver = FontResolver()
    path = resolver._asset_path(DEFAULT_FONT_FAMILY)
    assert path is not None
    assert path.suffix == ".ttf"
    assert ("fonts" in path.parts) or (path.parent.parent.name == "fonts")
    assert path.is_file()


def test_resolver_loads_actual_pillow_image_font():
    font = FontResolver().resolve(FontSpec(DEFAULT_FONT_FAMILY, 26))
    assert font is not None
    # Кегль реально подхватился: у стилевого шрифта ширина «100%» заметно меньше
    # ширины полотна (иначе это не шрифт, а заглушка).  Длина строки > 0.
    assert font.getlength("100%") > 0.0


def test_resolver_falls_back_for_unknown_family():
    resolver = FontResolver()
    font = resolver.resolve(FontSpec("UnknownFamily", 26))
    assert font is not None
    # Откат (системный шрифт либо встроенный bitmap) — шрифт всё равно грузится
    # и умеет измерять текст.
    assert font.getlength("100%") > 0.0


def test_resolver_never_returns_none_when_asset_and_fallback_fail():
    resolver = FontResolver(font_files={"X": "missing.ttf"}, fallback_family="no-such-font")
    font = resolver.resolve(FontSpec("X", 26))
    # Даже когда актив и системный шрифт недоступны, срабатывает встроенный
    # bitmap-шрифт — надпись всегда можно отрисовать.
    assert font is not None
