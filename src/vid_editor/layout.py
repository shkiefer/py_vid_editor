"""Where each Panel sits in the Output, and each Source in its Panel.

Plain arithmetic, no video. Panels are set up by the user, each with a Row and
a typed width and height. Panels that share a Row sit side by side in their
listed order. A Row is as tall as its tallest Panel, and the Output is as wide
as its widest Row; a narrower Row is centred. No Source sets the size of a
Panel (docs/adr/0003): a Source is centred in its Panel, with Bars where it is
smaller and an even cut where it is larger.
"""

from collections.abc import Sequence
from dataclasses import dataclass


def even(value: float) -> int:
    """Round down to an even number of pixels, as H.264 requires."""
    return max(2, int(value) // 2 * 2)


@dataclass(frozen=True)
class Box:
    """The area of the Output that one Panel occupies, in Output pixels."""

    row: int
    """Counted from 0 at the top."""
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class Layout:
    """The size of the Output and the Box of each Panel."""

    boxes: tuple[Box, ...]
    """One per Panel, in the order the Panels were given."""
    row_heights: tuple[int, ...]
    """They add up to `height`."""
    width: int
    height: int
    scale: float
    """Output pixels for each typed pixel: 1 unless an Output width scales the layout."""


def panel_layout(
    panels: Sequence[tuple[int, int, int]], output_width: int | None = None
) -> Layout:
    """Lay typed Panels out in Rows.

    `panels` are the (width, height, row) of each Panel as typed. Only the
    order of the Row numbers counts. `output_width` scales the whole layout;
    None keeps the typed sizes.
    """
    if not panels:
        raise ValueError("The layout needs at least one Panel")
    if any(width < 2 or height < 2 for width, height, _ in panels):
        raise ValueError("A Panel must be at least 2 pixels wide and 2 pixels high")
    numbers = sorted({number for *_, number in panels})
    row_of = {number: position for position, number in enumerate(numbers)}
    typed_heights = [0] * len(row_of)
    typed_widths = [0] * len(row_of)
    for width, height, number in panels:
        typed_heights[row_of[number]] = max(typed_heights[row_of[number]], height)
        typed_widths[row_of[number]] += width
    typed_width, typed_height = max(typed_widths), sum(typed_heights)

    if output_width is None:
        # Typed sizes are kept as they are. An odd pixel is trimmed off the
        # right or the bottom rather than scaling the whole layout to lose it.
        scale = 1.0
        width, height = even(typed_width), even(typed_height)
    else:
        width = even(output_width)
        scale = width / typed_width
        height = even(round(typed_height * scale))
    # Edges are rounded one by one, so Panels that touch as typed touch in the Output.
    tops = [round(sum(typed_heights[:count]) * scale) for count in range(len(row_of))]
    bottoms = [*tops[1:], height]
    row_heights = tuple(bottom - top for top, bottom in zip(tops, bottoms))
    if min(row_heights) < 1:
        raise ValueError("The Output is too narrow to show every Panel")

    boxes = []
    # A Row narrower than the Output is centred.
    across = [(typed_width - row_width) / 2 for row_width in typed_widths]
    for panel_width, panel_height, number in panels:
        row = row_of[number]
        left = min(round(across[row] * scale), width)
        right = min(round((across[row] + panel_width) * scale), width)
        across[row] += panel_width
        typed_top = sum(typed_heights[:row])
        # A Panel shorter than its Row sits at the top of the Row.
        bottom = min(round((typed_top + panel_height) * scale), bottoms[row])
        if right - left < 1 or bottom - tops[row] < 1:
            raise ValueError("The Output is too narrow to show every Panel")
        boxes.append(
            Box(row=row, left=left, top=tops[row], width=right - left, height=bottom - tops[row])
        )
    return Layout(
        boxes=tuple(boxes), row_heights=row_heights, width=width, height=height, scale=scale
    )


@dataclass(frozen=True)
class CropHint:
    """What a Source would need to lose to fill its Panel exactly.

    For a Source fitted inside its Panel it is what to crop to be rid of the
    Bars. For a Source larger than its Panel it is what the Panel cuts off.
    Both are in pixels of the Source after its rotation and crop, the same
    pixels its crop is typed in.
    """

    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class Picture:
    """One Source's picture in its Panel, in Output pixels."""

    width: int
    height: int
    """The Source as scaled, before the Panel cuts anything off."""
    left: int
    top: int
    """Where the part on show begins in the Output."""
    shown_width: int
    shown_height: int
    """The part on show. It is smaller than the Panel by the Bars."""
    cut_left: int
    cut_top: int
    """How much of the scaled picture is hidden beyond the Panel's left and top edges."""
    bars: tuple[int, int]
    """Total width of the Bars left and right, and total height above and below."""
    crop_hint: CropHint | None = None
    """None when there is nothing to crop: the Source fills its Panel, or is
    smaller than it at a typed size."""

    @property
    def cut(self) -> tuple[int, int]:
        """Total width the Panel cuts off left and right, and total height top and bottom."""
        return self.width - self.shown_width, self.height - self.shown_height


def picture_in(
    box: Box,
    typed: tuple[int, int],
    scale: float,
    size: tuple[int, int],
    resize_width: int | None = None,
) -> Picture:
    """Place a Source in its Panel, centred and never distorted.

    `typed` is the Panel's typed (width, height) and `box` is where it came
    out in the Output at the layout's `scale`. `size` is the (width, height)
    of the Source after its rotation and crop. `resize_width` is its typed
    resize, in typed pixels like the Panel's size; None fits it inside.

    The Source is sized against the Panel as typed. Where it matches the typed
    Panel to within a pixel it takes the whole of the Box, so that the
    rounding of an Output width never leaves a hairline Bar or cut.
    """
    source_width, source_height = size
    if resize_width is None:
        typed_factor = min(typed[0] / source_width, typed[1] / source_height)
    else:
        typed_factor = resize_width / source_width
    factor = typed_factor * scale

    def along(source_side: int, typed_side: int, box_side: int) -> int:
        if abs(source_side * typed_factor - typed_side) <= 1:
            return box_side
        scaled = max(1, round(source_side * factor))
        return box_side if abs(scaled - box_side) <= 1 else scaled

    width = along(source_width, typed[0], box.width)
    height = along(source_height, typed[1], box.height)
    shown_width, shown_height = min(width, box.width), min(height, box.height)
    bars = (box.width - shown_width, box.height - shown_height)

    if resize_width is None:
        # Fitted: one pair of Bars at most, which a crop of the other side removes.
        if bars[0]:
            hint = CropHint(height=round(source_height - source_width * typed[1] / typed[0]))
        elif bars[1]:
            hint = CropHint(width=round(source_width - source_height * typed[0] / typed[1]))
        else:
            hint = CropHint()
    else:
        hint = CropHint(
            width=round((width - shown_width) / factor),
            height=round((height - shown_height) / factor),
        )
    return Picture(
        width=width,
        height=height,
        left=box.left + bars[0] // 2,
        top=box.top + bars[1] // 2,
        shown_width=shown_width,
        shown_height=shown_height,
        cut_left=(width - shown_width) // 2,
        cut_top=(height - shown_height) // 2,
        bars=bars,
        crop_hint=hint if hint.width >= 1 or hint.height >= 1 else None,
    )


def width_for_height(size: tuple[int, int], height: int) -> int:
    """The resize width that makes a Source of `size` this high."""
    return max(2, round(size[0] * height / size[1]))
