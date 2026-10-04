# Resume here

Status on 2026-10-03. Delete this file once slice 7 is merged.

## Where things stand

- Slices 1 to 6 are verified, committed and merged to `main` (last commit `d357c81`).
- Slice 7 (Speed) is built and committed on branch `slice-7-speed`, not merged to `main`. All 150 automated tests pass. It has not been checked by the user yet.
- Slices 8 (Draft render) and 9 (Column, then grid) are not started. The order and every decision so far are in `build-plan.md`.

## Next step: verify slice 7

Start the app with `uv run streamlit run streamlit_app.py`, then:

1. Add `references/IMG_8199.MOV` and `references/NORM0001.MP4`. Give the dashcam clip a Record Rate of 120 and read the Source Speed, Output Speed and Frame Hint lines.
2. Switch Output Speed between Slowest Source, Real time and Custom, and watch the timing table and the sound warning beside the Audio Source.
3. Render one Output at Slowest Source and one at Real time, and watch both for smoothness and sync. Neither has been watched yet.
4. Save the Project, press F5, and open it again to confirm the Record Rate and Output Speed come back.

What an automated run on those two clips gave, with the dashcam treated as shot at 120 and a 3 s Output at 960 wide:

| Output Speed | iPhone Frame Hint | Dashcam Frame Hint | Sound | Render time |
|---|---|---|---|---|
| Slowest Source (0.5) | each frame held for 4 Output frames | every frame shown once | none | 15.5 s |
| Real time (1) | each frame held for 2 Output frames | 1 frame in 2 shown, 50% dropped | from the iPhone | 17.2 s |

## Choices in slice 7 to confirm or change

- A Record Rate within 0.5% of the Playback Rate counts as real time, so 30 typed for a 29.97 file keeps its sound.
- The Frame Hint counts Output Rate as well as Output Speed. A real-time 29.97 Source in a 60 Output reads "held for 2 Output frames" with no speed change at all.
- The custom Output Speed value is kept, and saved, while another choice is in use.

## After verification

1. Fix what the check finds, on `slice-7-speed`.
2. Mark slice 7 "(done)" in `build-plan.md`, delete this file, and commit.
3. Merge to `main` (fast-forward) and start slice 8 on a new branch.

## Slice 8 (Draft render) as agreed so far

- A Draft is a small, low-quality render of the whole Output, made only for checking it in motion. It covers the same running time as the Output and is thrown away.
- It is written to a temporary folder and replaced each time, and shows progress like the full render.
- Not yet decided: how small and how low in quality, and whether it plays inside the app or opens in an outside player. `drafts/` is already ignored by git.

## Things to know

- **Restart the app after changing anything under `src/vid_editor/`.** The running server keeps the old modules. Starting it with `--server.headless true` avoids a second browser tab.
- **Untracked files left alone**: `assets/logos/logo_2023.png`, and in `references/` the two test clips, `IMG_8199_edited.mp4`, the saved Projects `proj_slice_4.json` to `proj_slice_6.json`, and the renders `slice_5_01.mp4` and `slice_6_01.mp4`. Whether logos and saved Projects should be tracked in git has not been decided.
- `references/proj_slice_4.json` is a format 1 Project file and still opens.
- Open decisions that are not tied to a slice (OpenCV, HDR colour, the unreadable-file message) are in `build-plan.md`.
