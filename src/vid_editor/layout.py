"""Where each Panel sits in the Output. Plain arithmetic, no video.

Sources placed side by side form a Row and are matched in height. The first
Source sets the Row height; every other Source is scaled to it without
distortion, so each sets the width of its own Panel.
"""

from collections.abc import Sequence
from dataclasses import dataclass


def even(value: float) -> int:
    """Round down to an even number of pixels, as H.264 requires."""
    return max(2, int(value) // 2 * 2)


@dataclass(frozen=True)
class RowLayout:
    """The size of the Output and the width of each Panel in its one Row."""

    panel_widths: tuple[int, ...]
    """Width of each Panel in pixels, left to right. They add up to `width`."""
    width: int
    height: int
    """Height of the Output, which is also the height of every Panel."""


def row_layout(sizes: Sequence[tuple[int, int]], output_width: int | None = None) -> RowLayout:
    """Lay Sources out side by side.

    `sizes` are the (width, height) of each Source after its own rotation and
    crop, left to right. `output_width` scales the whole Row; None keeps the
    first Source at its own size.
    """
    if not sizes:
        raise ValueError("The Output needs at least one Source")
    row_height = sizes[0][1]
    natural_widths = [width * row_height / height for width, height in sizes]
    natural_width = sum(natural_widths)

    if output_width is None:
        # Keep the Row height, so the first Source is not scaled at all.
        height = even(row_height)
        scale = height / row_height
        width = even(round(natural_width * scale))
    else:
        width = even(output_width)
        scale = width / natural_width
        height = even(row_height * width / natural_width)
    # Panel edges are rounded one by one, so the widths add up exactly.
    edges = [round(sum(natural_widths[:count]) * scale) for count in range(len(sizes))] + [width]
    panel_widths = tuple(right - left for left, right in zip(edges, edges[1:]))
    if min(panel_widths) < 1:
        raise ValueError("The Output is too narrow to show every Source")
    return RowLayout(panel_widths=panel_widths, width=width, height=height)
