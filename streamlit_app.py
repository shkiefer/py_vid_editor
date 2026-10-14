"""Video editor screen. Run with: uv run streamlit run streamlit_app.py"""

import time
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

import streamlit as st

from vid_editor import dialogs, project_file
from vid_editor.model import (
    Corner,
    Crop,
    DraftSettings,
    ImageOverlay,
    OutputSettings,
    Panel,
    Project,
    Quality,
    SequenceSettings,
    Source,
    SpeedChoice,
    TextOverlay,
    Workflow,
)
from vid_editor.overlays import IMAGE_TYPES, LOGO_FOLDER, image_patch, text_patch
from vid_editor.sequence import on_show
from vid_editor.timing import frame_at, source_speed, step_frames
from vid_editor.render import (
    EditError,
    draft_project,
    fit_within,
    frame_hints,
    geometry,
    legacy_panels,
    open_source,
    output_rate,
    preview,
    render,
    render_draft,
    sequence_frame_hints,
    sequence_geometry,
    sequence_preview,
    sequence_silence_reason,
    sequence_spans,
    silence_reason,
    source_info,
    source_sizes,
    span_of,
    speeds,
    starting_panel,
)
from vid_editor.layout import width_for_height

st.set_page_config(page_title="Video editor", page_icon=":material/movie_edit:", layout="wide")

# The Preview is sent to the browser no larger than this many pixels, and shown
# no taller than a share of the window, so a tall Source fits without scrolling.
PREVIEW_BOX = (1280, 800)
st.html(
    "<style>.st-key-preview img "
    "{max-height: 55vh; object-fit: contain; object-position: left top;}</style>"
)

# Each Source and each Panel on the screen has a number of its own, counted
# from 1, that its settings are kept under. These stand for "no Audio Panel"
# and "a new Panel" in lists of Panels.
NO_SOUND = 0
NEW_PANEL = 0

OVERLAY_DEFAULTS = {
    "text_on": False,
    "text_value": "Proprietary – Do Not Distribute",
    "text_size": 30,
    "text_corner": Corner.BOTTOM_LEFT,
    "image_on": False,
    "image_path": "",
    "image_corner": Corner.TOP_LEFT,
    "image_width": 25.0,
    "image_opacity": 0.5,
}


@st.cache_resource(max_entries=16, on_release=lambda clip: clip.close(), show_spinner="Opening video")
def cached_source(path: str, modified: float):
    """An opened Source, reused across reruns until the file changes."""
    return open_source(path)


def opened(path: str):
    if not Path(path).is_file():
        raise EditError(f"No file found at {path}")
    return cached_source(path, Path(path).stat().st_mtime)


def clean(path: str) -> str:
    return path.strip().strip('"')


PANEL_KEYS = ("pn_row", "pn_width", "pn_height")


def add_panel(row: int = 1, width: int | None = None, height: int | None = None) -> int:
    """Put a Panel at the end of the list, which is the right-hand end of its Row.

    A Panel made for a new Source has no size until that Source's file has
    been opened and its size is known.
    """
    state = st.session_state
    panel_id = state.get("next_panel_id", 1)
    state.next_panel_id = panel_id + 1
    state.panel_ids = [*state.get("panel_ids", []), panel_id]
    state[f"pn_row_{panel_id}"] = row
    state[f"pn_width_{panel_id}"] = width
    state[f"pn_height_{panel_id}"] = height
    return panel_id


def add_empty_panel() -> None:
    """Add a Panel beside the last one: its Row's height, and the same width."""
    state = st.session_state
    sized = [panel_id for panel_id in state.panel_ids if state[f"pn_width_{panel_id}"]]
    if not sized:
        return
    last = sized[-1]
    row = state[f"pn_row_{last}"]
    row_height = max(
        state[f"pn_height_{panel_id}"] for panel_id in sized if state[f"pn_row_{panel_id}"] == row
    )
    add_panel(row, state[f"pn_width_{last}"], row_height)


def remove_panel(panel_id: int) -> None:
    state = st.session_state
    state.panel_ids = [other for other in state.panel_ids if other != panel_id]
    for key in PANEL_KEYS:
        state.pop(f"{key}_{panel_id}", None)


def move_panel(panel_id: int, step: int) -> None:
    """List a Panel earlier or later, which moves it left or right in its Row."""
    panel_ids = list(st.session_state.panel_ids)
    position = panel_ids.index(panel_id)
    target = min(max(position + step, 0), len(panel_ids) - 1)
    panel_ids.insert(target, panel_ids.pop(position))
    st.session_state.panel_ids = panel_ids


def panel_of(source_id: int) -> int:
    return st.session_state[f"in_panel_{source_id}"]


def empty_panels() -> list[int]:
    state = st.session_state
    held = {panel_of(source_id) for source_id in state.get("source_ids", [])}
    return [panel_id for panel_id in state.get("panel_ids", []) if panel_id not in held]


def assign_panel(source_id: int) -> None:
    """Move a Source into the Panel picked in its tab. The Panel it leaves stays, empty."""
    st.session_state[f"in_panel_{source_id}"] = st.session_state[f"panel_pick_{source_id}"]


def set_resize(source_id: int, width: int) -> None:
    st.session_state[f"source_width_{source_id}"] = width


def add_source(path: str, kept: dict | None = None, panel_id: int | None = None) -> int:
    """Add a Source, in a new Panel at the right-hand end of Row 1 unless one is given.

    `kept` holds settings from a Project file. They wait there until the
    Source's file is opened, which may be after it has been located.
    """
    state = st.session_state
    source_id = state.get("next_source_id", 1)
    state.next_source_id = source_id + 1
    state.source_ids = [*state.get("source_ids", []), source_id]
    state[f"path_{source_id}"] = path
    state[f"kept_{source_id}"] = kept or {}
    state[f"in_panel_{source_id}"] = add_panel() if panel_id is None else panel_id
    return source_id


def remove_source(source_id: int) -> None:
    """Take a Source away. Its Panel stays where it is, empty."""
    state = st.session_state
    state.source_ids = [other for other in state.source_ids if other != source_id]
    for key in ("path", "kept", "in_panel"):
        state.pop(f"{key}_{source_id}", None)
    if not state.source_ids:
        # With the last Source gone the layout goes too, and the next Source
        # added sets the Output up afresh.
        for panel_id in list(state.get("panel_ids", [])):
            remove_panel(panel_id)
        for key in (
            "lead_in",
            "lead_out",
            "out_width",
            "out_rate",
            "out_folder",
            "out_name",
            "seq_width",
            "seq_height",
        ):
            state.pop(key, None)
        state.audio_chosen = False
        state.legacy_rows = None


def move_source(source_id: int, step: int) -> None:
    """Move a Source earlier or later in the play order, which is the order of the Sources."""
    source_ids = list(st.session_state.source_ids)
    position = source_ids.index(source_id)
    target = min(max(position + step, 0), len(source_ids) - 1)
    source_ids.insert(target, source_ids.pop(position))
    st.session_state.source_ids = source_ids


def new_project() -> None:
    """Clear the screen. The workflow chosen stays as it is."""
    state = st.session_state
    for source_id in list(state.get("source_ids", [])):
        remove_source(source_id)
    for key in (*project_file.SHARED_KEYS, "audio_pick", "last_render", "draft", "seq_time"):
        if key != "workflow":
            state.pop(key, None)
    state.update(
        project_path=None, saved_text=None, saved_at=None, audio_chosen=False
    )


def browse_to_add() -> None:
    state = st.session_state
    source_ids = state.get("source_ids", [])
    start = str(Path(state[f"path_{source_ids[-1]}"]).parent) if source_ids else ""
    chosen = dialogs.pick_file(start)
    if chosen:
        state.add_path = chosen


def browse_to_locate(source_id: int) -> None:
    current = st.session_state[f"path_{source_id}"]
    chosen = dialogs.pick_file(str(Path(current).parent))
    if chosen:
        st.session_state[f"path_{source_id}"] = chosen


def browse_output_folder() -> None:
    chosen = dialogs.pick_folder(st.session_state.get("out_folder", ""))
    if chosen:
        st.session_state.out_folder = chosen


def browse_image() -> None:
    current = st.session_state.get("image_path", "")
    chosen = dialogs.pick_image(str(Path(current).parent) if current else str(LOGO_FOLDER))
    if chosen:
        st.session_state.image_path = chosen


def use_logo() -> None:
    if st.session_state.logo_pick:
        st.session_state.image_path = str(st.session_state.logo_pick)


def turn(source_id: int, degrees: float) -> None:
    key = f"rotation_{source_id}"
    st.session_state[key] = (st.session_state[key] + degrees) % 360


def step_sync_point(source_id: int, frames: int, rate: float, frame_count: int) -> None:
    """Refine a Sync Point frame by frame. The refined time replaces the typed one."""
    key = f"sync_point_{source_id}"
    st.session_state[key] = step_frames(st.session_state[key], frames, rate, frame_count)
    # The Preview moves to the Sync Event, where it shows the frame stepped to.
    st.session_state.preview_offset = 0.0


def step_trim(
    source_id: int, name: str, frames: int, rate: float, frame_count: int, duration: float
) -> None:
    """Move a Start Point or End Point frame by frame. An End Point not set starts at the end."""
    key = f"{name}_{source_id}"
    current = st.session_state[key]
    st.session_state[key] = step_frames(
        duration if current is None else current, frames, rate, frame_count
    )
    # The Preview moves to where the Source starts or ends.
    st.session_state.seq_focus = (source_id, name)


def set_seq_time(output_time: float) -> None:
    st.session_state.seq_time = output_time


def audio_was_chosen() -> None:
    st.session_state.audio_chosen = True


def project_folder() -> str:
    """Where a Project dialog starts: beside the Project file, or else the first Source."""
    state = st.session_state
    source_ids = state.get("source_ids", [])
    current = state.get("project_path") or (state[f"path_{source_ids[0]}"] if source_ids else "")
    return str(Path(current).parent) if current else ""


def open_project() -> None:
    chosen = dialogs.pick_project(project_folder())
    if not chosen:
        return
    try:
        settings = project_file.load(chosen)
    except EditError as error:
        st.session_state.project_error = str(error)
        return
    state = st.session_state
    new_project()
    state.workflow = settings.shared.get("workflow", Workflow.GRID)
    if settings.panels is None:
        # From before typed Panels. Each Source gets a Panel of its own, sized
        # by the old rules once every file is open. Under those rules only the
        # first Source's resize counted.
        legacy_rows = {}
        for position, source in enumerate(settings.sources):
            kept = {key: source[key] for key in project_file.SOURCE_KEYS if key in source}
            if position:
                kept["source_width"] = None
            legacy_rows[add_source(source["path"], kept)] = source["row"]
        state.legacy_rows = legacy_rows
    else:
        panel_ids = [
            add_panel(panel["row"], panel["width"], panel["height"]) for panel in settings.panels
        ]
        for source in settings.sources:
            kept = {key: source[key] for key in project_file.SOURCE_KEYS if key in source}
            add_source(source["path"], kept, panel_ids[source["panel"]])
    state.update(settings.shared)
    state.audio_pick = (
        NO_SOUND if settings.audio_panel is None else state.panel_ids[settings.audio_panel]
    )
    state.audio_chosen = True
    state.project_path = chosen


def save_project_as() -> None:
    chosen = dialogs.pick_project_to_save(project_folder())
    if chosen:
        if Path(chosen).suffix.lower() != project_file.EXTENSION:
            chosen += project_file.EXTENSION
        st.session_state.update(
            project_path=chosen, saved_text=None, saved_at=None
        )


def show_project_status(slot) -> None:
    state = st.session_state
    if state.get("project_path"):
        saved = f"; last saved at {state.saved_at}" if state.get("saved_at") else ""
        slot.caption(f"Project file: {state.project_path}. Every change is saved automatically{saved}.")
    else:
        slot.caption(
            "This Project is not saved. Choose Save Project as to keep its settings in a file."
        )


state = st.session_state
state.setdefault("source_ids", [])
state.setdefault("panel_ids", [])
state.setdefault("workflow", Workflow.GRID)
# The switch is drawn on every run, but its value is kept alive like the others.
state.workflow = state.workflow
grid = state.workflow is Workflow.GRID

# A path typed or browsed for is added as a Source here, before the box that
# holds it is drawn, so that the box can be emptied again.
new_path = clean(state.get("add_path", ""))
if new_path:
    state.add_path = ""
    try:
        opened(new_path)
    except EditError as error:
        state.add_error = str(error)
    else:
        into = state.get("add_into", NEW_PANEL) if grid else NEW_PANEL
        add_source(new_path, panel_id=into if into in empty_panels() else None)
        state.add_into = NEW_PANEL

st.title("Video editor")

# -------------------------------------------------------------------- Project
with st.container(horizontal=True, vertical_alignment="center"):
    st.button("New Project", icon=":material/note_add:", on_click=new_project, key="new_project")
    st.button(
        "Open Project", icon=":material/file_open:", on_click=open_project, key="open_project"
    )
    st.button(
        "Save Project as",
        icon=":material/save_as:",
        on_click=save_project_as,
        key="save_project_as",
        disabled=not state.source_ids,
    )
    project_status = st.empty()
show_project_status(project_status)
if project_error := state.pop("project_error", None):
    st.error(project_error, icon=":material/error:")

# ------------------------------------------------------------------- Workflow
st.segmented_control(
    "Workflow",
    list(Workflow),
    key="workflow",
    format_func=lambda workflow: workflow.value,
    required=True,
    help="A Synced grid shows the same event from several Sources at once, each in its own "
    "Panel, aligned on the Sync Event. A Sequence shows its Sources one after another in one "
    "Panel. Switching keeps the Sources and their picture settings, and keeps the other "
    "workflow's settings for when you switch back.",
)
if grid:
    st.caption(
        "Synced grid: each Source in its own Panel, all aligned on the Sync Event."
    )
else:
    st.caption(
        "Sequence: the Sources play one after another, in the order of their tabs, "
        "each from its Start Point to its End Point. To show a Sequence in a grid, render it "
        "and add the file to a grid as a Source."
    )

# -------------------------------------------------------------- Add a Source
with st.container(horizontal=True, vertical_alignment="bottom"):
    st.text_input(
        "Add a Source file",
        key="add_path",
        placeholder=r"C:\videos\camera_a.mp4",
        help="Type or paste the path of a video file on this computer and press Enter, "
        "or use Browse. "
        + (
            "Each Source added gets a new Panel at the right-hand end of "
            "Row 1, unless an empty Panel is chosen for it."
            if grid
            else "Each Source added plays after the ones before it."
        ),
    )
    st.button("Browse", icon=":material/folder_open:", on_click=browse_to_add, key="browse_source")
    if grid and empty_panels():
        listed = state.panel_ids
        if state.get("add_into") not in (NEW_PANEL, *empty_panels()):
            state.add_into = NEW_PANEL
        st.selectbox(
            "Into",
            [NEW_PANEL, *empty_panels()],
            key="add_into",
            format_func=lambda choice: (
                "A new Panel" if choice == NEW_PANEL else f"Panel {listed.index(choice) + 1} (empty)"
            ),
            width=220,
            help="Which Panel the next Source added goes into.",
        )
if add_error := state.pop("add_error", None):
    st.error(add_error, icon=":material/error:")

source_ids: list[int] = state.source_ids
if not source_ids:
    st.info("Add a Source file to begin.", icon=":material/video_file:")
    st.stop()

# ------------------------------------------------------------ Open the Sources
paths = {source_id: clean(state[f"path_{source_id}"]) for source_id in source_ids}
numbers = {source_id: position + 1 for position, source_id in enumerate(source_ids)}
clips, infos, problems = {}, {}, {}
for source_id in source_ids:
    try:
        clips[source_id] = opened(paths[source_id])
    except EditError as error:
        problems[source_id] = str(error)
        continue
    info = infos[source_id] = source_info(clips[source_id])
    # A Source new to the screen starts from its file. One that an opened
    # Project was holding settings for takes those instead.
    kept = state.get(f"kept_{source_id}", {})
    fresh = {
        "sync_point": 0.0,
        "rotation": 0.0,
        "crop_top": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "source_width": None,
        "record_rate": None,
        "aspect_on": False,
        "aspect_width": info.width,
        "aspect_height": info.height,
        "start_point": 0.0,
        "end_point": None,
        "play_speed": 1.0,
    }
    for name, value in fresh.items():
        if f"{name}_{source_id}" not in state:
            state[f"{name}_{source_id}"] = kept.get(name, value)
        # Kept alive across runs in which the workflow chosen does not draw its control.
        state[f"{name}_{source_id}"] = state[f"{name}_{source_id}"]
    for name in ("sync_point", "start_point"):
        state[f"{name}_{source_id}"] = min(state[f"{name}_{source_id}"], info.duration)
    end_key = f"end_point_{source_id}"
    if state[end_key] is not None:
        state[end_key] = min(state[end_key], info.duration)

def as_source(source_id: int, values: dict, panel: int = 0) -> Source:
    """A Source as the model has it, from its settings on the screen."""
    return Source(
        path=paths[source_id],
        sync_point=values["sync_point"],
        rotation=values["rotation"],
        crop=Crop(
            values["crop_top"], values["crop_bottom"], values["crop_left"], values["crop_right"]
        ),
        aspect_override=(
            (values["aspect_width"], values["aspect_height"]) if values["aspect_on"] else None
        ),
        width=values["source_width"],
        record_rate=values["record_rate"],
        panel=panel,
        start_point=values["start_point"],
        end_point=values["end_point"],
        play_speed=values["play_speed"],
    )


def on_screen(source_id: int) -> dict:
    return {name: state[f"{name}_{source_id}"] for name in project_file.SOURCE_KEYS}


def cropped_size(source_id: int) -> tuple[int, int] | None:
    """A Source's size after its rotation and crop, or None while those cannot be applied."""
    info = infos[source_id]
    try:
        return source_sizes((info.width, info.height), as_source(source_id, on_screen(source_id)))[0]
    except EditError:
        return None


# ------------------------------------------------------------- Size the Panels
panel_ids: list[int] = state.panel_ids
panel_numbers = {panel_id: position + 1 for position, panel_id in enumerate(panel_ids)}
holders = {panel_of(source_id): source_id for source_id in source_ids}

if state.get("legacy_rows") and not problems:
    # A Project from before typed Panels: give each Source's Panel the size
    # the old rules gave it, so the Output is the one the Project made before.
    try:
        old_panels = legacy_panels(
            [as_source(source_id, on_screen(source_id)) for source_id in source_ids],
            [clips[source_id] for source_id in source_ids],
            [state.legacy_rows[source_id] for source_id in source_ids],
        )
    except EditError:
        old_panels = [starting_panel(cropped_size(source_id) or (2, 2)) for source_id in source_ids]
    for source_id, old in zip(source_ids, old_panels):
        panel_id = panel_of(source_id)
        state[f"pn_row_{panel_id}"] = old.row
        state[f"pn_width_{panel_id}"] = old.width
        state[f"pn_height_{panel_id}"] = old.height
    # A Row the old layout left black at its end keeps that place, as an empty Panel.
    for old in old_panels[len(source_ids) :]:
        add_panel(old.row, old.width, old.height)
    panel_ids = state.panel_ids
    panel_numbers = {panel_id: position + 1 for position, panel_id in enumerate(panel_ids)}
    state.legacy_rows = None

for panel_id in panel_ids:
    holder = holders.get(panel_id)
    if state[f"pn_width_{panel_id}"] or holder not in clips or state.get("legacy_rows"):
        continue
    # A Panel made for a new Source starts at its Row's height and the width
    # that fits the Source. The first Panel of all starts at its Source's size.
    row = state[f"pn_row_{panel_id}"]
    row_heights = [
        state[f"pn_height_{other}"]
        for other in panel_ids
        if state[f"pn_height_{other}"] and state[f"pn_row_{other}"] == row
    ]
    start = starting_panel(
        cropped_size(holder) or (infos[holder].width, infos[holder].height),
        max(row_heights) if row_heights else None,
    )
    state[f"pn_width_{panel_id}"], state[f"pn_height_{panel_id}"] = start.width, start.height

sized_panels = [panel_id for panel_id in panel_ids if state[f"pn_width_{panel_id}"]]
# Kept alive across runs in which their controls are not drawn.
for panel_id in panel_ids:
    for key in PANEL_KEYS:
        state[f"{key}_{panel_id}"] = state[f"{key}_{panel_id}"]

# The first Source sets the Output up. Overlays start switched off.
first_id = source_ids[0]
first_path = Path(paths[first_id])
for key, value in {
    "lead_in": 0.0,
    "lead_out": round(infos[first_id].duration, 3) if first_id in infos else 10.0,
    "out_width": None,
    "out_rate": None,
    "speed_choice": SpeedChoice.SLOWEST,
    "speed_custom": 1.0,
    "quality": Quality.MEDIUM,
    "out_folder": str(first_path.parent),
    "out_name": f"{first_path.stem}_edited.mp4",
    "preview_offset": 0.0,
    "last_render": None,
    "draft": None,
    "draft_lead_in": DraftSettings.lead_in,
    "draft_lead_out": DraftSettings.lead_out,
    "draft_width": DraftSettings.width,
    "draft_sound": DraftSettings.sound,
    **OVERLAY_DEFAULTS,
}.items():
    state.setdefault(key, value)
# The Sequence's one Panel starts at the first Source's size after its rotation and crop.
if state.get("seq_width") is None and first_id in infos:
    first_size = cropped_size(first_id) or (infos[first_id].width, infos[first_id].height)
    state.seq_width, state.seq_height = max(2, first_size[0]), max(2, first_size[1])
state.setdefault("seq_time", 0.0)
# The Draft settings sit below the Preview, which is not drawn while something
# is wrong, and each workflow's settings are not drawn while the other is
# chosen. Setting them here keeps them from being forgotten in the meantime.
for key in (
    "draft_lead_in",
    "draft_lead_out",
    "draft_width",
    "draft_sound",
    "lead_in",
    "lead_out",
    "speed_choice",
    "speed_custom",
    "preview_offset",
    "seq_time",
):
    state[key] = state[key]
for key in ("seq_width", "seq_height"):
    if key in state:
        state[key] = state[key]


def source_label(source_id: int) -> str:
    return f"Source {numbers[source_id]}: {Path(paths[source_id]).name}"


def panel_label(panel_id: int) -> str:
    holder = holders.get(panel_id)
    return f"Panel {panel_numbers[panel_id]}: " + ("empty" if holder is None else source_label(holder))


# The Audio Panel is the first Panel whose Source has sound, until the user chooses.
with_sound = [
    panel_id
    for panel_id in panel_ids
    if holders.get(panel_id) in infos and infos[holders[panel_id]].has_sound
]
audio_options = [NO_SOUND] + [
    panel_id
    for panel_id in panel_ids
    if panel_id in with_sound
    or (holders.get(panel_id) in problems and panel_id == state.get("audio_pick"))
]
if not state.get("audio_chosen") or state.get("audio_pick") not in audio_options:
    state.audio_pick = with_sound[0] if with_sound else NO_SOUND
state.audio_pick = state.audio_pick  # kept while a Sequence hides it

settings, result = st.columns([5, 6], gap="large")

# ------------------------------------------------------------------- Settings
size_hints, frame_hint_slots, panel_hints, trim_hints = {}, {}, {}, {}
sequence_hint = None
with settings:
    if grid:
        with st.container(border=True):
            st.subheader("Layout")
            st.caption(
                "Panels that share a Row sit side by side, in the order listed here. A Row is as "
                "tall as its tallest Panel, and the Output is as wide as its widest Row."
            )
            for position, panel_id in enumerate(panel_ids):
                st.markdown(f"**{panel_label(panel_id)}**")
                if panel_id not in sized_panels:
                    st.caption("This Panel gets its size once its Source's file is located.")
                    continue
                columns = st.columns([2, 3, 3, 1, 1, 1], vertical_alignment="bottom")
                columns[0].number_input(
                    "Row",
                    key=f"pn_row_{panel_id}",
                    min_value=1,
                    max_value=max(1, len(panel_ids)),
                    step=1,
                    help="Row 1 is the top of the Output. Only the order of the numbers counts.",
                )
                columns[1].number_input(
                    "Width (px)", key=f"pn_width_{panel_id}", min_value=2, step=2
                )
                columns[2].number_input(
                    "Height (px)", key=f"pn_height_{panel_id}", min_value=2, step=2
                )
                columns[3].button(
                    "",
                    icon=":material/arrow_upward:",
                    key=f"panel_up_{panel_id}",
                    on_click=move_panel,
                    args=(panel_id, -1),
                    disabled=position == 0,
                    help="List this Panel earlier, which moves it left in its Row.",
                )
                columns[4].button(
                    "",
                    icon=":material/arrow_downward:",
                    key=f"panel_down_{panel_id}",
                    on_click=move_panel,
                    args=(panel_id, 1),
                    disabled=position == len(panel_ids) - 1,
                    help="List this Panel later, which moves it right in its Row.",
                )
                columns[5].button(
                    "",
                    icon=":material/delete:",
                    key=f"panel_remove_{panel_id}",
                    on_click=remove_panel,
                    args=(panel_id,),
                    disabled=panel_id in holders,
                    help="Remove this Panel. Only an empty Panel can be removed.",
                )
                panel_hints[panel_id] = st.empty()
            st.button(
                "Add a Panel",
                icon=":material/add:",
                key="add_panel",
                on_click=add_empty_panel,
                help="An empty Panel beside the last one, at its Row's height and the same width. "
                "An empty Panel is black in the Output until a Source is put in it.",
            )
    else:
        with st.container(border=True):
            st.subheader("Sequence Panel")
            st.caption(
                "Every Source is shown in this one Panel, in turn. It started at the first "
                "Source's size; it changes only when retyped."
            )
            seq_columns = st.columns(2)
            seq_columns[0].number_input("Width (px)", key="seq_width", min_value=2, step=2)
            seq_columns[1].number_input("Height (px)", key="seq_height", min_value=2, step=2)
            sequence_hint = st.empty()

    with st.container(border=True):
        st.subheader("Sources")
        tabs = st.tabs([source_label(source_id) for source_id in source_ids])
        for tab, source_id in zip(tabs, source_ids):
            with tab:
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    st.text_input(
                        "File",
                        key=f"path_{source_id}",
                        help="Change this only when the file has moved. The Source keeps its settings.",
                    )
                    st.button(
                        "Browse",
                        icon=":material/folder_open:",
                        on_click=browse_to_locate,
                        args=(source_id,),
                        key=f"locate_{source_id}",
                    )
                    st.button(
                        "Remove",
                        icon=":material/delete:",
                        on_click=remove_source,
                        args=(source_id,),
                        key=f"remove_{source_id}",
                    )
                    if not grid:
                        st.button(
                            "Earlier",
                            icon=":material/arrow_back:",
                            on_click=move_source,
                            args=(source_id, -1),
                            key=f"earlier_{source_id}",
                            disabled=source_id == source_ids[0],
                            help="Play this Source before the one now before it.",
                        )
                        st.button(
                            "Later",
                            icon=":material/arrow_forward:",
                            on_click=move_source,
                            args=(source_id, 1),
                            key=f"later_{source_id}",
                            disabled=source_id == source_ids[-1],
                            help="Play this Source after the one now after it.",
                        )
                if source_id in problems:
                    st.error(problems[source_id], icon=":material/error:")
                    st.info(
                        "The Project keeps this Source's settings. Choose where the file is now.",
                        icon=":material/search:",
                    )
                    continue

                info = infos[source_id]
                st.caption(
                    f"{info.width} by {info.height} pixels, {info.duration:.3f} s long, "
                    f"Playback Rate {info.playback_rate:g} frames per second, "
                    f"{'has sound' if info.has_sound else 'no sound'}."
                )
                if grid:
                    st.number_input(
                        "Sync Point (s)",
                        key=f"sync_point_{source_id}",
                        min_value=0.0,
                        max_value=info.duration,
                        step=0.1,
                        format="%.3f",
                        help="The time in this file at which the Sync Event is seen. Type it from "
                        "a video player, then refine it with the frame buttons.",
                    )
                    with st.container(horizontal=True):
                        for name, frames, label in (
                            ("back_10", -10, "−10 frames"),
                            ("back_1", -1, "−1 frame"),
                            ("forward_1", 1, "+1 frame"),
                            ("forward_10", 10, "+10 frames"),
                        ):
                            st.button(
                                label,
                                key=f"step_{name}_{source_id}",
                                on_click=step_sync_point,
                                args=(source_id, frames, info.playback_rate, info.frame_count),
                            )
                    sync_frame = frame_at(state[f"sync_point_{source_id}"], info.playback_rate)
                    st.caption(
                        f"The Sync Point is in frame {sync_frame + 1} of {info.frame_count}, which the "
                        f"file shows from {sync_frame / info.playback_rate:.3f} to "
                        f"{(sync_frame + 1) / info.playback_rate:.3f} s. "
                        "Stepping moves the Preview to the Sync Event."
                    )
                else:
                    trim_columns = st.columns(2)
                    trim_columns[0].number_input(
                        "Start Point (s)",
                        key=f"start_point_{source_id}",
                        min_value=0.0,
                        max_value=info.duration,
                        step=0.1,
                        format="%.3f",
                        help="The time in this file at which this Source starts to play.",
                    )
                    trim_columns[1].number_input(
                        "End Point (s)",
                        key=f"end_point_{source_id}",
                        value=None,
                        min_value=0.0,
                        max_value=info.duration,
                        step=0.1,
                        format="%.3f",
                        placeholder=f"End of the file ({info.duration:.3f})",
                        help="The time in this file at which the next Source takes over. "
                        "Leave empty to play to the end of the file.",
                    )
                    for column, name in zip(trim_columns, ("start_point", "end_point")):
                        with column.container(horizontal=True):
                            for step_name, frames, label in (
                                ("back_10", -10, "−10"),
                                ("back_1", -1, "−1"),
                                ("forward_1", 1, "+1"),
                                ("forward_10", 10, "+10"),
                            ):
                                st.button(
                                    label,
                                    key=f"step_{name}_{step_name}_{source_id}",
                                    on_click=step_trim,
                                    args=(
                                        source_id,
                                        name,
                                        frames,
                                        info.playback_rate,
                                        info.frame_count,
                                        info.duration,
                                    ),
                                    help=f"Move the {name.replace('_', ' ').title()} "
                                    f"{label} frame{'s' if abs(frames) > 1 else ''}. "
                                    "The Preview moves there.",
                                )
                    st.number_input(
                        "Play Speed",
                        key=f"play_speed_{source_id}",
                        min_value=0.01,
                        max_value=100.0,
                        step=0.25,
                        format="%.3g",
                        help="1 plays the file as it is. 0.5 plays it at half speed, taking twice "
                        "as long; 2 at double speed. Sound is kept only at 1.",
                    )
                    trim_hints[source_id] = st.empty()
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    st.number_input(
                        "Rotation (degrees, anticlockwise)",
                        key=f"rotation_{source_id}",
                        min_value=0.0,
                        max_value=360.0,
                        step=1.0,
                        format="%.1f",
                        help="Any angle. Angles that are not quarter turns leave black corners to crop away.",
                    )
                    st.button(
                        "Turn left",
                        icon=":material/rotate_left:",
                        on_click=turn,
                        args=(source_id, 90),
                        key=f"turn_left_{source_id}",
                    )
                    st.button(
                        "Turn right",
                        icon=":material/rotate_right:",
                        on_click=turn,
                        args=(source_id, -90),
                        key=f"turn_right_{source_id}",
                    )

                if grid:
                    # Without value=None a field that holds a number cannot be emptied
                    # again: Streamlit puts its smallest allowed value there instead.
                    record_rate = st.number_input(
                        "Record Rate (frames per second)",
                        key=f"record_rate_{source_id}",
                        value=None,
                        min_value=0.001,
                        step=1.0,
                        placeholder=f"Same as the Playback Rate ({info.playback_rate:g}): real time",
                        help="How many frames per second the camera captured of the real world. "
                        "Leave empty for a real-time file. Fill it in for slow motion (higher than "
                        "the Playback Rate) or timelapse (lower).",
                    )
                    own_speed = source_speed(info.playback_rate, record_rate)
                    if own_speed == 1:
                        st.caption("Source Speed 1: this file shows the real event in real time.")
                    else:
                        st.caption(
                            f"Source Speed {own_speed:.3g} (Playback Rate {info.playback_rate:g} "
                            f"divided by Record Rate {record_rate:g}): 1 s of this file shows "
                            f"{own_speed:.3g} s of the real event."
                        )
                frame_hint_slots[source_id] = st.empty()

                st.markdown("Crop (pixels, measured after rotation)")
                crop_columns = st.columns(4)
                for column, edge in zip(crop_columns, ("top", "bottom", "left", "right")):
                    column.number_input(
                        edge.capitalize(), key=f"crop_{edge}_{source_id}", min_value=0, step=10
                    )

                own_panel = panel_of(source_id)
                if grid:
                    state[f"panel_pick_{source_id}"] = own_panel
                    st.selectbox(
                        "Panel",
                        [own_panel, *empty_panels()],
                        key=f"panel_pick_{source_id}",
                        format_func=lambda panel_id: f"Panel {panel_numbers[panel_id]}",
                        on_change=assign_panel,
                        args=(source_id,),
                        help="The Panel this Source is shown in. It can be moved into any empty "
                        "Panel; the Panel it leaves stays in the layout, empty.",
                    )
                    own_size = (
                        (state[f"pn_width_{own_panel}"], state[f"pn_height_{own_panel}"])
                        if own_panel in sized_panels
                        else None
                    )
                else:
                    own_size = (state.seq_width, state.seq_height)
                cropped = cropped_size(source_id)
                can_scale = cropped is not None and own_size is not None
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    st.number_input(
                        "Resize to width (px)",
                        key=f"source_width_{source_id}",
                        value=None,
                        min_value=2,
                        step=10,
                        placeholder="Fitted inside its Panel",
                        help="Leave empty to fit the Source inside its Panel. Applied after the "
                        "crop; the height follows without distortion. A Source smaller than its "
                        "Panel gets Bars, and one larger is cut off evenly at both sides.",
                    )
                    st.button(
                        "Scale width to Panel",
                        key=f"scale_width_{source_id}",
                        on_click=set_resize,
                        args=(source_id, own_size[0] if can_scale else 0),
                        disabled=not can_scale,
                        help="Fills in the width that makes this Source as wide as its Panel. "
                        "It acts once: press it again after changing the crop or the Panel.",
                    )
                    st.button(
                        "Scale height to Panel",
                        key=f"scale_height_{source_id}",
                        on_click=set_resize,
                        args=(
                            source_id,
                            width_for_height(cropped, own_size[1])
                            if can_scale
                            else 0,
                        ),
                        disabled=not can_scale,
                        help="Fills in the width that makes this Source as high as its Panel. "
                        "It acts once: press it again after changing the crop or the Panel.",
                    )
                size_hints[source_id] = st.empty()

                with st.expander("Advanced"):
                    aspect_on = st.toggle(
                        "Override aspect ratio",
                        key=f"aspect_on_{source_id}",
                        help="Force a width and height for a file that plays stretched. Applied before rotation.",
                    )
                    aspect_columns = st.columns(2)
                    aspect_columns[0].number_input(
                        "Forced width (px)",
                        key=f"aspect_width_{source_id}",
                        min_value=2,
                        disabled=not aspect_on,
                    )
                    aspect_columns[1].number_input(
                        "Forced height (px)",
                        key=f"aspect_height_{source_id}",
                        min_value=2,
                        disabled=not aspect_on,
                    )

    with st.container(border=True):
        st.subheader("Output")
        if grid:
            lead_columns = st.columns(2)
            lead_columns[0].number_input(
                "Lead-in (s)",
                key="lead_in",
                min_value=0.0,
                step=0.5,
                format="%.3f",
                help="Output running time from the start of the Output to the Sync Event.",
            )
            lead_columns[1].number_input(
                "Lead-out (s)",
                key="lead_out",
                min_value=0.0,
                step=0.5,
                format="%.3f",
                help="Output running time from the Sync Event to the end of the Output.",
            )
        size_columns = st.columns(2)
        size_columns[0].number_input(
            "Output width (px)",
            key="out_width",
            value=None,
            min_value=2,
            step=2,
            placeholder="Natural size",
            help="Leave empty to keep the natural size. The height follows from the picture.",
        )
        size_columns[1].number_input(
            "Output Rate (frames per second)",
            key="out_rate",
            value=None,
            min_value=1.0,
            max_value=240.0,
            step=1.0,
            placeholder="Highest Playback Rate",
            help="Leave empty to use the highest Playback Rate among the Sources.",
        )
        if grid:
            speed_columns = st.columns(2)
            speed_columns[0].selectbox(
                "Output Speed",
                list(SpeedChoice),
                key="speed_choice",
                format_func=lambda choice: choice.value,
                help="How fast the Output shows the real event. Every Source is shown at this speed. "
                "Slowest Source drops no frame of any Source for being too slow. The Output keeps "
                "the same running time; a slower speed covers less of the real event.",
            )
            speed_columns[1].number_input(
                "Custom Output Speed (1 is real time)",
                key="speed_custom",
                min_value=0.001,
                step=0.05,
                format="%.3f",
                disabled=state.speed_choice != SpeedChoice.CUSTOM,
            )
            speed_hint = st.empty()
            st.selectbox(
                "Audio Panel",
                audio_options,
                key="audio_pick",
                format_func=lambda panel_id: "No sound" if panel_id == NO_SOUND else panel_label(panel_id),
                on_change=audio_was_chosen,
                help="The one Panel whose sound is used. Sound from every other Panel is discarded. "
                "The Output is silent during this Panel's Gaps.",
            )
            sound_hint = st.empty()
        else:
            st.caption(
                "Each Source keeps its own sound while it is on show. A Source with no sound, "
                "or whose Play Speed is not 1, is silent. The timing table says which."
            )
        st.segmented_control(
            "Quality",
            list(Quality),
            key="quality",
            format_func=lambda quality: quality.value,
            required=True,
        )
        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.text_input("Output folder", key="out_folder")
            st.button(
                "Browse", icon=":material/folder_open:", on_click=browse_output_folder, key="browse_folder"
            )
        st.text_input("Output file name", key="out_name")

    with st.container(border=True):
        st.subheader("Overlays")
        st.toggle(
            "Text Overlay",
            key="text_on",
            help="White text on a half-transparent black box, in one corner for the whole Output.",
        )
        text_off = not state.text_on
        st.text_area(
            "Text", key="text_value", height=68, disabled=text_off, help="Press Enter for a new line."
        )
        text_columns = st.columns(2)
        text_columns[0].number_input(
            "Text size (px)",
            key="text_size",
            min_value=4,
            step=2,
            disabled=text_off,
            help="Measured in Output pixels, so the same size looks larger on a narrower Output.",
        )
        text_columns[1].selectbox(
            "Text corner",
            list(Corner),
            key="text_corner",
            format_func=lambda corner: corner.value,
            disabled=text_off,
        )
        text_hint = st.empty()

        st.toggle(
            "Image Overlay",
            key="image_on",
            help="An image such as a logo on a black box, in one corner for the whole Output.",
        )
        image_off = not state.image_on
        logos = sorted(
            file for file in LOGO_FOLDER.glob("*") if file.suffix.lower() in IMAGE_TYPES
        )
        if logos:
            st.selectbox(
                "Quick pick from assets/logos",
                logos,
                key="logo_pick",
                index=None,
                format_func=lambda file: file.name,
                placeholder="Choose a logo",
                on_change=use_logo,
                disabled=image_off,
            )
        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.text_input("Image file", key="image_path", disabled=image_off)
            st.button(
                "Browse",
                icon=":material/folder_open:",
                on_click=browse_image,
                key="browse_image",
                disabled=image_off,
            )
        image_columns = st.columns(3)
        image_columns[0].selectbox(
            "Image corner",
            list(Corner),
            key="image_corner",
            format_func=lambda corner: corner.value,
            disabled=image_off,
        )
        image_columns[1].number_input(
            "Width (% of Output)",
            key="image_width",
            min_value=1.0,
            max_value=100.0,
            step=1.0,
            disabled=image_off,
            help="Width of the box holding the image, as a percentage of the Output width.",
        )
        image_columns[2].number_input(
            "Background opacity",
            key="image_opacity",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            disabled=image_off,
            help="The black box behind the image: 0 is clear, 1 is solid black.",
        )
        image_hint = st.empty()
        corner_warning = st.empty()

# ------------------------------------------------------ Settings as a Project
# Each Source's settings are also kept apart from its controls, which the
# screen forgets whenever they are not shown, as when its file cannot be found.
for source_id in clips:
    state[f"kept_{source_id}"] = {
        name: state[f"{name}_{source_id}"] for name in project_file.SOURCE_KEYS
    }
kept = {source_id: state.get(f"kept_{source_id}", {}) for source_id in source_ids}
quality = state.quality or Quality.MEDIUM
audio_panel = None if state.audio_pick == NO_SOUND else panel_ids.index(state.audio_pick)

# Every change is saved to the Project file, once the Project has one. A Panel
# still waiting for its size cannot be written down, so saving waits with it.
if state.get("project_path") and len(sized_panels) == len(panel_ids):
    project_text = project_file.dumps(
        project_file.ProjectSettings(
            sources=[
                {"path": paths[source_id], "panel": panel_ids.index(panel_of(source_id))}
                | kept[source_id]
                for source_id in source_ids
            ],
            shared={key: state[key] for key in project_file.SHARED_KEYS if key in state}
            | {"quality": quality},
            panels=[
                {
                    "row": state[f"pn_row_{panel_id}"],
                    "width": state[f"pn_width_{panel_id}"],
                    "height": state[f"pn_height_{panel_id}"],
                }
                for panel_id in panel_ids
            ],
            audio_panel=audio_panel,
        )
    )
    if project_text != state.get("saved_text"):
        try:
            project_file.write(state.project_path, project_text)
        except OSError as error:
            project_status.error(
                f"The Project could not be saved to {state.project_path}: {error}",
                icon=":material/error:",
            )
        else:
            state.saved_text = project_text
            state.saved_at = datetime.now().strftime("%H:%M:%S")
            show_project_status(project_status)

text_overlay = None
if state.text_on and state.text_value.strip():
    text_overlay = TextOverlay(text=state.text_value, size=state.text_size, corner=state.text_corner)
image_overlay = None
if state.image_on and state.image_path.strip():
    image_overlay = ImageOverlay(
        path=clean(state.image_path),
        corner=state.image_corner,
        width_percent=state.image_width,
        background_opacity=state.image_opacity,
    )
if state.text_on and text_overlay is None:
    text_hint.caption("Type some text to show the text Overlay.")
if state.image_on and image_overlay is None:
    image_hint.caption("Choose an image file to show the image Overlay.")
if text_overlay and image_overlay and text_overlay.corner == image_overlay.corner:
    corner_warning.warning(
        f"Both Overlays are in the {text_overlay.corner.value.lower()} corner, "
        "so the text is drawn over the image.",
        icon=":material/warning:",
    )

# -------------------------------------------------------- Preview and render
with result:
    st.subheader("Preview")
    if problems:
        missing = " and ".join(f"Source {numbers[source_id]}" for source_id in problems)
        st.error(f"Locate {missing} to see the Preview.", icon=":material/error:")
        st.stop()

    row_clips = [clips[source_id] for source_id in source_ids]
    project = Project(
        sources=tuple(
            as_source(source_id, values, panel_ids.index(panel_of(source_id)))
            for source_id, values in kept.items()
        ),
        panels=tuple(
            Panel(
                width=state[f"pn_width_{panel_id}"],
                height=state[f"pn_height_{panel_id}"],
                row=state[f"pn_row_{panel_id}"],
            )
            for panel_id in panel_ids
        ),
        output=OutputSettings(
            lead_in=state.lead_in,
            lead_out=state.lead_out,
            width=state.out_width,
            rate=state.out_rate,
            speed={
                SpeedChoice.SLOWEST: None,
                SpeedChoice.REAL_TIME: 1.0,
                SpeedChoice.CUSTOM: state.speed_custom,
            }[state.speed_choice],
            quality=quality,
            text_overlay=text_overlay,
            image_overlay=image_overlay,
        ),
        audio_panel=audio_panel,
        workflow=state.workflow,
        sequence=None if grid else SequenceSettings(state.seq_width, state.seq_height),
    )
    if grid and project.output.running_time <= 0:
        st.error("Lead-in plus Lead-out must be greater than zero.", icon=":material/error:")
        st.stop()

    rate = output_rate(project, row_clips)
    scaled = False
    if grid:
        state.preview_offset = min(max(state.preview_offset, -state.lead_in), state.lead_out)
        st.slider(
            "Time from the Sync Event (s)",
            key="preview_offset",
            min_value=-float(state.lead_in),
            max_value=float(state.lead_out),
            step=1 / rate,
            format="%.3f",
            help="0 shows every Source at its Sync Point. Negative is before the Sync Event.",
        )

        try:
            sizes = geometry(project, row_clips)
            speed = speeds(project, row_clips)
            hints = frame_hints(project, row_clips)
            silent_because = silence_reason(project, row_clips)
            frame = preview(project, row_clips, output_time=state.lead_in + state.preview_offset)
            spans = [
                span_of(clip, source, project, speed.output)
                for clip, source in zip(row_clips, project.sources)
            ]
        except (EditError, ValueError) as error:
            st.error(str(error), icon=":material/error:")
            st.stop()
        width, height = sizes.layout.width, sizes.layout.height

        # What the speeds do, shown beside the settings that cause it.
        running_time = project.output.running_time
        speed_hint.caption(
            f"Output Speed {speed.output:.3g}: the {running_time:.3f} s Output shows "
            f"{running_time * speed.output:.3f} s of the real event."
        )
        for source_id, hint in zip(source_ids, hints):
            frame_hint_slots[source_id].caption(
                f"Frame Hint at Output Speed {speed.output:.3g} and Output Rate {rate:g}: {hint}."
            )
        if silent_because and audio_panel is not None:
            sound_hint.warning(
                f"The Output has no sound, because {silent_because}. Sound is kept only when "
                "the Source in the Audio Panel and the Output Speed are both real time.",
                icon=":material/volume_off:",
            )

        # Each Panel's size in the Output, shown beside its typed size when they differ.
        scaled = abs(sizes.layout.scale - 1) > 1e-9
        for panel_id, box in zip(panel_ids, sizes.layout.boxes):
            if scaled:
                panel_hints[panel_id].caption(
                    f"{box.width} by {box.height} pixels in the Output "
                    f"({sizes.layout.scale:.0%} of the typed size)."
                )
    else:
        try:
            spans = sequence_spans(project, row_clips)
            sizes = sequence_geometry(project, row_clips)
            hints = sequence_frame_hints(project, row_clips)
        except (EditError, ValueError) as error:
            st.error(str(error), icon=":material/error:")
            st.stop()
        width, height = sizes.layout.width, sizes.layout.height
        running_time = spans[-1].output_end
        last_frame_time = max(0.0, running_time - 1 / rate)

        # A step of a Start Point or End Point moves the Preview to it.
        if focus := state.pop("seq_focus", None):
            focus_id, which = focus
            if focus_id in source_ids:
                span = spans[source_ids.index(focus_id)]
                state.seq_time = span.output_start if which == "start_point" else span.output_end - 1 / rate
        state.seq_time = min(max(float(state.seq_time), 0.0), last_frame_time)
        st.slider(
            "Time in the Output (s)",
            key="seq_time",
            min_value=0.0,
            max_value=max(last_frame_time, 1 / rate),
            step=1 / rate,
            format="%.3f",
            help="The Preview shows the Source on show at this time, at the frame it shows then.",
        )
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption("Go to the start of")
            for source_id, span in zip(source_ids, spans):
                st.button(
                    f"Source {numbers[source_id]}",
                    key=f"go_to_{source_id}",
                    on_click=set_seq_time,
                    args=(span.output_start,),
                    type="tertiary",
                )
        try:
            frame = sequence_preview(project, row_clips, state.seq_time)
        except (EditError, ValueError) as error:
            st.error(str(error), icon=":material/error:")
            st.stop()
        showing = source_ids[on_show(spans, state.seq_time)]

        for source_id, source, span, hint in zip(source_ids, project.sources, spans, hints):
            frame_hint_slots[source_id].caption(
                f"Frame Hint at Play Speed {source.play_speed:g} and Output Rate {rate:g}: {hint}."
            )
            trim_hints[source_id].caption(
                f"Plays {span.file_end - span.file_start:.3f} s of the file, from "
                f"{span.file_start:.3f} to {span.file_end:.3f} s, for {span.time_on_show:.3f} s: "
                f"from {span.output_start:.3f} to {span.output_end:.3f} s of the Output."
            )
        scaled = abs(sizes.layout.scale - 1) > 1e-9
        if scaled:
            sequence_hint.caption(
                f"{width} by {height} pixels in the Output "
                f"({sizes.layout.scale:.0%} of the typed size)."
            )

    def each_side(total: float, across: bool) -> str:
        return f"{total / 2:g} pixels " + ("left and right" if across else "above and below")

    # Each Source's size, and how it sits in its Panel, shown beside its settings.
    for position, source_id in enumerate(source_ids):
        cropped_width, cropped_height = sizes.cropped[position]
        picture = sizes.pictures[position]
        if grid:
            box = sizes.layout.boxes[panel_ids.index(panel_of(source_id))]
            panel_name = f"Panel {panel_numbers[panel_of(source_id)]}"
        else:
            box, panel_name = sizes.layout.boxes[0], "The Sequence Panel"
        typed_width = state[f"source_width_{source_id}"]
        hint = (
            f"After rotation and crop this Source is {cropped_width} by {cropped_height} pixels. "
            f"{panel_name} is {box.width} by {box.height} pixels. "
        )
        hint += (
            "Fitted inside it"
            if typed_width is None
            else f"At its resize width of {typed_width}"
        )
        hint += (
            f", the Source is {picture.width} by {picture.height} pixels "
            f"({picture.width / cropped_width:.0%} of that size)"
        )
        bars = [each_side(total, across) for total, across in zip(picture.bars, (True, False)) if total]
        cuts = [each_side(total, across) for total, across in zip(picture.cut, (True, False)) if total]
        if not bars and not cuts:
            hint += " and fills the Panel."
        else:
            if bars:
                hint += ", with Bars of " + " and ".join(bars)
            hint += "."
            if cuts:
                hint += " The Panel cuts off " + " and ".join(cuts) + "."
        crop_hint = picture.crop_hint
        if crop_hint is not None and typed_width is None:
            if crop_hint.width:
                remedy = f"crop {crop_hint.width} pixels of width, to {cropped_width - crop_hint.width} wide"
            else:
                remedy = f"crop {crop_hint.height} pixels of height, to {cropped_height - crop_hint.height} high"
            hint += f" Crop Hint: {remedy}, and it fills the Panel."
        elif crop_hint is not None:
            hidden = [
                f"{amount} pixels of the Source's {side}"
                for amount, side in ((crop_hint.width, "width"), (crop_hint.height, "height"))
                if amount
            ]
            hint += (
                " Crop Hint: what is cut off is " + " and ".join(hidden) + ", half from each "
                "side. Crop that much yourself to choose which part is kept."
            )
        if bars and typed_width is not None:
            hint += " Bars at a typed width go when the Source is scaled to the Panel."
        size_hints[source_id].caption(hint)

    # Each Overlay's size against the Output, shown beside its settings.
    for overlay, hint_slot, name in (
        (text_overlay, text_hint, "text"),
        (image_overlay, image_hint, "image"),
    ):
        if overlay is None:
            continue
        picture = text_patch(overlay) if name == "text" else image_patch(overlay, width)
        box_height, box_width = picture.shape[:2]
        if box_width > width or box_height > height:
            hint_slot.warning(
                f"The {name} box is {box_width} by {box_height} pixels, larger than the "
                f"{width} by {height} Output, so it is cut off.",
                icon=":material/warning:",
            )
        else:
            hint_slot.caption(
                f"The {name} box is {box_width} by {box_height} pixels: "
                f"{box_width / width:.0%} of the Output width and "
                f"{box_height / height:.0%} of its height."
            )

    # One Source can be shown alone, at a larger size, to judge its Sync Point.
    shown = frame
    if grid and len(source_ids) > 1:
        show_options = ["all", *source_ids]
        if state.get("preview_show") not in show_options:
            state.preview_show = "all"
        st.segmented_control(
            "Show",
            show_options,
            key="preview_show",
            format_func=lambda option: (
                "Whole Output" if option == "all" else f"Source {numbers[option]}"
            ),
            required=True,
        )
        if state.preview_show in source_ids:
            box = sizes.layout.boxes[panel_ids.index(panel_of(state.preview_show))]
            shown = frame[box.top : box.top + box.height, box.left : box.left + box.width]

    with st.container(key="preview"):
        st.image(fit_within(shown, *PREVIEW_BOX), width="stretch")

    if not grid:
        span = spans[source_ids.index(showing)]
        file_time = span.file_time_at(min(state.seq_time, span.output_end))
        st.caption(
            f"Output is {width} by {height} pixels and runs for {running_time:.3f} s at {rate:g} "
            f"frames per second. At {state.seq_time:.3f} s it shows {source_label(showing)}, "
            f"at {file_time:.3f} s into its file."
        )
        sounds = [
            sequence_silence_reason(clip, source) for clip, source in zip(row_clips, project.sources)
        ]
        st.table(
            {
                "Source": [source_label(source_id) for source_id in source_ids],
                "On show from (s)": [f"{span.output_start:.3f}" for span in spans],
                "On show to (s)": [f"{span.output_end:.3f}" for span in spans],
                "Time on show (s)": [f"{span.time_on_show:.3f}" for span in spans],
                "File from (s)": [f"{span.file_start:.3f}" for span in spans],
                "File to (s)": [f"{span.file_end:.3f}" for span in spans],
                "Play Speed": [f"{source.play_speed:g}" for source in project.sources],
                "Frame Hint": [str(hint) for hint in hints],
                "Sound": ["yes" if reason is None else f"no: {reason}" for reason in sounds],
            }
        )
        st.caption(
            f"Total running time {running_time:.3f} s: the times on show added together."
        )

    if grid:
        sound = "no sound" if silent_because else f"sound from Panel {audio_panel + 1}"
        row_count = len(sizes.layout.row_heights)
        grid_shape = f", in {row_count} Rows" if row_count > 1 else ""
        st.caption(
            f"Output is {width} by {height} pixels{grid_shape} and runs for {running_time:.3f} s "
            f"at {rate:g} frames per second, with {sound}. Output Speed {speed.output:.3g}."
        )
        st.table(
            {
                "Source": [source_label(source_id) for source_id in source_ids],
                "Footage from (s)": [f"{span.file_start:.3f}" for span in spans],
                "Footage to (s)": [f"{span.file_end:.3f}" for span in spans],
                "Front Gap (s)": [f"{span.front_gap:.3f}" for span in spans],
                "Back Gap (s)": [f"{span.back_gap:.3f}" for span in spans],
                "Source Speed": [f"{own_speed:.3g}" for own_speed in speed.sources],
                "Frame Hint": [str(hint) for hint in hints],
            }
        )

        st.subheader("Draft")
        # The Draft goes beside the Output, under the Output's name with "_draft" added.
        draft_file = None
        if state.out_folder.strip() and state.out_name.strip():
            draft_file = Path(clean(state.out_folder)) / f"{Path(state.out_name.strip()).stem}_draft.mp4"
        draft_columns = st.columns(4, vertical_alignment="bottom")
        draft_columns[0].number_input(
            "Draft Lead-in (s)",
            key="draft_lead_in",
            min_value=0.0,
            step=0.5,
            format="%.3f",
            help="Draft running time from the start of the Draft to the Sync Event.",
        )
        draft_columns[1].number_input(
            "Draft Lead-out (s)",
            key="draft_lead_out",
            min_value=0.0,
            step=0.5,
            format="%.3f",
            help="Draft running time from the Sync Event to the end of the Draft.",
        )
        draft_columns[2].number_input(
            "Draft width (px)",
            key="draft_width",
            min_value=16,
            step=16,
            help="The height follows from the picture. An Output narrower than this is not enlarged.",
        )
        draft_columns[3].checkbox(
            "Draft sound", key="draft_sound", help="Carry the sound the Output would have."
        )
        draft_settings = DraftSettings(
            lead_in=state.draft_lead_in,
            lead_out=state.draft_lead_out,
            width=state.draft_width,
            sound=state.draft_sound,
        )
        small = None
        try:
            small = draft_project(project, row_clips, draft_settings)
            draft_size = geometry(small, row_clips).layout
            draft_silent = silence_reason(small, row_clips)
        except EditError as error:
            small = None
            st.error(str(error), icon=":material/error:")
        else:
            draft_time = small.output.running_time
            if not state.draft_sound:
                draft_sound = "without sound"
            elif draft_silent:
                draft_sound = f"without sound, because {draft_silent}"
            else:
                draft_sound = f"with sound from Panel {audio_panel + 1}"
            st.caption(
                f"The Draft will be {draft_size.width} by {draft_size.height} pixels "
                f"({draft_size.width / width:.0%} of the Output's size) at low picture quality, "
                f"{draft_sound}. It runs for {draft_time:.3f} s at {rate:g} frames per second and "
                f"Output Speed {speed.output:.3g}, with the Sync Event {state.draft_lead_in:.3f} s in."
            )

        draft_problem = None
        if draft_file is None:
            draft_problem = "Choose an Output folder and file name. The Draft is written beside the Output."
        elif any(draft_file.resolve() == Path(path).resolve() for path in paths.values()):
            draft_problem = f"The Draft would replace the Source file {draft_file.name}."
        if draft_problem:
            st.warning(draft_problem, icon=":material/warning:")
        elif small is not None:
            st.caption(f"It is written to {draft_file}, replacing the Draft before it.")

        if st.button(
            "Make Draft",
            icon=":material/play_circle:",
            key="make_draft",
            disabled=small is None or bool(draft_problem),
        ):
            bar = st.progress(0.0, text="Starting")
            started = time.perf_counter()
            try:
                # Separate readers, so the cached Preview readers are left alone.
                with ExitStack() as readers:
                    fresh_clips = [
                        readers.enter_context(open_source(source.path)) for source in project.sources
                    ]
                    render_draft(
                        project,
                        fresh_clips,
                        draft_file,
                        draft_settings,
                        on_progress=lambda stage, fraction: bar.progress(fraction, text=f"Writing {stage}"),
                    )
            except (EditError, OSError) as error:
                bar.empty()
                st.error(f"The Draft failed: {error}", icon=":material/error:")
                st.stop()
            bar.empty()
            state.draft = {
                "project": small,
                "path": str(draft_file),
                "seconds": time.perf_counter() - started,
            }

        if state.draft and Path(state.draft["path"]).is_file():
            st.success(
                f"Draft written to {state.draft['path']} in {state.draft['seconds']:.1f} s",
                icon=":material/check_circle:",
            )
            if state.draft["project"] != small:
                st.warning(
                    "Settings have changed since this Draft was made. Make it again to see them.",
                    icon=":material/warning:",
                )
            if st.button("Open Draft", icon=":material/open_in_new:", key="open_draft"):
                try:
                    dialogs.open_file(state.draft["path"])
                except OSError as error:
                    st.error(f"The Draft could not be opened: {error}", icon=":material/error:")

    st.subheader("Render")
    destination = Path(clean(state.out_folder)) / state.out_name.strip()
    problem = None
    if not state.out_folder.strip() or not state.out_name.strip():
        problem = "Choose an Output folder and file name."
    elif destination.suffix.lower() != ".mp4":
        problem = "The Output file name must end in .mp4."
    elif any(destination.resolve() == Path(path).resolve() for path in paths.values()):
        problem = "The Output cannot replace its own Source file."
    if problem:
        st.warning(problem, icon=":material/warning:")
    if grid and empty_panels():
        st.info(
            " and ".join(f"Panel {panel_numbers[panel_id]}" for panel_id in empty_panels())
            + (" is empty and is" if len(empty_panels()) == 1 else " are empty and are")
            + " black in the Output.",
            icon=":material/crop_free:",
        )

    replace_allowed = True
    if not problem and destination.exists():
        replace_allowed = st.checkbox(f"Replace the existing file {destination.name}", key="replace")

    if st.button(
        "Render Output",
        type="primary",
        icon=":material/movie:",
        key="render",
        disabled=bool(problem) or not replace_allowed,
    ):
        bar = st.progress(0.0, text="Starting")
        try:
            # Separate readers, so the cached Preview readers are left alone.
            with ExitStack() as readers:
                fresh_clips = [
                    readers.enter_context(open_source(source.path)) for source in project.sources
                ]
                written = render(
                    project,
                    fresh_clips,
                    destination,
                    on_progress=lambda stage, fraction: bar.progress(fraction, text=f"Writing {stage}"),
                )
        except (EditError, OSError) as error:
            bar.empty()
            st.error(f"The render failed: {error}", icon=":material/error:")
            st.stop()
        bar.empty()
        state.last_render = str(written)

    if state.last_render:
        st.success(f"Output written to {state.last_render}", icon=":material/check_circle:")
