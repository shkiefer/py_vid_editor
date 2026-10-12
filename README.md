# Video editor

A local tool for trimming, cropping, and annotating videos, and for combining several videos of the same event into one time-aligned Output.

- `CONTEXT.md` defines the vocabulary used throughout the code and screens.
- `docs/build-plan.md` lists the build order, which is complete, the decisions made along the way, the known limits and what was deferred.
- `docs/adr/` records the decisions that would be costly to change.

## Run

```
uv sync
uv run streamlit run streamlit_app.py
```

The app only listens on this computer. It reads Source files by path and writes the Output to a folder you choose.

## Use

1. Add each Source by path or with Browse. Each gets a Panel at the right-hand end of Row 1. The Layout section lists the Panels: type a Panel's width, height and Row, reorder them, or add an empty one and move a Source into it from the Source's tab.
2. Type each Source's Sync Point, the time in that file at which the shared Sync Event is seen, and refine it with the frame buttons. The Preview shows every Source at the same moment.
3. Set the Lead-in and Lead-out, which trim the Output around the Sync Event, and rotate and crop each Source. A Source is fitted inside its Panel unless you type a resize width or press one of the scale-to-Panel buttons. Where it does not fill its Panel, the Crop Hint says how much to crop.
4. For slow motion or timelapse, give the Source its Record Rate and choose the Output Speed. The Frame Hint says which frames are held or dropped.
5. Switch on the text or image Overlay if wanted.
6. Make a Draft, a quick small render around the Sync Event, to check the sync in motion. Then render the Output.

Save Project as keeps every setting in a readable JSON file, which is then updated after every change.

## Test

```
uv run pytest
```
