"""Sequence arithmetic, using the scenarios agreed in CONTEXT.md."""

import pytest

from vid_editor.model import EditError, JoinKind, Source, Transition
from vid_editor.sequence import clip_spans, mix_at, on_show, running_time


def test_sources_play_one_after_another_in_full():
    # Clips of 4 s, 6 s and 5 s with no trims give a 15 s Sequence.
    spans = clip_spans([Source("a"), Source("b"), Source("c")], [4, 6, 5])
    assert [(s.output_start, s.output_end) for s in spans] == [(0, 4), (4, 10), (10, 15)]
    assert running_time(spans) == 15


def test_start_and_end_points_trim_a_source():
    spans = clip_spans([Source("a", start_point=1, end_point=3), Source("b")], [4, 6])
    assert (spans[0].file_start, spans[0].file_end, spans[0].time_on_show) == (1, 3, 2)
    assert (spans[1].output_start, spans[1].output_end) == (2, 8)


def test_play_speed_changes_the_time_on_show_not_the_file_stretch():
    # 2 s of file at Play Speed 0.5 is 4 s on show; at 2 it is 1 s.
    spans = clip_spans([Source("a", play_speed=0.5), Source("b", play_speed=2)], [2, 2])
    assert [s.time_on_show for s in spans] == [4, 1]
    assert spans[0].file_time_at(3) == 1.5
    assert spans[1].file_time_at(4.5) == 1.0


def test_on_show_names_the_source_at_a_time():
    spans = clip_spans([Source("a"), Source("b")], [4, 6])
    assert [on_show(spans, t) for t in (-1, 0, 3.99, 4, 9.9, 10, 99)] == [0, 0, 0, 1, 1, 1, 1]


def test_an_end_point_just_past_a_rounded_duration_is_the_end():
    spans = clip_spans([Source("a", end_point=4.001)], [4.0])
    assert spans[0].file_end == 4.0


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (Source("a", start_point=3, end_point=3), "Start Point must be before the End Point"),
        (Source("a", start_point=-1), "cannot be negative"),
        (Source("a", end_point=9), "after the end of the file"),
        (Source("a", play_speed=0), "Play Speed must be greater than zero"),
    ],
)
def test_unusable_settings_are_refused(source, message):
    with pytest.raises(EditError, match=message):
        clip_spans([source], [4])


def test_an_error_names_its_source_once_there_are_several():
    with pytest.raises(EditError, match="^Source 2: "):
        clip_spans([Source("a"), Source("b", start_point=5)], [4, 4])


# ---------------------------------------------------------------- Transitions


def joined(kind: JoinKind, length: float = 1.0, **settings) -> Source:
    return Source("a", join=Transition(kind, length), **settings)


def test_a_crossfade_overlaps_two_sources_and_shortens_the_sequence():
    # Clips of 4 s, 6 s and 5 s with 1 s crossfades: 15 - 1 - 1 = 13 s.
    spans = clip_spans(
        [joined(JoinKind.CROSSFADE), joined(JoinKind.CROSSFADE), Source("c")], [4, 6, 5]
    )
    assert [(s.output_start, s.output_end) for s in spans] == [(0, 4), (3, 9), (8, 13)]
    assert running_time(spans) == 13
    assert [s.time_on_show for s in spans] == [4, 6, 5]


def test_a_fade_through_black_keeps_the_running_time_and_splits_its_length():
    spans = clip_spans([joined(JoinKind.BLACK, 2.0), Source("b")], [4, 6])
    assert running_time(spans) == 10
    assert (spans[0].fade_out, spans[1].fade_in) == (1.0, 1.0)


def test_weights_fade_to_black_and_crossfade():
    black = clip_spans([joined(JoinKind.BLACK, 2.0), Source("b")], [4, 6])
    assert mix_at(black, 3.5) == [(0, 0.5)]
    assert mix_at(black, 4.0) == [(1, 0.0)]
    assert mix_at(black, 4.5) == [(1, 0.5)]
    cross = clip_spans([joined(JoinKind.CROSSFADE, 2.0), Source("b")], [4, 6])
    assert mix_at(cross, 3.0) == [(0, 0.5), (1, 0.5)]
    assert mix_at(cross, 3.5) == [(0, 0.25), (1, 0.75)]
    assert on_show(cross, 3.0) == 1  # halfway is the later Source
    assert on_show(cross, 2.9) == 0


def test_the_fades_at_the_start_and_end_of_the_sequence():
    spans = clip_spans([Source("a"), Source("b")], [4, 6], fade_in=1.0, fade_out=2.0)
    assert (spans[0].fade_in, spans[1].fade_out) == (1.0, 2.0)
    assert mix_at(spans, 0.25) == [(0, 0.25)]
    assert mix_at(spans, 9.0) == [(1, 0.5)]


def test_a_cut_ignores_its_length():
    spans = clip_spans([joined(JoinKind.CUT, 0.0), Source("b")], [4, 6])
    assert running_time(spans) == 10


def test_the_last_sources_join_is_not_used():
    spans = clip_spans([Source("a"), joined(JoinKind.CROSSFADE, 9.0)], [4, 6])
    assert running_time(spans) == 10


def test_a_crossfade_longer_than_a_source_is_refused():
    with pytest.raises(EditError, match=r"Join 1 \(Source 1 to Source 2\).*longer than Source 2's 2.000 s"):
        clip_spans([joined(JoinKind.CROSSFADE, 3.0), Source("b")], [4, 2])


def test_transitions_that_overfill_a_source_are_refused():
    # Source 2 is 2 s long; 1.5 s of crossfade in and 1.5 s of fade out is too much.
    with pytest.raises(EditError, match="^Source 2: its Transitions take 3.000 s"):
        clip_spans(
            [joined(JoinKind.CROSSFADE, 1.5), joined(JoinKind.BLACK, 3.0), Source("c")],
            [4, 2, 4],
        )
    with pytest.raises(EditError, match="^The fades take"):
        clip_spans([Source("a")], [4], fade_in=3, fade_out=2)


def test_a_transition_needs_a_length():
    with pytest.raises(EditError, match="must be greater than zero"):
        clip_spans([joined(JoinKind.BLACK, 0.0), Source("b")], [4, 6])
