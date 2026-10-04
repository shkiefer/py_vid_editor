"""Timing arithmetic, using the scenarios agreed in CONTEXT.md."""

import pytest

from vid_editor.timing import (
    file_time_at,
    frame_at,
    frame_hint,
    frame_time,
    source_span,
    source_speed,
    step_frames,
)


def test_source_with_enough_footage_has_no_gaps():
    # Source A: Sync Point 12.0 s, Lead-in 5 s, Lead-out 10 s.
    span = source_span(duration=60, sync_point=12, lead_in=5, lead_out=10)
    assert (span.file_start, span.file_end) == (7, 22)
    assert (span.front_gap, span.back_gap) == (0, 0)
    assert span.footage_time == 15


def test_source_short_before_sync_point_has_front_gap():
    # Source B: only 3 s of footage before the Sync Event, Lead-in is 5 s.
    span = source_span(duration=60, sync_point=3, lead_in=5, lead_out=10)
    assert (span.file_start, span.file_end) == (0, 13)
    assert (span.front_gap, span.back_gap) == (2, 0)


def test_source_short_after_sync_point_has_back_gap():
    # Source B is 9 s long: 6 s after the Sync Event, Lead-out is 10 s.
    span = source_span(duration=9, sync_point=3, lead_in=5, lead_out=10)
    assert (span.file_start, span.file_end) == (0, 9)
    assert (span.front_gap, span.back_gap) == (2, 4)
    assert span.front_gap + span.footage_time + span.back_gap == 15


def test_gaps_never_change_the_output_running_time():
    span = source_span(duration=1, sync_point=0.5, lead_in=5, lead_out=10)
    assert span.front_gap + span.footage_time + span.back_gap == pytest.approx(15)


def test_sync_event_lands_at_the_lead_in_mark():
    assert file_time_at(5, sync_point=12, lead_in=5) == 12
    assert file_time_at(0, sync_point=12, lead_in=5) == 7
    assert file_time_at(15, sync_point=12, lead_in=5) == 22


def test_slow_motion_source_at_its_own_speed_plays_unchanged():
    # Recorded at 240, plays at 30: Source Speed 1/8. Output Speed 1/8.
    span = source_span(
        duration=60, sync_point=20, lead_in=2, lead_out=4,
        source_speed=1 / 8, output_speed=1 / 8,
    )
    assert (span.file_start, span.file_end) == (18, 24)
    assert span.footage_time == 6


def test_real_time_source_in_a_slow_output_uses_less_file_time():
    # Real-time Source shown at Output Speed 1/8: 2 s of Output is 0.25 s of file.
    span = source_span(
        duration=60, sync_point=20, lead_in=2, lead_out=4,
        source_speed=1, output_speed=1 / 8,
    )
    assert (span.file_start, span.file_end) == pytest.approx((19.75, 20.5))
    assert span.footage_time == pytest.approx(6)


def test_slow_motion_source_in_a_real_time_output_uses_more_file_time():
    span = source_span(
        duration=60, sync_point=20, lead_in=2, lead_out=4,
        source_speed=1 / 8, output_speed=1,
    )
    assert (span.file_start, span.file_end) == pytest.approx((4, 52))
    assert span.footage_time == pytest.approx(6)


def test_gaps_are_in_output_running_time_when_speeds_differ():
    # Slow-motion Source, real-time Output: wants file 4..52 but file is 40 s long.
    span = source_span(
        duration=40, sync_point=20, lead_in=4, lead_out=4,
        source_speed=1 / 8, output_speed=1,
    )
    # Wants file -12..52. 12 s of file missing at the front is 1.5 s of Output.
    assert (span.file_start, span.file_end) == (0, 40)
    assert span.front_gap == pytest.approx(1.5)
    assert span.back_gap == pytest.approx(1.5)


def test_source_entirely_outside_the_output_is_all_gap():
    span = source_span(duration=2, sync_point=0, lead_in=0, lead_out=0.0001)
    assert span.has_footage
    nothing = source_span(duration=0, sync_point=0, lead_in=3, lead_out=4)
    assert not nothing.has_footage
    assert nothing.front_gap + nothing.back_gap == 7


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(duration=10, sync_point=1, lead_in=-1, lead_out=2),
        dict(duration=10, sync_point=1, lead_in=1, lead_out=-2),
        dict(duration=10, sync_point=1, lead_in=0, lead_out=0),
        dict(duration=10, sync_point=1, lead_in=1, lead_out=1, source_speed=0),
        dict(duration=10, sync_point=1, lead_in=1, lead_out=1, output_speed=0),
    ],
)
def test_invalid_timing_is_rejected(kwargs):
    with pytest.raises(ValueError):
        source_span(**kwargs)


# ------------------------------------------------------------- Frame stepping


def test_a_file_time_falls_in_the_frame_on_show_at_that_time():
    # At 29.97 frames per second, frame 99 (counted from 0) runs from 3.3033 to 3.3367 s.
    assert frame_at(3.3, 29.97) == 98
    assert frame_at(3.31, 29.97) == 99
    assert frame_at(0.0, 29.97) == 0


@pytest.mark.parametrize("rate", [10, 23.976, 25, 29.97, 30, 59.94, 60, 120, 240])
def test_the_time_given_for_a_frame_is_inside_that_frame_and_in_whole_milliseconds(rate):
    for frame in (0, 1, 2, 99, 100, 1234, 54321):
        time = frame_time(frame, rate)
        assert frame_at(time, rate) == frame
        assert frame / rate < time < (frame + 1) / rate
        assert time == round(time, 3)


def test_stepping_moves_a_sync_point_by_whole_frames():
    # A typed 3.3 s is in frame 98. One frame on is frame 99, which begins at 3.3033 s.
    assert step_frames(3.3, 1, 29.97, 161) == 3.304
    assert step_frames(3.304, -1, 29.97, 161) == 3.27
    assert step_frames(3.3, 10, 29.97, 161) == pytest.approx(3.604)
    there_and_back = step_frames(step_frames(3.304, 7, 29.97, 161), -7, 29.97, 161)
    assert there_and_back == 3.304


def test_stepping_stops_at_the_first_and_last_frames():
    assert frame_at(step_frames(0.05, -10, 29.97, 161), 29.97) == 0
    assert frame_at(step_frames(5.3, 10, 29.97, 161), 29.97) == 160


# ---------------------------------------------------------------------- Speed


def test_source_speed_is_playback_rate_divided_by_record_rate():
    assert source_speed(60, 240) == 0.25
    assert source_speed(30, None) == 1
    assert source_speed(30, 1) == 30
    # A Record Rate typed in round numbers still makes a real-time Source.
    assert source_speed(29.97002997, 30) == 1
    with pytest.raises(ValueError, match="Record Rate"):
        source_speed(30, 0)


def hints(output_speed):
    """The agreed example: A recorded at 240 and played at 60, B at 30 and 30, Output Rate 60."""
    a = frame_hint(playback_rate=60, source_speed=0.25, output_speed=output_speed, output_rate=60)
    b = frame_hint(playback_rate=30, source_speed=1, output_speed=output_speed, output_rate=60)
    return a, b


def test_at_the_slowest_source_speed_no_frame_is_dropped():
    a, b = hints(output_speed=0.25)
    assert str(a) == "every frame shown once" and a.dropped == 0
    # B shows 7.5 of its frames each second, so each stays for 8 frames of the Output.
    assert b.source_frames_per_output_frame * 60 == 7.5
    assert str(b) == "each frame held for 8 Output frames" and b.dropped == 0


def test_at_real_time_the_slow_motion_source_has_frames_dropped():
    a, b = hints(output_speed=1)
    assert str(a) == "1 frame in 4 shown, 75% dropped" and a.dropped == 0.75
    assert str(b) == "each frame held for 2 Output frames"


def test_a_lower_output_rate_drops_frames_too():
    hint = frame_hint(playback_rate=60, source_speed=1, output_speed=1, output_rate=24)
    assert str(hint) == "1 frame in 2.5 shown, 60% dropped"
