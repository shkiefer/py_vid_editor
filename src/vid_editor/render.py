"""Turns a Project into pictures: the Preview and the rendered Output.

This is the only module that talks to MoviePy.
"""

import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy import ColorClip, VideoClip, VideoFileClip, concatenate_videoclips, vfx
from moviepy.video.io.ffmpeg_reader import FFmpegInfosParser
from proglog import ProgressBarLogger

from vid_editor.model import Crop, Project, Quality, Source
from vid_editor.timing import SourceSpan, source_span

# H.264 constant rate factor per quality level. Lower is better and larger.
_CRF = {Quality.HIGH: 18, Quality.MEDIUM: 23, Quality.SMALL: 28}

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


class EditError(ValueError):
    """A setting cannot be applied to the Source it belongs to."""


@dataclass(frozen=True)
class SourceInfo:
    """Facts read from a Source file."""

    duration: float
    width: int
    height: int
    playback_rate: float
    has_sound: bool


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
    )


def even(value: float) -> int:
    """Round down to an even number of pixels, as H.264 requires."""
    return max(2, int(value) // 2 * 2)


def _rotator(angle: float) -> Callable[[np.ndarray], np.ndarray]:
    """Rotate frames by any angle, growing the picture to fit, with black corners.

    MoviePy's own Rotate turns every frame into floating point, which more
    than doubles the cost of this step and of every step after it.
    """

    def rotate(frame: np.ndarray) -> np.ndarray:
        image = Image.fromarray(frame)
        return np.asarray(image.rotate(angle, expand=True, resample=Image.Resampling.BILINEAR))

    return rotate


def _edited(clip: VideoClip, source: Source) -> VideoClip:
    """Apply a Source's own geometry: aspect override, rotation, crop, then resize."""
    if source.aspect_override is not None:
        width, height = source.aspect_override
        if width < 2 or height < 2:
            raise EditError("The aspect ratio override needs a width and height of at least 2")
        clip = clip.with_effects([vfx.Resize(new_size=(width, height))])
    angle = source.rotation % 360
    if angle % 90 == 0:
        if angle:
            clip = clip.with_effects([vfx.Rotate(angle, expand=True)])
    else:
        clip = clip.image_transform(_rotator(angle))

    crop = source.crop
    width, height = clip.size
    if min(crop.top, crop.bottom, crop.left, crop.right) < 0:
        raise EditError("Crop amounts cannot be negative")
    if crop.left + crop.right > width - 2 or crop.top + crop.bottom > height - 2:
        raise EditError(
            f"The crop removes the whole picture. After rotation it is {width} by {height} pixels."
        )
    if crop != Crop():
        clip = clip.with_effects(
            [
                vfx.Crop(
                    x1=crop.left, y1=crop.top, x2=width - crop.right, y2=height - crop.bottom
                )
            ]
        )

    if source.width is not None:
        if source.width < 2:
            raise EditError("The Source width must be at least 2 pixels")
        width, height = clip.size
        resized = (int(source.width), max(2, round(height * source.width / width)))
        if resized != (width, height):
            clip = clip.with_effects([vfx.Resize(new_size=resized)])
    return clip


def edited_size(clip: VideoFileClip, source: Source) -> tuple[int, int]:
    """Width and height of a Source after its own rotation, crop and resize."""
    width, height = _edited(clip, source).size
    return int(width), int(height)


def span_of(clip: VideoFileClip, source: Source, project: Project) -> SourceSpan:
    """Which footage of a Source the Output shows, and its Gaps."""
    return source_span(
        duration=float(clip.duration),
        sync_point=source.sync_point,
        lead_in=project.output.lead_in,
        lead_out=project.output.lead_out,
    )


def _panel(clip: VideoFileClip, source: Source, project: Project) -> VideoClip:
    """One Source as it appears in the Output: footage with black Gaps.

    Gaps are joined end to end with the footage rather than layered under it.
    Layering costs about ten times more per frame.
    """
    span = span_of(clip, source, project)
    running_time = project.output.running_time
    edited = _edited(clip, source)

    def black(duration: float) -> VideoClip:
        return ColorClip(size=edited.size, color=(0, 0, 0), duration=duration)

    if not span.has_footage:
        return black(running_time)
    pieces = [edited.subclipped(span.file_start, span.file_end)]
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


def build_output(project: Project, clips: Sequence[VideoFileClip]) -> VideoClip:
    """Compose the whole Output. `clips` are the opened Sources, in order."""
    if len(project.sources) != 1 or len(clips) != 1:
        raise NotImplementedError("Only one Source is supported so far")
    output = _panel(clips[0], project.sources[0], project)

    natural_width, natural_height = output.size
    width = even(project.output.width or natural_width)
    height = even(natural_height * width / natural_width)
    if (width, height) != (natural_width, natural_height):
        output = output.with_effects([vfx.Resize(new_size=(width, height))])
    return output.with_fps(output_rate(project, clips))


def preview(
    project: Project, clips: Sequence[VideoFileClip], output_time: float
) -> np.ndarray:
    """The Preview: one frame of the Output at a given running time."""
    output = build_output(project, clips)
    last_frame_time = max(0.0, output.duration - 1 / output.fps)
    return output.get_frame(min(max(output_time, 0.0), last_frame_time))


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
    destination.parent.mkdir(parents=True, exist_ok=True)

    output = build_output(project, clips)
    output.write_videofile(
        str(destination),
        fps=output.fps,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", str(_CRF[project.output.quality])],
        pixel_format="yuv420p",
        temp_audiofile_path=tempfile.gettempdir(),
        logger=_ProgressLogger(on_progress) if on_progress else None,
    )
    return destination
