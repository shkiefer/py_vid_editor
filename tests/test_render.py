"""The Preview and the rendered Output for one Source."""

from dataclasses import replace

import pytest
from conftest import file_time_shown, is_black
from moviepy import VideoFileClip
from PIL import Image
from moviepy.video.io.ffmpeg_reader import FFmpegInfosParser

from vid_editor.model import (
    Corner,
    Crop,
    ImageOverlay,
    OutputSettings,
    Project,
    Quality,
    Source,
    TextOverlay,
)
from vid_editor.render import (
    EditError,
    build_output,
    edited_size,
    geometry,
    fit_within,
    open_source,
    preview,
    render,
    silence_reason,
    source_frame,
    source_info,
    span_of,
    speeds,
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


# What ffmpeg reports for a portrait iPhone recording. The line after the
# rotation has no "name: value" shape, which MoviePy 2.2.1 cannot parse.
IPHONE_REPORT = """\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'IMG_0001.MOV':
  Metadata:
    major_brand     : qt
    com.apple.quicktime.model: iPhone 15 Pro Max
  Duration: 00:00:05.37, start: 0.000000, bitrate: 8821 kb/s
  Stream #0:0[0x1](und): Video: hevc (Main 10) (hvc1 / 0x31637668), yuv420p10le(tv, bt2020nc/bt2020/arib-std-b67), 1920x1080, 8580 kb/s, 29.98 fps, 29.97 tbr, 600 tbn (default)
      Metadata:
        handler_name    : Core Media Video
        encoder         : HEVC
      Side data:
        DOVI configuration record: version: 1.0, profile: 8, level: 4, rpu flag: 1, el flag: 0, bl flag: 1, compatibility id: 4, compression: 0
        displaymatrix: rotation of -90.00 degrees
        Ambient Viewing Environment, ambient_illuminance=314.000000, ambient_light_x=0.312700, ambient_light_y=0.329000
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 170 kb/s (default)
      Metadata:
        handler_name    : Core Media Audio
  Stream #0:2[0x3](und): Data: none (mebx / 0x7862656D), 0 kb/s (default)
      Metadata:
        handler_name    : Core Media Metadata
At least one output file must be specified
"""


def test_an_iphone_recording_with_extra_side_data_can_be_read():
    infos = FFmpegInfosParser(IPHONE_REPORT, "IMG_0001.MOV").parse()
    assert infos["video_size"] == [1920, 1080]
    assert infos["video_rotation"] == 90
    assert infos["duration"] == pytest.approx(5.37)
    assert infos["audio_found"]


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


def test_source_width_resizes_after_the_crop_without_distortion(source_path, source_clip):
    # Cropped to 80 by 120, then halved.
    source = Source(source_path, crop=Crop(left=80), width=40)
    assert edited_size(source_clip, source) == (40, 60)
    frame = preview(project_for(source), [source_clip], output_time=1.0)
    assert frame.shape[:2] == (60, 40)
    assert edited_size(source_clip, Source(source_path, rotation=90, width=240)) == (240, 320)
    with pytest.raises(EditError, match="at least 2"):
        edited_size(source_clip, Source(source_path, width=1))


def test_fit_within_shrinks_a_frame_to_a_box_and_never_enlarges(source_path, source_clip):
    frame = preview(project_for(Source(source_path)), [source_clip], output_time=1.0)
    assert fit_within(frame, 80, 80).shape[:2] == (60, 80)
    assert fit_within(frame, 400, 30).shape[:2] == (30, 40)
    assert fit_within(frame, 400, 400) is frame


def test_output_width_scales_the_picture_to_even_dimensions(source_path, source_clip):
    project = project_for(Source(source_path), width=101)
    assert tuple(build_output(project, [source_clip]).size) == (100, 74)
    natural = project_for(Source(source_path))
    assert tuple(build_output(natural, [source_clip]).size) == (160, 120)


def test_a_text_overlay_is_drawn_in_its_corner_of_the_output(source_path, source_clip):
    plain = preview(project_for(Source(source_path)), [source_clip], output_time=1.0)
    project = project_for(
        Source(source_path), text_overlay=TextOverlay("Hi", size=20, corner=Corner.BOTTOM_RIGHT)
    )
    frame = preview(project, [source_clip], output_time=1.0)
    assert frame.shape == plain.shape
    assert frame[-30:, -30:].min(axis=2).max() > 200, "no white text in the bottom right"
    assert frame[-1, -1, 0] < 0.6 * plain[-1, -1, 0], "the box did not darken its corner"
    assert (frame[:60] == plain[:60]).all(), "the top half was changed"


def test_overlays_are_measured_on_the_output_after_it_is_scaled(source_path, source_clip, tmp_path):
    logo = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), (0, 0, 255)).save(logo)
    overlay = ImageOverlay(str(logo), corner=Corner.TOP_RIGHT, width_percent=50, background_opacity=1)
    project = project_for(Source(source_path), width=320, image_overlay=overlay)
    frame = preview(project, [source_clip], output_time=1.0)
    assert frame.shape[:2] == (240, 320)
    # The box is 160 wide: black at its edge, the blue image inside, footage beside it.
    assert frame[0, 161:].max() < 30
    assert frame[40, 240, 2] > 200 and frame[40, 240, 0] < 60
    assert frame[40, 150, 1] > 200


def test_overlays_stay_on_through_a_gap(source_path, source_clip):
    project = project_for(
        Source(source_path, sync_point=1.0),
        lead_in=3.0,
        lead_out=1.0,
        text_overlay=TextOverlay("Hi", size=20, corner=Corner.TOP_LEFT),
    )
    frame = preview(project, [source_clip], output_time=1.0)
    assert is_black(frame[60:])
    assert frame[:30, :30].max() > 200


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


def test_render_writes_the_overlays_into_the_file(source_path, source_clip, tmp_path):
    project = project_for(
        Source(source_path), text_overlay=TextOverlay("Hi", size=24, corner=Corner.TOP_RIGHT)
    )
    written = render(project, [source_clip], tmp_path / "out.mp4")
    with VideoFileClip(str(written)) as result:
        assert result.audio is not None
        frame = result.get_frame(1.0)
        assert frame[:30, -30:].min(axis=2).max() > 180
        assert file_time_shown(frame) == pytest.approx(0.0, abs=3 * FRAME)


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


# ------------------------------------------------------------ Several Sources


def pair(source_path, tall_source_path, first=None, second=None, audio_source=0, **output) -> Project:
    """The 160 by 120 Source with sound on the left, the 100 by 200 silent one on the right."""
    output.setdefault("lead_in", 1.0)
    output.setdefault("lead_out", 1.0)
    return Project(
        sources=(
            Source(source_path, **(first or {"sync_point": 2.0})),
            Source(tall_source_path, **(second or {"sync_point": 1.0})),
        ),
        output=OutputSettings(**output),
        audio_source=audio_source,
    )


def test_sources_sit_side_by_side_matched_to_the_first_height(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    project = pair(source_path, tall_source_path)
    clips = [source_clip, tall_source_clip]
    frame = preview(project, clips, output_time=1.0)
    assert frame.shape[:2] == (120, 220)
    # Left Panel: the first Source, green quadrant top left. Right Panel: the blue Source.
    assert frame[30, 40, 1] > 200 and frame[30, 40, 2] < 60
    assert frame[60, 190, 2] > 200 and frame[60, 190, 1] < 60

    sizes = geometry(project, clips)
    assert sizes.cropped == ((160, 120), (100, 200))
    assert sizes.layout.panel_widths == (160, 60)
    assert (sizes.layout.width, sizes.layout.height) == (220, 120)


def test_each_source_is_shown_at_its_own_sync_point(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    project = pair(source_path, tall_source_path)
    frame = preview(project, [source_clip, tall_source_clip], output_time=1.0)
    assert file_time_shown(frame[:, :160]) == pytest.approx(2.0, abs=2 * FRAME)
    assert file_time_shown(frame[:, 160:]) == pytest.approx(1.0, abs=2 * FRAME)


def test_a_gap_blacks_out_one_panel_and_leaves_the_other_playing(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    # The tall Source is 2 s long with its Sync Point at 1 s: 1 s of footage each side.
    project = pair(source_path, tall_source_path, lead_in=2.0, lead_out=2.0)
    clips = [source_clip, tall_source_clip]
    early = preview(project, clips, output_time=0.5)
    late = preview(project, clips, output_time=3.5)
    for frame, file_time in ((early, 0.5), (late, 3.5)):
        assert is_black(frame[:, 160:])
        assert file_time_shown(frame[:, :160]) == pytest.approx(file_time, abs=2 * FRAME)
    assert build_output(project, clips).duration == pytest.approx(4.0)


def test_only_the_first_source_can_be_resized(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    project = pair(
        source_path,
        tall_source_path,
        first={"width": 80},
        second={"width": 400, "crop": Crop(top=100)},
    )
    sizes = geometry(project, [source_clip, tall_source_clip])
    assert sizes.resized == (80, 60)
    assert sizes.cropped[1] == (100, 100)
    assert sizes.layout.panel_widths == (80, 60)
    assert tuple(build_output(project, [source_clip, tall_source_clip]).size) == (140, 60)


def test_output_width_scales_every_panel(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    project = pair(source_path, tall_source_path, width=440)
    frame = preview(project, [source_clip, tall_source_clip], output_time=1.0)
    assert frame.shape[:2] == (240, 440)
    assert frame[120, 380, 2] > 200


def test_the_output_rate_defaults_to_the_highest_playback_rate(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    clips = [source_clip, tall_source_clip]
    assert build_output(pair(source_path, tall_source_path), clips).fps == pytest.approx(20)
    assert build_output(pair(source_path, tall_source_path, rate=12), clips).fps == 12


def test_the_audio_source_alone_gives_the_output_its_sound(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    clips = [source_clip, tall_source_clip]
    assert build_output(pair(source_path, tall_source_path, audio_source=0), clips).audio is not None
    # The second Source has no sound, and "none" is allowed.
    assert build_output(pair(source_path, tall_source_path, audio_source=1), clips).audio is None
    assert build_output(pair(source_path, tall_source_path, audio_source=None), clips).audio is None
    with pytest.raises(EditError, match="Audio Source"):
        build_output(pair(source_path, tall_source_path, audio_source=2), clips)
    assert build_output(project_for(Source(source_path)), [source_clip]).audio is not None
    silent = Project((Source(source_path),), OutputSettings(1.0, 1.0), audio_source=None)
    assert build_output(silent, [source_clip]).audio is None


def test_a_problem_names_the_source_it_belongs_to(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    project = pair(source_path, tall_source_path, second={"crop": Crop(left=150)})
    with pytest.raises(EditError, match="Source 2: The crop removes the whole picture"):
        geometry(project, [source_clip, tall_source_clip])
    with pytest.raises(EditError, match="Source 2: The crop removes the whole picture"):
        build_output(project, [source_clip, tall_source_clip])


def test_render_writes_a_row_with_overlays_and_the_audio_source_sound(
    source_path, tall_source_path, source_clip, tall_source_clip, tmp_path
):
    project = pair(
        source_path,
        tall_source_path,
        lead_in=2.0,
        lead_out=2.0,
        text_overlay=TextOverlay("Hi", size=20, corner=Corner.TOP_RIGHT),
    )
    written = render(project, [source_clip, tall_source_clip], tmp_path / "row.mp4")
    with VideoFileClip(str(written)) as result:
        assert result.size == [220, 120]
        assert result.duration == pytest.approx(4.0, abs=0.15)
        assert result.fps == pytest.approx(20)
        assert result.audio is not None
        gap = result.get_frame(0.5)
        assert is_black(gap[40:, 170:])
        assert gap[:30, -30:].min(axis=2).max() > 180, "the Overlay is missing over the Gap"
        middle = result.get_frame(2.0)
        assert middle[60, 190, 2] > 180
        assert file_time_shown(middle[:, :160]) == pytest.approx(2.0, abs=3 * FRAME)

    silent = render(
        pair(source_path, tall_source_path, audio_source=None),
        [source_clip, tall_source_clip],
        tmp_path / "silent.mp4",
    )
    with VideoFileClip(str(silent)) as result:
        assert result.audio is None


# ------------------------------------------------------------- Frame stepping


def test_source_info_counts_the_frames(source_clip):
    assert source_info(source_clip).frame_count == pytest.approx(40, abs=1)


def test_frames_can_be_stepped_through_in_either_direction(source_clip):
    def shown(frame: int) -> float:
        return file_time_shown(source_frame(source_clip, (frame + 0.5) / 10))

    forward = [shown(frame) for frame in (20, 21, 22, 23)]
    back = [shown(frame) for frame in (22, 21, 20, 10, 9, 8)]
    assert forward == sorted(forward) and forward[-1] - forward[0] == pytest.approx(0.3, abs=0.06)
    assert back == sorted(back, reverse=True)
    assert back[:3] == forward[2::-1], "a frame read again is not the frame read before"
    assert shown(9) == pytest.approx(0.9, abs=0.06)
    # Past the end of the file the last frame is given, not an error.
    assert file_time_shown(source_frame(source_clip, 99.0)) == pytest.approx(3.9, abs=0.06)


def test_the_preview_shows_the_same_picture_as_the_rendered_output(
    source_path, tall_source_path, source_clip, tall_source_clip, tmp_path
):
    project = pair(
        source_path,
        tall_source_path,
        first={"sync_point": 2.0, "rotation": 90, "crop": Crop(top=10, left=20), "width": 80},
        second={"sync_point": 1.0, "aspect_override": (120, 100), "rotation": 3},
        width=300,
        text_overlay=TextOverlay("Hi", size=14),
    )
    clips = [source_clip, tall_source_clip]
    seen = preview(project, clips, output_time=1.0).astype(int)
    built = build_output(project, clips).get_frame(1.0).astype(int)
    assert seen.shape == built.shape
    assert abs(seen - built).mean() < 3


# ---------------------------------------------------------------------- Speed


def test_the_output_speed_defaults_to_the_slowest_source_speed(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    clips = [source_clip, tall_source_clip]
    real_time = pair(source_path, tall_source_path)
    assert speeds(real_time, clips).output == 1
    # The 20 frames per second Source was recorded at 40: half of real time.
    slow = pair(source_path, tall_source_path, second={"sync_point": 1.0, "record_rate": 40})
    assert speeds(slow, clips).sources == (1, 0.5)
    assert speeds(slow, clips).output == 0.5
    assert speeds(replace(slow, output=replace(slow.output, speed=1.0)), clips).output == 1
    with pytest.raises(EditError, match="Output Speed"):
        speeds(replace(slow, output=replace(slow.output, speed=0)), clips)


def test_every_source_moves_through_the_event_at_the_output_speed(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    clips = [source_clip, tall_source_clip]
    project = pair(
        source_path,
        tall_source_path,
        second={"sync_point": 1.0, "record_rate": 40},
        lead_in=1.0,
        lead_out=1.0,
    )
    # Output Speed 0.5. The slow Source plays as it is; the real-time one is slowed to half.
    assert span_of(tall_source_clip, project.sources[1], project, 0.5).file_start == 0.0
    slowed = span_of(source_clip, project.sources[0], project, 0.5)
    assert (slowed.file_start, slowed.file_end) == (1.5, 2.5)
    frame = preview(project, clips, output_time=2.0 - FRAME)
    assert file_time_shown(frame[:, :160]) == pytest.approx(2.45, abs=2 * FRAME)
    assert file_time_shown(frame[:, 160:]) == pytest.approx(1.9, abs=2 * FRAME)

    built = build_output(project, clips)
    assert built.duration == pytest.approx(2.0)
    late = built.get_frame(2.0 - FRAME)
    assert file_time_shown(late[:, :160]) == pytest.approx(2.45, abs=2 * FRAME)
    assert file_time_shown(late[:, 160:]) == pytest.approx(1.9, abs=2 * FRAME)


def test_at_real_time_a_slow_motion_source_is_sped_up_and_runs_out_sooner(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    clips = [source_clip, tall_source_clip]
    project = pair(
        source_path,
        tall_source_path,
        second={"sync_point": 1.0, "record_rate": 40},
        lead_in=1.0,
        lead_out=1.0,
        speed=1.0,
    )
    # 2 s of slow-motion file is 1 s of the real event: half a second each side.
    span = span_of(tall_source_clip, project.sources[1], project, 1.0)
    assert (span.front_gap, span.footage_time, span.back_gap) == (0.5, 1.0, 0.5)
    assert is_black(preview(project, clips, output_time=0.25)[:, 160:])
    middle = preview(project, clips, output_time=1.25)
    assert file_time_shown(middle[:, 160:]) == pytest.approx(1.5, abs=2 * FRAME)
    assert file_time_shown(middle[:, :160]) == pytest.approx(2.25, abs=2 * FRAME)
    built = build_output(project, clips).get_frame(1.25)
    assert file_time_shown(built[:, 160:]) == pytest.approx(1.5, abs=2 * FRAME)


def test_sound_is_kept_only_when_the_audio_source_and_the_output_are_real_time(
    source_path, tall_source_path, source_clip, tall_source_clip
):
    clips = [source_clip, tall_source_clip]
    slow_second = {"sync_point": 1.0, "record_rate": 40}

    real_time = pair(source_path, tall_source_path, second=slow_second, speed=1.0)
    assert silence_reason(real_time, clips) is None
    assert build_output(real_time, clips).audio is not None

    slowest = pair(source_path, tall_source_path, second=slow_second)
    assert "Output Speed is 0.5" in silence_reason(slowest, clips)
    assert build_output(slowest, clips).audio is None

    slow_audio = pair(
        source_path, tall_source_path, first={"sync_point": 2.0, "record_rate": 20}, speed=1.0
    )
    assert "Source 1 is not real time" in silence_reason(slow_audio, clips)
    assert build_output(slow_audio, clips).audio is None

    assert "has no sound" in silence_reason(pair(source_path, tall_source_path, audio_source=1), clips)
    assert "no Audio Source" in silence_reason(pair(source_path, tall_source_path, audio_source=None), clips)


def test_render_changes_speed_and_keeps_the_running_time(
    source_path, tall_source_path, source_clip, tall_source_clip, tmp_path
):
    project = pair(
        source_path,
        tall_source_path,
        second={"sync_point": 1.0, "record_rate": 40},
        lead_in=1.0,
        lead_out=1.0,
    )
    written = render(project, [source_clip, tall_source_clip], tmp_path / "slow.mp4")
    with VideoFileClip(str(written)) as result:
        assert result.duration == pytest.approx(2.0, abs=0.15)
        assert result.audio is None
        early, late = result.get_frame(0.25), result.get_frame(1.75)
        # The real-time Source covers 1 s of its file in the 2 s Output.
        assert file_time_shown(early[:, :160]) == pytest.approx(1.625, abs=3 * FRAME)
        assert file_time_shown(late[:, :160]) == pytest.approx(2.375, abs=3 * FRAME)
        assert file_time_shown(late[:, 160:]) == pytest.approx(1.75, abs=3 * FRAME)
