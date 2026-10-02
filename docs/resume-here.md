# Resume here

Status on 2026-10-01. Delete this file once slice 2 is merged.

## Where things stand

- Slice 2 (one Source, end to end) is on branch `slice-2-one-source`, not merged to `main`.
- An iPhone HDR recording could not be opened because of a fault in MoviePy 2.2.1. A workaround in `src/vid_editor/render.py` and a regression test in `tests/test_render.py` fix it. All 47 automated tests pass.
- An automated pass drove the real screen with two real clips and rendered 15 check files into `output/slice2_checks/` (not tracked by git). Sizes, running times, frame rates, sound position, Gaps, captions, the timing table, and every error and warning were measured and are correct.
- The two real clips are `references/IMG_8199.MOV` (iPhone, 1080 by 1920, 5.370 s, 29.97 frames per second) and `references/NORM0001.MP4` (dashcam, 1920 by 1080, 12.530 s, 60 frames per second). They are not tracked by git.

## Next step: your verification

Start the app with `uv run streamlit run streamlit_app.py`, then go through the two lists below.

### Check files in `output/slice2_checks/`

| File | Settings | Confirm |
|---|---|---|
| `01_iphone_whole_file` | defaults | Colours match the phone (HDR clip). Plays smoothly. The knock is heard as the finger hits the bolt, about 3.3 s in. |
| `02_iphone_trim_sync2_in1_out1.5` | Sync Point 2.0, Lead-in 1.0, Lead-out 1.5 | Nothing needed. |
| `03_iphone_front_gap_2s` | Sync Point 1.0, Lead-in 3.0, Lead-out 1.0 | Black to picture is clean, with no flash or click. |
| `04_iphone_back_gap_2s` | Sync Point 4.37, Lead-in 1.0, Lead-out 3.0 | Ends in black, not a frozen frame. |
| `05_iphone_turn_left_90` | Turn left | "Turn left" turned it the way you expect (top of the picture now on the left). |
| `06_iphone_rotate_3_degrees` | Rotation 3 | Tilt direction and black corners are what you expect; still sharp enough. |
| `07_iphone_crop_top_200` | Crop top 200 | Only the top is removed. |
| `08_iphone_aspect_forced_1080x1080` | Override 1080 by 1080 | Squashed to a square, as the setting intends. |
| `09_iphone_width_540` | Output width 540 | Sharp enough at half size. |
| `10_iphone_combined` | Turn left, crop left and right 200, width 960, 1 s front Gap | Everything together looks right. |
| `11_dashcam_whole_file_60fps` | defaults | Smooth at 60 frames per second. Loudness is fine. |
| `12_dashcam_output_rate_30` | Output Rate 30 | The bolt's fall still looks fine at 30. |
| `13_dashcam_quality_high`, `_medium`, `_small` | each Quality | 3.49, 1.12 and 0.52 MB: the levels look different enough and Small is usable. |

`output/slice2_checks/_sheets/` holds six still frames from each file. If the folder is gone, the files can be rendered again from the settings above.

### In the app itself

- Both Browse dialogs (Source file and Output folder).
- The progress bar during a render.
- Layout and labels.
- A multi-gigabyte camera file. The largest tested so far is 45 MB.

## Open decisions

1. **Screen speed.** Each setting or slider change takes 1 to 2 s on 1080p footage. Every change rebuilds the clip chain, and MoviePy re-reads the first frame each time, which restarts ffmpeg. Decide whether to fix this now or after slice 3. It will matter for the frame stepper in slice 6.
2. **OpenCV for rotation.** Rotation by an angle that is not a quarter turn costs about 110 ms per 1080p frame with Pillow. OpenCV would cut that but adds a dependency.
3. **HDR colour.** iPhone HDR footage is converted to standard colour without tone mapping. Fix only if `01_iphone_whole_file` looks wrong.
4. **Unreadable file message.** It includes a few lines of ffmpeg output. Could be shortened.

## Things to know

- The dashcam Source is mono. The Output is stereo with each channel 3 dB lower, which is the standard conversion.
- The dashcam picture is on its side in the Source itself.
- A trim that starts partway through a file can show the Source frame one before the expected one. The frame stepper in slice 6 is where frame-exact Sync Points arrive.

## After verification

Fix what the verification finds on this branch, merge to `main`, then start slice 3 (Overlays). The slice order is in `build-plan.md`.
