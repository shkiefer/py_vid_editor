"""The settings that make up a Project. Terms follow CONTEXT.md."""

from dataclasses import dataclass, field
from enum import Enum


class EditError(ValueError):
    """A setting cannot be applied to the Source or Output it belongs to."""


class Quality(Enum):
    """Named quality levels for the Output file."""

    HIGH = "High"
    MEDIUM = "Medium"
    SMALL = "Small file"


class SpeedChoice(Enum):
    """How the Output Speed is chosen."""

    SLOWEST = "Slowest Source"
    REAL_TIME = "Real time"
    CUSTOM = "Custom"


class Workflow(Enum):
    """What a Project makes of its Sources."""

    GRID = "Synced grid"
    SEQUENCE = "Sequence"


class JoinKind(Enum):
    """What happens where one Source of a Sequence hands over to the next."""

    CUT = "Cut"
    BLACK = "Fade through black"
    CROSSFADE = "Crossfade"


class Corner(Enum):
    """The corner of the Output an Overlay sits in."""

    TOP_LEFT = "Top left"
    TOP_RIGHT = "Top right"
    BOTTOM_LEFT = "Bottom left"
    BOTTOM_RIGHT = "Bottom right"

    @property
    def is_top(self) -> bool:
        return self in (Corner.TOP_LEFT, Corner.TOP_RIGHT)

    @property
    def is_left(self) -> bool:
        return self in (Corner.TOP_LEFT, Corner.BOTTOM_LEFT)


@dataclass(frozen=True)
class TextOverlay:
    """White text on a half-transparent black box in one corner of the Output."""

    text: str
    size: int = 30
    """Font size in Output pixels."""
    corner: Corner = Corner.BOTTOM_LEFT


@dataclass(frozen=True)
class ImageOverlay:
    """An image file on a black box in one corner of the Output."""

    path: str
    corner: Corner = Corner.TOP_LEFT
    width_percent: float = 25.0
    """Width of the box, as a percentage of the Output width."""
    background_opacity: float = 0.5
    """Opacity of the black box behind the image: 0 is clear, 1 is solid black."""


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
    """Width to resize to, applied after the crop, in the same typed pixels as
    the Panel sizes. The height follows without distortion. None fits the
    Source inside its Panel."""
    record_rate: float | None = None
    """Record Rate in frames per second. None means the file's Playback Rate,
    which makes the Source real time."""
    panel: int = 0
    """Position in the Project's `panels` of the Panel the Source is assigned to."""
    start_point: float = 0.0
    """In a Sequence, the file time before which none of the Source is used."""
    end_point: float | None = None
    """In a Sequence, the file time after which none of the Source is used.
    None is the end of the file."""
    play_speed: float = 1.0
    """In a Sequence, how much faster than its file the Source is played."""
    join: "Transition" = field(default_factory=lambda: Transition())
    """In a Sequence, the Transition at the Join after this Source. The last
    Source's is not used."""


@dataclass(frozen=True)
class Transition:
    """What happens at a Join, and over how many seconds of Output running time."""

    kind: JoinKind = JoinKind.CUT
    length: float = 1.0
    """Not used by a cut. A fade through black spends half of it fading out
    and half fading in; a crossfade overlaps the two Sources by all of it."""


@dataclass(frozen=True)
class AudioTrack:
    """A sound file laid over the Output, placed on its running time."""

    path: str
    start: float = 0.0
    """Output running time at which the Audio Track begins."""
    file_start: float = 0.0
    """File time from which the Audio Track plays."""
    volume: float = 100.0
    """Percentage of the sound as it is in its file, from 0 to 200."""
    fade_out: float = 1.0
    """Seconds before the end of the Output over which an Audio Track it cuts off
    fades out. 0 stops it dead at the end."""


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
    speed: float | None = None
    """Output Speed, where 1 is real time. None uses the slowest Source Speed,
    at which no frame of any Source is dropped for being too slow."""
    quality: Quality = Quality.MEDIUM
    text_overlay: TextOverlay | None = None
    image_overlay: ImageOverlay | None = None
    audio_tracks: tuple[AudioTrack, ...] = ()
    source_volume: float = 100.0
    """Percentage for the sound from the Sources: the Audio Panel's in a
    Synced grid, every Source's in a Sequence."""

    @property
    def running_time(self) -> float:
        return self.lead_in + self.lead_out


@dataclass(frozen=True)
class DraftSettings:
    """How the Draft differs from the Output it is a rough copy of."""

    lead_in: float = 2.0
    """Draft running time from the start of the Draft to the Sync Event."""
    lead_out: float = 2.0
    """Draft running time from the Sync Event to the end of the Draft."""
    width: int = 640
    """Draft width in pixels. An Output narrower than this is not enlarged."""
    sound: bool = False
    """Whether the Draft carries the sound the Output would have."""


@dataclass(frozen=True)
class Panel:
    """An area of the Output, set up in the layout, with a size typed by the user."""

    width: int
    height: int
    row: int = 1
    """The Row the Panel sits in, counted from 1 at the top. Only the order of
    the numbers counts, so Rows 1 and 3 with no Row 2 are two Rows."""


@dataclass(frozen=True)
class SequenceSettings:
    """What belongs to a Sequence as a whole."""

    width: int
    """Width of the Sequence's one Panel, in typed pixels."""
    height: int
    """Height of the Sequence's one Panel, in typed pixels."""
    fade_in: float = 0.0
    """Seconds of fade from black at the very start of the Sequence."""
    fade_out: float = 0.0
    """Seconds of fade to black at the very end of the Sequence."""


@dataclass(frozen=True)
class Project:
    """The Panels, Sources and settings that produce one Output."""

    sources: tuple[Source, ...]
    """In the order added, which in a Sequence is the play order."""
    output: OutputSettings
    panels: tuple[Panel, ...]
    """In their listed order, which is left to right within each Row. A Panel
    that no Source is assigned to is empty, and black."""
    audio_panel: int | None = 0
    """Position in `panels` of the Audio Panel. None gives an Output with no sound."""
    workflow: Workflow = Workflow.GRID
    sequence: SequenceSettings | None = None
    """The Sequence's settings; needed only when the workflow is a Sequence."""
