# Resume here

Status on 2026-10-12. Delete this file once slice 10 is merged.

## Where things stand

- Slices 1 to 9 are verified, committed and merged to `main` (last commit `e3c48af`).
- Slice 10 (Layout of typed Panels) is built and committed on branch `slice-10-layout` (commit `f1c6059`), not merged to `main`. All 209 automated tests pass. It has not been checked by the user, and has not been clicked through in a browser.
- Slices 11 (Sequences) and 12 (Transitions) are planned and not started. What was agreed for them is in `build-plan.md` under "Agreed for slices 11 and 12, not yet built", and the terms are in `../CONTEXT.md`.
- `adr/0003-panels-have-typed-sizes.md` records why Panels have typed sizes.

## Next step: verify slice 10

Start the app with `uv run streamlit run streamlit_app.py --server.headless true` and open http://localhost:8501, then:

1. Open `references/proj_slice_9.json` and confirm the Preview matches what it rendered before. It should open as a 1196 by 1782 Output with three Sources and a fourth, empty Panel in Row 1.
2. Retype a Panel's width or height and read the Source's caption. Try "Scale width to Panel" and "Scale height to Panel", then change the crop and confirm the typed width stays as it was.
3. Press "Add a Panel", move a Source into the empty Panel from its tab, then remove the Panel it left.
4. Change a Panel's Row, and use the arrows to swap two Panels in a Row.
5. Set an Output width and confirm each Panel shows its size in the Output under its typed size.
6. Make a Draft, render an Output, then save the Project, press F5 and open it again.

**Opening an older Project rewrites its file in the new format**, as soon as it opens. The six Projects in `references/` are still in the old format. To keep one as it is, open a copy.

What an automated comparison of the old and new layouts gave for the saved Projects:

| Project | Result |
|---|---|
| `proj_slice_4`, `_7`, `_8`, `_9` | same Output size and same position for every Source |
| `proj_slice_5`, `_6` (Output width 1080) | same Output size; the boundary between the two Panels is at 450 instead of 449 |

## Choices in slice 10 to confirm or change

- The first Source still starts the layout. A Panel cannot be added before any Source, because there is nothing to size it from.
- A new Panel's width is rounded to an even number, so Panels made by adding Sources add up to an even Output.
- A Row that an older Project left black at its right-hand end opens with an empty Panel there, which keeps the Output the same. Removing that Panel centres the Row.
- When an empty Panel exists, an "Into" picker beside the Add box sends the next Source straight into it.
- With no Output width, an odd typed total loses one pixel from the right or bottom; nothing is scaled.
- Removing the last Source clears the layout as well.

## After verification

1. Fix what the check finds, on `slice-10-layout`.
2. Mark slice 10 "(done)" in `build-plan.md`, delete this file, and commit.
3. Merge to `main` (fast-forward), delete the branch, and start slice 11 on a new one.

## Things to know

- **Restart the app after changing anything under `src/vid_editor/`.** The running server keeps the old modules.
- **Code shape after slice 10**: `layout.py` is the typed-Panel arithmetic (`panel_layout`, `picture_in`). `legacy_layout.py` is the old Source-sets-the-size arithmetic, kept only so `render.legacy_panels` can size the Panels of an older Project. On the screen, Panels have ids and their settings are kept under `pn_row_`, `pn_width_` and `pn_height_`; a Source's Panel is under `in_panel_`.
- **The test suite takes about 3.5 minutes** now, most of it the screen tests.
- **Untracked files left alone**: `assets/logos/logo_2023.png`, and in `references/` the test clips, the saved Projects `proj_slice_4.json` to `proj_slice_9.json`, and several renders and Drafts. Whether these should be tracked or ignored has not been decided.
- Open decisions that are not tied to a slice (OpenCV, HDR colour, the unreadable-file message) are in `build-plan.md`.
