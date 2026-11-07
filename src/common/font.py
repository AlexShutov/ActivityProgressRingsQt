"""Шрифты для отрисовки надписей индикаторов (MIT).

Единая точка выбора шрифта:

- :class:`FontSpec` — общепринятое описание шрифта по модели CSS
  (``family``/``size``/``weight``/``style``).  Другой шрифт подставляется сменой
  ``family``, без правки кода рисования.
- :class:`FontResolver` — превращает ``FontSpec`` в нагруженный ``PIL.ImageFont``,
  зная, где лежат TTF-активы (папка ``fonts/`` рядом с модулем).  Если семейство
  не найдено или файл битый — откат на системный ``DejaVuSans``, чтобы надписи
  всегда рисовались.

``FontSizeCalculator`` (см. :mod:`font_size`) измеряет текст этим же резолвером,
чтобы подобрать максимальный читаемый размер без «магических» чисел.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Папка с TTF-активами: рядом с этим модулем (``<пакет>/common/fonts/``).
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"

# Семейство -> имя TTF-файла в ``_FONTS_DIR``.  Добавление нового шрифта — новая
# запись (и файл рядом), без изменения кода рисования.
DEFAULT_FONT_FAMILY = "Spacetron"
_FONT_FILES: dict[str, str] = {
    DEFAULT_FONT_FAMILY: "Spacetron-Regular.ttf",
    # Настоящий «киберпанк»-шрифт для верхних подписей (замена самодельной
    # рекреации из скриншота).  Загружается по файлу, поэтому имя семейства —
    # произвольный ключ.
    "Cyberpunk": "Cyberpunk-Regular.ttf",
    # Самодельная рекреация из шрифтового спесимена (личные нужды) — оставлена
    # как запасной вариант, больше не включена по умолчанию.
    "CyberFont": "CyberFont.ttf",
}

# Откат, если семейство не зарегистрировано или файл не прочитался: системный
# шрифт (как раньше рисовались надписи).
_SYSTEM_FALLBACK_FAMILY = "DejaVuSans"


@dataclass(frozen=True)
class FontSpec:
    """Общепринятое описание шрифта (модель CSS: семейство/кегль/начертание/стиль).

    ``size`` — кегль в px; ``weight`` — ``"normal"``/``"bold"``; ``style`` —
    ``"normal"``/``"italic"``.  Формат стандартный (не привязан к проекту),
    поэтому виджеты могут получать любой шрифт сменой ``family``.
    """

    family: str
    size: int
    weight: str = "normal"
    style: str = "normal"


class FontResolver:
    """Выбирает ``PIL.ImageFont`` по ``FontSpec`` (замена DejaVu на стилевой шрифт)."""

    def __init__(
        self,
        fonts_dir: Path | None = None,
        font_files: dict[str, str] | None = None,
        fallback_family: str = _SYSTEM_FALLBACK_FAMILY,
    ) -> None:
        self._fonts_dir = Path(fonts_dir) if fonts_dir is not None else _FONTS_DIR
        self._font_files = dict(font_files) if font_files is not None else _FONT_FILES
        self._fallback_family = fallback_family

    def resolve(self, spec: FontSpec):
        """Возвращает нагруженный ``PIL.ImageFont`` для ``spec`` (или ``None``).

        Порядок: TTF-актив семейства → системный fallback → встроенный bitmap-шрифт.
        Последний срабатывает, когда и актив, и системный шрифт недоступны, поэтому
        надписи рисуются всегда (в худшем случае мелким bitmap-шрифтом).
        """
        from PIL import ImageFont

        path = self._asset_path(spec.family)
        candidates = []
        if path is not None:
            candidates.append(str(path))
        candidates.append(self._fallback_family)
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, spec.size)
            except Exception:
                continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _asset_path(self, family: str) -> Path | None:
        """Путь к TTF-файлу семейства или ``None``, если он не зарегистрирован/битый."""
        filename = self._font_files.get(family)
        if filename is None:
            return None
        candidate = self._fonts_dir / filename
        return candidate if candidate.is_file() else None
