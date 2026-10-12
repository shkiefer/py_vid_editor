"""Turns a Project into pictures: the Preview and the rendered Output.

This is the only module that talks to MoviePy. A Source's own geometry is
applied one frame at a time by `edit_frame`, which the Preview and the
rendered Output share. The Preview reads just the frames it shows, so the
screen does not wait for MoviePy to rebuild a chain of clips on every change.
"""

import tempfile
import weakref
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy import ColorClip, VideoClip, VideoFileClip, concatenate_videoclips, vfx
from moviepy.video.io.ffmpeg_reader import FFmpegInfosParser
from proglog import ProgressBarLogger

from vid_editor.layout import GridLayout, grid_layout
from vid_editor.model import Crop, DraftSettings, EditError, Project, Quality, Source
from vid_editor.overlays import overlay_patches, stamper
from vid_editor.timing import (
    FrameHint,
    SourceSpan,
    file_time_at,
    frame_at,
    frame_hint,
    is_real_time,
    source_span,
    source_speed,
)

# H.264 constant rate factor per quality level. Lower is better and larger.
_CRF = {Quality.HIGH: 18, Quality.MEDIUM: 23, Quality.SMALL: 28}

# A Draft is encoded fast and coarsely.
_DRAFT_CRF = 30

# Gaps shorter than this many seconds are rounding noise, not real Gaps.
_NEGLIGIBLE = 1e-6

ProgressCallback = Callable[[str, float], None]
"""Called with a stage name ("sound" or "picture") and a fraction from 0 to 1."""


def _tolerate_unnamed_metadata_lines() -> None:
    """Work around a MoviePy 2.2.1 fault that rejects iPhone recordings.

    MoviePy reads a line of ffmpeg's report that has no "name: value" shape as
    more text for the value before it. When that value is the rotation, already
    turned into a number, joining the two fails and the file cannot be opened.
    iPhone HDR footage has such a line straight after its rotation. Giving the
    line a name of its own keeps it apart from the value before it.
    """
    read_field = FFmpegInfosParser.parse_metadata_field_value

    def read_field_or_name_the_line(self, line: str) -> tuple[str, str]:
        if ":" not in line:
            return line.strip(), ""
        return read_field(self, line)

    FFmpegInfosParser.parse_metadata_field_value = read_field_or_name_the_line


_tolerate_unnamed_metadata_lines()


@dataclass(frozen=True)
class SourceInfo:
    """Facts read from a Source file."""

    duration: float
    width: int
    height: int
    playback_rate: float
    has_sound: bool
    frame_count: int


def open_source(path: str) -> VideoFileClip:
    """Open a Source file. The caller closes it."""
    if not Path(path).is_file():
        raise EditError(f"No file found at {path}")
    try:
        return VideoFileClip(path)
    except Exception as error:  # MoviePy raises several types for bad files
        raise EditError(f"Could not read {path} as a video: {error}") from error


def source_info(clip: VideoFileClip) -> SourceInfo:
    return SourceInfo(
        duration=float(clip.duration),
        width=int(clip.w),
        height=int(clip.h),
        playback_rate=float(clip.fps),
        has_sound=clip.audio is not None,
        frame_count=max(1, int(getattr(clip.reader, "n_frames", 0)) or round(clip.duration * clip.fps)),
    )


# Frames lately read for the Preview, newest last, kept within a memory budget.
_recent_frames: OrderedDict[tuple[int, int], np.ndarray] = OrderedDict()
_RECENT_FRAMES_BYTES = 200_000_000
# Going back in a file means restarting ffmpeg. It is restarted this many
# frames early, so that the next steps back are already in hand.
_RUN_UP_FRAMES = 12
_known_readers: set[int] = set()


def _forget_reader(reader: int) -> None:
    _known_readers.discard(reader)
    for key in [key for key in _recent_frames if key[0] == reader]:
        del _recent_frames[key]


def source_frame(clip: VideoFileClip, file_time: float) -> np.ndarray:
    """The frame of a Source file on show at a file time, as the file has it.

    Stepping forward reads one more frame. Stepping back is served from the
    frames lately read where it can be.
    """
    rate = float(clip.fps)
    last_frame = max(1, int(getattr(clip.reader, "n_frames", 0)) or round(clip.duration * rate)) - 1
    wanted = min(frame_at(file_time, rate), last_frame)
    reader = id(clip.reader)
    if reader not in _known_readers:
        # A later file can be given the same id once this one is gone, so its
        # frames are dropped with it.
        _known_readers.add(reader)
        weakref.finalize(clip.reader, _forget_reader, reader)

    def read(frame: int) -> np.ndarray:
        picture = clip.get_frame((frame + 0.5) / rate)
        _recent_frames[(reader, frame)] = picture
        _recent_frames.move_to_end((reader, frame))
        used = sum(kept.nbytes for kept in _recent_frames.values())
        while used > _RECENT_FRAMES_BYTES and len(_recent_frames) > 1:
            used -= _recent_frames.popitem(last=False)[1].nbytes
        return picture

    if (reader, wanted) in _recent_frames:
        _recent_frames.move_to_end((reader, wanted))
        return _recent_frames[(reader, wanted)]
    going_back = wanted < getattr(clip.reader, "pos", 0) - 1
    if going_back:
        for frame in range(max(0, wanted - _RUN_UP_FRAMES), wanted):
            read(frame)
    return read(wanted)


def _turned_size(size: tuple[int, int], angle: float) -> tuple[int, int]:
    """The size of a picture after rotation, grown to fit."""
    width, height = size
    angle %= 360
    if angle % 180 == 0:
        return width, height
    if angle % 90 == 0:
        return height, width
    return Image.new("1", (width, height)).rotate(angle, expand=True).size


def source_sizes(size: tuple[int, int], source: Source) -> tuple[tuple[int, int], tuple[int, int]]:
    """The size of a Source after its rotation and crop, and then after its resize.

    `size` is the (width, height) of the file's own picture. This is plain
    arithmetic, and is where a Source's settings are checked.
    """
    if source.aspect_override is not None:
        size = source.aspect_override
        if min(size) < 2:
            raise EditError("The aspect ratio override needs a width and height of at least 2")
    width, height = _turned_size(size, source.rotation)

    crop = source.crop
    if min(crop.top, crop.bottom, crop.left, crop.right) < 0:
        raise EditError("Crop amounts cannot be negative")
    if crop.left + crop.right > width - 2 or crop.top + crop.bottom > height - 2:
        raise EditError(
            f"The crop removes the whole picture. After rotation it is {width} by {height} pixels."
        )
    cropped = (width - crop.left - crop.right, height - crop.top - crop.bottom)

    if source.width is None:
        return cropped, cropped
    if source.width < 2:
        raise EditError("The Source width must be at least 2 pixels")
    return cropped, (int(source.width), max(2, round(cropped[1] * source.width / cropped[0])))


def _resized(frame: np.ndarray, size: tuple[int, int], rough: bool = False) -> np.ndarray:
    image = Image.fromarray(np.ascontiguousarray(frame))
    if rough:
        # About half the cost of the careful resize, and good enough for a Draft.
        return np.asarray(image.resize(size, Image.Resampling.BILINEAR, reducing_gap=1.0))
    return np.asarray(image.resize(size, Image.Resampling.LANCZOS))


def edit_frame(
    frame: np.ndarray,
    source: Source,
    panel_size: tuple[int, int] | None = None,
    rough: bool = False,
) -> np.ndarray:
    """Apply a Source's own geometry to one frame of its file.

    The order is aspect override, rotation, crop, then one resize: to
    `panel_size` when the frame is headed for a Panel, or else to the Source's
    own resize. The settings must already have passed `source_sizes`. `rough`
    trades the quality of the resize for speed, which is what a Draft wants.
    """
    if source.aspect_override is not None:
        frame = _resized(frame, source.aspect_override, rough)

    angle = source.rotation % 360
    if angle % 90 == 0:
        frame = np.rot90(frame, k=int(angle // 90))  # anticlockwise
    else:
        # Any other angle grows the picture to fit and leaves black corners.
        image = Image.fromarray(np.ascontiguousarray(frame))
        frame = np.asarray(image.rotate(angle, expand=True, resample=Image.Resampling.BILINEAR))

    crop = source.crop
    height, width = frame.shape[:2]
    frame = frame[crop.top : height - crop.bottom, crop.left : width - crop.right]

    height, width = frame.shape[:2]
    if panel_size is None:
        panel_size = source_sizes((width, height), Source(source.path, width=source.width))[1]
    if panel_size != (width, height):
        frame = _resized(frame, panel_size, rough)
    return np.ascontiguousarray(frame)


def edited_size(clip: VideoFileClip, source: Source) -> tuple[int, int]:
    """Width and height of a Source after its own rotation, crop and resize."""
    return source_sizes((int(clip.w), int(clip.h)), source)[1]


@dataclass(frozen=True)
class Speeds:
    """The Output Speed in use and each Source's Source Speed, where 1 is real time."""

    output: float
    sources: tuple[float, ...]


def speeds(project: Project, clips: Sequence[VideoFileClip]) -> Speeds:
    """Work out the speeds. The Output Speed defaults to the slowest Source Speed."""
    try:
        sources = tuple(
            source_speed(float(clip.fps), source.record_rate)
            for clip, source in zip(clips, project.sources)
        )
    except ValueError as error:
        raise EditError(str(error)) from error
    output = project.output.speed
    if output is None:
        output = min(sources)
    elif output <= 0:
        raise EditError("The Output Speed must be greater than zero")
    return Speeds(output=output, sources=sources)


def silence_reason(project: Project, clips: Sequence[VideoFileClip]) -> str | None:
    """Why the Output has no sound, or None when it has.

    Sound is kept only when the Audio Source and the Output are both real time.
    """
    chosen = project.audio_source
    if chosen is None:
        return "no Audio Source is chosen"
    if not 0 <= chosen < len(clips):
        raise EditError("The Audio Source is not one of the Sources")
    if clips[chosen].audio is None:
        return f"Source {chosen + 1} has no sound"
    speed = speeds(project, clips)
    if not is_real_time(speed.sources[chosen]):
        return f"Source {chosen + 1} is not real time (Source Speed {speed.sources[chosen]:.3g})"
    if not is_real_time(speed.output):
        return f"the Output Speed is {speed.output:.3g}, not real time"
    return None


def frame_hints(project: Project, clips: Sequence[VideoFileClip]) -> list[FrameHint]:
    """The Frame Hint of every Source at the Output Speed and Output Rate in use."""
    speed = speeds(project, clips)
    rate = output_rate(project, clips)
    return [
        frame_hint(
            playback_rate=float(clip.fps),
            source_speed=own_speed,
            output_speed=speed.output,
            output_rate=rate,
        )
        for clip, own_speed in zip(clips, speed.sources)
    ]


def span_of(
    clip: VideoFileClip, source: Source, project: Project, output_speed: float = 1.0
) -> SourceSpan:
    """Which footage of a Source the Output shows, and its Gaps."""
    return source_span(
        duration=float(clip.duration),
        sync_point=source.sync_point,
        lead_in=project.output.lead_in,
        lead_out=project.output.lead_out,
        source_speed=source_speed(float(clip.fps), source.record_rate),
        output_speed=output_speed,
    )


def _panel(
    clip: VideoFileClip, source: Source, edited: VideoClip, project: Project, output_speed: float
) -> VideoClip:
    """One Source as it appears in the Output: footage with black Gaps.

    `edited` is the Source's picture at the size of its Panel. Gaps are joined
    end to end with the footage rather than layered under it. Layering costs
    about ten times more per frame.
    """
    span = span_of(clip, source, project, output_speed)
    running_time = project.output.running_time

    def black(duration: float) -> VideoClip:
        return ColorClip(size=edited.size, color=(0, 0, 0), duration=duration)

    if not span.has_footage:
        return black(running_time)
    footage = edited.subclipped(span.file_start, span.file_end)
    file_seconds_per_output_second = (span.file_end - span.file_start) / span.footage_time
    if not is_real_time(file_seconds_per_output_second):
        # Sound never survives a change of speed, so it is not carried through one.
        footage = footage.without_audio().with_effects(
            [vfx.MultiplySpeed(factor=file_seconds_per_output_second)]
        )
    pieces = [footage]
    if span.front_gap > _NEGLIGIBLE:
        pieces.insert(0, black(span.front_gap))
    if span.back_gap > _NEGLIGIBLE:
        pieces.append(black(span.back_gap))
    if len(pieces) == 1:
        return pieces[0].with_duration(running_time)
    return concatenate_videoclips(pieces, method="chain").with_duration(running_time)


def output_rate(project: Project, clips: Sequence[VideoFileClip]) -> float:
    """The Output Rate: the chosen one, or the highest Playback Rate."""
    return project.output.rate or max(float(clip.fps) for clip in clips)


def _in_row(project: Project, clips: Sequence[VideoFileClip]) -> list[tuple[VideoFileClip, Source]]:
    """Each opened Source with its settings as they count in the layout.

    Only the first Source's resize counts. It sets the height of the first Row
    and the width of the first Column, and every other Source is scaled to
    fit whatever its own resize says.
    """
    if not project.sources:
        raise EditError("The Output needs at least one Source")
    if len(project.sources) != len(clips):
        raise ValueError("Each Source needs its own opened file")
    return [
        (clip, source if position == 0 else replace(source, width=None))
        for position, (clip, source) in enumerate(zip(clips, project.sources))
    ]


def _named(error: EditError, position: int, project: Project) -> EditError:
    """Say which Source a problem belongs to, once there is more than one."""
    if len(project.sources) == 1:
        return error
    return EditError(f"Source {position + 1}: {error}")


def _grid(sizes: Sequence[tuple[int, int]], project: Project) -> GridLayout:
    try:
        return grid_layout(
            sizes, [source.row for source in project.sources], project.output.width
        )
    except ValueError as error:
        raise EditError(str(error)) from error


@dataclass(frozen=True)
class Geometry:
    """The sizes that follow from the Sources' settings and the Output width."""

    cropped: tuple[tuple[int, int], ...]
    """Each Source after its rotation and crop, before any resize."""
    resized: tuple[int, int]
    """The first Source after its resize. Its height is the height of the first Row."""
    layout: GridLayout


def geometry(project: Project, clips: Sequence[VideoFileClip]) -> Geometry:
    """Work out every Panel size. Plain arithmetic: no frame is read."""
    cropped = []
    for position, (clip, source) in enumerate(_in_row(project, clips)):
        try:
            sizes = source_sizes((int(clip.w), int(clip.h)), source)
        except EditError as error:
            raise _named(error, position, project) from error
        cropped.append(sizes[0])
        if position == 0:
            resized = sizes[1]
    return Geometry(tuple(cropped), resized, _grid([resized, *cropped[1:]], project))


def _picture_sizes(
    project: Project, clips: Sequence[VideoFileClip]
) -> tuple[GridLayout, list[tuple[int, int]]]:
    """The layout, and the size each Source's picture is scaled to inside its Panel."""
    layout = geometry(project, clips).layout
    return layout, [(panel.picture_width, panel.picture_height) for panel in layout.panels]


def _composed(layout: GridLayout, pictures: Sequence[np.ndarray]) -> np.ndarray:
    """One frame of the Output: each Source's picture in its Panel, on black.

    The black shows as Bars beside a picture smaller than its Panel, and fills
    any place in the grid that has no Source. Pictures are placed as plain
    arrays rather than layered as MoviePy clips, which costs far more per frame.
    """
    frame = np.zeros((layout.height, layout.width, 3), dtype=np.uint8)
    for panel, picture in zip(layout.panels, pictures):
        frame[
            panel.picture_top : panel.picture_top + panel.picture_height,
            panel.picture_left : panel.picture_left + panel.picture_width,
        ] = picture
    return frame


def _is_untouched(clip: VideoFileClip, source: Source, panel_size: tuple[int, int]) -> bool:
    """Whether a Source goes into its Panel exactly as its file has it."""
    return (
        source.aspect_override is None
        and source.rotation % 360 == 0
        and source.crop == Crop()
        and panel_size == (int(clip.w), int(clip.h))
    )


def build_output(
    project: Project, clips: Sequence[VideoFileClip], rough: bool = False
) -> VideoClip:
    """Compose the whole Output. `clips` are the opened Sources, in order."""
    layout, panel_sizes = _picture_sizes(project, clips)
    output_speed = speeds(project, clips).output

    # Each Source is scaled once, straight to the size of its Panel.
    panels = []
    for clip, source, size in zip(clips, project.sources, panel_sizes):
        picture = clip
        if not _is_untouched(clip, source, size):
            picture = clip.image_transform(
                lambda frame, source=source, size=size: edit_frame(frame, source, size, rough)
            )
        panels.append(_panel(clip, source, picture, project, output_speed))

    if len(panels) == 1:
        output = panels[0]
    else:
        output = VideoClip(
            frame_function=lambda t: _composed(layout, [panel.get_frame(t) for panel in panels]),
            duration=project.output.running_time,
        )

    silent = silence_reason(project, clips) is not None
    sound = None if silent else panels[project.audio_source].audio
    output = output.without_audio() if sound is None else output.with_audio(sound)

    patches = overlay_patches(project.output, layout.width)
    if patches:
        output = output.image_transform(stamper(patches, (layout.width, layout.height)))
    return output.with_fps(output_rate(project, clips))


def preview(
    project: Project, clips: Sequence[VideoFileClip], output_time: float
) -> np.ndarray:
    """The Preview: one frame of the Output at a given running time.

    Each Source's frame is read straight from its file and edited here, which
    gives the same picture as `build_output` without building it.
    """
    layout, panel_sizes = _picture_sizes(project, clips)
    last_frame_time = max(0.0, project.output.running_time - 1 / output_rate(project, clips))
    output_time = min(max(output_time, 0.0), last_frame_time)
    speed = speeds(project, clips)

    panels = []
    for clip, source, size, own_speed in zip(clips, project.sources, panel_sizes, speed.sources):
        span = span_of(clip, source, project, speed.output)
        file_time = file_time_at(
            output_time,
            sync_point=source.sync_point,
            lead_in=project.output.lead_in,
            source_speed=own_speed,
            output_speed=speed.output,
        )
        if span.has_footage and span.file_start <= file_time < span.file_end:
            panels.append(edit_frame(source_frame(clip, file_time), source, size))
        else:
            panels.append(np.zeros((size[1], size[0], 3), dtype=np.uint8))  # a Gap
    frame = panels[0] if len(panels) == 1 else _composed(layout, panels)

    patches = overlay_patches(project.output, layout.width)
    if patches:
        frame = stamper(patches, (layout.width, layout.height))(frame)
    return frame


def fit_within(frame: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    """Shrink a frame to fit a box without distortion. A frame that fits is left alone."""
    height, width = frame.shape[:2]
    scale = min(max_width / width, max_height / height)
    if scale >= 1:
        return frame
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    image = Image.fromarray(frame.astype(np.uint8))
    return np.asarray(image.resize(size, Image.Resampling.BILINEAR))


class _ProgressLogger(ProgressBarLogger):
    def __init__(self, on_progress: ProgressCallback):
        super().__init__()
        self._on_progress = on_progress

    def bars_callback(self, bar, attr, value, old_value=None):
        total = self.bars[bar]["total"]
        if attr == "index" and total:
            stage = "sound" if bar == "chunk" else "picture"
            self._on_progress(stage, min(value / total, 1.0))


def _write(
    output: VideoClip,
    destination: Path,
    preset: str,
    crf: int,
    on_progress: ProgressCallback | None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.write_videofile(
        str(destination),
        fps=output.fps,
        codec="libx264",
        audio_codec="aac",
        preset=preset,
        ffmpeg_params=["-crf", str(crf)],
        pixel_format="yuv420p",
        temp_audiofile_path=tempfile.gettempdir(),
        logger=_ProgressLogger(on_progress) if on_progress else None,
    )
    return destination


def render(
    project: Project,
    clips: Sequence[VideoFileClip],
    destination: str | Path,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Write the Output as an H.264 MP4 and return where it was written."""
    destination = Path(destination)
    if destination.suffix.lower() != ".mp4":
        raise EditError("The Output file name must end in .mp4")
    return _write(
        build_output(project, clips), destination, "medium", _CRF[project.output.quality], on_progress
    )


def draft_project(
    project: Project, clips: Sequence[VideoFileClip], draft: DraftSettings
) -> Project:
    """The Project that gives the Draft.

    It is the same Output with the Draft's own Lead-in, Lead-out and width, and
    with no sound unless the Draft asks for it. The Output Rate and the speeds
    are the Output's. The text Overlay is sized in Output pixels, so it shrinks
    with the picture. An Output narrower than the Draft width is not enlarged.
    """
    if draft.lead_in < 0 or draft.lead_out < 0 or draft.lead_in + draft.lead_out <= 0:
        raise EditError("The Draft Lead-in plus Lead-out must be greater than zero")
    if draft.width < 2:
        raise EditError("The Draft width must be at least 2 pixels")
    output = replace(project.output, lead_in=draft.lead_in, lead_out=draft.lead_out)
    full_width = geometry(project, clips).layout.width
    if draft.width < full_width:
        text = output.text_overlay
        if text is not None:
            text = replace(text, size=max(4, round(text.size * draft.width / full_width)))
        output = replace(output, width=draft.width, text_overlay=text)
    return replace(
        project, output=output, audio_source=project.audio_source if draft.sound else None
    )


def render_draft(
    project: Project,
    clips: Sequence[VideoFileClip],
    destination: str | Path,
    draft: DraftSettings,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Write the Draft and return where it was written."""
    small = draft_project(project, clips, draft)
    return _write(
        build_output(small, clips, rough=True), Path(destination), "ultrafast", _DRAFT_CRF, on_progress
    )
