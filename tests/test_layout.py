"""Layout arithmetic, using the rules agreed in CONTEXT.md."""

import pytest

from vid_editor.layout import CropHint, grid_layout

WIDE = (1920, 1080)
TALL = (1080, 1920)


def test_one_source_keeps_its_own_size():
    layout = grid_layout([WIDE])
    assert (layout.width, layout.height, layout.panel_widths) == (1920, 1080, (1920,))


def test_sources_in_a_row_are_matched_to_the_height_of_the_first():
    # A 1920 by 1080 Source, then a portrait 1080 by 1920 one scaled to 1080 high.
    layout = grid_layout([WIDE, TALL])
    assert layout.height == 1080
    assert layout.panel_widths == (1920, 608)
    assert layout.width == 2528


def test_the_order_sources_are_added_in_decides_which_one_sets_the_height():
    layout = grid_layout([TALL, WIDE])
    assert layout.height == 1920
    # 3413.3 wide at that height; the Output width is rounded down to an even 4492.
    assert layout.panel_widths == (1080, 3412)


def test_output_width_scales_the_whole_row():
    layout = grid_layout([WIDE, TALL], output_width=1264)
    assert (layout.width, layout.height) == (1264, 540)
    assert layout.panel_widths == (960, 304)


def test_width_and_height_are_always_even_and_panels_fill_the_width():
    layout = grid_layout([(161, 121), (100, 200), (77, 33)], output_width=501)
    assert layout.width == 500 and layout.height % 2 == 0
    assert sum(layout.panel_widths) == layout.width
    natural = grid_layout([(161, 121), (100, 200)])
    assert natural.height == 120 and natural.width % 2 == 0
    assert sum(natural.panel_widths) == natural.width


def test_a_row_too_narrow_for_its_sources_is_an_error():
    with pytest.raises(ValueError, match="too narrow"):
        grid_layout([WIDE, (10, 1080)], output_width=2)
    with pytest.raises(ValueError, match="at least one Source"):
        grid_layout([])


def test_sources_in_a_row_fill_their_panels_and_get_no_crop_hint():
    layout = grid_layout([WIDE, TALL])
    for panel in layout.panels:
        assert panel.bars == (0, 0) and panel.crop_hint is None
    first, second = layout.panels
    assert (first.sets_row, first.sets_column) == (True, True)
    assert (second.sets_row, second.sets_column) == (False, True)
    assert (second.left, second.top) == (1920, 0)


def test_sources_in_a_column_are_matched_to_the_width_of_the_first():
    # The portrait Source is scaled to 1920 wide, which makes it 3413.3 high.
    layout = grid_layout([WIDE, TALL], rows=[1, 2])
    assert (layout.width, layout.height) == (1920, 4492)
    assert layout.row_heights == (1080, 3412)
    below = layout.panels[1]
    assert (below.left, below.top, below.width, below.height) == (0, 1080, 1920, 3412)
    assert below.sets_row and not below.sets_column
    assert below.bars == (0, 0) and below.crop_hint is None


def test_only_the_order_of_row_numbers_counts():
    assert grid_layout([WIDE, TALL], rows=[1, 5]) == grid_layout([WIDE, TALL], rows=[1, 2])


def test_the_first_source_must_be_in_the_first_row():
    with pytest.raises(ValueError, match="first Row"):
        grid_layout([WIDE, TALL], rows=[2, 1])


def test_in_a_grid_a_source_that_cannot_match_both_gets_bars_and_a_crop_hint():
    # Row 1: wide, tall. Row 2: wide, wide. The Columns are 1920 and 608 wide.
    layout = grid_layout([WIDE, TALL, WIDE, WIDE], rows=[1, 1, 2, 2])
    assert layout.column_widths == (1920, 608)
    assert layout.row_heights == (1080, 1080)
    assert (layout.width, layout.height) == (2528, 2160)

    under_first = layout.panels[2]
    assert under_first.sets_row and under_first.crop_hint is None

    # A 608 by 1080 Panel holds the wide Source at 608 by 342, with Bars above and below.
    last = layout.panels[3]
    assert (last.left, last.top, last.width, last.height) == (1920, 1080, 608, 1080)
    assert (last.picture_width, last.picture_height) == (608, 342)
    assert (last.picture_left, last.picture_top) == (1920, 1080 + 369)
    assert last.bars == (0, 738)
    assert not last.sets_row and not last.sets_column
    # Cropped to 608 wide it would be 608 by 1080 and fill the Panel.
    assert last.crop_hint == CropHint(width=1312)


def test_a_source_too_narrow_for_its_panel_gets_a_crop_hint_for_height():
    # Row 2 is 1080 high. The portrait Source fits at 608 wide in a 1920 wide Panel.
    layout = grid_layout([WIDE, WIDE, WIDE, TALL], rows=[1, 1, 2, 2])
    last = layout.panels[3]
    assert (last.width, last.height) == (1920, 1080)
    assert (last.picture_width, last.picture_height) == (608, 1080)
    assert last.bars == (1312, 0)
    # Cropped to 608 high (rounded from 607.5) it would fill the Panel.
    assert last.crop_hint == CropHint(height=1312)


def test_a_source_of_the_same_shape_as_its_panel_fills_it():
    layout = grid_layout([WIDE, WIDE, WIDE, (960, 540)], rows=[1, 1, 2, 2])
    last = layout.panels[3]
    assert last.bars == (0, 0) and last.crop_hint is None


def test_a_later_row_can_be_longer_and_its_extra_source_sets_a_new_column():
    layout = grid_layout([WIDE, WIDE, TALL], rows=[1, 2, 2])
    # The portrait Source is matched to its Row height of 1080, so it is 607.5 wide.
    assert layout.column_widths == (1920, 608)
    assert (layout.width, layout.height) == (2528, 2160)
    extra = layout.panels[2]
    assert (extra.row, extra.column) == (1, 1)
    assert extra.sets_column and extra.crop_hint is None


def test_output_width_scales_the_whole_grid():
    layout = grid_layout([WIDE, TALL, WIDE, WIDE], rows=[1, 1, 2, 2], output_width=1264)
    assert (layout.width, layout.height) == (1264, 1080)
    assert layout.column_widths == (960, 304)
    assert layout.row_heights == (540, 540)
    assert layout.panels[3].crop_hint == CropHint(width=1312)
