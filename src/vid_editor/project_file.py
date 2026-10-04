"""The Project file: every setting on the screen, kept as readable text.

The file is JSON. It refers to its Sources and its Overlay image by file
location and never holds video data. Settings travel to and from the screen
as `ProjectSettings`, keyed by the names in `SOURCE_KEYS` and `SHARED_KEYS`.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from vid_editor.model import Corner, EditError, Quality

FORMAT = 2
_READABLE_FORMATS = (1, 2)  # format 1 held one Source and had no Audio Source
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


# Per-Source setting, name within each entry of "sources", reader.
_SOURCE_FIELDS: tuple[tuple[str, str, Callable[[Any], Any]], ...] = (
    ("path", "path", _text),
    ("sync_point", "sync_point", _number(float, 0)),
    ("rotation", "rotation", _number(float, 0, 360)),
    ("crop_top", "crop.top", _number(int, 0)),
    ("crop_bottom", "crop.bottom", _number(int, 0)),
    ("crop_left", "crop.left", _number(int, 0)),
    ("crop_right", "crop.right", _number(int, 0)),
    ("source_width", "width", _optional(_number(int, 2))),
    ("aspect_on", "aspect_override.on", _switch),
    ("aspect_width", "aspect_override.width", _number(int, 2)),
    ("aspect_height", "aspect_override.height", _number(int, 2)),
)

# Shared setting, section of the file, name within the section, reader.
_SHARED_FIELDS: tuple[tuple[str, str, str, Callable[[Any], Any]], ...] = (
    ("lead_in", "output", "lead_in", _number(float, 0)),
    ("lead_out", "output", "lead_out", _number(float, 0)),
    ("out_width", "output", "width", _optional(_number(int, 2))),
    ("out_rate", "output", "rate", _optional(_number(float, 1, 240))),
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
_SHARED_SECTIONS = ("output", "text_overlay", "image_overlay")

SOURCE_KEYS = tuple(key for key, *_ in _SOURCE_FIELDS if key != "path")
"""The settings each Source has, besides its path."""
SHARED_KEYS = tuple(key for key, *_ in _SHARED_FIELDS)
"""The settings that belong to the Output as a whole."""


@dataclass
class ProjectSettings:
    """What a Project file holds."""

    sources: list[dict[str, Any]]
    """One dict per Source, left to right: its "path" and any of `SOURCE_KEYS`."""
    shared: dict[str, Any] = field(default_factory=dict)
    """Any of `SHARED_KEYS`."""
    audio_source: int | None = 0
    """Position in `sources` of the Audio Source, counted from 0. None is no sound."""


def _put(section: dict, name: str, value: Any) -> None:
    *groups, last = name.split(".")
    for group in groups:
        section = section.setdefault(group, {})
    section[last] = value.value if isinstance(value, Enum) else value


def _read(section: Any, name: str, read: Callable[[Any], Any], shown: str, file: str) -> Any:
    """One value from a section. Raises KeyError when the file does not mention it."""
    value = section
    try:
        for part in name.split("."):
            value = value[part]
    except TypeError as error:
        raise KeyError(name) from error
    try:
        return read(value)
    except (ValueError, TypeError) as error:
        raise EditError(f"{file} has a value for {shown} that cannot be used: {value!r}") from error


def dumps(settings: ProjectSettings) -> str:
    """The text of a Project file holding these settings.

    A setting that is not given is left out of the file.
    """
    sources = []
    for source in settings.sources:
        entry: dict = {}
        for key, name, _ in _SOURCE_FIELDS:
            if key in source:
                _put(entry, name, source[key])
        sources.append(entry)
    sections: dict[str, dict] = {section: {} for section in _SHARED_SECTIONS}
    for key, section, name, _ in _SHARED_FIELDS:
        if key in settings.shared:
            _put(sections[section], name, settings.shared[key])
    document = {
        "format": FORMAT,
        "sources": sources,
        # Counted from 1, to match "Source 1" on the screen.
        "audio_source": None if settings.audio_source is None else settings.audio_source + 1,
        **sections,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def loads(text: str, name: str = "This file") -> ProjectSettings:
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
    if document["format"] not in _READABLE_FORMATS:
        raise EditError(f"{name} was written by a different version of the editor")
    entries = document.get("sources")
    if not isinstance(entries, list) or not entries:
        raise EditError(f"{name} must hold at least one Source")

    sources = []
    for number, entry in enumerate(entries, start=1):
        source = {}
        for key, field_name, read in _SOURCE_FIELDS:
            shown = f"source {number} {field_name}".replace("_", " ")
            try:
                source[key] = _read(entry, field_name, read, shown, name)
            except KeyError:
                continue
        if not source.get("path"):
            raise EditError(f"{name} does not say where Source {number} is")
        sources.append(source)

    shared = {}
    for key, section, field_name, read in _SHARED_FIELDS:
        shown = f"{section}.{field_name}".replace("_", " ")
        try:
            shared[key] = _read(document.get(section, {}), field_name, read, shown, name)
        except KeyError:
            continue

    audio_source = 0
    if "audio_source" in document:
        chosen = document["audio_source"]
        if chosen is None:
            audio_source = None
        elif isinstance(chosen, int) and not isinstance(chosen, bool) and 1 <= chosen <= len(sources):
            audio_source = chosen - 1
        else:
            raise EditError(f"{name} has a value for audio source that cannot be used: {chosen!r}")
    return ProjectSettings(sources=sources, shared=shared, audio_source=audio_source)


def load(path: str | Path) -> ProjectSettings:
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
