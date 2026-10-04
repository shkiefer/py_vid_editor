"""Row layout arithmetic, using the rules agreed in CONTEXT.md."""

import pytest

from vid_editor.layout import row_layout


def test_one_source_keeps_its_own_size():
    layout = row_layout([(1920, 1080)])
    assert (layout.width, layout.height, layout.panel_widths) == (1920, 1080, (1920,))


def test_sources_in_a_row_are_matched_to_the_height_of_the_first():
    # A 1920 by 1080 Source, then a portrait 1080 by 1920 one scaled to 1080 high.
    layout = row_layout([(1920, 1080), (1080, 1920)])
    assert layout.height == 1080
    assert layout.panel_widths == (1920, 608)
    assert layout.width == 2528


def test_the_order_sources_are_added_in_decides_which_one_sets_the_height():
    layout = row_layout([(1080, 1920), (1920, 1080)])
    assert layout.height == 1920
    # 3413.3 wide at that height; the Output width is rounded down to an even 4492.
    assert layout.panel_widths == (1080, 3412)


def test_output_width_scales_the_whole_row():
    layout = row_layout([(1920, 1080), (1080, 1920)], output_width=1264)
    assert (layout.width, layout.height) == (1264, 540)
    assert layout.panel_widths == (960, 304)


def test_width_and_height_are_always_even_and_panels_fill_the_width():
    layout = row_layout([(161, 121), (100, 200), (77, 33)], output_width=501)
    assert layout.width == 500 and layout.height % 2 == 0
    assert sum(layout.panel_widths) == layout.width
    natural = row_layout([(161, 121), (100, 200)])
    assert natural.height == 120 and natural.width % 2 == 0
    assert sum(natural.panel_widths) == natural.width


def test_a_row_too_narrow_for_its_sources_is_an_error():
    with pytest.raises(ValueError, match="too narrow"):
        row_layout([(1920, 1080), (10, 1080)], output_width=2)
    with pytest.raises(ValueError, match="at least one Source"):
        row_layout([])
