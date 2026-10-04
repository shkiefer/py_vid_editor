"""Video editor screen. Run with: uv run streamlit run streamlit_app.py"""

from dataclasses import replace
from pathlib import Path

import streamlit as st

from vid_editor.dialogs import pick_file, pick_folder, pick_image
from vid_editor.model import (
    Corner,
    Crop,
    ImageOverlay,
    OutputSettings,
    Project,
    Quality,
    Source,
    TextOverlay,
)
from vid_editor.overlays import IMAGE_TYPES, LOGO_FOLDER, image_patch, text_patch
from vid_editor.render import (
    EditError,
    build_output,
    edited_size,
    fit_within,
    open_source,
    preview,
    render,
    source_info,
    span_of,
)

st.set_page_config(page_title="Video editor", page_icon=":material/movie_edit:", layout="wide")

# The Preview is sent to the browser no larger than this many pixels, and shown
# no taller than a share of the window, so a tall Source fits without scrolling.
PREVIEW_BOX = (1280, 800)
st.html(
    "<style>.st-key-preview img "
    "{max-height: 55vh; object-fit: contain; object-position: left top;}</style>"
)


@st.cache_resource(max_entries=4, on_release=lambda clip: clip.close(), show_spinner="Opening video")
def cached_source(path: str, modified: float):
    """An opened Source, reused across reruns until the file changes."""
    return open_source(path)


def browse_source() -> None:
    current = st.session_state.get("source_path", "")
    chosen = pick_file(str(Path(current).parent) if current else "")
    if chosen:
        st.session_state.source_path = chosen


def browse_output_folder() -> None:
    chosen = pick_folder(st.session_state.get("out_folder", ""))
    if chosen:
        st.session_state.out_folder = chosen


def browse_image() -> None:
    current = st.session_state.get("image_path", "")
    chosen = pick_image(str(Path(current).parent) if current else str(LOGO_FOLDER))
    if chosen:
        st.session_state.image_path = chosen


def use_logo() -> None:
    if st.session_state.logo_pick:
        st.session_state.image_path = str(st.session_state.logo_pick)


def turn(degrees: float) -> None:
    st.session_state.rotation = (st.session_state.rotation + degrees) % 360


st.title("Video editor")

# ---------------------------------------------------------------- Source file
with st.container(horizontal=True, vertical_alignment="bottom"):
    st.text_input(
        "Source file",
        key="source_path",
        placeholder=r"C:\videos\camera_a.mp4",
        help="Path to a video file on this computer.",
    )
    st.button("Browse", icon=":material/folder_open:", on_click=browse_source, key="browse_source")

path = st.session_state.source_path.strip().strip('"')
if not path:
    st.info("Choose a Source file to begin.", icon=":material/video_file:")
    st.stop()

try:
    if not Path(path).is_file():
        raise EditError(f"No file found at {path}")
    clip = cached_source(path, Path(path).stat().st_mtime)
except EditError as error:
    st.error(str(error), icon=":material/error:")
    st.stop()

info = source_info(clip)

# A newly chosen Source resets every setting to match that file.
if st.session_state.get("loaded_path") != path:
    st.session_state.update(
        loaded_path=path,
        sync_point=0.0,
        rotation=0.0,
        crop_top=0,
        crop_bottom=0,
        crop_left=0,
        crop_right=0,
        source_width=None,
        aspect_on=False,
        aspect_width=info.width,
        aspect_height=info.height,
        lead_in=0.0,
        lead_out=round(info.duration, 3),
        out_width=None,
        out_rate=info.playback_rate,
        quality=Quality.MEDIUM,
        out_folder=str(Path(path).parent),
        out_name=f"{Path(path).stem}_edited.mp4",
        preview_offset=0.0,
        last_render=None,
    )

# Overlays belong to the Output, so a newly chosen Source leaves them alone.
for key, value in {
    "text_on": False,
    "text_value": "Proprietary – Do Not Distribute",
    "text_size": 30,
    "text_corner": Corner.BOTTOM_LEFT,
    "image_on": False,
    "image_path": "",
    "image_corner": Corner.TOP_LEFT,
    "image_width": 25.0,
    "image_opacity": 0.5,
}.items():
    st.session_state.setdefault(key, value)

st.caption(
    f"{info.width} by {info.height} pixels, {info.duration:.3f} s long, "
    f"Playback Rate {info.playback_rate:g} frames per second, "
    f"{'has sound' if info.has_sound else 'no sound'}."
)

settings, result = st.columns([5, 6], gap="large")

# ------------------------------------------------------------------- Settings
with settings:
    with st.container(border=True):
        st.subheader("Source")
        st.number_input(
            "Sync Point (s)",
            key="sync_point",
            min_value=0.0,
            max_value=info.duration,
            step=0.1,
            format="%.3f",
            help="The time in this file at which the Sync Event is seen.",
        )
        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.number_input(
                "Rotation (degrees, anticlockwise)",
                key="rotation",
                min_value=0.0,
                max_value=360.0,
                step=1.0,
                format="%.1f",
                help="Any angle. Angles that are not quarter turns leave black corners to crop away.",
            )
            st.button("Turn left", icon=":material/rotate_left:", on_click=turn, args=(90,))
            st.button("Turn right", icon=":material/rotate_right:", on_click=turn, args=(-90,))

        st.markdown("Crop (pixels, measured after rotation)")
        crop_columns = st.columns(4)
        for column, edge in zip(crop_columns, ("top", "bottom", "left", "right")):
            column.number_input(edge.capitalize(), key=f"crop_{edge}", min_value=0, step=10)

        st.number_input(
            "Resize to width (px)",
            key="source_width",
            min_value=2,
            step=10,
            placeholder="Cropped size",
            help="Leave empty to keep the cropped size. Applied after the crop; "
            "the height follows without distortion.",
        )
        size_hint = st.empty()

        with st.expander("Advanced"):
            st.toggle(
                "Override aspect ratio",
                key="aspect_on",
                help="Force a width and height for a file that plays stretched. Applied before rotation.",
            )
            aspect_columns = st.columns(2)
            aspect_columns[0].number_input(
                "Forced width (px)", key="aspect_width", min_value=2, disabled=not st.session_state.aspect_on
            )
            aspect_columns[1].number_input(
                "Forced height (px)", key="aspect_height", min_value=2, disabled=not st.session_state.aspect_on
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
            min_value=2,
            step=2,
            placeholder="Natural size",
            help="Leave empty to keep the natural size. The height follows from the picture.",
        )
        size_columns[1].number_input(
            "Output Rate (frames per second)", key="out_rate", min_value=1.0, max_value=240.0, step=1.0
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
        text_off = not st.session_state.text_on
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
        image_off = not st.session_state.image_on
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

state = st.session_state
text_overlay = None
if state.text_on and state.text_value.strip():
    text_overlay = TextOverlay(text=state.text_value, size=state.text_size, corner=state.text_corner)
image_overlay = None
if state.image_on and state.image_path.strip():
    image_overlay = ImageOverlay(
        path=state.image_path.strip().strip('"'),
        corner=state.image_corner,
        width_percent=state.image_width,
        background_opacity=state.image_opacity,
    )
project = Project(
    sources=(
        Source(
            path=path,
            sync_point=state.sync_point,
            rotation=state.rotation,
            crop=Crop(state.crop_top, state.crop_bottom, state.crop_left, state.crop_right),
            aspect_override=(state.aspect_width, state.aspect_height) if state.aspect_on else None,
            width=state.source_width,
        ),
    ),
    output=OutputSettings(
        lead_in=state.lead_in,
        lead_out=state.lead_out,
        width=state.out_width,
        rate=state.out_rate,
        quality=state.quality or Quality.MEDIUM,
        text_overlay=text_overlay,
        image_overlay=image_overlay,
    ),
)

try:
    source = project.sources[0]
    cropped_width, cropped_height = edited_size(clip, replace(source, width=None))
    source_width, source_height = edited_size(clip, source)
except EditError:
    pass  # reported beside the Preview
else:
    hint = f"After rotation and crop this Source is {cropped_width} by {cropped_height} pixels"
    if (source_width, source_height) != (cropped_width, cropped_height):
        hint += (
            f", resized to {source_width} by {source_height} "
            f"({source_width / cropped_width:.0%} of that size)"
        )
    size_hint.caption(hint + ".")

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
    if project.output.running_time <= 0:
        st.error("Lead-in plus Lead-out must be greater than zero.", icon=":material/error:")
        st.stop()

    state.preview_offset = min(max(state.preview_offset, -state.lead_in), state.lead_out)
    st.slider(
        "Time from the Sync Event (s)",
        key="preview_offset",
        min_value=-float(state.lead_in),
        max_value=float(state.lead_out),
        step=1 / project.output.rate,
        format="%.3f",
        help="0 shows every Source at its Sync Point. Negative is before the Sync Event.",
    )

    try:
        frame = preview(project, [clip], output_time=state.lead_in + state.preview_offset)
        width, height = build_output(project, [clip]).size
        span = span_of(clip, project.sources[0], project)
    except (EditError, ValueError) as error:
        st.error(str(error), icon=":material/error:")
        st.stop()

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

    with st.container(key="preview"):
        st.image(fit_within(frame, *PREVIEW_BOX), width="stretch")
    st.caption(
        f"Output is {width} by {height} pixels and runs for {project.output.running_time:.3f} s."
    )
    st.table(
        {
            "Source": [Path(path).name],
            "Footage from (s)": [f"{span.file_start:.3f}"],
            "Footage to (s)": [f"{span.file_end:.3f}"],
            "Front Gap (s)": [f"{span.front_gap:.3f}"],
            "Back Gap (s)": [f"{span.back_gap:.3f}"],
        }
    )

    st.subheader("Render")
    destination = Path(state.out_folder.strip().strip('"')) / state.out_name.strip()
    problem = None
    if not state.out_folder.strip() or not state.out_name.strip():
        problem = "Choose an Output folder and file name."
    elif destination.suffix.lower() != ".mp4":
        problem = "The Output file name must end in .mp4."
    elif destination.resolve() == Path(path).resolve():
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
            # A separate reader, so the cached Preview reader is left alone.
            with open_source(path) as fresh_clip:
                written = render(
                    project,
                    [fresh_clip],
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
