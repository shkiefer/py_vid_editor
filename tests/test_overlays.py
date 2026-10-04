"""Overlays drawn as pictures and stamped onto frames."""

import numpy as np
import pytest
from PIL import Image

from vid_editor.model import Corner, EditError, ImageOverlay, OutputSettings, TextOverlay
from vid_editor.overlays import image_patch, overlay_patches, stamper, text_patch


@pytest.fixture
def logo_path(tmp_path) -> str:
    """A 40 by 20 solid red image with no transparency."""
    path = tmp_path / "logo.png"
    Image.new("RGB", (40, 20), (255, 0, 0)).save(path)
    return str(path)


def test_text_is_white_on_a_half_transparent_black_box():
    picture = text_patch(TextOverlay("Sync", size=40))
    assert picture.shape[2] == 4
    corner_pixel = picture[0, 0]
    assert tuple(corner_pixel[:3]) == (0, 0, 0) and corner_pixel[3] == 128
    solid = picture[picture[..., 3] == 255]
    assert len(solid) and solid[:, :3].min() >= 250


def test_text_box_grows_with_text_size_and_with_each_line():
    small = text_patch(TextOverlay("Sync", size=20))
    large = text_patch(TextOverlay("Sync", size=40))
    two_lines = text_patch(TextOverlay("Sync\nEvent", size=20))
    assert large.shape[0] > small.shape[0] and large.shape[1] > small.shape[1]
    assert two_lines.shape[0] > 1.5 * small.shape[0]


def test_text_with_nothing_to_draw_is_an_edit_error():
    with pytest.raises(EditError, match="no text"):
        text_patch(TextOverlay("  \n"))
    with pytest.raises(EditError, match="at least 4"):
        text_patch(TextOverlay("Sync", size=2))


def test_image_box_width_is_a_percentage_of_the_output_width(logo_path):
    picture = image_patch(ImageOverlay(logo_path, width_percent=25), output_width=400)
    height, width = picture.shape[:2]
    assert width == 100
    # 4 pixels of padding each side leave a 92 by 46 image.
    assert height == 46 + 8
    assert tuple(picture[height // 2, width // 2]) == (255, 0, 0, 255)


def test_image_background_opacity_sets_the_box_behind_the_image(logo_path):
    clear = image_patch(ImageOverlay(logo_path, background_opacity=0), output_width=400)
    solid = image_patch(ImageOverlay(logo_path, background_opacity=1), output_width=400)
    assert clear[0, 0, 3] == 0
    assert tuple(solid[0, 0]) == (0, 0, 0, 255)


def test_a_missing_or_unreadable_image_is_an_edit_error(tmp_path, logo_path):
    with pytest.raises(EditError, match="No image found"):
        image_patch(ImageOverlay(str(tmp_path / "missing.png")), output_width=400)
    not_image = tmp_path / "notes.png"
    not_image.write_text("not an image")
    with pytest.raises(EditError, match="Could not read"):
        image_patch(ImageOverlay(str(not_image)), output_width=400)
    with pytest.raises(EditError, match="at most 100 percent"):
        image_patch(ImageOverlay(logo_path, width_percent=0), output_width=400)


@pytest.mark.parametrize(
    ("corner", "rows", "columns"),
    [
        (Corner.TOP_LEFT, slice(0, 10), slice(0, 20)),
        (Corner.TOP_RIGHT, slice(0, 10), slice(80, 100)),
        (Corner.BOTTOM_LEFT, slice(50, 60), slice(0, 20)),
        (Corner.BOTTOM_RIGHT, slice(50, 60), slice(80, 100)),
    ],
)
def test_an_overlay_is_stamped_flush_in_its_corner(corner, rows, columns):
    solid_white = np.full((10, 20, 4), 255, dtype=np.uint8)
    frame = np.full((60, 100, 3), 100, dtype=np.uint8)
    stamped = stamper([(solid_white, corner)], (100, 60))(frame)
    assert stamped[rows, columns].min() == 255
    assert int((stamped == 255).all(axis=2).sum()) == 10 * 20
    assert frame.max() == 100, "the frame passed in was changed"


def test_a_half_transparent_overlay_darkens_what_is_under_it():
    half_black = np.zeros((10, 20, 4), dtype=np.uint8)
    half_black[..., 3] = 128
    frame = np.full((60, 100, 3), 200, dtype=np.uint8)
    stamped = stamper([(half_black, Corner.TOP_LEFT)], (100, 60))(frame)
    assert stamped[5, 5, 0] == pytest.approx(100, abs=1)
    assert stamped[30, 50, 0] == 200


def test_an_overlay_larger_than_the_frame_keeps_the_part_nearest_its_corner():
    picture = np.full((10, 150, 4), 255, dtype=np.uint8)
    picture[:, :50, :3] = 0  # the left third is black, the rest white
    frame = np.full((60, 100, 3), 100, dtype=np.uint8)
    at_left = stamper([(picture, Corner.TOP_LEFT)], (100, 60))(frame)
    at_right = stamper([(picture, Corner.TOP_RIGHT)], (100, 60))(frame)
    assert at_left[0, 0, 0] == 0 and at_left[0, 99, 0] == 255
    assert at_right[0, 0, 0] == 255 and at_right[0, 99, 0] == 255


def test_text_is_drawn_after_the_image_so_it_ends_up_on_top(logo_path):
    output = OutputSettings(
        lead_in=1,
        lead_out=1,
        text_overlay=TextOverlay("Sync"),
        image_overlay=ImageOverlay(logo_path),
    )
    corners = [corner for _, corner in overlay_patches(output, output_width=400)]
    assert corners == [Corner.TOP_LEFT, Corner.BOTTOM_LEFT]
    assert overlay_patches(OutputSettings(lead_in=1, lead_out=1), output_width=400) == []
