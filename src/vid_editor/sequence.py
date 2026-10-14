"""Where each Source sits in the running time of a Sequence.

A Sequence has no Sync Event. Its Sources play one after another in play
order, each from its Start Point to its End Point at its own Play Speed, so
the running time follows from the Sources. A crossfade overlaps two Sources
and so shortens it; a fade through black does not. Plain arithmetic: no
frame is read.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .model import EditError, JoinKind, Source

# File times within this much of the end of the file count as the end; a typed
# End Point is rounded to the millisecond and a duration need not be.
_END_ALLOWANCE = 0.0015
# Transitions may fill a Source's time on show to within rounding.
_ROUNDING = 1e-6


@dataclass(frozen=True)
class ClipSpan:
    """One Source as it appears in a Sequence."""

    output_start: float
    """Output running time at which the Source comes on show."""
    output_end: float
    """Output running time at which the Source has gone."""
    file_start: float
    """The Source's Start Point."""
    file_end: float
    """The Source's End Point, the end of the file unless set."""
    play_speed: float
    fade_in: float = 0.0
    """Seconds at its start over which it fades up from black."""
    fade_out: float = 0.0
    """Seconds at its end over which it fades down to black."""
    cross_in: float = 0.0
    """Seconds at its start over which it crossfades from the Source before."""
    cross_out: float = 0.0
    """Seconds at its end over which it crossfades to the Source after."""

    @property
    def time_on_show(self) -> float:
        return self.output_end - self.output_start

    def file_time_at(self, output_time: float) -> float:
        """File time of the Source shown at an Output running time within its span."""
        return self.file_start + (output_time - self.output_start) * self.play_speed

    def weight_at(self, output_time: float) -> float:
        """How much of the Source's picture and sound is in the Output at a time, from 0 to 1."""
        if not self.output_start <= output_time < self.output_end:
            return 0.0
        since, until = output_time - self.output_start, self.output_end - output_time
        weight = 1.0
        for length, left in (
            (self.cross_in, since),
            (self.fade_in, since),
            (self.cross_out, until),
            (self.fade_out, until),
        ):
            if length > 0 and left < length:
                weight *= left / length
        return weight


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


def _named(error: EditError, position: int, count: int) -> EditError:
    return error if count == 1 else EditError(f"Source {position + 1}: {error}")


def clip_spans(
    sources: Sequence[Source],
    durations: Sequence[float],
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> tuple[ClipSpan, ...]:
    """Each Source's place in the Sequence, in play order.

    `durations` are the Source files' lengths, in the order of the Sources.
    Each Source's `join` is the Transition to the next; the last one's is not
    used. `fade_in` and `fade_out` are the fades at the very start and end.
    """
    if not sources:
        raise EditError("The Output needs at least one Source")
    if len(sources) != len(durations):
        raise ValueError("Each Source needs its own duration")
    if fade_in < 0 or fade_out < 0:
        raise EditError("A fade cannot be negative")
    count = len(sources)

    trims, lengths = [], []
    for position, (source, duration) in enumerate(zip(sources, durations)):
        try:
            start, end = _check(source, float(duration))
        except EditError as error:
            raise _named(error, position, count) from error
        trims.append((start, end))
        lengths.append((end - start) / source.play_speed)

    # What each Join takes from the end of one Source and the start of the next.
    fades_in, fades_out = [0.0] * count, [0.0] * count
    cross_in, cross_out = [0.0] * count, [0.0] * count
    fades_in[0], fades_out[-1] = fade_in, fade_out
    for position in range(count - 1):
        join = sources[position].join
        if join.kind is JoinKind.CUT:
            continue
        name = f"Join {position + 1} (Source {position + 1} to Source {position + 2})"
        if join.length <= 0:
            raise EditError(f"{name}: the length of a {join.kind.value.lower()} must be greater than zero")
        if join.kind is JoinKind.BLACK:
            fades_out[position] = fades_in[position + 1] = join.length / 2
        else:
            for side in (position, position + 1):
                if join.length > lengths[side] + _ROUNDING:
                    raise EditError(
                        f"{name}: the {join.length:.3f} s crossfade is longer than Source "
                        f"{side + 1}'s {lengths[side]:.3f} s on show"
                    )
            cross_out[position] = cross_in[position + 1] = join.length

    spans, now = [], 0.0
    for position, ((start, end), length) in enumerate(zip(trims, lengths)):
        taken = fades_in[position] + cross_in[position] + fades_out[position] + cross_out[position]
        if taken > length + _ROUNDING:
            raise _named(
                EditError(
                    f"its Transitions take {taken:.3f} s, longer than its {length:.3f} s on show"
                    if count > 1
                    else f"The fades take {taken:.3f} s, longer than the {length:.3f} s on show"
                ),
                position,
                count,
            )
        now -= cross_in[position]
        spans.append(
            ClipSpan(
                output_start=now,
                output_end=now + length,
                file_start=start,
                file_end=end,
                play_speed=sources[position].play_speed,
                fade_in=fades_in[position],
                fade_out=fades_out[position],
                cross_in=cross_in[position],
                cross_out=cross_out[position],
            )
        )
        now += length
    return tuple(spans)


def running_time(spans: Sequence[ClipSpan]) -> float:
    """The Output running time of a Sequence."""
    return spans[-1].output_end if spans else 0.0


def on_show(spans: Sequence[ClipSpan], output_time: float) -> int:
    """Position of the Source most on show at an Output running time.

    A time before the start counts as the first Source, and one at or after
    the end as the last. Halfway through a crossfade it is the later one.
    """
    weights = mix_at(spans, output_time)
    if weights:
        return max(reversed(weights), key=lambda pair: pair[1])[0]
    return 0 if output_time < 0 else len(spans) - 1


def mix_at(spans: Sequence[ClipSpan], output_time: float) -> list[tuple[int, float]]:
    """The Sources in the Output at a time, each with how much of it there is.

    Weights below 1 that add up to less than 1 are a fade to or from black;
    two that add up to 1 are a crossfade.
    """
    mix = []
    for position, span in enumerate(spans):
        if span.output_start <= output_time < span.output_end:
            mix.append((position, span.weight_at(output_time)))
    return mix
