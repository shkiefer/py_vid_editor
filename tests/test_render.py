"""The Preview and the rendered Output for one Source."""

from dataclasses import replace

import pytest
from conftest import file_time_shown, is_black
from moviepy import VideoFileClip

from vid_editor.model import Crop, OutputSettings, Project, Quality, Source
from vid_editor.render import (
    EditError,
    build_output,
    edited_size,
    open_source,
    preview,
    render,
    source_info,
)

FRAME = 0.1  # one frame of the 10 frames per second test Source


def project_for(source: Source, **output) -> Project:
    output.setdefault("lead_in", 1.0)
    output.setdefault("lead_out", 1.0)
    return Project(sources=(source,), output=OutputSettings(**output))


def test_source_info_reads_the_file(source_clip):
    info = source_info(source_clip)
    assert info.duration == pytest.approx(4.0, abs=0.15)
    assert (info.width, info.height) == (160, 120)
    assert info.playback_rate == pytest.approx(10)
    assert info.has_sound


def test_opening_a_missing_or_unreadable_file_is_an_edit_error(tmp_path):
    with pytest.raises(EditError, match="No file found"):
        open_source(str(tmp_path / "missing.mp4"))
    not_video = tmp_path / "notes.mp4"
    not_video.write_text("not a video")
    with pytest.raises(EditError, match="Could not read"):
        open_source(str(not_video))


def test_preview_at_the_lead_in_mark_shows_the_sync_point(source_path, source_clip):
    project = project_for(Source(source_path, sync_point=2.0), lead_in=1.0, lead_out=1.5)
    frame = preview(project, [source_clip], output_time=1.0)
    assert file_time_shown(frame) == pytest.approx(2.0, abs=2 * FRAME)


def test_front_gap_is_black_then_footage_starts_from_the_first_frame(source_path, source_clip):
    # 1 s of footage before the Sync Event but a 3 s Lead-in: 2 s front Gap.
    project = project_for(Source(source_path, sync_point=1.0), lead_in=3.0, lead_out=1.0)
    assert is_black(preview(project, [source_clip], output_time=1.0))
    frame = preview(project, [source_clip], output_time=2.5)
    assert file_time_shown(frame) == pytest.approx(0.5, abs=2 * FRAME)


def test_back_gap_is_black_and_does_not_freeze_the_last_frame(source_path, source_clip):
    # 1 s of footage after the Sync Event but a 3 s Lead-out: 2 s back Gap.
    project = project_for(Source(source_path, sync_point=3.0), lead_in=1.0, lead_out=3.0)
    frame = preview(project, [source_clip], output_time=1.5)
    assert file_time_shown(frame) == pytest.approx(3.5, abs=2 * FRAME)
    assert is_black(preview(project, [source_clip], output_time=3.0))
    assert build_output(project, [source_clip]).duration == pytest.approx(4.0)


def test_rotation_is_anticlockwise_and_swaps_width_and_height(source_path, source_clip):
    source = Source(source_path, rotation=90)
    assert edited_size(source_clip, source) == (120, 160)
    frame = preview(project_for(source), [source_clip], output_time=1.0)
    # The green quadrant starts top-left; a quarter turn anticlockwise puts it bottom-left.
    assert frame[120, 30, 1] > 200
    assert frame[40, 30, 1] < 60
    assert frame[120, 90, 1] < 60


def test_crop_is_measured_on_the_picture_after_rotation(source_path, source_clip):
    source = Source(source_path, rotation=90, crop=Crop(top=10, bottom=0, left=20, right=0))
    assert edited_size(source_clip, source) == (100, 150)


def test_crop_removes_the_named_edges(source_path, source_clip):
    # Removing the left half removes the green quadrant.
    source = Source(source_path, crop=Crop(left=80))
    frame = preview(project_for(source), [source_clip], output_time=1.0)
    assert frame.shape[:2] == (120, 80)
    assert frame[:, :, 1].max() < 60


def test_crop_that_removes_the_whole_picture_is_an_edit_error(source_path, source_clip):
    source = Source(source_path, crop=Crop(left=100, right=60))
    with pytest.raises(EditError, match="removes the whole picture"):
        edited_size(source_clip, source)
    with pytest.raises(EditError, match="negative"):
        edited_size(source_clip, Source(source_path, crop=Crop(top=-1)))


def test_any_rotation_angle_grows_the_picture_to_fit(source_path, source_clip):
    width, height = edited_size(source_clip, Source(source_path, rotation=3))
    assert width > 160 and height > 120


def test_aspect_override_is_applied_before_rotation(source_path, source_clip):
    source = Source(source_path, aspect_override=(200, 100), rotation=90)
    assert edited_size(source_clip, source) == (100, 200)


def test_output_width_scales_the_picture_to_even_dimensions(source_path, source_clip):
    project = project_for(Source(source_path), width=101)
    assert tuple(build_output(project, [source_clip]).size) == (100, 74)
    natural = project_for(Source(source_path))
    assert tuple(build_output(natural, [source_clip]).size) == (160, 120)


def test_output_rate_defaults_to_the_playback_rate(source_path, source_clip):
    assert build_output(project_for(Source(source_path)), [source_clip]).fps == pytest.approx(10)
    chosen = project_for(Source(source_path), rate=25)
    assert build_output(chosen, [source_clip]).fps == 25


def test_render_writes_an_mp4_with_gaps_footage_and_sound(source_path, source_clip, tmp_path):
    project = project_for(
        Source(source_path, sync_point=1.0), lead_in=2.0, lead_out=1.0, quality=Quality.HIGH
    )
    progress = []

    written = render(
        project,
        [source_clip],
        tmp_path / "nested" / "out.mp4",
        on_progress=lambda stage, fraction: progress.append((stage, fraction)),
    )

    assert written.is_file()
    assert {stage for stage, _ in progress} == {"sound", "picture"}
    assert progress[-1] == ("picture", 1.0)
    with VideoFileClip(str(written)) as result:
        assert result.duration == pytest.approx(3.0, abs=0.15)
        assert result.size == [160, 120]
        assert result.audio is not None
        assert is_black(result.get_frame(0.5))
        assert file_time_shown(result.get_frame(2.0)) == pytest.approx(1.0, abs=3 * FRAME)


def test_smaller_quality_levels_make_smaller_files(source_path, source_clip, tmp_path):
    base = project_for(Source(source_path, sync_point=2.0), lead_in=2.0, lead_out=2.0)
    sizes = {}
    for quality in Quality:
        project = replace(base, output=replace(base.output, quality=quality))
        sizes[quality] = render(project, [source_clip], tmp_path / f"{quality.name}.mp4").stat().st_size
    assert sizes[Quality.HIGH] >= sizes[Quality.MEDIUM] >= sizes[Quality.SMALL]


def test_render_refuses_a_file_name_that_is_not_mp4(source_path, source_clip, tmp_path):
    with pytest.raises(EditError, match=".mp4"):
        render(project_for(Source(source_path)), [source_clip], tmp_path / "out.wmv")
