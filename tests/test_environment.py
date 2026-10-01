"""Smoke tests: the environment can do everything the editor relies on.

No system binaries are assumed. ffmpeg comes from imageio-ffmpeg and text is
drawn by Pillow using the font bundled in assets/fonts.
"""

from pathlib import Path

import numpy as np
import pytest
from moviepy import (
    AudioClip,
    ColorClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    clips_array,
    vfx,
)

FONT = Path(__file__).parent.parent / "assets" / "fonts" / "Carlito-Bold.ttf"


def _tone(duration: float) -> AudioClip:
    return AudioClip(
        lambda t: np.sin(2 * np.pi * 440 * t), duration=duration, fps=44100
    )


def test_bundled_font_exists():
    assert FONT.is_file()


def test_text_is_drawn_with_bundled_font():
    text = TextClip(font=str(FONT), text="Sync", font_size=40, color="white")
    background = ColorClip(size=(320, 240), color=(0, 0, 0), duration=1)
    frame = CompositeVideoClip([background, text.with_duration(1)]).get_frame(0)
    assert frame.shape == (240, 320, 3)
    assert frame.max() > 200, "no white text pixels were drawn"


def test_rotate_crop_resize_and_speed_effects():
    clip = ColorClip(size=(320, 240), color=(255, 0, 0), duration=2).with_fps(30)
    edited = clip.with_effects(
        [
            vfx.Rotate(90),
            vfx.Crop(x1=10, y1=20, x2=230, y2=300),
            vfx.Resize(width=110),
            vfx.MultiplySpeed(0.5),
        ]
    )
    assert edited.size == (110, 140)
    assert edited.duration == pytest.approx(4.0)


def test_encode_side_by_side_mp4_with_sound_and_read_back(tmp_path):
    left = ColorClip(size=(160, 120), color=(255, 0, 0), duration=1)
    right = ColorClip(size=(160, 120), color=(0, 0, 255), duration=1)
    output = clips_array([[left, right]]).with_audio(_tone(1))
    path = tmp_path / "out.mp4"

    output.write_videofile(
        str(path), fps=30, codec="libx264", audio_codec="aac", logger=None
    )

    with VideoFileClip(str(path)) as read_back:
        assert read_back.size == [320, 120]
        assert read_back.duration == pytest.approx(1.0, abs=0.1)
        assert read_back.audio is not None
        frame = read_back.get_frame(0.5)
        assert frame[60, 80, 0] > 200 and frame[60, 80, 2] < 60, "left Panel is not red"
        assert frame[60, 240, 2] > 200 and frame[60, 240, 0] < 60, "right Panel is not blue"
