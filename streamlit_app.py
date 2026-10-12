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
    Project,
    Quality,
    Source,
    SpeedChoice,
    TextOverlay,
)
from vid_editor.overlays import IMAGE_TYPES, LOGO_FOLDER, image_patch, text_patch
from vid_editor.timing import frame_at, source_speed, step_frames
from vid_editor.render import (
    EditError,
    draft_project,
    fit_within,
    frame_hints,
    geometry,
    open_source,
    output_rate,
    preview,
    render,
    render_draft,
    silence_reason,
    source_info,
    span_of,
    speeds,
)

st.set_page_config(page_title="Video editor", page_icon=":material/movie_edit:", layout="wide")

# The Preview is sent to the browser no larger than this many pixels, and shown
# no taller than a share of the window, so a tall Source fits without scrolling.
PREVIEW_BOX = (1280, 800)
st.html(
    "<style>.st-key-preview img "
    "{max-height: 55vh; object-fit: contain; object-position: left top;}</style>"
)

# Each Source on the screen has a number of its own, counted from 1, that its
# settings are kept under. This stands for "no Audio Source" in the same list.
NO_SOUND = 0

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


def add_source(path: str, kept: dict | None = None) -> None:
    """Put a Source at the right-hand end of the Row.

    `kept` holds settings from a Project file. They wait there until the
    Source's file is opened, which may be after it has been located.
    """
    state = st.session_state
    source_id = state.get("next_source_id", 1)
    state.next_source_id = source_id + 1
    state.source_ids = [*state.get("source_ids", []), source_id]
    state[f"path_{source_id}"] = path
    state[f"kept_{source_id}"] = kept or {}


def remove_source(source_id: int) -> None:
    state = st.session_state
    state.source_ids = [other for other in state.source_ids if other != source_id]
    state.pop(f"path_{source_id}", None)
    state.pop(f"kept_{source_id}", None)
    if not state.source_ids:
        # The next Source added is the first of a new Row, and sets the Output up afresh.
        for key in ("lead_in", "lead_out", "out_width", "out_rate", "out_folder", "out_name"):
            state.pop(key, None)
        state.audio_chosen = False


def new_project() -> None:
    state = st.session_state
    for source_id in list(state.get("source_ids", [])):
        remove_source(source_id)
    for key in (*project_file.SHARED_KEYS, "audio_pick", "last_render", "draft"):
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
    for source in settings.sources:
        add_source(source["path"], {key: value for key, value in source.items() if key != "path"})
    state.update(settings.shared)
    state.audio_pick = (
        NO_SOUND if settings.audio_source is None else state.source_ids[settings.audio_source]
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
        add_source(new_path)

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

# -------------------------------------------------------------- Add a Source
with st.container(horizontal=True, vertical_alignment="bottom"):
    st.text_input(
        "Add a Source file",
        key="add_path",
        placeholder=r"C:\videos\camera_a.mp4",
        help="Type or paste the path of a video file on this computer and press Enter, "
        "or use Browse. Each Source added goes to the right-hand end of Row 1. "
        "Its Row can then be changed in its tab.",
    )
    st.button("Browse", icon=":material/folder_open:", on_click=browse_to_add, key="browse_source")
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
        "row": 1,
        "aspect_on": False,
        "aspect_width": info.width,
        "aspect_height": info.height,
    }
    for name, value in fresh.items():
        if f"{name}_{source_id}" not in state:
            state[f"{name}_{source_id}"] = kept.get(name, value)
    sync_key = f"sync_point_{source_id}"
    state[sync_key] = min(state[sync_key], info.duration)

# The first Source sets the Output up. Overlays start switched off.
first_id = source_ids[0]
if first_id in clips:
    # It also sets the size of the layout, from the first place in Row 1.
    state[f"row_{first_id}"] = 1
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
# The Draft settings sit below the Preview, which is not drawn while something
# is wrong. Setting them here keeps them from being forgotten in the meantime.
for key in ("draft_lead_in", "draft_lead_out", "draft_width", "draft_sound"):
    state[key] = state[key]


def source_label(source_id: int) -> str:
    return f"Source {numbers[source_id]}: {Path(paths[source_id]).name}"


# The Audio Source is the first Source with sound, until the user chooses.
with_sound = [source_id for source_id in source_ids if source_id in infos and infos[source_id].has_sound]
audio_options = [NO_SOUND] + [
    source_id
    for source_id in source_ids
    if source_id in with_sound or (source_id in problems and source_id == state.get("audio_pick"))
]
if not state.get("audio_chosen") or state.get("audio_pick") not in audio_options:
    state.audio_pick = with_sound[0] if with_sound else NO_SOUND

settings, result = st.columns([5, 6], gap="large")

# ------------------------------------------------------------------- Settings
size_hints, frame_hint_slots = {}, {}
with settings:
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

                sets_row_height = source_id == first_id
                st.number_input(
                    "Row",
                    key=f"row_{source_id}",
                    min_value=1,
                    max_value=max(1, len(source_ids)),
                    step=1,
                    disabled=sets_row_height,
                    help="Row 1 is the top of the Output. Sources that share a Row sit side by "
                    "side, in the order they were added, and are matched in height. A Source in "
                    "a Row of its own sits under Row 1 and is matched in width. Source 1 is "
                    "always first in Row 1.",
                )
                st.number_input(
                    "Resize to width (px)",
                    key=f"source_width_{source_id}",
                    value=None,
                    min_value=2,
                    step=10,
                    placeholder="Cropped size" if sets_row_height else "Scaled to fit its Panel",
                    disabled=not sets_row_height,
                    help="Only for Source 1, which sets the height of Row 1 and the width of "
                    "Column 1. Leave empty to keep the cropped size. Applied after the crop; the "
                    "height follows without distortion. Every other Source is scaled to fit.",
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
            "Audio Source",
            audio_options,
            key="audio_pick",
            format_func=lambda source_id: "No sound" if source_id == NO_SOUND else source_label(source_id),
            on_change=audio_was_chosen,
            help="The one Source whose sound is used. Sound from every other Source is discarded. "
            "The Output is silent during this Source's Gaps.",
        )
        sound_hint = st.empty()
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
audio_source = None if state.audio_pick == NO_SOUND else source_ids.index(state.audio_pick)

# Every change is saved to the Project file, once the Project has one.
if state.get("project_path"):
    project_text = project_file.dumps(
        project_file.ProjectSettings(
            sources=[{"path": paths[source_id]} | kept[source_id] for source_id in source_ids],
            shared={key: state[key] for key in project_file.SHARED_KEYS} | {"quality": quality},
            audio_source=audio_source,
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
            Source(
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
                row=values["row"],
            )
            for source_id, values in kept.items()
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
        audio_source=audio_source,
    )
    if project.output.running_time <= 0:
        st.error("Lead-in plus Lead-out must be greater than zero.", icon=":material/error:")
        st.stop()

    rate = output_rate(project, row_clips)
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
    if silent_because and audio_source is not None:
        sound_hint.warning(
            f"The Output has no sound, because {silent_because}. Sound is kept only when "
            "the Audio Source and the Output Speed are both real time.",
            icon=":material/volume_off:",
        )

    # Each Source's size, and what the layout does to it, shown beside its settings.
    one_row = len(sizes.layout.row_heights) == 1
    for position, source_id in enumerate(source_ids):
        cropped_width, cropped_height = sizes.cropped[position]
        panel = sizes.layout.panels[position]
        place = f"Row {panel.row + 1}, Column {panel.column + 1}"
        box = f"{panel.width} by {panel.height} pixels"
        hint = f"After rotation and crop this Source is {cropped_width} by {cropped_height} pixels"
        if position == 0:
            resized_width, resized_height = sizes.resized
            if sizes.resized != sizes.cropped[0]:
                hint += (
                    f", resized to {resized_width} by {resized_height} "
                    f"({resized_width / cropped_width:.0%} of that size)"
                )
            hint += "."
            if len(source_ids) > 1 and one_row:
                hint += f" It sets the Row height. Its Panel is {box}."
            elif len(source_ids) > 1:
                hint += f" It sets the height of Row 1 and the width of Column 1. Its Panel is {box}."
        elif panel.sets_column:
            hint += (
                f". Scaled to the Row height, its Panel is {box} "
                f"({panel.height / cropped_height:.0%} of that size)."
            )
            if not one_row:
                hint += f" It is in {place}, and sets the width of Column {panel.column + 1}."
        elif panel.sets_row:
            hint += (
                f". Scaled to the width of Column 1, its Panel is {box} "
                f"({panel.width / cropped_width:.0%} of that size). It is in {place}, and sets "
                f"the height of Row {panel.row + 1}."
            )
        else:
            scale = panel.picture_width / cropped_width
            hint += f". Its Panel, in {place}, is already {box}. "
            if panel.crop_hint is None:
                hint += f"Scaled to fit ({scale:.0%} of that size), it fills the Panel with no Bars."
            else:
                bars_wide, bars_high = panel.bars
                if panel.crop_hint.width:
                    bars = f"{bars_high / 2:g} pixels above and below"
                    lose = panel.crop_hint.width
                    remedy = f"crop {lose} pixels of width, to {cropped_width - lose} wide"
                else:
                    bars = f"{bars_wide / 2:g} pixels left and right"
                    lose = panel.crop_hint.height
                    remedy = f"crop {lose} pixels of height, to {cropped_height - lose} high"
                hint += (
                    f"Scaled to fit, it is {panel.picture_width} by {panel.picture_height} pixels "
                    f"({scale:.0%} of that size), with Bars of {bars}. Crop Hint: {remedy}, and "
                    "it fills the Panel."
                )
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
    if len(source_ids) > 1:
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
            panel = sizes.layout.panels[source_ids.index(state.preview_show)]
            shown = frame[
                panel.top : panel.top + panel.height, panel.left : panel.left + panel.width
            ]

    with st.container(key="preview"):
        st.image(fit_within(shown, *PREVIEW_BOX), width="stretch")
    sound = "no sound" if silent_because else f"sound from Source {audio_source + 1}"
    grid_shape = ""
    if not one_row:
        column_count = len(sizes.layout.column_widths)
        grid_shape = (
            f", in {len(sizes.layout.row_heights)} Rows and {column_count} "
            f"Column{'s' if column_count > 1 else ''}"
        )
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
            draft_sound = f"with sound from Source {audio_source + 1}"
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
