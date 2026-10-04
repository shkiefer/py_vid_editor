# Video editor

A local tool for trimming, cropping, and annotating videos, and for combining several videos of the same event into one time-aligned Output.

- `CONTEXT.md` defines the vocabulary used throughout the code and screens.
- `docs/build-plan.md` lists the build order and what is done.
- `docs/adr/` records the decisions that would be costly to change.

## Run

```
uv sync
uv run streamlit run streamlit_app.py
```

The app only listens on this computer. Sources added one after another are placed side by side and lined up on their Sync Points. It reads Source files by path and writes the Output to a folder you choose. Save Project as keeps every setting in a readable JSON file, which is then updated after every change.

## Test

```
uv run pytest
```
