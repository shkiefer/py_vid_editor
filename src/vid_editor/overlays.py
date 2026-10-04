"""Overlays: text or an image drawn in a corner of the Output.

Each Overlay is drawn once as a small picture with its own transparency and
then stamped onto every frame. Layering clips in MoviePy instead costs far
more per frame.
"""

from collections.abc import Callable, Sequence
from functools import lru_cache
from math import ceil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vid_editor.model import Corner, EditError, ImageOverlay, OutputSettings, TextOverlay

_ROOT = Path(__file__).parents[2]
FONT = _ROOT / "assets" / "fonts" / "Carlito-Bold.ttf"
LOGO_FOLDER = _ROOT / "assets" / "logos"
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

_TEXT_BOX_OPACITY = 0.5

Patch = tuple[np.ndarray, Corner]
"""An Overlay as a picture (height by width by red, green, blue, opacity) and its corner."""


@lru_cache(maxsize=16)
def text_patch(overlay: TextOverlay) -> np.ndarray:
    """The text Overlay as a picture: white text on a half-transparent black box."""
    if not overlay.text.strip():
        raise EditError("The text Overlay has no text")
    if overlay.size < 4:
        raise EditError("The text size must be at least 4 pixels")
    font = ImageFont.truetype(str(FONT), overlay.size)
    padding = max(2, round(overlay.size / 3))
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = measure.multiline_textbbox((0, 0), overlay.text, font=font)
    size = (ceil(right - left) + 2 * padding, ceil(bottom - top) + 2 * padding)
    box = Image.new("RGBA", size, (0, 0, 0, round(255 * _TEXT_BOX_OPACITY)))
    ImageDraw.Draw(box).multiline_text(
        (padding - left, padding - top), overlay.text, font=font, fill=(255, 255, 255, 255)
    )
    return np.asarray(box)


def image_patch(overlay: ImageOverlay, output_width: int) -> np.ndarray:
    """The image Overlay as a picture: the image, scaled, on a black box."""
    path = Path(overlay.path)
    if not path.is_file():
        raise EditError(f"No image found at {overlay.path}")
    return _image_patch(overlay, output_width, path.stat().st_mtime)


@lru_cache(maxsize=16)
def _image_patch(overlay: ImageOverlay, output_width: int, modified: float) -> np.ndarray:
    if not 0 < overlay.width_percent <= 100:
        raise EditError("The image width must be more than 0 and at most 100 percent of the Output")
    if not 0 <= overlay.background_opacity <= 1:
        raise EditError("The image background opacity must be between 0 and 1")
    try:
        with Image.open(overlay.path) as file:
            picture = file.convert("RGBA")
    except Exception as error:  # Pillow raises several types for bad files
        raise EditError(f"Could not read {overlay.path} as an image") from error

    box_width = max(3, round(output_width * overlay.width_percent / 100))
    padding = min(max(2, round(box_width / 24)), (box_width - 1) // 2)
    width = box_width - 2 * padding
    height = max(1, round(picture.height * width / picture.width))
    picture = picture.resize((width, height), Image.Resampling.LANCZOS)
    box = Image.new(
        "RGBA",
        (box_width, height + 2 * padding),
        (0, 0, 0, round(255 * overlay.background_opacity)),
    )
    box.alpha_composite(picture, (padding, padding))
    return np.asarray(box)


def overlay_patches(output: OutputSettings, output_width: int) -> list[Patch]:
    """The Output's Overlays as pictures. The image comes first, so text is drawn over it."""
    patches = []
    if output.image_overlay is not None:
        patches.append((image_patch(output.image_overlay, output_width), output.image_overlay.corner))
    if output.text_overlay is not None:
        patches.append((text_patch(output.text_overlay), output.text_overlay.corner))
    return patches


def stamper(
    patches: Sequence[Patch], frame_size: tuple[int, int]
) -> Callable[[np.ndarray], np.ndarray]:
    """A function that draws the Overlays onto a frame of the given (width, height).

    An Overlay larger than the frame keeps the part nearest its corner.
    """
    frame_width, frame_height = frame_size
    prepared = []
    for picture, corner in patches:
        height = min(picture.shape[0], frame_height)
        width = min(picture.shape[1], frame_width)
        rows = slice(0, height) if corner.is_top else slice(picture.shape[0] - height, None)
        columns = slice(0, width) if corner.is_left else slice(picture.shape[1] - width, None)
        part = picture[rows, columns].astype(np.float32)
        opacity = part[..., 3:] / 255
        top = 0 if corner.is_top else frame_height - height
        left = 0 if corner.is_left else frame_width - width
        where = (slice(top, top + height), slice(left, left + width))
        prepared.append((where, part[..., :3] * opacity, 1 - opacity))

    def stamp(frame: np.ndarray) -> np.ndarray:
        stamped = np.array(frame, dtype=np.uint8)
        for where, colour, show_through in prepared:
            stamped[where] = (stamped[where] * show_through + colour + 0.5).astype(np.uint8)
        return stamped

    return stamp
