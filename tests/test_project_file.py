"""The Project file: settings to readable text and back."""

import json

import pytest

from vid_editor import project_file
from vid_editor.model import Corner, EditError, JoinKind, Quality, SpeedChoice, Workflow
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
    "panel": 0,
    "aspect_on": False,
    "aspect_width": 1920,
    "aspect_height": 1080,
    "start_point": 0.5,
    "end_point": None,
    "play_speed": 1.0,
    "join_kind": JoinKind.CROSSFADE,
    "join_length": 0.5,
}
SHARED = {
    "workflow": Workflow.SEQUENCE,
    "seq_width": 1920,
    "seq_height": 1080,
    "seq_fade_in": 1.0,
    "seq_fade_out": 0.0,
    "lead_in": 1.0,
    "lead_out": 3.0,
    "out_width": 960,
    "out_rate": None,
    "speed_choice": SpeedChoice.CUSTOM,
    "speed_custom": 0.5,
    "quality": Quality.HIGH,
    "source_volume": 80.0,
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
    "draft_lead_in": 1.5,
    "draft_lead_out": 0.5,
    "draft_width": 480,
    "draft_sound": True,
    "draft_at": 1,
}
PANELS = [
    {"row": 1, "width": 1920, "height": 1080},
    {"row": 1, "width": 608, "height": 1080},
    {"row": 2, "width": 2528, "height": 360},
]
TRACK = {
    "path": r"C:\music\song.mp3",
    "track_start": 2.0,
    "track_file_start": 30.0,
    "track_volume": 30.0,
    "track_fade_out": 1.5,
}
SETTINGS = ProjectSettings(
    sources=[SOURCE, SOURCE | {"path": r"C:\videos\camera_b.mp4", "sync_point": 0.75, "panel": 2}],
    shared=SHARED,
    panels=PANELS,
    audio_panel=1,
    tracks=[TRACK, TRACK | {"path": r"C:\music\voice.wav", "track_volume": 150.0}],
)


def test_the_settings_fixture_covers_every_saved_setting():
    assert set(SOURCE) == {"path", "panel", *project_file.SOURCE_KEYS}
    assert set(SHARED) == set(project_file.SHARED_KEYS)
    assert set(TRACK) == {"path", *project_file.TRACK_KEYS}


def test_settings_survive_being_saved_and_opened(tmp_path):
    path = tmp_path / "nested" / "drop.json"
    project_file.write(path, project_file.dumps(SETTINGS))
    assert project_file.load(path) == SETTINGS
    assert [file.name for file in path.parent.iterdir()] == ["drop.json"]


def test_the_file_is_readable_text_grouped_by_what_each_setting_belongs_to():
    document = json.loads(project_file.dumps(SETTINGS))
    assert document["format"] == 5
    assert document["audio_tracks"][0] == {
        "path": r"C:\music\song.mp3",
        "start": 2.0,
        "file_start": 30.0,
        "volume": 30.0,
        "fade_out": 1.5,
    }
    assert document["output"]["source_volume"] == 80.0
    assert document["workflow"] == "Sequence"
    assert document["sequence"] == {"width": 1920, "height": 1080, "fade_in": 1.0, "fade_out": 0.0}
    assert document["sources"][0]["join_after"] == {"kind": "Crossfade", "length": 0.5}
    assert document["sources"][0]["start_point"] == 0.5
    assert document["sources"][0]["end_point"] is None
    assert [source["sync_point"] for source in document["sources"]] == [2.5, 0.75]
    assert document["sources"][0]["crop"] == {"top": 10, "bottom": 0, "left": 20, "right": 0}
    assert document["panels"][2] == {"row": 2, "width": 2528, "height": 360}
    assert [source["panel"] for source in document["sources"]] == [1, 3]
    # Panels are counted from 1, as they are on the screen.
    assert document["audio_panel"] == 2
    assert document["output"]["quality"] == "High"
    assert document["output"]["speed"] == "Custom" and document["output"]["custom_speed"] == 0.5
    assert document["sources"][0]["record_rate"] == 240.0
    assert document["text_overlay"]["corner"] == "Bottom left"
    assert document["draft"] == {
        "lead_in": 1.5,
        "lead_out": 0.5,
        "width": 480,
        "sound": True,
        "sequence_join": 1,
    }
    # An Overlay that is switched off keeps its settings.
    assert document["text_overlay"]["on"] is False
    assert "Proprietary – Do Not Distribute" in project_file.dumps(SETTINGS)


def test_no_audio_panel_survives_being_saved_and_opened():
    silent = ProjectSettings(sources=[SOURCE], shared=SHARED, panels=PANELS, audio_panel=None)
    assert project_file.loads(project_file.dumps(silent)).audio_panel is None


def test_a_file_from_before_a_setting_existed_still_opens():
    document = json.loads(project_file.dumps(SETTINGS))
    document.pop("image_overlay")
    document["sources"][0].pop("width")
    document.pop("audio_panel")
    document.pop("audio_tracks")
    settings = project_file.loads(json.dumps(document))
    assert settings.tracks == []
    assert "image_path" not in settings.shared and "source_width" not in settings.sources[0]
    assert settings.sources[0]["sync_point"] == 2.5
    assert settings.audio_panel == 0


def test_a_format_3_file_opens_with_no_workflow_or_sequence_settings():
    document = json.loads(project_file.dumps(SETTINGS))
    document["format"] = 3
    for key in ("workflow", "sequence"):
        document.pop(key)
    for source in document["sources"]:
        for key in ("start_point", "end_point", "play_speed", "join_after"):
            source.pop(key)
    settings = project_file.loads(json.dumps(document))
    assert not {"workflow", "seq_width", "seq_height"} & set(settings.shared)
    assert "start_point" not in settings.sources[0]
    assert settings.panels == PANELS


def test_an_unknown_workflow_is_refused():
    document = json.loads(project_file.dumps(SETTINGS)) | {"workflow": "Montage"}
    with pytest.raises(EditError, match="value for workflow"):
        project_file.loads(json.dumps(document))


def test_a_setting_that_is_not_given_is_left_out_of_the_file():
    partial = ProjectSettings(sources=[{"path": "a.mp4"}], shared={"lead_in": 1.0})
    document = json.loads(project_file.dumps(partial))
    assert document["sources"] == [{"path": "a.mp4"}]
    assert document["output"] == {"lead_in": 1.0}


def test_a_file_from_before_typed_panels_gives_each_source_its_row_and_no_panels():
    old = {
        "format": 2,
        "sources": [{"path": "a.mp4"}, {"path": "b.mp4", "row": 2}],
        "audio_source": 2,
    }
    settings = project_file.loads(json.dumps(old))
    assert settings.panels is None
    assert [source["row"] for source in settings.sources] == [1, 2]
    assert all("panel" not in source for source in settings.sources)
    # Each Source gets a Panel of its own in the same order, so the number carries over.
    assert settings.audio_panel == 1


ONE_PANEL = '"panels": [{"row": 1, "width": 100, "height": 50}]'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"format": 3, "sources": [{"path": "a.mp4", "panel": 1}]}', "at least one Panel"),
        (
            '{"format": 3, "panels": [{"row": 1, "width": 100}], "sources": [{"path": "a.mp4", "panel": 1}]}',
            "does not give Panel 1 a height",
        ),
        (
            '{"format": 3, "panels": [{"row": 1, "width": 1, "height": 50}], "sources": [{"path": "a.mp4", "panel": 1}]}',
            "panel 1 width",
        ),
        ('{"format": 3, %s, "sources": [{"path": "a.mp4"}]}' % ONE_PANEL, "which Panel Source 1 is in"),
        ('{"format": 3, %s, "sources": [{"path": "a.mp4", "panel": 2}]}' % ONE_PANEL, "source 1 panel"),
        (
            '{"format": 3, %s, "sources": [{"path": "a.mp4", "panel": 1}], "audio_panel": 2}' % ONE_PANEL,
            "audio panel",
        ),
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


def test_an_audio_track_must_say_where_it_is_and_have_a_usable_volume():
    document = json.loads(project_file.dumps(SETTINGS))
    document["audio_tracks"][1].pop("path")
    with pytest.raises(EditError, match="where Audio Track 2 is"):
        project_file.loads(json.dumps(document))
    document = json.loads(project_file.dumps(SETTINGS))
    document["audio_tracks"][0]["volume"] = 300
    with pytest.raises(EditError, match="audio track 1 volume"):
        project_file.loads(json.dumps(document))
