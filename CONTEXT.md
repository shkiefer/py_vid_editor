# Video Editor

A local tool for trimming, cropping, and annotating videos, and for combining several videos of the same real-world event into one time-aligned output.

## Language

### Composition

**Source**:
One input video file.
_Avoid_: Clip, input, video

**Panel**:
An area of the **Output** that shows one **Source** at a time, or is empty. A **Synced grid** has as many as its layout sets up; a **Sequence** has exactly one.
_Avoid_: Cell, tile, pane, window

**Output**:
The single finished video produced from one or more **Sources**.
_Avoid_: Final video, result, export, composite

**Project**:
The saved set of **Sources** and settings that produces one **Output**.
_Avoid_: Session, workspace, job

**Audio Panel**:
In a **Synced grid**, the one **Panel** whose sound is used in the **Output**, taken from the **Source** in it.
_Avoid_: Audio Source, audio track, sound file, master audio

**Draft**:
A small, low-quality render of a stretch of the **Output**, made only for checking it in motion: around the **Sync Event** in a **Synced grid**, or around a chosen **Join** (or the start) in a **Sequence**.
_Avoid_: Preview video, proxy, test render

**Synced grid**:
The workflow that shows the same real-world event from several **Sources** at once, each in its own **Panel**, aligned on the **Sync Event**.
_Avoid_: Grid mode, multicam, split screen

**Sequence**:
The workflow that shows **Sources** one after another in the **Output**'s one **Panel**, in a chosen play order, with no **Sync Event**.
_Avoid_: Playlist, track, reel, montage

**Join**:
The place in a **Sequence** where one **Source** hands over to the next in play order.
_Avoid_: Cut point, edit point, splice

**Transition**:
What happens at a **Join**: a cut, a fade through black, or a crossfade, each but the cut with its own length. Also a fade from black at the very start of a **Sequence** or to black at its very end.
_Avoid_: Dissolve, wipe, effect

**Play Speed**:
In a **Sequence**, how much faster or slower than its file a **Source** is played, where 1 is as the file plays.
_Avoid_: Speed factor, slow-mo, rate

**Overlay**:
Text or an image drawn on top of the **Output** as a whole.
_Avoid_: Watermark, caption, label

### Layout

**Row**:
A horizontal run of **Panels**, side by side.
_Avoid_: Line, strip, side by side group, Column

**Bars**:
Black areas inside a **Panel** beside a **Source** that, after its own crop and resize, is narrower or shorter than the **Panel**.
_Avoid_: Letterbox, padding, gap

**Crop Hint**:
The amount of width or height a **Source** would need to lose to fill its **Panel** exactly: what to crop to be rid of **Bars**, or what the **Panel** is cutting off.
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

**Start Point**:
The timestamp within one **Source** before which none of its footage is used; the start of the file unless set.
_Avoid_: In point, trim start, start time

**End Point**:
The timestamp within one **Source** after which none of its footage is used; the end of the file unless set.
_Avoid_: Out point, trim end, end time

**Lead-in**:
The length of **Output** running time between the start of the **Output** and the **Sync Event**.
_Avoid_: Start offset, start time, pre-roll

**Lead-out**:
The length of **Output** running time between the **Sync Event** and the end of the **Output**.
_Avoid_: End offset, end time, duration

**Gap**:
A stretch of the **Output** during which a **Panel** has no footage to show, rendered as black.
_Avoid_: Padding, filler, freeze

## Relationships

- A **Project** produces exactly one **Output** and refers to its **Sources** by file location; it never contains video data
- A **Project** is saved automatically after every change, once the user has chosen where to keep it
- A **Draft** is thrown away; it is never the deliverable
- A **Draft** has its own **Lead-in**, **Lead-out** and width, and has sound only when asked
- A **Draft** has the same **Output Rate**, **Output Speed** and **Overlays** as the **Output**, so the **Sync Event** looks in it as it will in the **Output**
- The **Preview** checks one instant; the **Draft** checks motion, such as a wrong **Sync Point** or drift from a wrong **Record Rate**
- A **Project** whose **Source** file has moved keeps that **Source**'s settings until the file is located again
- An **Output** is built from one or more **Sources**; a single **Source** is not a separate mode
- **Panels** are set up first, each in a **Row**; every **Source** is then assigned to exactly one **Panel**
- A **Panel** has its own width and height, typed in the layout; no **Source** sets the size of a **Panel**
- Every **Source** has its own resize, and can be scaled in one step so that its width, or its height, equals its **Panel**'s
- A **Source** is centred in its **Panel**: where it is smaller it gets **Bars**, and where it is larger the overflow is cut off evenly from both sides
- A **Source** with no resize set is scaled to fit inside its **Panel**
- In a **Synced grid** a **Panel** holds at most one **Source**; several **Sources** share a **Panel** only in a **Sequence**
- A **Panel** can be set up with no **Source** in it; an empty **Panel** is black and cannot be the **Audio Panel**
- Removing a **Source** leaves its **Panel** in place; a **Panel** can be removed only when it is empty
- Adding a **Source** makes a new **Panel** for it at the end of the first **Row**, unless it is assigned to an empty one; it can then be moved into another **Panel**
- A new **Panel** starts at the height of its **Row** and the width that fits its **Source** at that height; the first **Panel** of all starts at its **Source**'s own size
- Once a **Panel** exists its size changes only when it is retyped, so cropping or rotating a **Source** never resizes a **Panel**
- Each **Source** has its own crop, rotation, resize, and aspect ratio, used in both workflows
- A **Source** is rotated before it is cropped, so crop amounts and the **Crop Hint** are measured on the picture as it appears after rotation
- A **Source** is resized after it is cropped, to a chosen width with the height following, so crop amounts never need retyping and the resize never distorts
- A **Sync Point** is typed in by the user and can then be refined frame by frame; refining overwrites the typed value, and retyping discards the refinement
- **Sources** are added one at a time, and the **Preview** is refreshed after each is added
- Each **Panel** is given a **Row**; within a **Row**, **Panels** run left to right in their listed order
- A **Row** is as tall as its tallest **Panel** and as wide as its **Panels** added together; a shorter **Panel** sits at the top of its **Row** with black below
- The **Output** is as wide as its widest **Row**; a narrower **Row** is centred with black either side
- **Panels** in different **Rows** need not line up with one another
- A **Source** is never distorted to fit its **Panel**
- **Bars** are split evenly either side of the **Source**
- The **Crop Hint** is measured in the same pixels as the crop, on the picture after rotation and crop; a **Source** that already fills its **Panel** has none
- Each **Source** has a **Record Rate** and a **Playback Rate**, which together give its **Source Speed**
- A **Source** whose **Record Rate** is not given is real time: its **Record Rate** is taken to be its **Playback Rate**
- Every **Source** is shown at the **Output Speed**, so all **Panels** move through the real event at the same rate
- The **Output Speed** defaults to the slowest **Source Speed**, at which no frame of any **Source** is dropped
- The user can override the **Output Speed** once the **Sources** are synced
- A **Source** slower than the **Output Speed** has frames dropped; a **Source** faster than the **Output Speed** has each frame held longer
- The **Output** has sound only when the **Output Speed** is real time, and then only while the **Source** the **Audio Panel** is showing is real time and has sound
- Each **Source** in a **Synced grid** is placed on **Event Time** using its own **Sync Point** and **Source Speed**; **Panels** are never matched to one another directly
- The **Output Speed** is chosen as the slowest **Source Speed**, real time, or a custom value
- The **Output Rate** defaults to the highest **Playback Rate** among the **Sources**
- Every **Source** gets a **Frame Hint** whenever the **Output Speed** or **Output Rate** changes
- The **Output** has exactly one **Lead-in** and one **Lead-out**, both measured from the **Sync Event**
- The **Output** running time is **Lead-in** plus **Lead-out**
- **Lead-in** and **Lead-out** are measured in **Output** running time, not **Event Time**; changing the **Output Speed** keeps the **Output** the same length and changes how much of the real event it covers
- **Overlays**, size, frame rate, quality, and file format belong to the **Output**, not to any **Source**
- The **Output** has at most one text **Overlay** and at most one image **Overlay**; each sits in one corner and lasts the whole running time
- An **Overlay** is sized against the finished **Output** and stays on through every **Gap**
- The **Output** has at most one **Audio Panel**; sound from every other **Panel** is discarded, never mixed
- Only a **Panel** holding a **Source** that has sound can be the **Audio Panel**; the default is the first such **Panel**, and "none" is allowed
- Sound stays locked to its picture: the **Output** is silent during the **Audio Panel**'s **Gaps**
- A **Panel** with less footage before its **Sync Point** than the **Lead-in** has a **Gap** at the front
- A **Panel** with less footage after its **Sync Point** than the **Lead-out** has a **Gap** at the back
- A **Gap** never shortens the **Output** and never freezes a frame

### The two workflows

- A **Project** is either a **Synced grid** or a **Sequence**, chosen at the top of the page and saved with it; the two never mix
- Switching a **Project** between them keeps its **Sources** with their crop, rotation, resize and aspect ratio; each workflow's own settings are kept, unused, while the other is chosen, so switching back restores them
- A **Sequence** joins a **Synced grid** only as a rendered file, added like any other **Source**
- In a **Sequence** there is no **Sync Point**, **Lead-in**, **Lead-out**, **Record Rate**, **Output Speed**, **Audio Panel** or **Gap**

### Sequence

- The play order of a **Sequence** is the order of its **Sources**, changed by moving a **Source** earlier or later
- The **Sequence**'s one **Panel** has a typed width and height, starting at the first **Source**'s size after its rotation and crop; each **Source** is fitted, resized, given **Bars** and a **Crop Hint** as in any **Panel**
- Each **Source** in a **Sequence** has a **Start Point**, an **End Point** and a **Play Speed**; it shows its file from **Start Point** to **End Point**, so its time on show is that stretch divided by its **Play Speed**
- **Start Point** and **End Point** are file times, so on a **Source** whose **Play Speed** is not 1 they are not **Output** running time
- The **Output** running time of a **Sequence** is the sum of its **Sources**' times on show, less the length of every crossfade
- A fade through black leaves the running time as it is, spending half its length fading the earlier **Source** out and half fading the later one in; a crossfade overlaps the two **Sources** it joins by its length, so the running time is shorter by that much
- Each **Source**'s setting for the **Join** after it goes with it when the play order changes; the last **Source**'s is not used
- A **Source**'s **Transitions** together are no longer than its time on show
- A crossfade is no longer than the time on show of either **Source** it joins
- Each **Source** in a **Sequence** keeps its own sound, which plays with its picture; sound from two **Sources** is mixed only during a crossfade, and a fade through black fades the sound with the picture
- A **Source** whose **Play Speed** is not 1, or that has no sound, is silent in a **Sequence**
- The **Output Rate** of a **Sequence** defaults to the highest **Playback Rate** among its **Sources**, and each **Source** gets a **Frame Hint** at its **Play Speed**

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
> **Dev:** "I put a wide **Source** in a narrow **Panel**. Do we squeeze it?"
> **Domain expert:** "Never. Left alone it is scaled to fit and gets **Bars** above and below. Scale its height to the **Panel** instead and it fills the height, with the overflow cut evenly from the left and right. Either way the **Crop Hint** gives the crop that makes it fill the **Panel** exactly."
> **Dev:** "**Source** A was recorded at 240 and plays at 60. **Source** B was recorded at 30 and plays at 30. What does the **Output** do?"
> **Domain expert:** "A has a **Source Speed** of one quarter, B is real time. By default the **Output Speed** is the slowest, one quarter. A plays as it is. B is slowed to match, so it shows 7.5 of its frames each second. It looks choppy, but no frame is dropped."
> **Dev:** "Can I play that **Output** in real time instead, so B looks normal and keeps its sound?"
> **Domain expert:** "Yes. Override the **Output Speed** to 1. A is now sped up to real time, so most of its frames are dropped. B's **Panel** is the **Audio Panel**, B is real time, and the **Output Speed** is real time, so the sound is kept."
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
