# Resume here

Status on 2026-10-14. Delete this file once slice 12 is merged.

## Where things stand

- The editor now has two workflows that never mix, picked with a "Sequence / Synced grid" switch at the top of the page. Why is in `adr/0004-two-workflows-do-not-mix.md`, and the terms are in `../CONTEXT.md`. The earlier plan for several Sources in one grid Panel, with an Anchor, was dropped.
- Slices 1 to 11 are verified, committed and merged to `main`. Slice 11 is the Sequence with cuts (last commit on `main`: `f48eae0`).
- Slice 12 (Transitions) is built and committed on branch `slice-12-transitions` (commit `dcfd3d4`), not merged to `main`. All 255 automated tests pass. It has not been checked by the user, and has not been clicked through in a browser.
- No slice is planned after 12.

## Next step: verify slice 12

Start the app with `uv run streamlit run streamlit_app.py --server.headless true` and open http://localhost:8501. Press New Project, switch to Sequence, and add `references/slice_5_01.mp4` then `references/slice_6_01.mp4`. Then:

1. Set the first clip's "After this Source" to Crossfade, 1 s. Check that the timing table's total drops by 1 s, and that the caption under the setting gives the crossfade's start and end times.
2. Move the Preview slider into the crossfade. Check that the Preview shows both clips mixed and that the caption gives each one's share.
3. Change it to Fade through black, 1 s. Check that the total goes back up, and that the Preview is black at the Join.
4. Set Fade in from black and Fade out to black in the Sequence box, and look at the start and end in the Preview.
5. Set a crossfade longer than one of the clips and confirm the error names the Join.
6. Make a Draft around Join 1 with sound, and play it.
7. Render the Output with one of each kind of Join and play it. Check the crossfade is shorter by its length, and listen across the Joins.
8. Save the Project, press F5, open it again, and check the Transitions and fades are kept.

## Choices in slice 12 to confirm or change

- Each Source holds the setting for the Join after it, so a Transition moves with its clip when the play order changes or a clip is removed. The last Source's setting is not shown or used.
- A fade through black of length L fades out over L/2 and in over L/2.
- Fades are linear, in picture and in sound.
- A Draft in a Sequence covers a chosen number of seconds before and after "The start" or a chosen Join. It shares the seconds, width and sound settings with the grid's Draft.
- A Join is placed at the middle of its fade or crossfade, which is where the Draft centres on it.

## After verification

1. Fix what the check finds, on `slice-12-transitions`.
2. Mark slice 12 "(done)" in `build-plan.md`, delete this file, and commit.
3. Merge to `main` (fast-forward) and delete the branch.

## Things to know

- **Restart the app after changing anything under `src/vid_editor/`.** The running server keeps the old modules.
- **Code shape**:
  - `sequence.py` is the Sequence arithmetic: `clip_spans`, `mix_at` (how much of each Source is on show at a time), `on_show`.
  - `render.py` has the Sequence functions beside the grid ones: `sequence_spans`, `sequence_geometry`, `build_sequence`, `sequence_preview`, `join_times` and `render_sequence_draft`. `render()` chooses by `project.workflow`.
  - In `streamlit_app.py`, `grid` says which workflow is shown. The other workflow's settings are kept alive on every run so that switching back restores them.
- **In a Sequence each Source still gets a hidden grid Panel**, so switching to the grid shows the clips side by side. The user confirmed this.
- **The test suite takes about 5 minutes** now, most of it the screen tests.
- **Untracked files left alone**: `assets/logos/logo_2023.png`, and in `references/` the test clips, the saved Projects `proj_slice_4.json` to `proj_slice_9.json`, and several renders and Drafts. Whether these should be tracked or ignored has not been decided.
- Open decisions that are not tied to a slice (OpenCV, HDR colour, the unreadable-file message) are in `build-plan.md`.
