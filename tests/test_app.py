"""The Streamlit screen, driven headlessly."""

import json
import shutil
from pathlib import Path

import pytest
import streamlit as st
from conftest import file_time_shown, is_black
from moviepy import VideoFileClip
from PIL import Image
from streamlit.testing.v1 import AppTest

from vid_editor import dialogs

APP = str(Path(__file__).parent.parent / "streamlit_app.py")


def open_app(*source_paths: str) -> AppTest:
    """The screen with these Sources added, left to right."""
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    for source_path in source_paths:
        add_source(app, source_path)
    assert not app.exception
    return app


def add_source(app: AppTest, source_path: str) -> None:
    app.text_input(key="add_path").set_value(source_path).run()
    assert not app.exception


TIMING = ["Source", "Footage from (s)", "Footage to (s)", "Front Gap (s)", "Back Gap (s)"]


def timing_row(app: AppTest, number: int = 1) -> dict:
    return app.table[0].value.iloc[number - 1][TIMING].to_dict()


def speed_row(app: AppTest, number: int = 1) -> tuple[str, str]:
    row = app.table[0].value.iloc[number - 1]
    return row["Source Speed"], row["Frame Hint"]


def captions(app: AppTest) -> str:
    return "\n".join(caption.value for caption in app.caption)


def test_without_a_source_the_app_asks_for_one():
    app = open_app()
    assert "Add a Source file" in app.info[0].value
    assert not app.table


def test_a_missing_file_is_reported_without_crashing(tmp_path):
    app = open_app(str(tmp_path / "missing.mp4"))
    assert "No file found" in app.error[0].value
    assert "Add a Source file" in app.info[0].value


def test_a_new_source_defaults_to_the_whole_file(source_path):
    app = open_app(source_path)
    assert app.number_input(key="sync_point_1").value == 0
    assert app.number_input(key="lead_in").value == 0
    assert app.number_input(key="lead_out").value == pytest.approx(4.0, abs=0.15)
    assert app.number_input(key="out_rate").value is None
    assert "at 10 frames per second, with sound from Source 1" in captions(app)
    assert app.text_input(key="out_name").value == "source_edited.mp4"
    row = timing_row(app)
    assert row["Front Gap (s)"] == "0.000" and row["Back Gap (s)"] == "0.000"
    assert any("160 by 120" in caption.value for caption in app.caption)


def test_timing_feedback_shows_footage_times_and_gaps(source_path):
    app = open_app(source_path)
    app.number_input(key="sync_point_1").set_value(1.0)
    app.number_input(key="lead_in").set_value(3.0)
    app.number_input(key="lead_out").set_value(1.0).run()
    assert not app.exception
    assert timing_row(app) == {
        "Source": "Source 1: source.mp4",
        "Footage from (s)": "0.000",
        "Footage to (s)": "2.000",
        "Front Gap (s)": "2.000",
        "Back Gap (s)": "0.000",
    }


def test_quarter_turn_buttons_rotate_and_change_the_output_size(source_path):
    app = open_app(source_path)
    app.button(key="turn_left_1").click().run()
    assert not app.exception
    assert app.number_input(key="rotation_1").value == 90
    assert any("120 by 160" in caption.value for caption in app.caption)
    app.button(key="turn_right_1").click().run()
    app.button(key="turn_right_1").click().run()
    assert app.number_input(key="rotation_1").value == 270


def test_an_impossible_crop_is_reported_without_crashing(source_path):
    app = open_app(source_path)
    app.number_input(key="crop_left_1").set_value(200).run()
    assert not app.exception
    assert "removes the whole picture" in app.error[0].value


def test_resizing_the_source_reports_both_sizes_and_sets_the_output_size(source_path):
    app = open_app(source_path)
    assert any("this Source is 160 by 120 pixels." in caption.value for caption in app.caption)
    app.number_input(key="crop_left_1").set_value(80)
    app.number_input(key="source_width_1").set_value(40).run()
    assert not app.exception
    assert any(
        "this Source is 80 by 120 pixels, resized to 40 by 60 (50% of that size)." in caption.value
        for caption in app.caption
    )
    assert any("Output is 40 by 60" in caption.value for caption in app.caption)


def test_overlays_are_off_until_switched_on_and_then_report_their_size(source_path):
    app = open_app(source_path)
    assert not app.toggle(key="text_on").value and not app.toggle(key="image_on").value
    assert app.text_area(key="text_value").disabled

    app.toggle(key="text_on").set_value(True).run()
    assert not app.exception
    # The default text at 30 pixels is wider than the 160 pixel test Output.
    assert any("larger than the 160 by 120 Output" in warning.value for warning in app.warning)

    app.text_area(key="text_value").set_value("Hi")
    app.number_input(key="text_size").set_value(12).run()
    assert not app.warning
    assert any("The text box is" in caption.value for caption in app.caption)

    app.text_area(key="text_value").set_value("").run()
    assert any("Type some text" in caption.value for caption in app.caption)


def test_overlays_sharing_a_corner_give_a_warning(source_path, tmp_path):
    logo = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), (0, 0, 255)).save(logo)
    app = open_app(source_path)
    app.toggle(key="image_on").set_value(True).run()
    assert any("Choose an image file" in caption.value for caption in app.caption)

    app.text_input(key="image_path").set_value(str(logo)).run()
    assert not app.exception and not app.warning
    assert any("The image box is 40 by 22 pixels" in caption.value for caption in app.caption)

    app.toggle(key="text_on").set_value(True).run()
    app.text_area(key="text_value").set_value("Hi")
    app.number_input(key="text_size").set_value(12)
    app.selectbox(key="text_corner").set_value(app.session_state["image_corner"]).run()
    assert not app.exception
    assert any("Both Overlays are in the top left corner" in warning.value for warning in app.warning)


def test_a_missing_overlay_image_is_reported_without_crashing(source_path, tmp_path):
    app = open_app(source_path)
    app.toggle(key="image_on").set_value(True).run()
    app.text_input(key="image_path").set_value(str(tmp_path / "missing.png")).run()
    assert not app.exception
    assert "No image found" in app.error[0].value


def test_zero_running_time_is_reported(source_path):
    app = open_app(source_path)
    app.number_input(key="lead_out").set_value(0.0).run()
    assert not app.exception
    assert "greater than zero" in app.error[0].value


def test_render_writes_the_output_to_the_chosen_folder(source_path, tmp_path):
    app = open_app(source_path)
    app.number_input(key="sync_point_1").set_value(1.0)
    app.number_input(key="lead_in").set_value(2.0)
    app.number_input(key="lead_out").set_value(1.0)
    app.number_input(key="crop_left_1").set_value(80)
    app.text_input(key="out_folder").set_value(str(tmp_path))
    app.text_input(key="out_name").set_value("result.mp4").run()
    app.button(key="render").click().run()

    assert not app.exception
    written = tmp_path / "result.mp4"
    assert str(written) in app.success[0].value
    with VideoFileClip(str(written)) as output:
        assert output.size == [80, 120]
        assert output.duration == pytest.approx(3.0, abs=0.15)
        assert is_black(output.get_frame(0.5))
        assert file_time_shown(output.get_frame(2.0)) == pytest.approx(1.0, abs=0.3)


def test_an_existing_output_is_not_replaced_without_consent(source_path, tmp_path):
    existing = tmp_path / "result.mp4"
    existing.write_text("keep me")
    app = open_app(source_path)
    app.text_input(key="out_folder").set_value(str(tmp_path))
    app.text_input(key="out_name").set_value("result.mp4").run()
    assert app.button(key="render").disabled
    assert existing.read_text() == "keep me"

    app.checkbox(key="replace").check().run()
    assert not app.button(key="render").disabled


def test_the_output_cannot_replace_its_own_source(source_path):
    app = open_app(source_path)
    app.text_input(key="out_name").set_value(Path(source_path).name).run()
    assert "cannot replace its own Source" in app.warning[0].value
    assert app.button(key="render").disabled


def test_the_output_file_name_must_be_mp4(source_path):
    app = open_app(source_path)
    app.text_input(key="out_name").set_value("result.wmv").run()
    assert "must end in .mp4" in app.warning[0].value
    assert app.button(key="render").disabled


def saved(project: Path) -> dict:
    return json.loads(project.read_text(encoding="utf-8"))


def save_project_as(app: AppTest, project: Path, monkeypatch) -> None:
    monkeypatch.setattr(dialogs, "pick_project_to_save", lambda initial_dir="": str(project))
    app.button(key="save_project_as").click().run()
    assert not app.exception


def open_project(app: AppTest, project: Path, monkeypatch) -> None:
    monkeypatch.setattr(dialogs, "pick_project", lambda initial_dir="": str(project))
    app.button(key="open_project").click().run()
    assert not app.exception


def test_a_project_is_not_saved_until_it_is_given_a_file(source_path):
    app = open_app()
    assert app.button(key="save_project_as").disabled
    app = open_app(source_path)
    assert not app.button(key="save_project_as").disabled
    assert any("This Project is not saved" in caption.value for caption in app.caption)


def test_every_change_is_saved_once_the_project_has_a_file(source_path, tmp_path, monkeypatch):
    project = tmp_path / "drop.json"
    app = open_app(source_path)
    app.number_input(key="sync_point_1").set_value(1.5).run()
    save_project_as(app, project, monkeypatch)
    assert saved(project)["format"] == 2 and saved(project)["audio_source"] == 1
    assert saved(project)["sources"][0] | {"crop": None, "aspect_override": None} == {
        "path": source_path,
        "sync_point": 1.5,
        "rotation": 0.0,
        "crop": None,
        "width": None,
        "record_rate": None,
        "row": 1,
        "aspect_override": None,
    }
    assert any(f"Project file: {project}" in caption.value for caption in app.caption)

    app.number_input(key="crop_left_1").set_value(20)
    app.number_input(key="lead_in").set_value(1.0).run()
    assert saved(project)["sources"][0]["crop"]["left"] == 20
    assert saved(project)["output"]["lead_in"] == 1.0

    # A setting the Preview rejects is still the current setting, and is saved.
    app.number_input(key="crop_left_1").set_value(200).run()
    assert "removes the whole picture" in app.error[0].value
    assert saved(project)["sources"][0]["crop"]["left"] == 200


def test_opening_a_project_restores_every_setting(source_path, tmp_path, monkeypatch):
    project = tmp_path / "drop.json"
    first = open_app(source_path)
    first.number_input(key="sync_point_1").set_value(1.5)
    first.number_input(key="crop_left_1").set_value(20)
    first.number_input(key="source_width_1").set_value(70)
    first.number_input(key="lead_out").set_value(2.0)
    first.text_input(key="out_name").set_value("drop_final.mp4")
    first.toggle(key="text_on").set_value(True).run()
    first.text_area(key="text_value").set_value("Test 14")
    first.number_input(key="text_size").set_value(12).run()
    first.toggle(key="text_on").set_value(False).run()
    save_project_as(first, project, monkeypatch)

    app = open_app()
    open_project(app, project, monkeypatch)
    assert app.text_input(key="path_1").value == source_path
    assert app.number_input(key="sync_point_1").value == 1.5
    assert app.number_input(key="crop_left_1").value == 20
    assert app.number_input(key="source_width_1").value == 70
    assert app.number_input(key="lead_out").value == 2.0
    assert app.text_input(key="out_name").value == "drop_final.mp4"
    # The text Overlay is off, but its text and size came back with it.
    assert not app.toggle(key="text_on").value
    assert app.text_area(key="text_value").value == "Test 14"
    assert app.number_input(key="text_size").value == 12
    assert any("Output is 70 by 60" in caption.value for caption in app.caption)


def test_a_moved_source_keeps_its_settings_until_it_is_located(source_path, tmp_path, monkeypatch):
    moved_from = tmp_path / "old_place.mp4"
    shutil.copy(source_path, moved_from)
    project = tmp_path / "drop.json"
    first = open_app(str(moved_from))
    first.number_input(key="sync_point_1").set_value(1.5)
    first.number_input(key="crop_left_1").set_value(20).run()
    save_project_as(first, project, monkeypatch)
    st.cache_resource.clear()  # closes the Source so that it can be moved
    moved_to = moved_from.rename(tmp_path / "new_place.mp4")
    before = project.read_text(encoding="utf-8")

    app = open_app()
    open_project(app, project, monkeypatch)
    assert "No file found" in app.error[0].value
    assert "keeps this Source's settings" in app.info[0].value
    assert any("Locate Source 1" in error.value for error in app.error)
    assert project.read_text(encoding="utf-8") == before

    app.text_input(key="path_1").set_value(str(moved_to)).run()
    assert not app.exception and not app.error
    assert app.number_input(key="sync_point_1").value == 1.5
    assert app.number_input(key="crop_left_1").value == 20
    assert saved(project)["sources"][0]["path"] == str(moved_to)


def test_new_project_clears_the_screen_and_leaves_the_project_file_alone(
    source_path, tmp_path, monkeypatch
):
    project = tmp_path / "drop.json"
    app = open_app(source_path)
    app.number_input(key="sync_point_1").set_value(1.5).run()
    save_project_as(app, project, monkeypatch)
    before = project.read_text(encoding="utf-8")

    app.button(key="new_project").click().run()
    assert not app.exception
    assert "Add a Source file" in app.info[0].value
    assert "This Project is not saved" in captions(app)
    add_source(app, source_path)
    assert app.number_input(key="sync_point_2").value == 0
    assert project.read_text(encoding="utf-8") == before


def test_a_project_file_from_before_several_sources_still_opens(source_path, tmp_path, monkeypatch):
    project = tmp_path / "old.json"
    project.write_text(
        json.dumps(
            {
                "format": 1,
                "sources": [{"path": source_path, "sync_point": 1.5, "crop": {"left": 20}}],
                "output": {"lead_in": 1.0, "lead_out": 2.0, "rate": 10.0},
            }
        ),
        encoding="utf-8",
    )
    app = open_app()
    open_project(app, project, monkeypatch)
    assert app.number_input(key="sync_point_1").value == 1.5
    assert app.number_input(key="crop_left_1").value == 20
    assert app.number_input(key="out_rate").value == 10
    assert "Output is 140 by 120 pixels and runs for 3.000 s" in captions(app)
    assert "sound from Source 1" in captions(app)


# ------------------------------------------------------------ Several Sources


def test_sources_are_placed_side_by_side_and_matched_in_height(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path)
    # The 100 by 200 Source is scaled to the 120 high Row: 60 wide.
    assert "Output is 220 by 120 pixels" in captions(app)
    assert "It sets the Row height. Its Panel is 160 by 120 pixels." in captions(app)
    assert (
        "After rotation and crop this Source is 100 by 200 pixels. Scaled to the Row height, "
        "its Panel is 60 by 120 pixels (60% of that size)." in captions(app)
    )
    # Only the first Source can be resized; the rest follow the Row height.
    assert not app.number_input(key="source_width_1").disabled
    assert app.number_input(key="source_width_2").disabled

    app.number_input(key="source_width_1").set_value(80).run()
    assert "Output is 110 by 60 pixels" in captions(app)


def test_each_source_has_its_own_sync_point_and_gaps(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path)
    app.number_input(key="sync_point_1").set_value(2.0)
    app.number_input(key="sync_point_2").set_value(0.5)
    app.number_input(key="lead_in").set_value(1.0)
    app.number_input(key="lead_out").set_value(2.0).run()
    assert not app.exception
    assert timing_row(app, 1) == {
        "Source": "Source 1: source.mp4",
        "Footage from (s)": "1.000",
        "Footage to (s)": "4.000",
        "Front Gap (s)": "0.000",
        "Back Gap (s)": "0.000",
    }
    assert timing_row(app, 2) == {
        "Source": "Source 2: tall.mp4",
        "Footage from (s)": "0.000",
        "Footage to (s)": "2.000",
        "Front Gap (s)": "0.500",
        "Back Gap (s)": "0.500",
    }


def test_the_output_rate_defaults_to_the_highest_playback_rate(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path)
    assert "at 20 frames per second" in captions(app)
    app.number_input(key="out_rate").set_value(15.0).run()
    assert "at 15 frames per second" in captions(app)


def test_the_audio_source_is_the_first_source_with_sound_until_chosen(source_path, tall_source_path):
    app = open_app(tall_source_path)
    assert app.selectbox(key="audio_pick").options == ["No sound"]
    assert "with no sound" in captions(app)

    add_source(app, source_path)
    assert app.selectbox(key="audio_pick").options == ["No sound", "Source 2: source.mp4"]
    assert "with sound from Source 2" in captions(app)

    app.selectbox(key="audio_pick").set_value(0).run()
    assert "with no sound" in captions(app)


def test_a_problem_names_the_source_it_belongs_to(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path)
    app.number_input(key="crop_left_2").set_value(150).run()
    assert not app.exception
    assert "Source 2: The crop removes the whole picture" in app.error[0].value


def test_removing_a_source_closes_up_the_row(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path)
    app.number_input(key="sync_point_2").set_value(0.5).run()
    app.button(key="remove_1").click().run()
    assert not app.exception
    assert "Output is 100 by 200 pixels" in captions(app)
    assert timing_row(app)["Source"] == "Source 1: tall.mp4"
    assert app.number_input(key="sync_point_2").value == 0.5
    assert not app.number_input(key="source_width_2").disabled

    app.button(key="remove_2").click().run()
    assert "Add a Source file" in app.info[0].value


def test_a_project_with_several_sources_is_saved_and_reopened(
    source_path, tall_source_path, tmp_path, monkeypatch
):
    project = tmp_path / "pair.json"
    first = open_app(tall_source_path, source_path)
    first.number_input(key="sync_point_1").set_value(0.5)
    first.number_input(key="sync_point_2").set_value(2.0)
    first.number_input(key="crop_left_2").set_value(80).run()
    first.selectbox(key="audio_pick").set_value(0).run()
    save_project_as(first, project, monkeypatch)
    document = saved(project)
    assert [Path(source["path"]).name for source in document["sources"]] == ["tall.mp4", "source.mp4"]
    assert document["audio_source"] is None

    app = open_app()
    open_project(app, project, monkeypatch)
    assert app.number_input(key="sync_point_1").value == 0.5
    assert app.number_input(key="sync_point_2").value == 2.0
    assert app.number_input(key="crop_left_2").value == 80
    assert app.selectbox(key="audio_pick").value == 0
    # 100 by 200, then 80 by 120 scaled to 200 high: 133 wide.
    assert "Output is 232 by 200 pixels" in captions(app)


def test_one_moved_source_does_not_lose_the_settings_of_any(
    source_path, tall_source_path, tmp_path, monkeypatch
):
    moved_from = tmp_path / "old_place.mp4"
    shutil.copy(tall_source_path, moved_from)
    project = tmp_path / "pair.json"
    first = open_app(source_path, str(moved_from))
    first.number_input(key="sync_point_1").set_value(2.0)
    first.number_input(key="sync_point_2").set_value(0.5).run()
    save_project_as(first, project, monkeypatch)
    st.cache_resource.clear()  # closes the Source so that it can be moved
    moved_to = moved_from.rename(tmp_path / "new_place.mp4")

    app = open_app()
    open_project(app, project, monkeypatch)
    assert any("Locate Source 2" in error.value for error in app.error)
    assert app.number_input(key="sync_point_1").value == 2.0
    # A change made while Source 2 is missing is saved without losing its settings.
    app.number_input(key="lead_in").set_value(1.0).run()
    assert saved(project)["output"]["lead_in"] == 1.0
    assert saved(project)["sources"][1]["sync_point"] == 0.5

    app.text_input(key="path_2").set_value(str(moved_to)).run()
    assert not app.exception and not app.error
    assert app.number_input(key="sync_point_2").value == 0.5
    assert saved(project)["sources"][1]["path"] == str(moved_to)


def test_a_file_that_is_not_a_project_is_reported_and_changes_nothing(source_path, tmp_path, monkeypatch):
    not_project = tmp_path / "notes.json"
    not_project.write_text("not a project")
    app = open_app(source_path)
    app.number_input(key="sync_point_1").set_value(1.5).run()
    open_project(app, not_project, monkeypatch)
    assert "is not a Project file" in app.error[0].value
    assert app.number_input(key="sync_point_1").value == 1.5
    assert any("This Project is not saved" in caption.value for caption in app.caption)


# ------------------------------------------------------------- Frame stepping


def test_the_frame_buttons_refine_the_sync_point_by_whole_frames(source_path):
    app = open_app(source_path)
    app.number_input(key="sync_point_1").set_value(2.0).run()
    assert "The Sync Point is in frame 21 of 40" in captions(app)

    app.button(key="step_forward_1_1").click().run()
    assert not app.exception
    # Frame 22 of a 10 frames per second file begins at 2.1 s.
    assert app.number_input(key="sync_point_1").value == 2.101
    assert "The Sync Point is in frame 22 of 40, which the file shows from 2.100 to 2.200 s" in captions(app)

    app.button(key="step_forward_10_1").click().run()
    app.button(key="step_back_1_1").click().run()
    assert app.number_input(key="sync_point_1").value == 3.001

    # Retyping replaces the refined value.
    app.number_input(key="sync_point_1").set_value(1.0).run()
    assert "The Sync Point is in frame 11 of 40" in captions(app)


def test_stepping_stops_at_the_ends_of_the_file(source_path):
    app = open_app(source_path)
    app.button(key="step_back_10_1").click().run()
    assert "The Sync Point is in frame 1 of 40" in captions(app)
    app.number_input(key="sync_point_1").set_value(3.95).run()
    app.button(key="step_forward_10_1").click().run()
    assert not app.exception
    assert "The Sync Point is in frame 40 of 40" in captions(app)


def test_stepping_moves_the_preview_to_the_sync_event(source_path):
    app = open_app(source_path)
    app.number_input(key="sync_point_1").set_value(2.0)
    app.number_input(key="lead_in").set_value(1.0)
    app.number_input(key="lead_out").set_value(1.0).run()
    app.slider(key="preview_offset").set_value(0.5).run()
    app.button(key="step_forward_1_1").click().run()
    assert app.slider(key="preview_offset").value == 0


def test_one_source_can_be_shown_alone_in_the_preview(source_path, tall_source_path):
    alone = open_app(source_path)
    assert not [control for control in alone.button_group if control.key == "preview_show"]

    app = open_app(source_path, tall_source_path)
    show = next(control for control in app.button_group if control.key == "preview_show")
    assert show.value == "all"
    show.set_value(app.session_state["source_ids"][1]).run()
    assert not app.exception
    # The Output itself is unchanged; only what the Preview shows of it.
    assert "Output is 220 by 120 pixels" in captions(app)


# ---------------------------------------------------------------------- Speed


def test_a_real_time_source_is_shown_at_real_time_with_its_sound(source_path):
    app = open_app(source_path)
    assert "Source Speed 1: this file shows the real event in real time." in captions(app)
    assert "Output Speed 1: the 4.000 s Output shows 4.000 s of the real event." in captions(app)
    assert speed_row(app) == ("1", "every frame shown once")
    assert "with sound from Source 1. Output Speed 1." in captions(app)
    assert not app.warning


def test_a_slow_motion_source_sets_the_output_speed_and_loses_its_sound(source_path):
    app = open_app(source_path)
    # Recorded at 40 frames per second, played at 10: a quarter of real time.
    app.number_input(key="record_rate_1").set_value(40.0).run()
    assert not app.exception
    assert (
        "Source Speed 0.25 (Playback Rate 10 divided by Record Rate 40): "
        "1 s of this file shows 0.25 s of the real event." in captions(app)
    )
    assert "Output Speed 0.25: the 4.000 s Output shows 1.000 s of the real event." in captions(app)
    assert speed_row(app) == ("0.25", "every frame shown once")
    assert "with no sound" in captions(app)
    assert "because Source 1 is not real time (Source Speed 0.25)" in app.warning[0].value


def test_the_output_speed_can_be_real_time_or_custom(source_path):
    app = open_app(source_path)
    app.number_input(key="record_rate_1").set_value(40.0)
    app.number_input(key="sync_point_1").set_value(2.0)
    app.number_input(key="lead_in").set_value(0.25)
    app.number_input(key="lead_out").set_value(0.25).run()
    assert app.number_input(key="speed_custom").disabled

    app.selectbox(key="speed_choice").set_value(app.selectbox(key="speed_choice").options[1]).run()
    assert not app.exception
    assert "Output Speed 1: the 0.500 s Output shows 0.500 s of the real event." in captions(app)
    # Real time needs 4 file seconds for each second of Output: 1 s of file each side.
    assert timing_row(app)["Footage from (s)"] == "1.000"
    assert timing_row(app)["Footage to (s)"] == "3.000"
    assert speed_row(app) == ("0.25", "1 frame in 4 shown, 75% dropped")

    app.selectbox(key="speed_choice").set_value(app.selectbox(key="speed_choice").options[2]).run()
    app.number_input(key="speed_custom").set_value(0.125).run()
    assert not app.exception
    assert speed_row(app) == ("0.25", "each frame held for 2 Output frames")


def test_every_source_gets_a_frame_hint_at_the_slowest_source_speed(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path)
    # The 20 frames per second Source was recorded at 80: a quarter of real time.
    app.number_input(key="record_rate_2").set_value(80.0).run()
    assert not app.exception
    assert "Output Speed 0.25" in captions(app)
    # The Output Rate is 20. The real-time 10 frames per second Source is slowed to a quarter.
    assert speed_row(app, 1) == ("1", "each frame held for 8 Output frames")
    assert speed_row(app, 2) == ("0.25", "every frame shown once")
    assert (
        "Frame Hint at Output Speed 0.25 and Output Rate 20: each frame held for 8 Output frames."
        in captions(app)
    )
    assert "because the Output Speed is 0.25, not real time" in app.warning[0].value


def test_speed_settings_are_saved_and_reopened(source_path, tmp_path, monkeypatch):
    project = tmp_path / "speed.json"
    first = open_app(source_path)
    first.number_input(key="record_rate_1").set_value(40.0).run()
    first.selectbox(key="speed_choice").set_value(first.selectbox(key="speed_choice").options[2]).run()
    first.number_input(key="speed_custom").set_value(0.5).run()
    save_project_as(first, project, monkeypatch)
    assert saved(project)["sources"][0]["record_rate"] == 40.0
    assert saved(project)["output"]["speed"] == "Custom"
    assert saved(project)["output"]["custom_speed"] == 0.5

    app = open_app()
    open_project(app, project, monkeypatch)
    assert app.number_input(key="record_rate_1").value == 40.0
    assert app.number_input(key="speed_custom").value == 0.5
    assert "Output Speed 0.5" in captions(app)


def test_a_draft_is_written_beside_the_output_with_its_own_settings(
    source_path, tmp_path, monkeypatch
):
    app = open_app(source_path)
    app.text_input(key="out_folder").set_value(str(tmp_path))
    app.text_input(key="out_name").set_value("result.mp4")
    app.number_input(key="sync_point_1").set_value(2.0).run()
    assert app.number_input(key="draft_width").value == 640
    assert not app.checkbox(key="draft_sound").value
    app.number_input(key="draft_lead_in").set_value(1.0)
    app.number_input(key="draft_lead_out").set_value(0.5)
    app.number_input(key="draft_width").set_value(80).run()
    assert (
        "The Draft will be 80 by 60 pixels (50% of the Output's size) at low picture quality, "
        "without sound. It runs for 1.500 s at 10 frames per second and Output Speed 1, "
        "with the Sync Event 1.000 s in." in captions(app)
    )

    app.button(key="make_draft").click().run()

    assert not app.exception
    written = tmp_path / "result_draft.mp4"
    assert str(written) in app.success[0].value
    assert not (tmp_path / "result.mp4").exists()
    with VideoFileClip(str(written)) as draft:
        assert draft.size == [80, 60]
        assert draft.duration == pytest.approx(1.5, abs=0.15)
        assert draft.audio is None
        assert file_time_shown(draft.get_frame(1.0)) == pytest.approx(2.0, abs=0.3)
    assert not app.warning

    # The Output's own Lead-out is not part of the Draft; the Sync Point is.
    app.number_input(key="lead_out").set_value(1.0).run()
    assert not app.warning
    app.number_input(key="sync_point_1").set_value(1.0).run()
    assert "Settings have changed since this Draft was made" in app.warning[0].value

    opened = []
    monkeypatch.setattr(dialogs, "open_file", opened.append)
    app.button(key="open_draft").click().run()
    assert opened == [str(written)]


def test_a_draft_needs_an_output_folder_and_never_replaces_a_source(source_path, tmp_path):
    source = tmp_path / "clip_draft.mp4"
    shutil.copy(source_path, source)
    app = open_app(str(source))
    app.text_input(key="out_folder").set_value(str(tmp_path))
    app.text_input(key="out_name").set_value("clip.mp4").run()
    assert app.button(key="make_draft").disabled
    assert any("would replace the Source file clip_draft.mp4" in warning.value for warning in app.warning)

    app.text_input(key="out_name").set_value("other.mp4").run()
    assert not app.button(key="make_draft").disabled

    app.text_input(key="out_folder").set_value("").run()
    assert app.button(key="make_draft").disabled
    assert any("The Draft is written beside the Output" in warning.value for warning in app.warning)


def test_draft_sound_follows_the_output_and_says_why_when_there_is_none(source_path):
    app = open_app(source_path)
    app.checkbox(key="draft_sound").check().run()
    assert "with sound from Source 1" in captions(app)
    app.number_input(key="record_rate_1").set_value(40.0).run()
    assert "without sound, because Source 1 is not real time" in captions(app)


def test_draft_settings_are_saved_and_reopened(source_path, tmp_path, monkeypatch):
    project = tmp_path / "project.json"
    app = open_app(source_path)
    save_project_as(app, project, monkeypatch)
    app.number_input(key="draft_lead_in").set_value(0.5)
    app.number_input(key="draft_width").set_value(320)
    app.checkbox(key="draft_sound").check().run()
    assert saved(project)["draft"] == {"lead_in": 0.5, "lead_out": 2.0, "width": 320, "sound": True}

    again = AppTest.from_file(APP, default_timeout=60)
    again.run()
    open_project(again, project, monkeypatch)
    assert not again.exception
    assert again.number_input(key="draft_lead_in").value == 0.5
    assert again.number_input(key="draft_width").value == 320
    assert again.checkbox(key="draft_sound").value


def test_a_setting_that_can_be_left_empty_can_be_emptied_again(source_path):
    app = open_app(source_path)
    app.number_input(key="record_rate_1").set_value(40.0)
    app.number_input(key="source_width_1").set_value(80)
    app.number_input(key="out_width").set_value(80)
    app.number_input(key="out_rate").set_value(20.0).run()
    for key in ("record_rate_1", "source_width_1", "out_width", "out_rate"):
        # With no default to fall back on, emptying the field leaves it empty.
        assert not app.number_input(key=key).proto.HasField("default"), key

    app.number_input(key="record_rate_1").set_value(None).run()
    assert not app.exception
    assert "Source Speed 1: this file shows the real event in real time." in captions(app)


def test_a_source_in_a_row_of_its_own_sits_under_row_1_matched_in_width(
    source_path, tall_source_path, tmp_path
):
    app = open_app(source_path, tall_source_path)
    assert app.number_input(key="row_1").disabled
    app.number_input(key="row_2").set_value(2).run()

    assert not app.exception
    text = captions(app)
    assert "It sets the height of Row 1 and the width of Column 1. Its Panel is 160 by 120 pixels." in text
    assert (
        "Scaled to the width of Column 1, its Panel is 160 by 320 pixels (160% of that size). "
        "It is in Row 2, Column 1, and sets the height of Row 2." in text
    )
    assert "Output is 160 by 440 pixels, in 2 Rows and 1 Column and runs" in text

    app.text_input(key="out_folder").set_value(str(tmp_path))
    app.text_input(key="out_name").set_value("column.mp4").run()
    app.button(key="render").click().run()
    assert not app.exception
    with VideoFileClip(str(tmp_path / "column.mp4")) as output:
        assert output.size == [160, 440]


def test_a_source_with_bars_gets_a_crop_hint_that_removes_them(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path, source_path, source_path)
    app.number_input(key="row_3").set_value(2)
    app.number_input(key="row_4").set_value(2).run()

    assert not app.exception
    text = captions(app)
    assert "It is in Row 1, Column 2, and sets the width of Column 2." in text
    assert (
        "Its Panel, in Row 2, Column 2, is already 60 by 120 pixels. Scaled to fit, it is "
        "60 by 45 pixels (38% of that size), with Bars of 37.5 pixels above and below. "
        "Crop Hint: crop 100 pixels of width, to 60 wide, and it fills the Panel." in text
    )
    assert "Output is 220 by 240 pixels, in 2 Rows and 2 Columns" in text

    app.number_input(key="crop_left_4").set_value(50)
    app.number_input(key="crop_right_4").set_value(50).run()
    assert "Scaled to fit (100% of that size), it fills the Panel with no Bars." in captions(app)


def test_rows_are_saved_and_reopened(source_path, tall_source_path, tmp_path, monkeypatch):
    project = tmp_path / "grid.json"
    app = open_app(source_path, tall_source_path)
    save_project_as(app, project, monkeypatch)
    app.number_input(key="row_2").set_value(2).run()
    assert [source["row"] for source in saved(project)["sources"]] == [1, 2]

    again = AppTest.from_file(APP, default_timeout=60)
    again.run()
    open_project(again, project, monkeypatch)
    assert not again.exception
    assert again.number_input(key="row_2").value == 2
    assert "Output is 160 by 440 pixels" in captions(again)


def test_removing_the_first_source_puts_the_next_one_first_in_row_1(source_path, tall_source_path):
    app = open_app(source_path, tall_source_path)
    app.number_input(key="row_2").set_value(2).run()
    app.button(key="remove_1").click().run()
    assert not app.exception
    assert app.number_input(key="row_2").value == 1
    assert "Output is 100 by 200 pixels and runs" in captions(app)
