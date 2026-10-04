"""The Project file: settings to readable text and back."""

import json

import pytest

from vid_editor import project_file
from vid_editor.model import Corner, EditError, Quality, SpeedChoice
from vid_editor.project_file import ProjectSettings

SOURCE = {
    "path": r"C:\videos\camera_a.mp4",
    "sync_point": 2.5,
    "rotation": 90.0,
    "crop_top": 10,
    "crop_bottom": 0,
    "crop_left": 20,
    "crop_right": 0,
    "source_width": None,
    "record_rate": 240.0,
    "aspect_on": False,
    "aspect_width": 1920,
    "aspect_height": 1080,
}
SHARED = {
    "lead_in": 1.0,
    "lead_out": 3.0,
    "out_width": 960,
    "out_rate": None,
    "speed_choice": SpeedChoice.CUSTOM,
    "speed_custom": 0.5,
    "quality": Quality.HIGH,
    "out_folder": r"C:\videos\out",
    "out_name": "camera_a_edited.mp4",
    "text_on": False,
    "text_value": "Proprietary – Do Not Distribute\nTest 14",
    "text_size": 30,
    "text_corner": Corner.BOTTOM_LEFT,
    "image_on": True,
    "image_path": r"C:\logos\logo.png",
    "image_corner": Corner.TOP_RIGHT,
    "image_width": 25.0,
    "image_opacity": 0.5,
}
SETTINGS = ProjectSettings(
    sources=[SOURCE, SOURCE | {"path": r"C:\videos\camera_b.mp4", "sync_point": 0.75}],
    shared=SHARED,
    audio_source=1,
)


def test_the_settings_fixture_covers_every_saved_setting():
    assert set(SOURCE) == {"path", *project_file.SOURCE_KEYS}
    assert set(SHARED) == set(project_file.SHARED_KEYS)


def test_settings_survive_being_saved_and_opened(tmp_path):
    path = tmp_path / "nested" / "drop.json"
    project_file.write(path, project_file.dumps(SETTINGS))
    assert project_file.load(path) == SETTINGS
    assert [file.name for file in path.parent.iterdir()] == ["drop.json"]


def test_the_file_is_readable_text_grouped_by_what_each_setting_belongs_to():
    document = json.loads(project_file.dumps(SETTINGS))
    assert document["format"] == 2
    assert [source["sync_point"] for source in document["sources"]] == [2.5, 0.75]
    assert document["sources"][0]["crop"] == {"top": 10, "bottom": 0, "left": 20, "right": 0}
    # The Audio Source is counted from 1, as Sources are on the screen.
    assert document["audio_source"] == 2
    assert document["output"]["quality"] == "High"
    assert document["output"]["speed"] == "Custom" and document["output"]["custom_speed"] == 0.5
    assert document["sources"][0]["record_rate"] == 240.0
    assert document["text_overlay"]["corner"] == "Bottom left"
    # An Overlay that is switched off keeps its settings.
    assert document["text_overlay"]["on"] is False
    assert "Proprietary – Do Not Distribute" in project_file.dumps(SETTINGS)


def test_no_audio_source_survives_being_saved_and_opened():
    silent = ProjectSettings(sources=[SOURCE], shared=SHARED, audio_source=None)
    assert project_file.loads(project_file.dumps(silent)).audio_source is None


def test_a_file_from_before_a_setting_existed_still_opens():
    document = json.loads(project_file.dumps(SETTINGS))
    document.pop("image_overlay")
    document["sources"][0].pop("width")
    document.pop("audio_source")
    settings = project_file.loads(json.dumps(document))
    assert "image_path" not in settings.shared and "source_width" not in settings.sources[0]
    assert settings.sources[0]["sync_point"] == 2.5
    assert settings.audio_source == 0


def test_a_setting_that_is_not_given_is_left_out_of_the_file():
    partial = ProjectSettings(sources=[{"path": "a.mp4"}], shared={"lead_in": 1.0})
    document = json.loads(project_file.dumps(partial))
    assert document["sources"] == [{"path": "a.mp4"}]
    assert document["output"] == {"lead_in": 1.0}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "is not a Project file"),
        ("[1, 2]", "is not a Project file"),
        ('{"sources": []}', "is not a Project file"),
        ('{"format": 99, "sources": [{"path": "a.mp4"}]}', "different version"),
        ('{"format": 1, "sources": []}', "at least one Source"),
        ('{"format": 2, "sources": [{"path": "a.mp4"}, {}]}', "does not say where Source 2 is"),
        ('{"format": 1, "sources": [{"path": "a.mp4", "crop": {"top": -5}}]}', "source 1 crop.top"),
        ('{"format": 2, "sources": [{"path": "a.mp4"}], "audio_source": 2}', "audio source"),
        ('{"format": 1, "sources": [{"path": "a.mp4", "rotation": "left"}]}', "'left'"),
        (
            '{"format": 1, "sources": [{"path": "a.mp4"}], "output": {"quality": "Best"}}',
            "output.quality",
        ),
    ],
)
def test_a_file_that_cannot_be_used_is_an_edit_error(text, message):
    with pytest.raises(EditError, match=message):
        project_file.loads(text)


def test_a_missing_project_file_is_an_edit_error(tmp_path):
    with pytest.raises(EditError, match="Could not read"):
        project_file.load(tmp_path / "missing.json")
