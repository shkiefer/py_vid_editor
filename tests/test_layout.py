"""Layout arithmetic for typed Panels, using the rules agreed in CONTEXT.md."""

import pytest

from vid_editor.layout import Box, CropHint, panel_layout, picture_in, width_for_height

WIDE = (1920, 1080)
TALL = (1080, 1920)
PANEL = Box(row=0, left=0, top=0, width=960, height=540)
TYPED = (960, 540)


def test_one_panel_is_the_whole_output_at_its_typed_size():
    layout = panel_layout([(1920, 1080, 1)])
    assert (layout.width, layout.height, layout.scale) == (1920, 1080, 1.0)
    assert layout.boxes == (Box(row=0, left=0, top=0, width=1920, height=1080),)


def test_panels_that_share_a_row_sit_side_by_side_in_their_listed_order():
    layout = panel_layout([(1920, 1080, 1), (608, 1080, 1)])
    assert (layout.width, layout.height) == (2528, 1080)
    assert [(box.left, box.top, box.width) for box in layout.boxes] == [(0, 0, 1920), (1920, 0, 608)]


def test_panels_in_different_rows_need_not_line_up():
    # One large Panel over three small ones.
    layout = panel_layout([(1920, 1080, 1), (640, 360, 2), (640, 360, 2), (640, 360, 2)])
    assert (layout.width, layout.height) == (1920, 1440)
    assert layout.row_heights == (1080, 360)
    assert [(box.left, box.top) for box in layout.boxes[1:]] == [(0, 1080), (640, 1080), (1280, 1080)]


def test_only_the_order_of_row_numbers_counts():
    assert panel_layout([(100, 50, 1), (100, 50, 7)]) == panel_layout([(100, 50, 1), (100, 50, 2)])
    # A Panel listed first can still be in a lower Row.
    below, above = panel_layout([(100, 50, 2), (100, 80, 1)]).boxes
    assert (above.top, below.top) == (0, 80)


def test_a_row_narrower_than_the_output_is_centred():
    layout = panel_layout([(1920, 1080, 1), (640, 360, 2), (640, 360, 2), (320, 360, 2)])
    assert layout.width == 1920
    assert [(box.left, box.width) for box in layout.boxes[1:]] == [(160, 640), (800, 640), (1440, 320)]


def test_a_row_is_as_tall_as_its_tallest_panel_and_a_shorter_one_sits_at_the_top():
    layout = panel_layout([(1920, 1080, 1), (608, 540, 1)])
    assert layout.height == 1080
    short = layout.boxes[1]
    assert (short.top, short.height) == (0, 540)


def test_output_width_scales_the_whole_layout():
    layout = panel_layout([(1920, 1080, 1), (608, 1080, 1), (2528, 360, 2)], output_width=1264)
    assert (layout.width, layout.height, layout.scale) == (1264, 720, 0.5)
    assert [(box.left, box.top, box.width, box.height) for box in layout.boxes] == [
        (0, 0, 960, 540),
        (960, 0, 304, 540),
        (0, 540, 1264, 180),
    ]


def test_the_output_is_always_an_even_size():
    layout = panel_layout([(101, 51, 1)])
    assert (layout.width, layout.height) == (100, 50)
    assert layout.boxes[0].width == 100 and layout.boxes[0].height == 50
    scaled = panel_layout([(161, 121, 1), (100, 200, 1)], output_width=501)
    assert scaled.width == 500 and scaled.height % 2 == 0
    assert sum(box.width for box in scaled.boxes) == 500


def test_a_layout_that_cannot_be_shown_is_an_error():
    with pytest.raises(ValueError, match="at least one Panel"):
        panel_layout([])
    with pytest.raises(ValueError, match="at least 2 pixels"):
        panel_layout([(1920, 1, 1)])
    with pytest.raises(ValueError, match="too narrow"):
        panel_layout([(1920, 1080, 1), (2, 1080, 1)], output_width=2)


def test_a_source_with_no_resize_is_fitted_inside_its_panel():
    picture = picture_in(PANEL, TYPED, 1.0, TALL)
    assert (picture.width, picture.height) == (304, 540)
    assert (picture.left, picture.top) == (328, 0)
    assert picture.bars == (656, 0) and picture.cut == (0, 0)
    # Cropped to 608 high (rounded from 607.5) it would have the Panel's shape.
    assert picture.crop_hint == CropHint(height=1312)


def test_a_fitted_source_that_is_too_wide_gets_bars_above_and_below():
    picture = picture_in(Box(0, 100, 50, 608, 1080), (608, 1080), 1.0, WIDE)
    assert (picture.width, picture.height) == (608, 342)
    assert (picture.left, picture.top) == (100, 50 + 369)
    assert picture.bars == (0, 738)
    assert picture.crop_hint == CropHint(width=1312)


def test_a_source_of_the_same_shape_as_its_panel_fills_it():
    picture = picture_in(PANEL, TYPED, 1.0, WIDE)
    assert (picture.width, picture.height) == (960, 540)
    assert picture.bars == (0, 0) and picture.cut == (0, 0) and picture.crop_hint is None
    # A pixel of rounding is not worth a Bar.
    assert picture_in(PANEL, TYPED, 1.0, (1921, 1080)).bars == (0, 0)


def test_a_source_resized_larger_than_its_panel_is_cut_off_evenly():
    # Scaled to the Panel's width the portrait Source is 960 by 1707.
    picture = picture_in(PANEL, TYPED, 1.0, TALL, resize_width=960)
    assert (picture.width, picture.height) == (960, 1707)
    assert (picture.shown_width, picture.shown_height) == (960, 540)
    assert (picture.left, picture.top) == (0, 0)
    assert (picture.cut_left, picture.cut_top) == (0, 583)
    assert picture.bars == (0, 0) and picture.cut == (0, 1167)
    # The Panel hides 1167 scaled pixels, which is 1313 of the Source's own.
    assert picture.crop_hint == CropHint(height=1313)


def test_a_source_resized_smaller_than_its_panel_gets_bars_and_no_crop_hint():
    picture = picture_in(PANEL, TYPED, 1.0, WIDE, resize_width=480)
    assert (picture.width, picture.height) == (480, 270)
    assert (picture.left, picture.top) == (240, 135)
    assert picture.bars == (480, 270)
    assert picture.crop_hint is None


def test_a_source_can_have_bars_one_way_and_be_cut_the_other():
    picture = picture_in(PANEL, TYPED, 1.0, TALL, resize_width=608)
    assert (picture.width, picture.height) == (608, 1081)
    assert picture.bars == (352, 0) and picture.cut == (0, 541)
    assert picture.crop_hint == CropHint(height=961)


def test_a_typed_resize_is_in_typed_pixels_and_scales_with_the_output_width():
    half = panel_layout([(1920, 1080, 1)], output_width=960)
    picture = picture_in(half.boxes[0], (1920, 1080), half.scale, WIDE, resize_width=1920)
    assert (picture.width, picture.height) == (960, 540)
    assert picture.bars == (0, 0) and picture.crop_hint is None


def test_a_source_that_fills_the_typed_panel_fills_it_at_any_output_width():
    # At 1000 wide the Output is 280 high where 281.25 would keep the shape.
    # The rounding is not shown as a hairline Bar beside a Source that fits as typed.
    layout = panel_layout([(1920, 1080, 1), (1920, 1080, 1)], output_width=1000)
    assert (layout.boxes[0].width, layout.boxes[0].height) == (500, 280)
    for resize_width in (None, 1920):
        picture = picture_in(layout.boxes[0], (1920, 1080), layout.scale, WIDE, resize_width)
        assert (picture.width, picture.height) == (500, 280)
        assert picture.bars == (0, 0) and picture.cut == (0, 0) and picture.crop_hint is None


def test_the_resize_width_that_matches_a_panels_height():
    assert width_for_height(TALL, 540) == 304
    assert picture_in(PANEL, TYPED, 1.0, TALL, resize_width=304).bars == (656, 0)
    assert picture_in(PANEL, TYPED, 1.0, TALL, resize_width=304).cut == (0, 0)
