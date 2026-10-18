# Video editor

A local tool for trimming, cropping, and annotating videos. It has two workflows, chosen with the "Sequence / Synced grid" switch at the top of the page:

- **Sequence**: clips one after another in one Panel, with cuts, fades through black or crossfades between them.
- **Synced grid**: several videos of the same event side by side, time-aligned on one Sync Event.

- `CONTEXT.md` defines the vocabulary used throughout the code and screens.
- `docs/build-plan.md` lists the build order, which is complete, the decisions made along the way, the known limits and what was deferred.
- `docs/adr/` records the decisions that would be costly to change.

## Run

```
uv sync
uv run streamlit run streamlit_app.py
```

The app only listens on this computer. It reads Source files by path and writes the Output to a folder you choose.

## Use a Synced grid

1. Add each Source by path or with Browse. Each gets a Panel at the right-hand end of Row 1. The Layout section lists the Panels: type a Panel's width, height and Row, reorder them, or add an empty one and move a Source into it from the Source's tab.
2. Type each Source's Sync Point, the time in that file at which the shared Sync Event is seen, and refine it with the frame buttons. The Preview shows every Source at the same moment.
3. Set the Lead-in and Lead-out, which trim the Output around the Sync Event, and rotate and crop each Source. A Source is fitted inside its Panel unless you type a resize width or press one of the scale-to-Panel buttons. Where it does not fill its Panel, the Crop Hint says how much to crop.
4. For slow motion or timelapse, give the Source its Record Rate and choose the Output Speed. The Frame Hint says which frames are held or dropped.
5. Switch on the text or image Overlay if wanted.
6. Make a Draft, a quick small render around the Sync Event, to check the sync in motion. Then render the Output.

## Use a Sequence

1. Switch to Sequence and add each clip. The order of the Source tabs is the play order; move a clip with the buttons in its tab.
2. Type the Sequence Panel's width and height, and give each clip a Start Point, an End Point and, for slow or fast motion, a Play Speed. The timing table gives each clip's place in the Output and the total running time.
3. Set each clip's "After this Source" to a cut, a fade through black or a crossfade, with a length, and set the fade in and fade out for the whole Sequence. The captions give each Transition's times; a crossfade shortens the Output by its length.
4. Move the Preview slider to check any moment, make a Draft around a Join, then render the Output.

## Add music or other sound

In either workflow, the Sound box under the Output settings sets the Sources' volume and adds Audio Tracks: any file with sound, laid over the Output. Give each one the Output time it starts at, how far into its file to begin, its volume and the fade-out used when the Output ends first. Each one says where it plays. The Mix Hint gives the loudest point of the mix and warns when it clips.

## Projects

Save Project as keeps every setting in a readable JSON file, which is then updated after every change.

## Test

```
uv run pytest
```
