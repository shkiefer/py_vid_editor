"""Shared test fixtures."""

import numpy as np
import pytest
from moviepy import AudioClip, VideoClip, VideoFileClip

SOURCE_DURATION = 4.0
SOURCE_SIZE = (160, 120)
SOURCE_RATE = 10


def _frame(t: float) -> np.ndarray:
    """A frame whose red level encodes its time and whose top-left is green.

    Red runs from 60 at 0 s to 220 at 4 s, so footage is never as dark as a
    black Gap. The green quadrant shows which way up the picture is.
    """
    width, height = SOURCE_SIZE
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = int(60 + 40 * t)
    frame[: height // 2, : width // 2, 1] = 255
    return frame


def file_time_shown(frame: np.ndarray) -> float:
    """Read back the file time encoded in the red level of a frame's last row."""
    red = float(frame[-4:, -4:, 0].mean())
    return (red - 60) / 40


def is_black(frame: np.ndarray) -> bool:
    return int(frame.max()) < 30


@pytest.fixture(scope="session")
def source_path(tmp_path_factory) -> str:
    """A 4 second, 160 by 120, 10 frames per second Source with sound."""
    path = tmp_path_factory.mktemp("sources") / "source.mp4"
    tone = AudioClip(lambda t: np.sin(2 * np.pi * 440 * t), duration=SOURCE_DURATION, fps=44100)
    clip = VideoClip(_frame, duration=SOURCE_DURATION).with_audio(tone)
    clip.write_videofile(
        str(path),
        fps=SOURCE_RATE,
        codec="libx264",
        audio_codec="aac",
        ffmpeg_params=["-crf", "10"],
        logger=None,
    )
    return str(path)


@pytest.fixture
def source_clip(source_path):
    with VideoFileClip(source_path) as clip:
        yield clip


TALL_DURATION = 2.0
TALL_SIZE = (100, 200)


def _tall_frame(t: float) -> np.ndarray:
    """A blue frame whose red level encodes its time, like the first Source."""
    width, height = TALL_SIZE
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = int(60 + 40 * t)
    frame[:, :, 2] = 255
    return frame


@pytest.fixture(scope="session")
def tall_source_path(tmp_path_factory) -> str:
    """A 2 second, 100 by 200, 20 frames per second Source with no sound."""
    path = tmp_path_factory.mktemp("sources") / "tall.mp4"
    VideoClip(_tall_frame, duration=TALL_DURATION).write_videofile(
        str(path), fps=20, codec="libx264", ffmpeg_params=["-crf", "10"], logger=None
    )
    return str(path)


@pytest.fixture
def tall_source_clip(tall_source_path):
    with VideoFileClip(tall_source_path) as clip:
        yield clip
