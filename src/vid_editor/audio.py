"""Where each Audio Track plays in the Output, and what a volume means. Plain arithmetic."""

import math
from dataclasses import dataclass

import numpy as np

from vid_editor.model import AudioTrack, EditError

MAX_VOLUME = 200.0
"""The loudest a volume can be set, as a percentage of the sound in its file."""


@dataclass(frozen=True)
class TrackSpan:
    """The stretch of an Audio Track's file that the Output plays, and where."""

    output_start: float
    output_end: float
    file_start: float
    file_end: float
    cut_off: float
    """Seconds of the file left unplayed because the Output ended first."""
    fade_out: float
    """Seconds of fade at the end of what is played; 0 unless it is cut off."""

    @property
    def plays(self) -> bool:
        return self.output_end > self.output_start


def check_volume(volume: float, name: str) -> None:
    if not 0 <= volume <= MAX_VOLUME:
        raise EditError(f"{name} must be from 0 to {MAX_VOLUME:g}%")


def track_span(track: AudioTrack, file_duration: float, running_time: float) -> TrackSpan:
    """Where an Audio Track plays: from its start until its file or the Output runs out.

    A start before 0, as a Draft can give, means the Audio Track was already
    playing when the Output began, so the part before then is not heard.
    """
    if track.file_start < 0:
        raise EditError("An Audio Track's file start cannot be negative")
    if track.fade_out < 0:
        raise EditError("An Audio Track's fade-out cannot be negative")
    check_volume(track.volume, "An Audio Track's volume")
    if track.file_start >= file_duration:
        raise EditError(
            f"The file start {track.file_start:.3f} s is not before the end of the file "
            f"at {file_duration:.3f} s"
        )
    first = min(track.file_start + max(0.0, -track.start), file_duration)
    available = file_duration - first
    start = min(max(track.start, 0.0), running_time)
    end = min(start + available, running_time)
    played = end - start
    cut_off = available - played if start + available > running_time else 0.0
    return TrackSpan(
        output_start=start,
        output_end=end,
        file_start=first,
        file_end=first + played,
        cut_off=cut_off,
        fade_out=min(track.fade_out, played) if cut_off > 0 else 0.0,
    )


def track_gain(span: TrackSpan, volume: float, output_time):
    """The factor an Audio Track's sound is multiplied by at Output running times.

    It is its volume, brought down in a straight line to nothing over the
    fade-out at its end. `output_time` may be one time or an array of them.
    """
    gain = volume / 100
    if span.fade_out <= 0:
        return np.full(np.shape(output_time), gain)
    return gain * np.clip((span.output_end - np.asarray(output_time)) / span.fade_out, 0.0, 1.0)


def decibels(volume: float) -> float | None:
    """A volume in percent as decibels against the file, or None for silence."""
    return None if volume <= 0 else 20 * math.log10(volume / 100)


def volume_text(volume: float) -> str:
    """A volume as the screen gives it, such as "30% = −10.5 dB"."""
    level = decibels(volume)
    if level is None:
        return f"{volume:g}%: silent"
    if abs(level) < 0.05:
        return f"{volume:g}% = 0.0 dB, as in the file"
    return f"{volume:g}% = {level:+.1f} dB".replace("-", "−")


@dataclass(frozen=True)
class MixLevel:
    """How loud the Output's mixed sound gets: what the Mix Hint reports."""

    peak: float
    """The loudest sample, where 1 is full scale. 0 when there is no sound."""
    at: float
    """Output running time of the loudest sample."""
    clipped: float
    """Seconds during which the mix is past full scale."""

    @property
    def clips(self) -> bool:
        return self.peak > 1

    @property
    def lower_by(self) -> float:
        """The fraction every volume must lose for the mix to stop clipping."""
        return 1 - 1 / self.peak if self.clips else 0.0


def mix_hint(level: MixLevel) -> str:
    """The Mix Hint, as the screen gives it."""
    if level.peak <= 0:
        return "Mix Hint: the Output has no sound."
    loudest = f"loudest point {20 * math.log10(level.peak):+.1f} dB at {level.at:.3f} s".replace("-", "−")
    if not level.clips:
        return f"Mix Hint: {loudest}, no clipping."
    return (
        f"Mix Hint: {loudest}: the mix clips for {level.clipped:.3f} s. "
        f"Lower the volumes by about {math.ceil(level.lower_by * 100)}% to stop it."
    )
