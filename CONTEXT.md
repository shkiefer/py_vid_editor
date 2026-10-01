# Video Editor

A local tool for trimming, cropping, and annotating videos, and for combining several videos of the same real-world event into one time-aligned output.

## Language

### Composition

**Source**:
One input video file.
_Avoid_: Clip, input, video

**Panel**:
The area of the **Output** occupied by one **Source**.
_Avoid_: Cell, tile, pane, window

**Output**:
The single finished video produced from one or more **Sources**.
_Avoid_: Final video, result, export, composite

**Project**:
The saved set of **Sources** and settings that produces one **Output**.
_Avoid_: Session, workspace, job

**Audio Source**:
The one **Source** whose sound is used in the **Output**.
_Avoid_: Audio track, sound file, master audio

**Draft**:
A small, low-quality render of the whole **Output**, made only for checking it in motion.
_Avoid_: Preview video, proxy, test render

**Overlay**:
Text or an image drawn on top of the **Output** as a whole.
_Avoid_: Watermark, caption, label

### Layout

**Row**:
A horizontal run of **Panels** that all share one height.
_Avoid_: Line, strip, side by side group

**Column**:
A vertical run of **Panels** that all share one width.
_Avoid_: Stack

**Bars**:
Black areas inside a **Panel** left over when a **Source** is scaled to fit without distortion and its shape does not match the **Panel**.
_Avoid_: Letterbox, padding, gap

**Crop Hint**:
The amount of width or height a **Source** would need to lose to fill its **Panel** exactly, with no **Bars**.
_Avoid_: Auto crop, fit suggestion

**Preview**:
A still image of the **Output** showing one frame from each **Source**, scaled and positioned in its **Panel**.
_Avoid_: Thumbnail, snapshot

### Speed

**Record Rate**:
The number of frames per second a **Source** captured of the real world.
_Avoid_: Capture fps, shooting speed, fps

**Playback Rate**:
The number of frames per second a **Source** file plays at.
_Avoid_: File fps, frame rate, fps

**Source Speed**:
How fast a **Source** file shows the real world, equal to its **Playback Rate** divided by its **Record Rate**, where 1 is real time.
_Avoid_: Slow-mo factor, time scale

**Output Speed**:
How fast the **Output** shows the real world, where 1 is real time.
_Avoid_: Playback speed, final speed

**Output Rate**:
The number of frames per second in the **Output** file.
_Avoid_: Output fps, frame rate

**Frame Hint**:
For one **Source** at the current **Output Speed** and **Output Rate**, how many of its frames are dropped or how many times each is held.
_Avoid_: Frame loss, resample report

### Time alignment

**Event Time**:
Time as it passed in the real world, measured from the **Sync Event**, shared by every **Source** regardless of its **Source Speed**.
_Avoid_: Real time clock, master clock, timeline

**Sync Event**:
A real-world moment that is visible in every **Source** being combined.
_Avoid_: Marker, cue

**Sync Point**:
The timestamp within one **Source** at which the **Sync Event** is seen.
_Avoid_: Sync time, sync offset, timestamp

**Lead-in**:
The length of **Output** running time between the start of the **Output** and the **Sync Event**.
_Avoid_: Start offset, start time, pre-roll

**Lead-out**:
The length of **Output** running time between the **Sync Event** and the end of the **Output**.
_Avoid_: End offset, end time, duration

**Gap**:
A stretch of the **Output** during which a **Source** has no footage to show, rendered as black in its **Panel**.
_Avoid_: Padding, filler, freeze

## Relationships

- A **Project** produces exactly one **Output** and refers to its **Sources** by file location; it never contains video data
- A **Project** is saved automatically after every change
- A **Draft** covers the same running time as the **Output** and is thrown away; it is never the deliverable
- The **Preview** checks one instant; the **Draft** checks motion, such as drift from a wrong **Record Rate**
- A **Project** whose **Source** file has moved keeps that **Source**'s settings until the file is located again
- An **Output** is built from one or more **Sources**; a single **Source** is not a separate mode
- Each **Source** fills exactly one **Panel**
- Each **Source** has exactly one **Sync Point**, and its own crop, rotation, and aspect ratio
- A **Source** is rotated before it is cropped, so crop amounts and the **Crop Hint** are measured on the picture as it appears after rotation
- A **Sync Point** is typed in by the user and can then be refined frame by frame; refining overwrites the typed value, and retyping discards the refinement
- **Sources** are added one at a time, and the **Preview** is refreshed after each is added
- **Sources** placed side by side form a **Row** and are matched in height
- **Sources** placed top and bottom form a **Column** and are matched in width
- In a grid, every **Row** is height matched and every **Column** is width matched
- A **Source** is never distorted to fit its **Panel**; where it cannot match both its **Row** and its **Column**, it gets **Bars**
- In the first **Row**, each **Source** sets the width of its **Column**
- In any later **Row**, the first **Source** added sets the height of that **Row**
- The order in which **Sources** are added therefore decides which ones set sizes and which ones get a **Crop Hint**
- Changing the crop of a size-setting **Source** recalculates every dependent **Panel** and **Crop Hint**
- Every other **Source** has a **Panel** of already fixed size and gets a **Crop Hint** for width (after matching the **Row** height) and for height (after matching the **Column** width)
- Each **Source** has a **Record Rate** and a **Playback Rate**, which together give its **Source Speed**
- Every **Source** is shown at the **Output Speed**, so all **Panels** move through the real event at the same rate
- The **Output Speed** defaults to the slowest **Source Speed**, at which no frame of any **Source** is dropped
- The user can override the **Output Speed** once the **Sources** are synced
- A **Source** slower than the **Output Speed** has frames dropped; a **Source** faster than the **Output Speed** has each frame held longer
- The **Output** has sound only when the **Audio Source** is real time and the **Output Speed** is real time
- Each **Source** is placed on **Event Time** using its own **Sync Point** and **Source Speed**; **Sources** are never matched to one another directly
- The **Output Speed** is chosen as the slowest **Source Speed**, real time, or a custom value
- The **Output Rate** defaults to the highest **Playback Rate** among the **Sources**
- Every **Source** gets a **Frame Hint** whenever the **Output Speed** or **Output Rate** changes
- The **Output** has exactly one **Lead-in** and one **Lead-out**, both measured from the **Sync Event**
- The **Output** running time is **Lead-in** plus **Lead-out**
- **Lead-in** and **Lead-out** are measured in **Output** running time, not **Event Time**; changing the **Output Speed** keeps the **Output** the same length and changes how much of the real event it covers
- **Overlays**, size, frame rate, quality, and file format belong to the **Output**, not to any **Source**
- The **Output** has at most one text **Overlay** and at most one image **Overlay**; each sits in one corner and lasts the whole running time
- The **Output** has at most one **Audio Source**; sound from every other **Source** is discarded, never mixed
- Only a **Source** that has sound can be the **Audio Source**; the default is the first such **Source** added, and "none" is allowed
- The **Audio Source** sound stays locked to its picture, so the **Output** is silent during that **Source**'s **Gaps**
- A **Source** with less footage before its **Sync Point** than the **Lead-in** has a **Gap** at the front
- A **Source** with less footage after its **Sync Point** than the **Lead-out** has a **Gap** at the back
- A **Gap** never shortens the **Output** and never freezes a frame

## Example dialogue

> **Dev:** "**Source** A has its **Sync Point** at 12.0 s and **Source** B at 3.0 s. With a 5 s **Lead-in**, where does B start?"
> **Domain expert:** "B only has 3 s of footage before the **Sync Event**, so its **Panel** has a 2 s **Gap** at the front, then plays from its very first frame. The **Sync Event** still lands at the 5 s mark in both **Panels**."
> **Dev:** "If I lengthen the **Lead-in** to 8 s, does the **Output** end later?"
> **Domain expert:** "No. The **Lead-out** is measured from the **Sync Event**, not from the start, so the end stays put and the **Output** just gets 3 s longer at the front."
> **Dev:** "B is only 9 s long and the **Lead-out** is 10 s. Do we hold its last frame?"
> **Domain expert:** "No. B gets a 4 s **Gap** at the back. A frozen frame would look like the scene stopped moving."
> **Dev:** "Camera A was mounted sideways. Do I rotate the **Output**?"
> **Domain expert:** "No, rotate **Source** A. Rotation and crop belong to each **Source**. The logo and the text line are **Overlays** and go on the **Output** once."
> **Dev:** "And if I only load one **Source**?"
> **Domain expert:** "Same workflow. Its **Sync Point** is just the reference time that the **Lead-in** and **Lead-out** trim around."
> **Dev:** "I add a wide **Source** to the second **Row**, under a narrow **Column**. Do we squeeze it?"
> **Domain expert:** "Never. It is scaled to fit and gets **Bars**. The **Crop Hint** tells you how much width to crop from that **Source** so the **Bars** go away."
> **Dev:** "**Source** A was recorded at 240 and plays at 60. **Source** B was recorded at 30 and plays at 30. What does the **Output** do?"
> **Domain expert:** "A has a **Source Speed** of one quarter, B is real time. By default the **Output Speed** is the slowest, one quarter. A plays as it is. B is slowed to match, so it shows 7.5 of its frames each second. It looks choppy, but no frame is dropped."
> **Dev:** "Can I play that **Output** in real time instead, so B looks normal and keeps its sound?"
> **Domain expert:** "Yes. Override the **Output Speed** to 1. A is now sped up to real time, so most of its frames are dropped. B is the **Audio Source**, it is real time, and the **Output Speed** is real time, so the sound is kept."
> **Dev:** "Is a **Gap** just **Bars** that cover the whole **Panel**?"
> **Domain expert:** "No. A **Gap** is about time: the **Source** has no footage at that moment. **Bars** are about shape: the **Source** has footage but does not fill the **Panel**."

## Flagged ambiguities

- "offset to the end time" could mean time after the start or time after the **Sync Event** — resolved: **Lead-out** is measured from the **Sync Event**.
- "video" was used for both an input file and the finished result — resolved: an input is a **Source**, the result is the **Output**.
- "black" appears in two roles — resolved: a **Gap** is missing footage in time, **Bars** are unfilled space in a **Panel**.
- "user sync time" suggested a typed value stored apart from the **Sync Point** — resolved: there is one value. The typed time is the **Sync Point**, and frame stepping edits it in place.
- "fps" was used for both capture and playback — resolved: **Record Rate** is capture, **Playback Rate** is the file.
- **Lead-in** and **Lead-out** could be measured in **Event Time** or in **Output** running time — resolved: **Output** running time.
- "preview" could mean a still image or a quick video — resolved: the **Preview** is a still image, the **Draft** is a quick video.
