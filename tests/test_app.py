"""The Streamlit screen, driven headlessly."""

from pathlib import Path

import pytest
from conftest import file_time_shown, is_black
from moviepy import VideoFileClip
from streamlit.testing.v1 import AppTest

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
    app.button[1].click().run()  # Turn left
    assert not app.exception
    assert app.number_input(key="rotation").value == 90
    assert any("120 by 160" in caption.value for caption in app.caption)
    app.button[2].click().run()  # Turn right
    app.button[2].click().run()
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
