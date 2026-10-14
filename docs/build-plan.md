# Build plan

The build order and the decisions that are not domain language. Domain terms live in `../CONTEXT.md`; hard-to-reverse decisions live in `adr/`.

## Slices

Each slice ends with something runnable.

1. **Environment** (done) — `uv` project on Python 3.13, MoviePy 2.x, Streamlit, a bundled open font, git repository, and a smoke test that MoviePy can read video, draw text, and encode MP4 with sound.
2. **One Source, end to end** (done) — Browse for a file, type a Sync Point, set Lead-in and Lead-out, rotate and crop, see the Preview, render the Output.
3. **Overlays** (done) — one text Overlay and one image Overlay.
4. **Project file** (done) — save, reopen, autosave.
5. **Several Sources in one Row** (done) — height matching, Gaps, Audio Source.
6. **Frame stepper** (done) — refine each Sync Point frame by frame.
7. **Speed** (done) — Record Rate, Output Speed, Output Rate, Frame Hint.
8. **Draft render** (done) — a quick, small render around the Sync Event, written beside the Output.
9. **Column, then grid** (done) — width matching, Bars, Crop Hint.
10. **Layout of typed Panels** (done) — Panels set up first, each with its own width, height and Row; Sources assigned to Panels, still one to a Panel; every Source with its own resize and the two scale-to-Panel buttons; the Audio Panel; a new Project file format. An existing Project opens with the same Output as before.
11. **Sequence, with cuts** — the Sequence / Synced grid switch; Sources in play order in one typed Panel, each with a Start Point, an End Point and a Play Speed; a timing table, a Preview at any running time, and the Render; a new Project file format.
12. **Transitions** — at each Join a cut, a fade through black or a crossfade, each with its own length; a fade in at the start and out at the end; sound that fades and crossfades with the picture; a Draft around a chosen Join.

## Decisions

### Foundations

- **Library**: MoviePy 2.x. Text is drawn with Pillow, so ImageMagick is not needed. ffmpeg comes bundled through `imageio-ffmpeg`.
- **Fonts**: open-licensed font files kept in `assets/fonts/`. Nothing depends on fonts installed in Windows.
- **Input**: local file paths with a native Browse dialog. No uploader. See `adr/0001`.
- **Timing**: every Source is placed on Event Time. See `adr/0002`.
- **Code shape**: timing and layout arithmetic are plain functions with automated tests, kept apart from the Streamlit screens.
- **One frame at a time**: a Source's aspect override, rotation, crop and resize are applied by one function to one frame. The Preview reads only the frames it shows and edits them with that function; the rendered Output uses the same function, so the two cannot differ. Panel sizes are plain arithmetic and read no frame.

### Sources

- **Adding and removing Sources**: each Source added gets a new Panel at the right-hand end of Row 1, unless an empty Panel is chosen for it beside the Add box. Removing a Source leaves its Panel in place, empty. Removing the last Source clears the layout. Changing a Source's file path keeps its settings, which is how a moved file is located; a different video is added as a new Source.
- **Per-Source geometry**: aspect ratio override (advanced, off by default), then rotation (any angle, with quarter-turn buttons), then crop (pixels per edge, measured after rotation), then resize (a width in pixels; the height follows).
- **Layout section**: lists the Panels in order, each with its Row, width and height, buttons to list it earlier or later (left or right in its Row) and to remove it when empty, and "Add a Panel", which puts an empty Panel beside the last one at its Row's height and the same width. See `adr/0003`.
- **A new Panel's size**: its Row's height and the width that fits its Source, rounded to an even number; the first Panel of all takes its Source's own size. After that it changes only when retyped.
- **Typed sizes and the Output**: with no Output width the Output is exactly the typed Panels, less an odd pixel trimmed from the right or bottom. An Output width scales the whole layout, and the screen then gives each Panel's size in the Output beside its typed one. Edges are rounded one by one, so Panels that touch as typed touch in the Output.
- **Placing a Source**: each Source's tab has a Panel picker. It offers the Source's own Panel and any empty one. Until slice 11 a Panel holds one Source.
- **A Source in its Panel**: with its resize left empty it is fitted inside. With a width typed it is that wide, in typed pixels. Either way it is centred, with Bars where it is smaller than the Panel and an even cut where it is larger. A Source sized to within a pixel of its typed Panel takes the whole Panel, so the rounding of an Output width never leaves a hairline Bar.
- **Scale to Panel buttons**: "Scale width to Panel" and "Scale height to Panel" fill in the Source's resize width once. A later change to the crop or to the Panel leaves that width as typed, so the button is pressed again.
- **Crop Hint feedback**: beside each Source's resize the screen gives its Panel's size, the size the Source is scaled to, its Bars and what the Panel cuts off. A fitted Source with Bars is told how much to crop to fill the Panel. A Source larger than its Panel is told how many of its own pixels are hidden, so the crop can be typed to choose which part is kept.
- **Joining Panels**: the part of each Source its Panel shows is placed on a black frame as a plain array rather than layered as a MoviePy clip. The black is the Bars, every empty Panel, and whatever the Panels leave of the Output.
- **Moved Source**: when a Source file is not found, that Source's settings are kept until the file is located; they are then applied to it and the new location is saved. The other Sources stay usable, but there is no Preview until every Source is found.

### Sync and timing

- **Sync Point entry**: typed from an external viewer, then optionally refined with a frame stepper that overwrites the typed value. No in-app player.
- **Frame stepper**: four buttons under each Sync Point move it by 1 or 10 frames of that Source's file and overwrite the typed value. A stepped Sync Point is stored in whole milliseconds, up to 1 ms after its frame begins and never on the boundary, so rounding cannot show the frame before. The screen reports which frame the Sync Point is in and the file times that frame covers. Stepping moves the Preview to the Sync Event.
- **Stepping back**: going back in a file restarts ffmpeg, so it is restarted 12 frames early and the frames lately read are kept (up to 200 MB) for the next steps back.
- **Timing feedback**: a table under the Preview shows each Source's start and end file times, its Gap lengths, its Source Speed and its Frame Hint.

### Speed

- **Settings that may be left empty** (Record Rate, Resize to width, Output width, Output Rate) can be emptied again after a number has been typed. Streamlit needs `value=None` on each for that; without it an emptied field takes its smallest allowed value.
- **Record Rate entry**: left empty, a Source's Record Rate is its Playback Rate, which makes it real time. A Record Rate within 0.5% of the Playback Rate counts as the same rate, so 30 typed for a 29.97 file is still real time and keeps its sound.
- **Output Speed choices**: slowest Source (default), real time, or custom. The custom value is kept when another choice is in use.
- **Output Rate**: left empty it follows the highest Playback Rate among the Sources.
- **Speed feedback**: each Source reports its Source Speed and its Frame Hint; the Output reports how much of the real event its running time shows. When the Output loses its sound to a speed, a warning beside the Audio Source says which speed.
- **Frame Hint wording**: "every frame shown once", "each frame held for 8 Output frames", or "1 frame in 4 shown, 75% dropped". It counts Output Rate as well as Output Speed, so a real-time 29.97 Source in a 60 Output is "held for 2 Output frames".

### Preview

- **Preview time**: the Preview shows every Source at its Sync Point by default, with a control to move earlier or later.
- **Preview size**: the Preview is shrunk to fit 1280 by 800 pixels before it is sent to the browser, and shown no taller than 55% of the window height.
- **Show one Source**: with several Sources the Preview can show one Source's Panel alone, Bars included, at a larger size.
- **Empty Panels are named above the Render button**, since one left by mistake shows as black in the Output.

### Output

- **Export**: MP4 with H.264 only. Three named quality levels. One Output width setting; height follows from the layout; both rounded to even numbers.
- **Output location**: written to a user-chosen folder, not offered as a browser download.
- **Audio Panel choice**: the first Panel whose Source has sound, until the user picks another or "No sound". The Project file stores it as a Panel number counted from 1.
- **Draft**: its main use is checking that the Sync Point renders as meant. It has its own Lead-in and Lead-out (2 s each to start), its own width (640 to start, never wider than the Output) and sound only when its box is ticked. The Output Rate, the speeds and the Overlays are the Output's. It is scaled with a quicker, rougher resize and encoded fast at low quality, and the text Overlay shrinks with the picture.
- **Draft file**: written to the Output folder under the Output's file name with `_draft` added, and replaced each time without asking. It never replaces a Source file. It is not played in the app; an Open Draft button hands it to the program Windows uses for MP4 files. The Draft settings are saved in the Project file.
- **Draft feedback**: the screen says how large and how long the Draft will be, where the Sync Event falls in it, whether it has sound and why not, how long it took, and when settings have changed since it was made. Both Draft and full render show progress.

### Overlays

- **Overlays**: text is white on a half-transparent black box with size and corner. Image is any file via Browse, plus a quick-pick list from `assets/logos/`, with corner, width as a percentage of the Output, and background opacity. Both default to off. Same-corner collision gives a warning, and the text is drawn over the image.
- **Overlay sizes**: both are measured on the finished Output, after any Output width scaling. Text size is in Output pixels. The image width is the width of its box, padding included, as a percentage of the Output width. Each box sits flush in its corner, and one larger than the Output is cut off with a warning.
- **Overlay drawing**: each Overlay is drawn once as a small picture and stamped onto every frame, rather than layered as a MoviePy clip. Both together cost roughly 5 ms per frame at 1080p.
- **Overlay settings belong to the Output**: adding or removing a Source leaves them as they are. New Project, or removing the last Source, puts them back to their starting values.

### Project file

- **Project file**: plain readable text (JSON), stored where the user chooses, holding Source paths and all settings, including the Output folder and file name and the settings of an Overlay that is switched off.
- **Saving**: a Project has no file until Save Project as gives it one. From then on every change is written to that file, including a setting the Preview rejects and changes made while a Source file is missing. The file is replaced in one step, so a failed save never leaves half a file.
- **Opening**: a setting the file does not mention takes its usual starting value, so older files still open. A value that cannot be used stops the file from opening and names the value.
- **New Project** clears the screen and lets go of the Project file without changing it.
- **Format 3** lists the Panels, says which Panel each Source is in, and names the Audio Panel. It also holds each Record Rate, the Output Speed and the Draft settings.
- **Older files still open.** Format 1 held one Source; format 2 held several, each with a Row. Each Source of such a file gets a Panel of the size the old rules gave it, worked out once every Source file is open, and only the first Source keeps its typed resize. A Row the old layout left black at its right-hand end gets an empty Panel there. The Output is then the same as before, except that with an Output width a boundary between Panels can move by one pixel. The file is rewritten in format 3 at the first save.

### Agreed for slices 11 and 12, not yet built

The terms are in `../CONTEXT.md`: Synced grid, Sequence, Join, Transition, Play Speed, Start Point, End Point. Why the two workflows are kept apart is in `adr/0004-two-workflows-do-not-mix.md`.

- **The switch** (slice 11): "Sequence / Synced grid" at the top of the page, saved in the Project. Switching keeps the Sources and their picture settings. The grid's Sync Points, Record Rates, Panels, Lead-in, Lead-out, Output Speed, Audio Panel and Draft are hidden in a Sequence but kept and saved, and the Sequence's settings likewise in a grid.
- **Play order** (slice 11): the order of the Sources, with buttons in each Source's tab to move it earlier or later. This also reorders the tabs of a grid.
- **The Sequence Panel** (slice 11): one width and height, typed, starting at the first Source's size after its rotation and crop. An Output width scales it as it scales a grid.
- **Start Point, End Point and Play Speed** (slice 11): file times, the whole file unless set, with frame buttons like the Sync Point's. Play Speed is a multiplier, 1 unless set; a Source not at 1 is silent.
- **Timing table** (slice 11): one row per Source with its Output start and end, time on show, file stretch used, Frame Hint and whether it has sound (and why not), and the total running time.
- **Preview** (slice 11): a slider over the running time, and a way to jump to the start of any Source.
- **Transitions** (slice 12): one per Join, a cut, a fade through black or a crossfade, with a length; a fade from black at the start and to black at the end. A fade through black of length L is L/2 out and L/2 in. A crossfade mixes the two sounds over its length.
- **Sequence Draft** (slice 12): a rough render a chosen number of seconds either side of a chosen Join.
- **Project file** (slice 11): format 4 adds the workflow, the Sequence Panel and each Source's Start Point, End Point and Play Speed. A file without a workflow opens as a Synced grid.

## Known limits

- **Rotation by an angle that is not a quarter turn is slow.** On a 1080p Source it costs roughly 110 ms per frame, against roughly 10 ms for a plain, cropped, or quarter-turned Source. The cost is in Pillow's image rotation.
- **Each Source scaled to fit its Panel costs roughly 40 ms per frame at 1080p**, also in Pillow. Two 1080p Sources in a 1280 wide Output took about 90 ms per frame, so a 7 s Output at 60 frames per second rendered in about 40 s.
- **A screen update takes about 0.25 s with two 1080p Sources** (it was 1.7 s before slice 6). About one step back in thirteen takes 0.8 s while ffmpeg restarts.
- **The Preview at the Sync Event shows exactly the frame a stepped Sync Point names.** The rendered Output takes a frame every 1 / Output Rate seconds from its start, so it shows that same frame at the Sync Event only when the Lead-in is a whole number of Output frames.
- **A mono Source gives a stereo Output** with each channel 3 dB lower, which is the standard conversion.
- **A Draft of two 1080p Sources takes about 2 to 3 s for each second of a 60 frames per second Output**, against about 11 s at full size. Most of what is left is reading the Source files, so a smaller Draft is hardly quicker: 480 wide saved under 10% against 640.
- **A large layout is slow at its typed size.** Four 1080p-sized Panels in two Rows of two gave a 2528 by 4492 Output under the old rules, and a 2 s Draft of it at 640 wide took about 11 s. An Output width brings the size down.
- **The first Source still starts the layout.** A Panel cannot be made before any Source has been added.
- **The app does not reopen the last Project on start.** Open Project is used each time.

## Open decisions

- **OpenCV for rotation and scaling.** It would cut both costs above to a few milliseconds per frame but adds a dependency.
- **HDR colour.** iPhone HDR footage is converted to standard colour without tone mapping. Accepted as it looks on the test recording.
- **Unreadable file message.** It includes a few lines of ffmpeg output and could be shortened.

## Deferred

- Text label on each Panel.
- More than one text or image Overlay, timed Overlays, colour choices.
- Hosting for other users (needs upload handling).
- Formats other than MP4.
