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

from vid_editor.model import Corner, EditError, JoinKind, Quality, SpeedChoice, Workflow

FORMAT = 5
# Format 1 held one Source and had no Audio Source. Format 2 held several, each
# with a Row, and the Sources set the sizes. Format 3 lists its Panels. Format 4
# adds the workflow and the Sequence's settings; a file without them is a
# Synced grid. Format 5 adds the Audio Tracks and the Sources' volume.
_READABLE_FORMATS = (1, 2, 3, 4, 5)
_FIRST_FORMAT_WITH_PANELS = 3
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
    ("record_rate", "record_rate", _optional(_number(float, 0.001))),
    ("aspect_on", "aspect_override.on", _switch),
    ("aspect_width", "aspect_override.width", _number(int, 2)),
    ("aspect_height", "aspect_override.height", _number(int, 2)),
    ("start_point", "start_point", _number(float, 0)),
    ("end_point", "end_point", _optional(_number(float, 0))),
    ("play_speed", "play_speed", _number(float, 0.001)),
    ("join_kind", "join_after.kind", JoinKind),
    ("join_length", "join_after.length", _number(float, 0.001)),
)

# Per-Audio Track setting, name within each entry of "audio_tracks", reader.
_TRACK_FIELDS: tuple[tuple[str, str, Callable[[Any], Any]], ...] = (
    ("path", "path", _text),
    ("track_start", "start", _number(float, 0)),
    ("track_file_start", "file_start", _number(float, 0)),
    ("track_volume", "volume", _number(float, 0, 200)),
    ("track_fade_out", "fade_out", _number(float, 0)),
)
TRACK_KEYS = tuple(key for key, *_ in _TRACK_FIELDS if key != "path")
"""The settings each Audio Track has, besides its path."""

# What each entry of "panels" holds.
_PANEL_FIELDS: tuple[tuple[str, Callable[[Any], Any]], ...] = (
    ("row", _number(int, 1)),
    ("width", _number(int, 2)),
    ("height", _number(int, 2)),
)
PANEL_KEYS = tuple(key for key, _ in _PANEL_FIELDS)
"""The settings each Panel has."""

# Shared setting, section of the file, name within the section, reader. The
# section "" is the top level of the file.
_SHARED_FIELDS: tuple[tuple[str, str, str, Callable[[Any], Any]], ...] = (
    ("workflow", "", "workflow", Workflow),
    ("seq_width", "sequence", "width", _number(int, 2)),
    ("seq_height", "sequence", "height", _number(int, 2)),
    ("seq_fade_in", "sequence", "fade_in", _number(float, 0)),
    ("seq_fade_out", "sequence", "fade_out", _number(float, 0)),
    ("lead_in", "output", "lead_in", _number(float, 0)),
    ("lead_out", "output", "lead_out", _number(float, 0)),
    ("out_width", "output", "width", _optional(_number(int, 2))),
    ("out_rate", "output", "rate", _optional(_number(float, 1, 240))),
    ("speed_choice", "output", "speed", SpeedChoice),
    ("speed_custom", "output", "custom_speed", _number(float, 0.001)),
    ("quality", "output", "quality", Quality),
    ("source_volume", "output", "source_volume", _number(float, 0, 200)),
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
    ("draft_lead_in", "draft", "lead_in", _number(float, 0)),
    ("draft_lead_out", "draft", "lead_out", _number(float, 0)),
    ("draft_width", "draft", "width", _number(int, 2)),
    ("draft_sound", "draft", "sound", _switch),
    ("draft_at", "draft", "sequence_join", _number(int, 0)),
)
_SHARED_SECTIONS = ("", "sequence", "output", "text_overlay", "image_overlay", "draft")

SOURCE_KEYS = tuple(key for key, *_ in _SOURCE_FIELDS if key != "path")
"""The settings each Source has, besides its path."""
SHARED_KEYS = tuple(key for key, *_ in _SHARED_FIELDS)
"""The settings that belong to the Output as a whole, and to its Draft."""


@dataclass
class ProjectSettings:
    """What a Project file holds."""

    sources: list[dict[str, Any]]
    """One dict per Source, in the order added: its "path", any of
    `SOURCE_KEYS`, and "panel", the position in `panels` of its Panel counted
    from 0. A Source from a file with no Panels has "row" instead, counted
    from 1."""
    shared: dict[str, Any] = field(default_factory=dict)
    """Any of `SHARED_KEYS`."""
    panels: list[dict[str, int]] | None = None
    """One dict per Panel, in listed order, holding `PANEL_KEYS`. None for a
    file from before typed Panels: each Source then has a Panel of its own, in
    the same order, whose size the old rules give (`render.legacy_panels`)."""
    audio_panel: int | None = 0
    """Position in `panels` of the Audio Panel, counted from 0. None is no sound."""
    tracks: list[dict[str, Any]] = field(default_factory=list)
    """One dict per Audio Track, in order: its "path" and any of `TRACK_KEYS`."""


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
        if "panel" in source:
            # Counted from 1, to match "Panel 1" on the screen.
            entry["panel"] = source["panel"] + 1
        sources.append(entry)
    sections: dict[str, dict] = {section: {} for section in _SHARED_SECTIONS}
    for key, section, name, _ in _SHARED_FIELDS:
        if key in settings.shared:
            _put(sections[section], name, settings.shared[key])
    top = sections.pop("")
    document = {
        "format": FORMAT,
        **top,
        "panels": [{key: panel[key] for key in PANEL_KEYS} for panel in settings.panels or []],
        "sources": sources,
        "audio_panel": None if settings.audio_panel is None else settings.audio_panel + 1,
        "audio_tracks": [
            {name: track[key] for key, name, _ in _TRACK_FIELDS if key in track}
            for track in settings.tracks
        ],
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
    has_panels = document["format"] >= _FIRST_FORMAT_WITH_PANELS

    panels = None
    if has_panels:
        listed = document.get("panels")
        if not isinstance(listed, list) or not listed:
            raise EditError(f"{name} must hold at least one Panel")
        panels = []
        for number, entry in enumerate(listed, start=1):
            try:
                panels.append(
                    {
                        key: _read(entry, key, read, f"panel {number} {key}", name)
                        for key, read in _PANEL_FIELDS
                    }
                )
            except KeyError as error:
                raise EditError(f"{name} does not give Panel {number} a {error.args[0]}") from error

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
        if has_panels:
            try:
                place = _read(
                    entry, "panel", _number(int, 1, len(panels)), f"source {number} panel", name
                )
            except KeyError as error:
                raise EditError(f"{name} does not say which Panel Source {number} is in") from error
            source["panel"] = place - 1
        else:
            try:
                source["row"] = _read(entry, "row", _number(int, 1), f"source {number} row", name)
            except KeyError:
                source["row"] = 1
        sources.append(source)

    listed = document.get("audio_tracks", [])
    if not isinstance(listed, list):
        raise EditError(f"{name} has a value for audio tracks that cannot be used: {listed!r}")
    tracks = []
    for number, entry in enumerate(listed, start=1):
        track = {}
        for key, field_name, read in _TRACK_FIELDS:
            shown = f"audio track {number} {field_name}".replace("_", " ")
            try:
                track[key] = _read(entry, field_name, read, shown, name)
            except KeyError:
                continue
        if not track.get("path"):
            raise EditError(f"{name} does not say where Audio Track {number} is")
        tracks.append(track)

    shared = {}
    for key, section, field_name, read in _SHARED_FIELDS:
        shown = (f"{section}.{field_name}" if section else field_name).replace("_", " ")
        place = document if not section else document.get(section, {})
        try:
            shared[key] = _read(place, field_name, read, shown, name)
        except KeyError:
            continue

    # Before typed Panels the file named an Audio Source. Each Source of such a
    # file gets a Panel of its own in the same order, so the number carries over.
    audio_key = "audio_panel" if has_panels else "audio_source"
    audio_count = len(panels) if has_panels else len(sources)
    audio_panel = 0
    if audio_key in document:
        chosen = document[audio_key]
        if chosen is None:
            audio_panel = None
        elif isinstance(chosen, int) and not isinstance(chosen, bool) and 1 <= chosen <= audio_count:
            audio_panel = chosen - 1
        else:
            raise EditError(
                f"{name} has a value for {audio_key.replace('_', ' ')} that cannot be used: {chosen!r}"
            )
    return ProjectSettings(
        sources=sources, shared=shared, panels=panels, audio_panel=audio_panel, tracks=tracks
    )


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
