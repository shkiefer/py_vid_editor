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
from moviepy import (
    AudioClip,
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    VideoClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
    vfx,
)
from moviepy.video.io.ffmpeg_reader import FFmpegInfosParser
from proglog import ProgressBarLogger

from vid_editor.audio import MixLevel, TrackSpan, check_volume, track_gain, track_span
from vid_editor.layout import Layout, Picture, even, panel_layout, picture_in, width_for_height
from vid_editor.legacy_layout import grid_layout
from vid_editor.model import (
    Crop,
    DraftSettings,
    EditError,
    Panel,
    Project,
    Quality,
    Source,
    Workflow,
)
from vid_editor.overlays import overlay_patches, stamper
from vid_editor.sequence import ClipSpan, clip_spans, mix_at
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


def open_track(path: str) -> AudioFileClip:
    """Open an Audio Track's file, which may be any file with sound. The caller closes it."""
    if not Path(path).is_file():
        raise EditError(f"No file found at {path}")
    try:
        return AudioFileClip(path)
    except Exception as error:  # MoviePy raises several types for bad files
        raise EditError(f"Could not read {path} as sound: {error}") from error


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

    Sound is kept only when the Source in the Audio Panel and the Output are
    both real time.
    """
    if project.audio_panel is None:
        return "no Audio Panel is chosen"
    if not 0 <= project.audio_panel < len(project.panels):
        raise EditError("The Audio Panel is not one of the Panels")
    chosen = audio_source(project)
    if chosen is None:
        return f"Panel {project.audio_panel + 1} is empty"
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


def _named(error: EditError, position: int, project: Project) -> EditError:
    """Say which Source a problem belongs to, once there is more than one."""
    if len(project.sources) == 1:
        return error
    return EditError(f"Source {position + 1}: {error}")


@dataclass(frozen=True)
class Geometry:
    """The sizes that follow from the Panels, the Sources' settings and the Output width."""

    cropped: tuple[tuple[int, int], ...]
    """Each Source after its rotation and crop, before any resize."""
    layout: Layout
    pictures: tuple[Picture, ...]
    """Each Source's picture in its Panel, in the order of the Sources."""


def geometry(project: Project, clips: Sequence[VideoFileClip]) -> Geometry:
    """Work out where every Panel and every Source sits. Plain arithmetic: no frame is read."""
    if not project.sources:
        raise EditError("The Output needs at least one Source")
    if len(project.sources) != len(clips):
        raise ValueError("Each Source needs its own opened file")
    try:
        layout = panel_layout(
            [(panel.width, panel.height, panel.row) for panel in project.panels],
            project.output.width,
        )
    except ValueError as error:
        raise EditError(str(error)) from error

    cropped, pictures, taken = [], [], set()
    for position, (clip, source) in enumerate(zip(clips, project.sources)):
        if not 0 <= source.panel < len(project.panels):
            raise EditError(f"Source {position + 1} is not assigned to a Panel")
        if source.panel in taken:
            raise EditError(f"Panel {source.panel + 1} holds more than one Source")
        taken.add(source.panel)
        try:
            size = source_sizes((int(clip.w), int(clip.h)), source)[0]
        except EditError as error:
            raise _named(error, position, project) from error
        cropped.append(size)
        panel = project.panels[source.panel]
        pictures.append(
            picture_in(
                layout.boxes[source.panel],
                (panel.width, panel.height),
                layout.scale,
                size,
                source.width,
            )
        )
    return Geometry(tuple(cropped), layout, tuple(pictures))


def _composed(
    layout: Layout, pictures: Sequence[Picture], frames: Sequence[np.ndarray]
) -> np.ndarray:
    """One frame of the Output: the part of each Source its Panel shows, on black.

    The black is the Bars beside a picture smaller than its Panel, every empty
    Panel, and whatever the Panels leave of the Output. Pictures are placed as
    plain arrays rather than layered as MoviePy clips, which costs far more
    per frame.
    """
    composed = np.zeros((layout.height, layout.width, 3), dtype=np.uint8)
    for picture, frame in zip(pictures, frames):
        composed[
            picture.top : picture.top + picture.shown_height,
            picture.left : picture.left + picture.shown_width,
        ] = frame[
            picture.cut_top : picture.cut_top + picture.shown_height,
            picture.cut_left : picture.cut_left + picture.shown_width,
        ]
    return composed


def _fills_the_output(layout: Layout, pictures: Sequence[Picture]) -> bool:
    """Whether one Source's picture is the whole Output, with nothing to place or cut."""
    return (
        len(pictures) == 1
        and (pictures[0].width, pictures[0].height) == (layout.width, layout.height)
        and (pictures[0].shown_width, pictures[0].shown_height) == (layout.width, layout.height)
    )


def starting_panel(size: tuple[int, int], row_height: int | None = None, row: int = 1) -> Panel:
    """The Panel a new Source starts with.

    `size` is the Source after its rotation and crop. The Panel takes its
    Row's height and the width that fits the Source at that height. With no
    Row height, as for the first Panel of all, it takes the Source's own size.
    """
    if row_height is None:
        return Panel(width=max(2, size[0]), height=max(2, size[1]), row=row)
    # An even width, so that Panels made this way add up to an even Output.
    return Panel(width=even(width_for_height(size, row_height) + 1), height=row_height, row=row)


def legacy_panels(
    sources: Sequence[Source], clips: Sequence[VideoFileClip], rows: Sequence[int]
) -> tuple[Panel, ...]:
    """The Panels of a Project from before typed Panels.

    The first Panels are one for each Source, in the order of the Sources,
    each at the size the old rules gave it. Under those rules only the first
    Source's resize counted; the others were fitted. A Row that was shorter
    than another was left black at its right-hand end, so an empty Panel
    follows for each such place. That keeps the Output as it was, where a Row
    narrower than the Output would now be centred.
    """
    sizes = []
    for position, (clip, source) in enumerate(zip(clips, sources)):
        try:
            cropped, resized = source_sizes((int(clip.w), int(clip.h)), source)
        except EditError as error:
            raise EditError(f"Source {position + 1}: {error}") from error
        sizes.append(resized if position == 0 else cropped)
    try:
        old = grid_layout(sizes, rows)
    except ValueError as error:
        raise EditError(str(error)) from error
    panels = [
        Panel(width=panel.width, height=panel.height, row=panel.row + 1) for panel in old.panels
    ]
    filled = {(panel.row, panel.column) for panel in old.panels}
    for row, height in enumerate(old.row_heights):
        for column, width in enumerate(old.column_widths):
            if (row, column) not in filled:
                panels.append(Panel(width=width, height=height, row=row + 1))
    return tuple(panels)


def audio_source(project: Project) -> int | None:
    """Position of the Source in the Audio Panel, or None when there is none."""
    for position, source in enumerate(project.sources):
        if source.panel == project.audio_panel:
            return position
    return None


def _is_untouched(clip: VideoFileClip, source: Source, panel_size: tuple[int, int]) -> bool:
    """Whether a Source goes into its Panel exactly as its file has it."""
    return (
        source.aspect_override is None
        and source.rotation % 360 == 0
        and source.crop == Crop()
        and panel_size == (int(clip.w), int(clip.h))
    )


def track_spans(
    project: Project, tracks: Sequence[AudioFileClip], running_time: float
) -> list[TrackSpan]:
    """Where each Audio Track plays in the Output. `tracks` are their opened files, in order."""
    if len(project.output.audio_tracks) != len(tracks):
        raise ValueError("Each Audio Track needs its own opened file")
    spans = []
    for number, (track, clip) in enumerate(zip(project.output.audio_tracks, tracks), start=1):
        try:
            spans.append(track_span(track, float(clip.duration), running_time))
        except EditError as error:
            raise EditError(f"Audio Track {number}: {error}") from error
    return spans


def _mixed_sound(
    project: Project,
    source_sound: AudioClip | None,
    tracks: Sequence[AudioFileClip],
    running_time: float,
) -> AudioClip | None:
    """The sound from the Sources at its volume, mixed with every Audio Track at its own."""
    output = project.output
    check_volume(output.source_volume, "The Sources' volume")
    sounds = []
    if source_sound is not None and output.source_volume > 0:
        if output.source_volume != 100:
            source_sound = source_sound.with_effects([afx.MultiplyVolume(output.source_volume / 100)])
        sounds.append(source_sound)
    for track, clip, span in zip(output.audio_tracks, tracks, track_spans(project, tracks, running_time)):
        if not span.plays or track.volume <= 0:
            continue
        piece = clip.subclipped(span.file_start, span.file_end).transform(
            lambda get_frame, t, span=span, volume=track.volume: get_frame(t)
            * track_gain(span, volume, t + span.output_start)[..., None],
            keep_duration=True,
        )
        sounds.append(piece.with_start(span.output_start))
    if not sounds:
        return None
    return CompositeAudioClip(sounds).with_duration(running_time)


def _with_sound(output: VideoClip, sound: AudioClip | None) -> VideoClip:
    return output.without_audio() if sound is None else output.with_audio(sound)


def build_output(
    project: Project,
    clips: Sequence[VideoFileClip],
    rough: bool = False,
    tracks: Sequence[AudioFileClip] = (),
) -> VideoClip:
    """Compose the whole Output. `clips` are the opened Sources and `tracks` the
    opened Audio Tracks, each in order."""
    sizes = geometry(project, clips)
    layout, pictures = sizes.layout, sizes.pictures
    output_speed = speeds(project, clips).output

    # Each Source is scaled once, straight to its size in the Output.
    panels = []
    for clip, source, picture in zip(clips, project.sources, pictures):
        size = (picture.width, picture.height)
        edited = clip
        if not _is_untouched(clip, source, size):
            edited = clip.image_transform(
                lambda frame, source=source, size=size: edit_frame(frame, source, size, rough)
            )
        panels.append(_panel(clip, source, edited, project, output_speed))

    if _fills_the_output(layout, pictures):
        output = panels[0]
    else:
        output = VideoClip(
            frame_function=lambda t: _composed(
                layout, pictures, [panel.get_frame(t) for panel in panels]
            ),
            duration=project.output.running_time,
        )

    silent = silence_reason(project, clips) is not None
    sound = None if silent else panels[audio_source(project)].audio
    output = _with_sound(
        output, _mixed_sound(project, sound, tracks, project.output.running_time)
    )

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
    sizes = geometry(project, clips)
    layout, pictures = sizes.layout, sizes.pictures
    last_frame_time = max(0.0, project.output.running_time - 1 / output_rate(project, clips))
    output_time = min(max(output_time, 0.0), last_frame_time)
    speed = speeds(project, clips)

    panels = []
    for clip, source, picture, own_speed in zip(clips, project.sources, pictures, speed.sources):
        size = (picture.width, picture.height)
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
    if _fills_the_output(layout, pictures):
        frame = panels[0]
    else:
        frame = _composed(layout, pictures, panels)

    patches = overlay_patches(project.output, layout.width)
    if patches:
        frame = stamper(patches, (layout.width, layout.height))(frame)
    return frame


def sequence_spans(project: Project, clips: Sequence[VideoFileClip]) -> tuple[ClipSpan, ...]:
    """Each Source's place in a Sequence's running time, in play order."""
    sequence = project.sequence
    return clip_spans(
        project.sources,
        [float(clip.duration) for clip in clips],
        fade_in=sequence.fade_in if sequence else 0.0,
        fade_out=sequence.fade_out if sequence else 0.0,
    )


def join_times(spans: Sequence[ClipSpan]) -> list[float]:
    """The Output running time of each Join: where a cut falls, or the middle of a fade or crossfade."""
    return [
        (later.output_start + earlier.output_end) / 2
        for earlier, later in zip(spans, spans[1:])
    ]


def sequence_geometry(project: Project, clips: Sequence[VideoFileClip]) -> Geometry:
    """Where every Source of a Sequence sits in its one Panel. No frame is read."""
    if not project.sources:
        raise EditError("The Output needs at least one Source")
    if len(project.sources) != len(clips):
        raise ValueError("Each Source needs its own opened file")
    if project.sequence is None:
        raise EditError("The Sequence has no Panel size")
    size = (project.sequence.width, project.sequence.height)
    try:
        layout = panel_layout([(*size, 1)], project.output.width)
    except ValueError as error:
        raise EditError(str(error)) from error
    cropped, pictures = [], []
    for position, (clip, source) in enumerate(zip(clips, project.sources)):
        try:
            own = source_sizes((int(clip.w), int(clip.h)), source)[0]
        except EditError as error:
            raise _named(error, position, project) from error
        cropped.append(own)
        pictures.append(picture_in(layout.boxes[0], size, layout.scale, own, source.width))
    return Geometry(tuple(cropped), layout, tuple(pictures))


def sequence_frame_hints(project: Project, clips: Sequence[VideoFileClip]) -> list[FrameHint]:
    """The Frame Hint of every Source of a Sequence at its Play Speed."""
    sequence_spans(project, clips)  # checks every Play Speed
    rate = output_rate(project, clips)
    return [
        frame_hint(
            playback_rate=float(clip.fps),
            source_speed=1 / source.play_speed,
            output_speed=1.0,
            output_rate=rate,
        )
        for clip, source in zip(clips, project.sources)
    ]


def sequence_silence_reason(clip: VideoFileClip, source: Source) -> str | None:
    """Why a Source is silent in a Sequence, or None when its sound is kept."""
    if clip.audio is None:
        return "the file has no sound"
    if not is_real_time(source.play_speed):
        return f"its Play Speed is {source.play_speed:.3g}, not 1"
    return None


def _mixed(frames: Sequence[np.ndarray], weights: Sequence[float]) -> np.ndarray:
    """Frames laid over one another in the given amounts, on black."""
    if len(frames) == 1 and weights[0] >= 1:
        return frames[0]
    total = np.zeros(frames[0].shape, dtype=np.float32)
    for frame, weight in zip(frames, weights):
        total += frame.astype(np.float32) * weight
    return np.clip(np.rint(total), 0, 255).astype(np.uint8)


def _has_transitions(spans: Sequence[ClipSpan]) -> bool:
    return any(
        span.fade_in or span.fade_out or span.cross_in or span.cross_out for span in spans
    )


def build_sequence(
    project: Project,
    clips: Sequence[VideoFileClip],
    rough: bool = False,
    tracks: Sequence[AudioFileClip] = (),
) -> VideoClip:
    """Compose a whole Sequence: each Source in turn, in play order, with its Transitions."""
    sizes = sequence_geometry(project, clips)
    layout, pictures = sizes.layout, sizes.pictures
    spans = sequence_spans(project, clips)

    pieces = []
    for clip, source, picture, span in zip(clips, project.sources, pictures, spans):
        size = (picture.width, picture.height)
        piece = clip.subclipped(span.file_start, span.file_end)
        if not _is_untouched(clip, source, size):
            piece = piece.image_transform(
                lambda frame, source=source, size=size: edit_frame(frame, source, size, rough)
            )
        if not is_real_time(source.play_speed):
            # Sound never survives a change of speed, so it is not carried through one.
            piece = piece.without_audio().with_effects(
                [vfx.MultiplySpeed(factor=source.play_speed)]
            )
        if not _fills_the_output(layout, [picture]):
            sound = piece.audio
            piece = VideoClip(
                frame_function=lambda t, piece=piece, picture=picture: _composed(
                    layout, [picture], [piece.get_frame(t)]
                ),
                duration=span.time_on_show,
            )
            if sound is not None:
                piece = piece.with_audio(sound)
        pieces.append(piece.with_duration(span.time_on_show))

    if not _has_transitions(spans):
        output = pieces[0] if len(pieces) == 1 else concatenate_videoclips(pieces, method="chain")
    else:
        # Most frames show one Source at full strength and cost no more than a
        # cut. Only a fade or a crossfade mixes frames.
        black = np.zeros((layout.height, layout.width, 3), dtype=np.uint8)

        def frame_at_time(t: float) -> np.ndarray:
            mix = mix_at(spans, t)
            if not mix:
                return black
            return _mixed(
                [pieces[position].get_frame(t - spans[position].output_start) for position, _ in mix],
                [weight for _, weight in mix],
            )

        output = VideoClip(frame_function=frame_at_time, duration=spans[-1].output_end)
        sounds = []
        for piece, span in zip(pieces, spans):
            if piece.audio is None:
                continue
            fades = []
            if span.fade_in + span.cross_in > 0:
                fades.append(afx.AudioFadeIn(span.fade_in + span.cross_in))
            if span.fade_out + span.cross_out > 0:
                fades.append(afx.AudioFadeOut(span.fade_out + span.cross_out))
            sound = piece.audio.with_effects(fades) if fades else piece.audio
            sounds.append(sound.with_start(span.output_start))
        if sounds:
            output = output.with_audio(
                CompositeAudioClip(sounds).with_duration(spans[-1].output_end)
            )
    output = _with_sound(
        output, _mixed_sound(project, output.audio, tracks, spans[-1].output_end)
    )

    patches = overlay_patches(project.output, layout.width)
    if patches:
        output = output.image_transform(stamper(patches, (layout.width, layout.height)))
    return output.with_fps(output_rate(project, clips))


def sequence_preview(
    project: Project, clips: Sequence[VideoFileClip], output_time: float
) -> np.ndarray:
    """The Preview of a Sequence: the frame on show at a running time, mixed as the Output mixes it."""
    sizes = sequence_geometry(project, clips)
    layout, pictures = sizes.layout, sizes.pictures
    spans = sequence_spans(project, clips)
    last_frame_time = max(0.0, spans[-1].output_end - 1 / output_rate(project, clips))
    output_time = min(max(output_time, 0.0), last_frame_time)
    frames, weights = [], []
    for position, weight in mix_at(spans, output_time):
        clip, source, picture, span = (
            clips[position], project.sources[position], pictures[position], spans[position]
        )
        file_time = min(span.file_time_at(output_time), span.file_end - 0.5 / float(clip.fps))
        frame = edit_frame(source_frame(clip, file_time), source, (picture.width, picture.height))
        if not _fills_the_output(layout, [picture]):
            frame = _composed(layout, [picture], [frame])
        frames.append(frame)
        weights.append(weight)
    if frames:
        frame = _mixed(frames, weights)
    else:
        frame = np.zeros((layout.height, layout.width, 3), dtype=np.uint8)
    patches = overlay_patches(project.output, layout.width)
    if patches:
        frame = stamper(patches, (layout.width, layout.height))(frame)
    return frame


def sequence_draft_window(
    project: Project, clips: Sequence[VideoFileClip], draft: DraftSettings, around: float
) -> tuple[float, float]:
    """The stretch of a Sequence's running time that its Draft covers."""
    if draft.lead_in < 0 or draft.lead_out < 0 or draft.lead_in + draft.lead_out <= 0:
        raise EditError("The Draft's seconds before plus seconds after must be greater than zero")
    total = sequence_spans(project, clips)[-1].output_end
    start, end = max(0.0, around - draft.lead_in), min(total, around + draft.lead_out)
    if end - start <= 0:
        raise EditError("The Draft would be empty")
    return start, end


def render_sequence_draft(
    project: Project,
    clips: Sequence[VideoFileClip],
    destination: str | Path,
    draft: DraftSettings,
    around: float,
    on_progress: ProgressCallback | None = None,
    tracks: Sequence[AudioFileClip] = (),
) -> Path:
    """Write a Draft of a Sequence: a stretch either side of a time, such as a Join."""
    start, end = sequence_draft_window(project, clips, draft, around)
    small = draft_project(project, clips, draft)
    if not draft.sound:
        tracks = ()
    output = build_sequence(small, clips, rough=True, tracks=tracks).subclipped(start, end)
    if not draft.sound:
        output = output.without_audio()
    return _write(output, Path(destination), "ultrafast", _DRAFT_CRF, on_progress)


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
    tracks: Sequence[AudioFileClip] = (),
) -> Path:
    """Write the Output as an H.264 MP4 and return where it was written."""
    destination = Path(destination)
    if destination.suffix.lower() != ".mp4":
        raise EditError("The Output file name must end in .mp4")
    build = build_sequence if project.workflow is Workflow.SEQUENCE else build_output
    output = build(project, clips, tracks=tracks)
    return _write(output, destination, "medium", _CRF[project.output.quality], on_progress)


def sound_settings(project: Project) -> Project:
    """The Project with every setting that cannot change its sound put back to its start.

    Two Projects that differ only in their picture have the same sound, so the
    Mix Hint need not be worked out again for them.
    """
    return replace(
        project,
        sources=tuple(
            replace(source, rotation=0.0, crop=Crop(), aspect_override=None, width=None)
            for source in project.sources
        ),
        output=replace(
            project.output,
            width=None,
            rate=None,
            quality=Quality.MEDIUM,
            text_overlay=None,
            image_overlay=None,
        ),
    )


_MIX_RATE = 44100
"""Samples per second at which the Mix Hint measures the sound, as the Output writes it."""
_MIX_CHUNK = 2000


def mix_level(
    project: Project, clips: Sequence[VideoFileClip], tracks: Sequence[AudioFileClip]
) -> MixLevel:
    """How loud the Output's mixed sound gets, read through from start to end."""
    build = build_sequence if project.workflow is Workflow.SEQUENCE else build_output
    sound = build(sound_settings(project), clips, tracks=tracks).audio
    if sound is None:
        return MixLevel(peak=0.0, at=0.0, clipped=0.0)
    peak, at, over, read = 0.0, 0.0, 0, 0
    # MoviePy's sound file reader gives silence for much more than a second at
    # once, so the sound is read in pieces of the size the Output is written in.
    for chunk in sound.iter_chunks(chunksize=_MIX_CHUNK, fps=_MIX_RATE):
        loudness = np.abs(chunk).max(axis=1) if chunk.ndim > 1 else np.abs(chunk)
        if len(loudness):
            loudest = int(loudness.argmax())
            if loudness[loudest] > peak:
                peak, at = float(loudness[loudest]), (read + loudest) / _MIX_RATE
            over += int((loudness > 1).sum())
        read += len(loudness)
    return MixLevel(peak=peak, at=at, clipped=over / _MIX_RATE)


def draft_project(
    project: Project, clips: Sequence[VideoFileClip], draft: DraftSettings
) -> Project:
    """The Project that gives the Draft.

    It is the same Output with the Draft's own Lead-in, Lead-out and width, and
    with no sound unless the Draft asks for it. The Output Rate and the speeds
    are the Output's. The text Overlay is sized in Output pixels, so it shrinks
    with the picture. An Output narrower than the Draft width is not enlarged.
    In a Synced grid each Audio Track is moved with the Sync Event, so it is
    heard against the same moment as in the Output.
    """
    if draft.lead_in < 0 or draft.lead_out < 0 or draft.lead_in + draft.lead_out <= 0:
        raise EditError("The Draft Lead-in plus Lead-out must be greater than zero")
    if draft.width < 2:
        raise EditError("The Draft width must be at least 2 pixels")
    output = replace(project.output, lead_in=draft.lead_in, lead_out=draft.lead_out)
    measure = sequence_geometry if project.workflow is Workflow.SEQUENCE else geometry
    full_width = measure(project, clips).layout.width
    if draft.width < full_width:
        text = output.text_overlay
        if text is not None:
            text = replace(text, size=max(4, round(text.size * draft.width / full_width)))
        output = replace(output, width=draft.width, text_overlay=text)
    if not draft.sound:
        output = replace(output, audio_tracks=())
    elif project.workflow is Workflow.GRID:
        earlier = project.output.lead_in - draft.lead_in
        output = replace(
            output,
            audio_tracks=tuple(
                replace(track, start=track.start - earlier) for track in output.audio_tracks
            ),
        )
    return replace(
        project, output=output, audio_panel=project.audio_panel if draft.sound else None
    )


def render_draft(
    project: Project,
    clips: Sequence[VideoFileClip],
    destination: str | Path,
    draft: DraftSettings,
    on_progress: ProgressCallback | None = None,
    tracks: Sequence[AudioFileClip] = (),
) -> Path:
    """Write the Draft and return where it was written."""
    small = draft_project(project, clips, draft)
    if not draft.sound:
        tracks = ()
    return _write(
        build_output(small, clips, rough=True, tracks=tracks),
        Path(destination),
        "ultrafast",
        _DRAFT_CRF,
        on_progress,
    )
