# Build plan

Agreed build order and the decisions that are not domain language. Domain terms live in `../CONTEXT.md`; hard-to-reverse decisions live in `adr/`.

## Slices

Each slice ends with something runnable.

1. **Environment** (done) — `uv` project on Python 3.13, MoviePy 2.x, Streamlit, a bundled open font, git repository, and a smoke test that MoviePy can read video, draw text, and encode MP4 with sound.
2. **One Source, end to end** (done) — Browse for a file, type a Sync Point, set Lead-in and Lead-out, rotate and crop, see the Preview, render the Output.
3. **Overlays** (done) — one text Overlay and one image Overlay.
4. **Project file** — save, reopen, autosave.
5. **Several Sources in one Row** — height matching, Gaps, Audio Source.
6. **Frame stepper** — refine each Sync Point frame by frame.
7. **Speed** — Record Rate, Output Speed, Output Rate, Frame Hint.
8. **Draft render.**
9. **Column, then grid** — width matching, Bars, Crop Hint.

## Decisions

- **Library**: MoviePy 2.x. Text is drawn with Pillow, so ImageMagick is not needed. ffmpeg comes bundled through `imageio-ffmpeg`.
- **Fonts**: open-licensed font files kept in `assets/fonts/`. Nothing depends on fonts installed in Windows.
- **Input**: local file paths with a native Browse dialog. No uploader. See `adr/0001`.
- **Timing**: every Source is placed on Event Time. See `adr/0002`.
- **Sync Point entry**: typed from an external viewer, then optionally refined with a frame stepper that overwrites the typed value. No in-app player.
- **Preview time**: the Preview shows every Source at its Sync Point by default, with a control to move earlier or later.
- **Timing feedback**: next to Lead-in and Lead-out, show each Source's start and end file times and its Gap lengths.
- **Per-Source geometry**: aspect ratio override (advanced, off by default), then rotation (any angle, with quarter-turn buttons), then crop (pixels per edge, measured after rotation), then resize (a width in pixels; the height follows).
- **Preview size**: the Preview is shrunk to fit 1280 by 800 pixels before it is sent to the browser, and shown no taller than 55% of the window height.
- **Output Speed choices**: slowest Source (default), real time, or custom.
- **Overlays**: text is white on a half-transparent black box with size and corner. Image is any file via Browse, plus a quick-pick list from `assets/logos/`, with corner, width as a percentage of the Output, and background opacity. Both default to off. Same-corner collision gives a warning, and the text is drawn over the image.
- **Overlay sizes**: both are measured on the finished Output, after any Output width scaling. Text size is in Output pixels. The image width is the width of its box, padding included, as a percentage of the Output width. Each box sits flush in its corner, and one larger than the Output is cut off with a warning.
- **Overlay drawing**: each Overlay is drawn once as a small picture and stamped onto every frame, rather than layered as a MoviePy clip. Both together cost roughly 5 ms per frame at 1080p.
- **Overlay settings outlive the Source**: choosing a new Source resets the Source and Output settings but leaves the Overlays as they are.
- **Export**: MP4 with H.264 only. Three named quality levels. One Output width setting; height follows from the layout; both rounded to even numbers.
- **Output location**: written to a user-chosen folder, not offered as a browser download.
- **Project file**: plain readable text, stored where the user chooses, holding Source paths and all settings.
- **Draft**: written to a temporary folder and replaced each time. Both Draft and full render show progress.
- **Code shape**: timing and layout arithmetic are plain functions with automated tests, kept apart from the Streamlit screens.

## Known limits

- **Rotation by an angle that is not a quarter turn is slow.** On a 1080p Source it costs roughly 110 ms per frame, against roughly 10 ms for a plain, cropped, or quarter-turned Source. The cost is in Pillow's image rotation. OpenCV would cut it to a few milliseconds but adds a dependency; not adopted yet.
- **Scaling to an Output width costs roughly 40 ms per frame at 1080p**, also in Pillow.
- **One Source keeps its own sound** until the Audio Source selector arrives in slice 5.

- **A trim that starts partway through a file can show the Source frame one before the expected one.** Frame-exact Sync Points arrive with the frame stepper in slice 6.
- **A mono Source gives a stereo Output** with each channel 3 dB lower, which is the standard conversion.

## Open decisions

- **Screen speed.** Each setting change takes 1 to 2 s on 1080p footage, because every change rebuilds the clip chain and MoviePy re-reads the first frame, which restarts ffmpeg. It will matter for the frame stepper in slice 6.
- **OpenCV for rotation.** It would remove the rotation cost above but adds a dependency.
- **HDR colour.** iPhone HDR footage is converted to standard colour without tone mapping. Accepted as it looks on the test recording.
- **Unreadable file message.** It includes a few lines of ffmpeg output and could be shortened.

## Deferred

- Text label on each Panel.
- More than one text or image Overlay, timed Overlays, colour choices.
- Draft of a time window only.
- Hosting for other users (needs upload handling).
- Formats other than MP4.
