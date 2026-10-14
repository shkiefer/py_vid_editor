"""The Preview and the rendered Output of a Sequence."""

import pytest
from conftest import file_time_shown, is_black
from moviepy import VideoFileClip

from vid_editor.model import (
    Corner,
    OutputSettings,
    Project,
    SequenceSettings,
    Source,
    TextOverlay,
    Workflow,
)
from vid_editor.render import (
    EditError,
    render,
    sequence_frame_hints,
    sequence_geometry,
    sequence_preview,
    sequence_silence_reason,
    sequence_spans,
)


def sequence_of(*sources: Source, size=(160, 120), **output) -> Project:
    output.setdefault("lead_in", 1.0)
    output.setdefault("lead_out", 1.0)
    return Project(
        sources=sources,
        output=OutputSettings(**output),
        panels=(),
        workflow=Workflow.SEQUENCE,
        sequence=SequenceSettings(*size),
    )


def test_the_preview_shows_the_source_on_show_at_its_file_time(source_path, source_clip):
    project = sequence_of(
        Source(source_path, start_point=1, end_point=2), Source(source_path, start_point=3)
    )
    clips = [source_clip, source_clip]
    assert [s.output_end for s in sequence_spans(project, clips)] == pytest.approx([1, 2], abs=0.02)
    assert file_time_shown(sequence_preview(project, clips, 0.5)) == pytest.approx(1.5, abs=0.1)
    assert file_time_shown(sequence_preview(project, clips, 1.5)) == pytest.approx(3.5, abs=0.1)


def test_a_slowed_source_shows_its_file_at_its_play_speed(source_path, source_clip):
    project = sequence_of(Source(source_path, start_point=1, end_point=2, play_speed=0.5))
    assert sequence_spans(project, [source_clip])[0].time_on_show == pytest.approx(2)
    assert file_time_shown(sequence_preview(project, [source_clip], 1.0)) == pytest.approx(
        1.5, abs=0.1
    )


def test_a_source_narrower_than_the_panel_gets_bars(tall_source_path, tall_source_clip):
    project = sequence_of(Source(tall_source_path))
    frame = sequence_preview(project, [tall_source_clip], 0.5)
    assert frame.shape[:2] == (120, 160)
    assert is_black(frame[:, :10])  # Bars at the left
    assert frame[60, 80, 2] > 200  # the blue picture in the middle


def test_an_output_width_scales_the_sequence_panel(source_path, source_clip):
    layout = sequence_geometry(sequence_of(Source(source_path), width=80), [source_clip]).layout
    assert (layout.width, layout.height) == (80, 60)


def test_a_sequence_needs_its_panel_size(source_path, source_clip):
    project = Project(
        sources=(Source(source_path),),
        output=OutputSettings(1, 1),
        panels=(),
        workflow=Workflow.SEQUENCE,
    )
    with pytest.raises(EditError, match="no Panel size"):
        sequence_preview(project, [source_clip], 0)


def test_sound_is_kept_only_at_play_speed_1(source_path, source_clip, tall_source_clip):
    assert sequence_silence_reason(source_clip, Source(source_path)) is None
    assert "Play Speed is 0.5" in sequence_silence_reason(
        source_clip, Source(source_path, play_speed=0.5)
    )
    assert "no sound" in sequence_silence_reason(tall_source_clip, Source("tall"))


def test_frame_hints_follow_the_play_speed(source_path, source_clip):
    project = sequence_of(Source(source_path, play_speed=2), Source(source_path, play_speed=0.5))
    hints = sequence_frame_hints(project, [source_clip, source_clip])
    assert [hint.source_frames_per_output_frame for hint in hints] == pytest.approx([2, 0.5])


def test_a_rendered_sequence_plays_its_sources_in_order(
    tmp_path, source_path, source_clip, tall_source_path, tall_source_clip
):
    project = sequence_of(
        Source(source_path, start_point=1, end_point=2),
        Source(tall_source_path, play_speed=2),  # 2 s of file in 1 s
        text_overlay=TextOverlay("Hi", size=12, corner=Corner.TOP_LEFT),
    )
    written = render(project, [source_clip, tall_source_clip], tmp_path / "sequence.mp4")
    with VideoFileClip(str(written)) as output:
        assert output.duration == pytest.approx(2.0, abs=0.15)
        assert (output.w, output.h) == (160, 120)
        assert file_time_shown(output.get_frame(0.55)) == pytest.approx(1.55, abs=0.15)
        later = output.get_frame(1.5)
        assert later[60, 80, 2] > 200  # the tall Source
        assert is_black(later[60:, :10])  # with Bars
        assert output.audio is not None
