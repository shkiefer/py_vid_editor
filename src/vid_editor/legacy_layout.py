"""The layout from before typed Panels, when Sources set the sizes.

Kept only to give the Panels of an older Project the sizes they had
(docs/adr/0003). Nothing else should use it.

Sources placed side by side formed a Row and were matched in height. Sources
placed top and bottom formed a Column and were matched in width. The order the
Sources were added in decided which ones set sizes:

- the first Source sets the height of the first Row and the width of the
  first Column;
- the first Source of any later Row is matched to the width of the first
  Column, and so sets the height of its Row;
- a Source that starts a new Column is matched to the height of its Row, and
  so sets the width of that Column;
- every other Source has a Panel of already fixed size. It is scaled to fit
  without distortion, gets Bars where its shape differs, and gets a Crop Hint.
"""

from collections.abc import Sequence
from dataclasses import dataclass


def even(value: float) -> int:
    """Round down to an even number of pixels, as H.264 requires."""
    return max(2, int(value) // 2 * 2)


@dataclass(frozen=True)
class CropHint:
    """What a Source would need to lose to fill its Panel exactly, with no Bars.

    Both are in pixels of the Source after its rotation and crop, the same
    pixels its crop is typed in. One of the two is always zero.
    """

    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class Panel:
    """The area of the Output that one Source occupies, in Output pixels."""

    row: int
    column: int
    """Counted from 0."""
    left: int
    top: int
    width: int
    height: int
    picture_left: int
    picture_top: int
    picture_width: int
    picture_height: int
    """Where the Source's picture sits. It is smaller than the Panel by its Bars."""
    sets_row: bool
    """Whether this Source sets the height of its Row."""
    sets_column: bool
    """Whether this Source sets the width of its Column."""
    crop_hint: CropHint | None = None
    """None when the Source fills its Panel."""

    @property
    def bars(self) -> tuple[int, int]:
        """Total width of the Bars left and right, and total height top and bottom."""
        return self.width - self.picture_width, self.height - self.picture_height


@dataclass(frozen=True)
class GridLayout:
    """The size of the Output and the Panel of each Source."""

    panels: tuple[Panel, ...]
    """One per Source, in the order the Sources were given."""
    column_widths: tuple[int, ...]
    """They add up to `width`."""
    row_heights: tuple[int, ...]
    """They add up to `height`."""
    width: int
    height: int

    @property
    def panel_widths(self) -> tuple[int, ...]:
        return tuple(panel.width for panel in self.panels)


def grid_layout(
    sizes: Sequence[tuple[int, int]],
    rows: Sequence[int] | None = None,
    output_width: int | None = None,
) -> GridLayout:
    """Lay Sources out in Rows, one above another.

    `sizes` are the (width, height) of each Source after its own rotation and
    crop, in the order the Sources were added. `rows` says which Row each is
    in; only the order of the numbers counts, and None puts every Source in
    one Row. Within a Row, Sources run left to right in the order added.
    `output_width` scales the whole Output; None keeps the first Source at its
    own size.
    """
    if not sizes:
        raise ValueError("The Output needs at least one Source")
    if rows is None:
        rows = [0] * len(sizes)
    if len(rows) != len(sizes):
        raise ValueError("Each Source needs a Row")
    row_of = {number: position for position, number in enumerate(sorted(set(rows)))}
    if row_of[rows[0]] != 0:
        raise ValueError("The first Source sets the size of the Output and must be in the first Row")

    # Each Source's place: its Row, and its Column counted along that Row.
    places = []
    filled = [0] * len(row_of)
    for number in rows:
        row = row_of[number]
        places.append((row, filled[row]))
        filled[row] += 1

    # Natural sizes, before the Output width scales them. Rows are settled top
    # to bottom, so an earlier Row's Sources are the ones that set the Columns.
    row_heights = [0.0] * len(row_of)
    column_widths = [0.0] * max(filled)
    for row, column in sorted(set(places)):
        width, height = sizes[places.index((row, column))]
        if column == 0:
            if row == 0:
                column_widths[0] = float(width)
                row_heights[0] = float(height)
            else:
                row_heights[row] = height * column_widths[0] / width
        elif not column_widths[column]:
            column_widths[column] = width * row_heights[row] / height
    natural_width, natural_height = sum(column_widths), sum(row_heights)

    if output_width is None:
        # Keep the first Row's height, so the first Source is not scaled at all.
        scale = even(row_heights[0]) / row_heights[0]
        width = even(round(natural_width * scale))
        height = even(round(natural_height * scale))
    else:
        width = even(output_width)
        scale = width / natural_width
        height = even(natural_height * scale)
    # Edges are rounded one by one, so the Panels add up exactly.
    lefts = [round(sum(column_widths[:count]) * scale) for count in range(len(column_widths))]
    tops = [round(sum(row_heights[:count]) * scale) for count in range(len(row_heights))]
    final_widths = tuple(right - left for left, right in zip(lefts, [*lefts[1:], width]))
    final_heights = tuple(bottom - top for top, bottom in zip(tops, [*tops[1:], height]))
    if min(final_widths) < 1 or min(final_heights) < 1:
        raise ValueError("The Output is too narrow to show every Source")

    first_in_column = {}
    for row, column in sorted(set(places)):
        first_in_column.setdefault(column, row)

    panels = []
    for (source_width, source_height), (row, column) in zip(sizes, places):
        panel_width, panel_height = final_widths[column], final_heights[row]
        sets_row = column == 0
        sets_column = first_in_column[column] == row and (column > 0 or row == 0)
        picture_width, picture_height, hint = panel_width, panel_height, None
        if not (sets_row or sets_column):
            # A Panel of fixed size: fit the Source inside it without distortion.
            if source_width * panel_height > source_height * panel_width:
                picture_height = min(
                    panel_height, max(1, round(source_height * panel_width / source_width))
                )
                lose = round(source_width - source_height * panel_width / panel_height)
                hint = CropHint(width=lose)
            else:
                picture_width = min(
                    panel_width, max(1, round(source_width * panel_height / source_height))
                )
                lose = round(source_height - source_width * panel_height / panel_width)
                hint = CropHint(height=lose)
            if (picture_width, picture_height) == (panel_width, panel_height) or lose < 1:
                picture_width, picture_height, hint = panel_width, panel_height, None
        panels.append(
            Panel(
                row=row,
                column=column,
                left=lefts[column],
                top=tops[row],
                width=panel_width,
                height=panel_height,
                picture_left=lefts[column] + (panel_width - picture_width) // 2,
                picture_top=tops[row] + (panel_height - picture_height) // 2,
                picture_width=picture_width,
                picture_height=picture_height,
                sets_row=sets_row,
                sets_column=sets_column,
                crop_hint=hint,
            )
        )
    return GridLayout(
        panels=tuple(panels),
        column_widths=final_widths,
        row_heights=final_heights,
        width=width,
        height=height,
    )
