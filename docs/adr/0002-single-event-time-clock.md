# All Sources are timed on one Event Time clock

Sources can have different Source Speeds (slow motion, real time, timelapse), so one Sync Point per Source is not enough to keep them aligned. The first idea was to slow every Source to match the slowest one. We instead convert each Source to Event Time using its own Sync Point and Source Speed, and let a single Output Speed decide how fast Event Time is played back. "Match the slowest Source" survives only as the default value of Output Speed.

## Considered Options

- **Match every Source to the slowest Source.** Never drops frames, but cannot produce a real-time Output from slow-motion footage, and needs separate rules for timelapse Sources and for when sound survives.
- **One Event Time clock with a settable Output Speed (chosen).** One formula per Source. Dropped and held frames, and whether sound is kept, all follow from Output Speed without special cases.

## Consequences

- Sources are never compared or matched to each other in the timing code. Anything that looks like "adjust B to match A" is a mistake.
- Frames can be dropped when Output Speed is faster than a Source's Source Speed. The Frame Hint exists to make that visible to the user.
