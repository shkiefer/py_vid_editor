"""Native Browse dialogs for choosing local files and folders.

The app is local-only (docs/adr/0001), so the dialog opens on the same
machine as the browser. Each dialog runs in its own short-lived process:
tkinter needs the main thread, and Streamlit runs scripts on worker threads.
"""

import os
import subprocess
import sys
from pathlib import Path

_DIALOG_SCRIPT = """
import sys
import tkinter
from tkinter import filedialog

kind, initial_dir = sys.argv[1], sys.argv[2]
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
options = {"parent": root}
if initial_dir:
    options["initialdir"] = initial_dir
if kind == "file":
    chosen = filedialog.askopenfilename(
        title="Choose a video",
        filetypes=[
            ("Video files", "*.mp4 *.mov *.avi *.mkv *.wmv *.m4v *.webm *.mts"),
            ("All files", "*.*"),
        ],
        **options,
    )
elif kind == "image":
    chosen = filedialog.askopenfilename(
        title="Choose an image",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
            ("All files", "*.*"),
        ],
        **options,
    )
elif kind == "project":
    chosen = filedialog.askopenfilename(
        title="Open a Project",
        filetypes=[("Project files", "*.json"), ("All files", "*.*")],
        **options,
    )
elif kind == "save_project":
    chosen = filedialog.asksaveasfilename(
        title="Save the Project as",
        defaultextension=".json",
        filetypes=[("Project files", "*.json")],
        **options,
    )
else:
    chosen = filedialog.askdirectory(title="Choose a folder", **options)
root.destroy()
sys.stdout.buffer.write((chosen or "").encode("utf-8"))
"""


def _ask(kind: str, initial_dir: str) -> str | None:
    if initial_dir and not Path(initial_dir).is_dir():
        initial_dir = ""
    result = subprocess.run(
        [sys.executable, "-c", _DIALOG_SCRIPT, kind, initial_dir],
        capture_output=True,
        check=False,
    )
    chosen = result.stdout.decode("utf-8").strip()
    return str(Path(chosen)) if chosen else None


def pick_file(initial_dir: str = "") -> str | None:
    """Ask the user for a video file. Returns None if they cancel."""
    return _ask("file", initial_dir)


def pick_image(initial_dir: str = "") -> str | None:
    """Ask the user for an image file. Returns None if they cancel."""
    return _ask("image", initial_dir)


def pick_project(initial_dir: str = "") -> str | None:
    """Ask the user for a Project file to open. Returns None if they cancel."""
    return _ask("project", initial_dir)


def pick_project_to_save(initial_dir: str = "") -> str | None:
    """Ask the user where to save a Project. Returns None if they cancel."""
    return _ask("save_project", initial_dir)


def pick_folder(initial_dir: str = "") -> str | None:
    """Ask the user for a folder. Returns None if they cancel."""
    return _ask("folder", initial_dir)


def open_file(path: str | Path) -> None:
    """Open a file in the program Windows uses for its type."""
    os.startfile(path)
