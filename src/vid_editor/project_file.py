"""The Project file: every setting on the screen, kept as readable text.

The file is JSON. It refers to its Source and its Overlay image by file
location and never holds video data. Settings travel to and from the screen
as a flat dict keyed by the names in `KEYS`.
"""

import json
import os
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

from vid_editor.model import Corner, EditError, Quality

FORMAT = 1
EXTENSION = ".json"


def _number(kind: type, low: float | None = None, high: float | None = None) -> Callable[[Any], Any]:
    def read(value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("not a number")
        if (low is not None and value < low) or (high is not None and value > high):
            raise ValueError("out of range")
        return kind(value)

    return read


def _optional(read: Callable[[Any], Any]) -> Callable[[Any], Any]:
    return lambda value: None if value is None else read(value)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("not text")
    return value


def _switch(value: Any) -> bool:
    if not isinstance(value, bool):
        raise TypeError("not true or false")
    return value


# Screen setting, section of the file, name within the section, reader.
_FIELDS: tuple[tuple[str, str, str, Callable[[Any], Any]], ...] = (
    ("source_path", "source", "path", _text),
    ("sync_point", "source", "sync_point", _number(float, 0)),
    ("rotation", "source", "rotation", _number(float, 0, 360)),
    ("crop_top", "source", "crop.top", _number(int, 0)),
    ("crop_bottom", "source", "crop.bottom", _number(int, 0)),
    ("crop_left", "source", "crop.left", _number(int, 0)),
    ("crop_right", "source", "crop.right", _number(int, 0)),
    ("source_width", "source", "width", _optional(_number(int, 2))),
    ("aspect_on", "source", "aspect_override.on", _switch),
    ("aspect_width", "source", "aspect_override.width", _number(int, 2)),
    ("aspect_height", "source", "aspect_override.height", _number(int, 2)),
    ("lead_in", "output", "lead_in", _number(float, 0)),
    ("lead_out", "output", "lead_out", _number(float, 0)),
    ("out_width", "output", "width", _optional(_number(int, 2))),
    ("out_rate", "output", "rate", _number(float, 1, 240)),
    ("quality", "output", "quality", Quality),
    ("out_folder", "output", "folder", _text),
    ("out_name", "output", "file_name", _text),
    ("text_on", "text_overlay", "on", _switch),
    ("text_value", "text_overlay", "text", _text),
    ("text_size", "text_overlay", "size", _number(int, 4)),
    ("text_corner", "text_overlay", "corner", Corner),
    ("image_on", "image_overlay", "on", _switch),
    ("image_path", "image_overlay", "path", _text),
    ("image_corner", "image_overlay", "corner", Corner),
    ("image_width", "image_overlay", "width_percent", _number(float, 1, 100)),
    ("image_opacity", "image_overlay", "background_opacity", _number(float, 0, 1)),
)

KEYS = tuple(key for key, *_ in _FIELDS)
"""The screen settings a Project file holds."""


def dumps(settings: dict[str, Any]) -> str:
    """The text of a Project file holding these settings."""
    sections: dict[str, dict] = {"source": {}, "output": {}, "text_overlay": {}, "image_overlay": {}}
    for key, section, name, _ in _FIELDS:
        value = settings[key]
        target = sections[section]
        *groups, last = name.split(".")
        for group in groups:
            target = target.setdefault(group, {})
        target[last] = value.value if isinstance(value, Enum) else value
    document = {
        "format": FORMAT,
        "sources": [sections["source"]],
        "output": sections["output"],
        "text_overlay": sections["text_overlay"],
        "image_overlay": sections["image_overlay"],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def loads(text: str, name: str = "This file") -> dict[str, Any]:
    """Read settings from the text of a Project file.

    A setting the file does not mention is left out of the result, so a file
    written before a setting existed still opens.
    """
    try:
        document = json.loads(text)
    except ValueError as error:
        raise EditError(f"{name} is not a Project file") from error
    if not isinstance(document, dict) or "format" not in document:
        raise EditError(f"{name} is not a Project file")
    if document["format"] != FORMAT:
        raise EditError(f"{name} was written by a different version of the editor")
    sources = document.get("sources")
    if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
        raise EditError(f"{name} must hold exactly one Source")
    sections = {"source": sources[0]} | {
        section: document.get(section, {}) for section in ("output", "text_overlay", "image_overlay")
    }

    settings = {}
    for key, section, field, read in _FIELDS:
        value = sections[section]
        try:
            for part in field.split("."):
                value = value[part]
        except (KeyError, TypeError):
            continue
        try:
            settings[key] = read(value)
        except (ValueError, TypeError) as error:
            shown = f"{section}.{field}".replace("_", " ")
            raise EditError(f"{name} has a value for {shown} that cannot be used: {value!r}") from error
    if not settings.get("source_path"):
        raise EditError(f"{name} does not say where its Source is")
    return settings


def load(path: str | Path) -> dict[str, Any]:
    """Read settings from a Project file."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise EditError(f"Could not read {path}") from error
    return loads(text, name=path.name)


def write(path: str | Path, text: str) -> None:
    """Replace a Project file in one step, so a failed save never leaves half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".saving")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)
