"""The settings that make up a Project. Terms follow CONTEXT.md."""

from dataclasses import dataclass, field
from enum import Enum


class Quality(Enum):
    """Named quality levels for the Output file."""

    HIGH = "High"
    MEDIUM = "Medium"
    SMALL = "Small file"


@dataclass(frozen=True)
class Crop:
    """Pixels removed from each edge of a Source, measured after rotation."""

    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0


@dataclass(frozen=True)
class Source:
    """One input video file and the settings that belong to it."""

    path: str
    sync_point: float = 0.0
    """File time, in seconds, at which the Sync Event is seen."""
    rotation: float = 0.0
    """Degrees, anticlockwise. Applied before the crop."""
    crop: Crop = field(default_factory=Crop)
    aspect_override: tuple[int, int] | None = None
    """Forced (width, height) in pixels, applied before rotation."""
    width: int | None = None
    """Width in pixels to resize to, applied after the crop. The height follows
    without distortion. None keeps the cropped size."""


@dataclass(frozen=True)
class OutputSettings:
    """Settings that belong to the Output as a whole."""

    lead_in: float
    """Output running time from the start of the Output to the Sync Event."""
    lead_out: float
    """Output running time from the Sync Event to the end of the Output."""
    width: int | None = None
    """Output width in pixels. None keeps the natural width of the layout."""
    rate: float | None = None
    """Output Rate in frames per second. None uses the Source's Playback Rate."""
    quality: Quality = Quality.MEDIUM

    @property
    def running_time(self) -> float:
        return self.lead_in + self.lead_out


@dataclass(frozen=True)
class Project:
    """The Sources and settings that produce one Output."""

    sources: tuple[Source, ...]
    output: OutputSettings
