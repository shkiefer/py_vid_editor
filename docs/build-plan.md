# Build plan

Agreed build order and the decisions that are not domain language. Domain terms live in `../CONTEXT.md`; hard-to-reverse decisions live in `adr/`.

## Slices

Each slice ends with something runnable.

1. **Environment** (done) — `uv` project on Python 3.13, MoviePy 2.x, Streamlit, a bundled open font, git repository, and a smoke test that MoviePy can read video, draw text, and encode MP4 with sound.
2. **One Source, end to end** (done) — Browse for a file, type a Sync Point, set Lead-in and Lead-out, rotate and crop, see the Preview, render the Output.
3. **Overlays** (done) — one text Overlay and one image Overlay.
4. **Project file** (done) — save, reopen, autosave.
5. **Several Sources in one Row** (done) — height matching, Gaps, Audio Source.
6. **Frame stepper** (done) — refine each Sync Point frame by frame.
7. **Speed** — Record Rate, Output Speed, Output Rate, Frame Hint.
8. **Draft render.**
9. **Column, then grid** — width matching, Bars, Crop Hint.

## Decisions

- **Library**: MoviePy 2.x. Text is drawn with Pillow, so ImageMagick is not needed. ffmpeg comes bundled through `imageio-ffmpeg`.
- **Fonts**: open-licensed font files kept in `assets/fonts/`. Nothing depends on fonts installed in Windows.
- **Input**: local file paths with a native Browse dialog. No uploader. See `adr/0001`.
- **Timing**: every Source is placed on Event Time. See `adr/0002`.
- **Sync Point entry**: typed from an external viewer, then optionally refined with a frame stepper that overwrites the typed value. No in-app player.
- **Frame stepper**: four buttons under each Sync Point move it by 1 or 10 frames of that Source's file and overwrite the typed value. A stepped Sync Point is stored in whole milliseconds, up to 1 ms after its frame begins and never on the boundary, so rounding cannot show the frame before. The screen reports which frame the Sync Point is in and the file times that frame covers. Stepping moves the Preview to the Sync Event, and with several Sources the Preview can show one Source alone.
- **One frame at a time**: a Source's aspect override, rotation, crop and resize are applied by one function to one frame. The Preview reads only the frames it shows and edits them with that function; the rendered Output uses the same function, so the two cannot differ. Panel sizes are plain arithmetic and read no frame.
- **Stepping back**: going back in a file restarts ffmpeg, so it is restarted 12 frames early and the frames lately read are kept (up to 200 MB) for the next steps back.
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
- **Project file**: plain readable text (JSON), stored where the user chooses, holding Source paths and all settings, including the Output folder and file name and the settings of an Overlay that is switched off.
- **Saving**: a Project has no file until Save Project as gives it one. From then on every change is written to that file, including a setting the Preview rejects and changes made while a Source file is missing. The file is replaced in one step, so a failed save never leaves half a file.
- **Opening**: a setting the file does not mention takes its usual starting value, so older files still open. A value that cannot be used stops the file from opening and names the value.
- **Moved Source**: when a Source file is not found, that Source's settings are kept until the file is located; they are then applied to it and the new location is saved. The other Sources stay usable, but there is no Preview until every Source is found.
- **Adding and removing Sources**: each Source added goes to the right-hand end of the Row, and any Source can be removed. New Project clears the screen and lets go of the Project file without changing it. Changing a Source's file path keeps its settings, which is how a moved file is located; a different video is added as a new Source.
- **Row height**: the first Source sets the Row height, after its own resize. Every other Source is scaled to that height, so its own resize is switched off. With no Output width the first Source is not scaled at all. Each Source is scaled once, straight to the size of its Panel, and Panel edges are rounded one by one so the widths add up to an even Output width.
- **Joining Panels**: Panels are joined side by side as plain arrays rather than layered as MoviePy clips.
- **Audio Source choice**: the first Source with sound, until the user picks another or "No sound". The Project file stores it as a Source number counted from 1.
- **Output Rate**: left empty it follows the highest Playback Rate among the Sources.
- **Project file format 2** holds several Sources and the Audio Source. Format 1 files still open.
- **Draft**: written to a temporary folder and replaced each time. Both Draft and full render show progress.
- **Code shape**: timing and layout arithmetic are plain functions with automated tests, kept apart from the Streamlit screens.

## Known limits

- **Rotation by an angle that is not a quarter turn is slow.** On a 1080p Source it costs roughly 110 ms per frame, against roughly 10 ms for a plain, cropped, or quarter-turned Source. The cost is in Pillow's image rotation. OpenCV would cut it to a few milliseconds but adds a dependency; not adopted yet.
- **Scaling to an Output width costs roughly 40 ms per frame at 1080p**, also in Pillow.
- **Each Source scaled to fit its Panel costs roughly 40 ms per frame at 1080p.** Two 1080p Sources in a 1280 wide Output took about 90 ms per frame, so a 7 s Output at 60 frames per second rendered in about 40 s.

- **The Preview at the Sync Event shows exactly the frame a stepped Sync Point names.** The rendered Output takes a frame every 1 / Output Rate seconds from its start, so it shows that same frame at the Sync Event only when the Lead-in is a whole number of Output frames.
- **A screen update takes about 0.25 s with two 1080p Sources** (it was 1.7 s before slice 6). About one step back in thirteen takes 0.8 s while ffmpeg restarts.
- **A mono Source gives a stereo Output** with each channel 3 dB lower, which is the standard conversion.

## Open decisions

- **OpenCV for rotation.** It would remove the rotation cost above but adds a dependency.
- **HDR colour.** iPhone HDR footage is converted to standard colour without tone mapping. Accepted as it looks on the test recording.
- **Unreadable file message.** It includes a few lines of ffmpeg output and could be shortened.

## Deferred

- Text label on each Panel.
- More than one text or image Overlay, timed Overlays, colour choices.
- Draft of a time window only.
- Hosting for other users (needs upload handling).
- Formats other than MP4.
