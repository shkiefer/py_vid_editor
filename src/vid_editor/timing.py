"""Where each Source sits in the Output's running time.

Every Source is placed on Event Time using its own Sync Point and Source
Speed; Sources are never matched to one another (docs/adr/0002). Lead-in and
Lead-out are measured in Output running time.

Three clocks appear here:

- Output running time: seconds of the finished video, 0 at its start.
- Event Time: seconds of the real world, 0 at the Sync Event.
- File time: seconds into one Source file, as an external viewer shows it.
"""

from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class SourceSpan:
    """The part of one Source that appears in the Output, and its Gaps."""

    file_start: float
    """File time where the footage shown in the Output begins."""
    file_end: float
    """File time where the footage shown in the Output ends."""
    front_gap: float
    """Output running time with no footage before the Source begins."""
    back_gap: float
    """Output running time with no footage after the Source ends."""
    footage_time: float
    """Output running time during which the Source has footage."""

    @property
    def has_footage(self) -> bool:
        return self.footage_time > 0


def _file_seconds_per_output_second(source_speed: float, output_speed: float) -> float:
    # 1 s of Output covers `output_speed` s of Event Time, and 1 s of Event
    # Time takes `1 / source_speed` s of file.
    if source_speed <= 0 or output_speed <= 0:
        raise ValueError("Source Speed and Output Speed must be greater than zero")
    return output_speed / source_speed


def file_time_at(
    output_time: float,
    *,
    sync_point: float,
    lead_in: float,
    source_speed: float = 1.0,
    output_speed: float = 1.0,
) -> float:
    """File time of a Source shown at a given Output running time.

    The result can fall outside the file, which means the Source is in a Gap.
    """
    rate = _file_seconds_per_output_second(source_speed, output_speed)
    return sync_point + (output_time - lead_in) * rate


def source_span(
    *,
    duration: float,
    sync_point: float,
    lead_in: float,
    lead_out: float,
    source_speed: float = 1.0,
    output_speed: float = 1.0,
) -> SourceSpan:
    """Work out which footage of a Source is shown and how long its Gaps are.

    `duration` and `sync_point` are in file time. `lead_in` and `lead_out`
    are in Output running time.
    """
    if lead_in < 0 or lead_out < 0:
        raise ValueError("Lead-in and Lead-out cannot be negative")
    running_time = lead_in + lead_out
    if running_time <= 0:
        raise ValueError("Lead-in plus Lead-out must be greater than zero")
    rate = _file_seconds_per_output_second(source_speed, output_speed)

    wanted_start = sync_point - lead_in * rate
    wanted_end = sync_point + lead_out * rate
    file_start = min(max(wanted_start, 0.0), duration)
    file_end = min(max(wanted_end, 0.0), duration)

    footage_time = (file_end - file_start) / rate
    if footage_time <= 0:
        return SourceSpan(file_start, file_start, running_time, 0.0, 0.0)
    return SourceSpan(
        file_start=file_start,
        file_end=file_end,
        front_gap=(file_start - wanted_start) / rate,
        back_gap=(wanted_end - file_end) / rate,
        footage_time=footage_time,
    )


def frame_at(file_time: float, playback_rate: float) -> int:
    """Which frame of a Source file is on show at a file time, counted from 0."""
    # The small allowance is the one MoviePy's reader uses, so both agree.
    return max(0, int(file_time * playback_rate + 0.00001))


def frame_time(frame: int, playback_rate: float) -> float:
    """A file time that shows the given frame, in whole milliseconds.

    The time is up to a millisecond after the frame begins, never on its
    boundary, so rounding cannot tip it into the frame before. It reads the
    same on screen and in the Project file as it is stored.
    """
    return (floor(frame * 1000 / playback_rate) + 1) / 1000


def step_frames(file_time: float, frames: int, playback_rate: float, frame_count: int) -> float:
    """The file time a given number of frames later (or earlier, if negative)."""
    target = frame_at(file_time, playback_rate) + frames
    return frame_time(min(max(target, 0), frame_count - 1), playback_rate)
