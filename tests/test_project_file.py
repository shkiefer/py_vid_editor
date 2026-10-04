"""The Project file: settings to readable text and back."""

import json

import pytest

from vid_editor import project_file
from vid_editor.model import Corner, EditError, Quality

SETTINGS = {
    "source_path": r"C:\videos\camera_a.mp4",
    "sync_point": 2.5,
    "rotation": 90.0,
    "crop_top": 10,
    "crop_bottom": 0,
    "crop_left": 20,
    "crop_right": 0,
    "source_width": None,
    "aspect_on": False,
    "aspect_width": 1920,
    "aspect_height": 1080,
    "lead_in": 1.0,
    "lead_out": 3.0,
    "out_width": 960,
    "out_rate": 29.97,
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


def test_the_settings_fixture_covers_every_saved_setting():
    assert set(SETTINGS) == set(project_file.KEYS)


def test_settings_survive_being_saved_and_opened(tmp_path):
    path = tmp_path / "nested" / "drop.json"
    project_file.write(path, project_file.dumps(SETTINGS))
    assert project_file.load(path) == SETTINGS
    assert [file.name for file in path.parent.iterdir()] == ["drop.json"]


def test_the_file_is_readable_text_grouped_by_what_each_setting_belongs_to():
    document = json.loads(project_file.dumps(SETTINGS))
    assert document["format"] == 1
    assert document["sources"][0]["sync_point"] == 2.5
    assert document["sources"][0]["crop"] == {"top": 10, "bottom": 0, "left": 20, "right": 0}
    assert document["output"]["quality"] == "High"
    assert document["text_overlay"]["corner"] == "Bottom left"
    # An Overlay that is switched off keeps its settings.
    assert document["text_overlay"]["on"] is False
    assert "Proprietary – Do Not Distribute" in project_file.dumps(SETTINGS)


def test_a_file_from_before_a_setting_existed_still_opens():
    document = json.loads(project_file.dumps(SETTINGS))
    del document["image_overlay"]
    del document["sources"][0]["width"]
    settings = project_file.loads(json.dumps(document))
    assert "image_path" not in settings and "source_width" not in settings
    assert settings["sync_point"] == 2.5


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "is not a Project file"),
        ("[1, 2]", "is not a Project file"),
        ('{"sources": []}', "is not a Project file"),
        ('{"format": 99, "sources": [{"path": "a.mp4"}]}', "different version"),
        ('{"format": 1, "sources": []}', "exactly one Source"),
        ('{"format": 1, "sources": [{}]}', "does not say where its Source is"),
        ('{"format": 1, "sources": [{"path": "a.mp4", "crop": {"top": -5}}]}', "source.crop.top"),
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
