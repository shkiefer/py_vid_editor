"""Where each Source sits in the running time of a Sequence.

A Sequence has no Sync Event. Its Sources play one after another in play
order, each from its Start Point to its End Point at its own Play Speed, so
the running time follows from the Sources. Plain arithmetic: no frame is read.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .model import EditError, Source

# File times within this much of the end of the file count as the end; a typed
# End Point is rounded to the millisecond and a duration need not be.
_END_ALLOWANCE = 0.0015


@dataclass(frozen=True)
class ClipSpan:
    """One Source as it appears in a Sequence."""

    output_start: float
    """Output running time at which the Source comes on show."""
    output_end: float
    """Output running time at which the next Source takes over."""
    file_start: float
    """The Source's Start Point."""
    file_end: float
    """The Source's End Point, the end of the file unless set."""
    play_speed: float

    @property
    def time_on_show(self) -> float:
        return self.output_end - self.output_start

    def file_time_at(self, output_time: float) -> float:
        """File time of the Source shown at an Output running time within its span."""
        return self.file_start + (output_time - self.output_start) * self.play_speed


def _check(source: Source, duration: float) -> tuple[float, float]:
    """The Source's Start Point and End Point, or an error saying what is wrong."""
    if source.play_speed <= 0:
        raise EditError("The Play Speed must be greater than zero")
    start = source.start_point
    end = duration if source.end_point is None else source.end_point
    if start < 0:
        raise EditError("The Start Point cannot be negative")
    if end > duration + _END_ALLOWANCE:
        raise EditError(f"The End Point {end:.3f} s is after the end of the file ({duration:.3f} s)")
    end = min(end, duration)
    if start >= end:
        raise EditError("The Start Point must be before the End Point")
    return start, end


def clip_spans(sources: Sequence[Source], durations: Sequence[float]) -> tuple[ClipSpan, ...]:
    """Each Source's place in the Sequence, in play order.

    `durations` are the Source files' lengths, in the order of the Sources.
    """
    if not sources:
        raise EditError("The Output needs at least one Source")
    if len(sources) != len(durations):
        raise ValueError("Each Source needs its own duration")
    spans, now = [], 0.0
    for position, (source, duration) in enumerate(zip(sources, durations)):
        try:
            start, end = _check(source, float(duration))
        except EditError as error:
            if len(sources) == 1:
                raise
            raise EditError(f"Source {position + 1}: {error}") from error
        length = (end - start) / source.play_speed
        spans.append(ClipSpan(now, now + length, start, end, source.play_speed))
        now += length
    return tuple(spans)


def running_time(spans: Sequence[ClipSpan]) -> float:
    """The Output running time of a Sequence."""
    return spans[-1].output_end if spans else 0.0


def on_show(spans: Sequence[ClipSpan], output_time: float) -> int:
    """Position of the Source on show at an Output running time.

    A time before the start counts as the first Source, and one at or after
    the end as the last.
    """
    for position, span in enumerate(spans):
        if output_time < span.output_end:
            return position
    return len(spans) - 1
