"""Audio Tracks: where they play, their volumes, the mix and the Mix Hint."""

from dataclasses import replace

import numpy as np
import pytest
from conftest import SOURCE_SIZE, TRACK_DURATION, TRACK_LEVEL
from moviepy import VideoFileClip

from vid_editor.audio import MixLevel, mix_hint, track_gain, track_span, volume_text
from vid_editor.model import (
    AudioTrack,
    DraftSettings,
    EditError,
    OutputSettings,
    Panel,
    Project,
    SequenceSettings,
    Source,
    Workflow,
)
from vid_editor.render import (
    build_output,
    build_sequence,
    draft_project,
    mix_level,
    open_track,
    render,
    sound_settings,
)


# The test Source's tone is written at full scale in mono, which is read as
# stereo 3 dB lower.
SOURCE_LEVEL = 2**-0.5


def loudness(sound, start: float, end: float) -> float:
    """The loudest sample of a sound between two of its times."""
    times = np.arange(start, end, 1 / 44100)
    return float(np.abs(sound.get_frame(times)).max())


def grid_of(source_path: str, *tracks: AudioTrack, audio_panel=0, **output) -> Project:
    """The 4 s test Source with sound, in a Panel of its size, as a 2 s Output."""
    output.setdefault("lead_in", 1.0)
    output.setdefault("lead_out", 1.0)
    return Project(
        sources=(Source(source_path, sync_point=2.0),),
        output=OutputSettings(audio_tracks=tracks, **output),
        panels=(Panel(*SOURCE_SIZE),),
        audio_panel=audio_panel,
    )


def test_a_track_plays_from_its_start_until_the_output_ends():
    # The example the design was agreed on: a 3 minute song in a 20 s Output.
    span = track_span(AudioTrack("song", start=2, file_start=30, fade_out=1), 180, 20)
    assert (span.output_start, span.output_end) == (2, 20)
    assert (span.file_start, span.file_end) == (30, 48)
    assert span.cut_off == 132 and span.fade_out == 1


def test_a_track_that_runs_out_first_ends_with_its_file_and_does_not_fade():
    span = track_span(AudioTrack("short", start=5, fade_out=2), 10, 20)
    assert (span.output_start, span.output_end, span.cut_off, span.fade_out) == (5, 15, 0, 0)


def test_a_track_starting_after_the_output_ends_does_not_play():
    assert not track_span(AudioTrack("late", start=25), 10, 20).plays


def test_a_track_started_before_the_output_is_heard_from_part_way_in():
    span = track_span(AudioTrack("early", start=-1.5, file_start=1), 10, 20)
    assert (span.output_start, span.file_start, span.output_end) == (0, 2.5, 7.5)


def test_a_file_start_past_the_end_of_the_file_is_an_edit_error():
    with pytest.raises(EditError, match="not before the end of the file"):
        track_span(AudioTrack("song", file_start=12), 10, 20)
    with pytest.raises(EditError, match="from 0 to 200%"):
        track_span(AudioTrack("song", volume=250), 10, 20)


def test_the_fade_out_brings_the_volume_down_in_a_straight_line():
    span = track_span(AudioTrack("song", volume=50, fade_out=2), 60, 10)
    assert track_gain(span, 50, np.array([5.0, 8.0, 9.0, 10.0])) == pytest.approx(
        [0.5, 0.5, 0.25, 0.0]
    )


def test_volumes_are_shown_in_decibels():
    assert volume_text(30) == "30% = −10.5 dB"
    assert volume_text(200) == "200% = +6.0 dB"
    assert volume_text(100) == "100% = 0.0 dB, as in the file"
    assert volume_text(0) == "0%: silent"


def test_the_mix_hint_says_how_loud_the_mix_gets_and_how_to_stop_it_clipping():
    assert mix_hint(MixLevel(peak=0.0, at=0.0, clipped=0.0)) == "Mix Hint: the Output has no sound."
    assert mix_hint(MixLevel(peak=0.5, at=1.25, clipped=0.0)) == (
        "Mix Hint: loudest point −6.0 dB at 1.250 s, no clipping."
    )
    assert mix_hint(MixLevel(peak=1.5, at=1.25, clipped=0.4)) == (
        "Mix Hint: loudest point +3.5 dB at 1.250 s: the mix clips for 0.400 s. "
        "Lower the volumes by about 34% to stop it."
    )


def test_a_track_gives_a_silent_grid_its_sound(source_path, source_clip, track_path, track_clip):
    project = grid_of(source_path, AudioTrack(track_path, start=0.5), audio_panel=None)
    sound = build_output(project, [source_clip], tracks=[track_clip]).audio
    assert sound is not None
    assert loudness(sound, 0.0, 0.45) == pytest.approx(0, abs=1e-6)
    assert loudness(sound, 0.6, 1.0) == pytest.approx(TRACK_LEVEL, abs=0.02)


def test_a_track_plays_when_the_output_speed_silences_the_sources(
    source_path, source_clip, track_path, track_clip
):
    project = grid_of(source_path, AudioTrack(track_path), speed=0.5)
    sound = build_output(project, [source_clip], tracks=[track_clip]).audio
    assert loudness(sound, 0.2, 0.6) == pytest.approx(TRACK_LEVEL, abs=0.02)


def test_the_volumes_scale_the_sources_and_each_track(
    source_path, source_clip, track_path, track_clip
):
    alone = grid_of(source_path, source_volume=50)
    assert mix_level(alone, [source_clip], []).peak == pytest.approx(SOURCE_LEVEL / 2, abs=0.03)
    quiet_track = grid_of(source_path, AudioTrack(track_path, volume=40), audio_panel=None)
    assert mix_level(quiet_track, [source_clip], [track_clip]).peak == pytest.approx(
        0.2, abs=0.02
    )


def test_two_loud_sounds_clip_and_the_mix_level_says_so(
    source_path, source_clip, track_path, track_clip
):
    project = grid_of(source_path, AudioTrack(track_path), source_volume=150)
    level = mix_level(project, [source_clip], [track_clip])
    # A 440 Hz and a 220 Hz tone never peak together, so the sum is less than 1.56.
    assert level.clips and 1.2 < level.peak < 1.5 * SOURCE_LEVEL + TRACK_LEVEL
    assert 0 < level.clipped <= 2
    assert level.lower_by == pytest.approx(1 - 1 / level.peak)
    alone = mix_level(grid_of(source_path), [source_clip], [])
    assert not alone.clips and alone.peak == pytest.approx(SOURCE_LEVEL, abs=0.03)


def test_a_track_cut_off_by_the_end_of_the_output_fades_out(
    source_path, source_clip, track_path, track_clip
):
    project = grid_of(source_path, AudioTrack(track_path, fade_out=1.0), audio_panel=None)
    sound = build_output(project, [source_clip], tracks=[track_clip]).audio
    assert loudness(sound, 0.4, 0.6) == pytest.approx(TRACK_LEVEL, abs=0.02)
    assert loudness(sound, 1.5, 1.55) == pytest.approx(TRACK_LEVEL / 2, abs=0.03)
    assert loudness(sound, 1.95, 1.99) < 0.03


def test_a_track_is_mixed_into_a_sequence(source_path, source_clip, track_path, track_clip):
    project = Project(
        sources=(Source(source_path, end_point=1.0), Source(source_path, end_point=1.0)),
        output=OutputSettings(
            lead_in=0, lead_out=0, source_volume=0, audio_tracks=(AudioTrack(track_path, start=1.0, fade_out=0),)
        ),
        panels=(),
        workflow=Workflow.SEQUENCE,
        sequence=SequenceSettings(*SOURCE_SIZE),
    )
    sound = build_sequence(project, [source_clip, source_clip], tracks=[track_clip]).audio
    assert loudness(sound, 0.1, 0.9) == pytest.approx(0, abs=1e-6)  # the Sources at 0%
    assert loudness(sound, 1.1, 1.5) == pytest.approx(TRACK_LEVEL, abs=0.02)


def test_a_grid_draft_moves_each_track_with_the_sync_event(source_path, source_clip, track_path):
    project = grid_of(source_path, AudioTrack(track_path, start=0.25), lead_in=1.0)
    loud = draft_project(project, [source_clip], DraftSettings(lead_in=0.5, lead_out=0.5, sound=True))
    assert loud.output.audio_tracks[0].start == pytest.approx(-0.25)
    quiet = draft_project(project, [source_clip], DraftSettings(lead_in=0.5, lead_out=0.5))
    assert quiet.output.audio_tracks == ()


def test_a_change_to_the_picture_leaves_the_sound_settings_alone(source_path, track_path):
    project = grid_of(source_path, AudioTrack(track_path))
    cropped = replace(
        project,
        sources=(replace(project.sources[0], rotation=90.0),),
        output=replace(project.output, width=80),
    )
    assert sound_settings(cropped) == sound_settings(project)
    louder = replace(project, output=replace(project.output, source_volume=50))
    assert sound_settings(louder) != sound_settings(project)


def test_render_writes_the_track_into_the_output(source_path, source_clip, track_path, tmp_path):
    project = grid_of(source_path, AudioTrack(track_path), audio_panel=None)
    with open_track(track_path) as track:
        written = render(project, [source_clip], tmp_path / "out.mp4", tracks=[track])
    with VideoFileClip(str(written)) as result:
        assert result.audio is not None
        assert loudness(result.audio, 0.4, 0.8) == pytest.approx(TRACK_LEVEL, abs=0.05)


def test_an_unreadable_track_is_an_edit_error(tmp_path):
    with pytest.raises(EditError, match="No file found"):
        open_track(str(tmp_path / "missing.mp3"))
    text = tmp_path / "notes.mp3"
    text.write_text("not sound")
    with pytest.raises(EditError, match="as sound"):
        open_track(str(text))


def test_the_track_fixture_is_as_long_as_it_says(track_clip):
    assert track_clip.duration == pytest.approx(TRACK_DURATION, abs=0.05)
