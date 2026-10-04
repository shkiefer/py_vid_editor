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


def open_app(source_path: str | None = None) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    if source_path is not None:
        app.session_state["source_path"] = source_path
    app.run()
    assert not app.exception
    return app


def timing_row(app: AppTest) -> dict:
    return app.table[0].value.iloc[0].to_dict()


def test_without_a_source_the_app_asks_for_one():
    app = open_app()
    assert "Choose a Source file" in app.info[0].value
    assert not app.table


def test_a_missing_file_is_reported_without_crashing(tmp_path):
    app = open_app(str(tmp_path / "missing.mp4"))
    assert "No file found" in app.error[0].value


def test_a_new_source_defaults_to_the_whole_file(source_path):
    app = open_app(source_path)
    assert app.number_input(key="sync_point").value == 0
    assert app.number_input(key="lead_in").value == 0
    assert app.number_input(key="lead_out").value == pytest.approx(4.0, abs=0.15)
    assert app.number_input(key="out_rate").value == pytest.approx(10)
    assert app.text_input(key="out_name").value == "source_edited.mp4"
    row = timing_row(app)
    assert row["Front Gap (s)"] == "0.000" and row["Back Gap (s)"] == "0.000"
    assert any("160 by 120" in caption.value for caption in app.caption)


def test_timing_feedback_shows_footage_times_and_gaps(source_path):
    app = open_app(source_path)
    app.number_input(key="sync_point").set_value(1.0)
    app.number_input(key="lead_in").set_value(3.0)
    app.number_input(key="lead_out").set_value(1.0).run()
    assert not app.exception
    assert timing_row(app) == {
        "Source": "source.mp4",
        "Footage from (s)": "0.000",
        "Footage to (s)": "2.000",
        "Front Gap (s)": "2.000",
        "Back Gap (s)": "0.000",
    }


def test_quarter_turn_buttons_rotate_and_change_the_output_size(source_path):
    app = open_app(source_path)
    app.button(key="turn_left").click().run()
    assert not app.exception
    assert app.number_input(key="rotation").value == 90
    assert any("120 by 160" in caption.value for caption in app.caption)
    app.button(key="turn_right").click().run()
    app.button(key="turn_right").click().run()
    assert app.number_input(key="rotation").value == 270


def test_an_impossible_crop_is_reported_without_crashing(source_path):
    app = open_app(source_path)
    app.number_input(key="crop_left").set_value(200).run()
    assert not app.exception
    assert "removes the whole picture" in app.error[0].value


def test_resizing_the_source_reports_both_sizes_and_sets_the_output_size(source_path):
    app = open_app(source_path)
    assert any("this Source is 160 by 120 pixels." in caption.value for caption in app.caption)
    app.number_input(key="crop_left").set_value(80)
    app.number_input(key="source_width").set_value(40).run()
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
    app.number_input(key="sync_point").set_value(1.0)
    app.number_input(key="lead_in").set_value(2.0)
    app.number_input(key="lead_out").set_value(1.0)
    app.number_input(key="crop_left").set_value(80)
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
    app.number_input(key="sync_point").set_value(1.5).run()
    save_project_as(app, project, monkeypatch)
    assert saved(project)["sources"][0] | {"crop": None, "aspect_override": None} == {
        "path": source_path,
        "sync_point": 1.5,
        "rotation": 0.0,
        "crop": None,
        "width": None,
        "aspect_override": None,
    }
    assert any(f"Project file: {project}" in caption.value for caption in app.caption)

    app.number_input(key="crop_left").set_value(20)
    app.number_input(key="lead_in").set_value(1.0).run()
    assert saved(project)["sources"][0]["crop"]["left"] == 20
    assert saved(project)["output"]["lead_in"] == 1.0

    # A setting the Preview rejects is still the current setting, and is saved.
    app.number_input(key="crop_left").set_value(200).run()
    assert "removes the whole picture" in app.error[0].value
    assert saved(project)["sources"][0]["crop"]["left"] == 200


def test_opening_a_project_restores_every_setting(source_path, tmp_path, monkeypatch):
    project = tmp_path / "drop.json"
    first = open_app(source_path)
    first.number_input(key="sync_point").set_value(1.5)
    first.number_input(key="crop_left").set_value(20)
    first.number_input(key="source_width").set_value(70)
    first.number_input(key="lead_out").set_value(2.0)
    first.text_input(key="out_name").set_value("drop_final.mp4")
    first.toggle(key="text_on").set_value(True).run()
    first.text_area(key="text_value").set_value("Test 14")
    first.number_input(key="text_size").set_value(12).run()
    first.toggle(key="text_on").set_value(False).run()
    save_project_as(first, project, monkeypatch)

    app = open_app()
    open_project(app, project, monkeypatch)
    assert app.text_input(key="source_path").value == source_path
    assert app.number_input(key="sync_point").value == 1.5
    assert app.number_input(key="crop_left").value == 20
    assert app.number_input(key="source_width").value == 70
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
    first.number_input(key="sync_point").set_value(1.5)
    first.number_input(key="crop_left").set_value(20).run()
    save_project_as(first, project, monkeypatch)
    st.cache_resource.clear()  # closes the Source so that it can be moved
    moved_to = moved_from.rename(tmp_path / "new_place.mp4")
    before = project.read_text(encoding="utf-8")

    app = open_app()
    open_project(app, project, monkeypatch)
    assert "No file found" in app.error[0].value
    assert "keeps this Source's settings" in app.info[0].value
    assert project.read_text(encoding="utf-8") == before

    app.text_input(key="source_path").set_value(str(moved_to)).run()
    assert not app.exception and not app.error
    assert app.number_input(key="sync_point").value == 1.5
    assert app.number_input(key="crop_left").value == 20
    assert saved(project)["sources"][0]["path"] == str(moved_to)


def test_choosing_another_source_leaves_the_project_file_alone(source_path, tmp_path, monkeypatch):
    other_source = tmp_path / "other.mp4"
    shutil.copy(source_path, other_source)
    project = tmp_path / "drop.json"
    app = open_app(source_path)
    app.number_input(key="sync_point").set_value(1.5).run()
    save_project_as(app, project, monkeypatch)
    before = project.read_text(encoding="utf-8")

    app.text_input(key="source_path").set_value(str(other_source)).run()
    assert not app.exception
    assert app.number_input(key="sync_point").value == 0
    assert any("was left as it was" in caption.value for caption in app.caption)
    app.number_input(key="sync_point").set_value(3.0).run()
    assert project.read_text(encoding="utf-8") == before


def test_a_file_that_is_not_a_project_is_reported_and_changes_nothing(source_path, tmp_path, monkeypatch):
    not_project = tmp_path / "notes.json"
    not_project.write_text("not a project")
    app = open_app(source_path)
    app.number_input(key="sync_point").set_value(1.5).run()
    open_project(app, not_project, monkeypatch)
    assert "is not a Project file" in app.error[0].value
    assert app.number_input(key="sync_point").value == 1.5
    assert any("This Project is not saved" in caption.value for caption in app.caption)
