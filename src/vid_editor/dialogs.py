"""Native Browse dialogs for choosing local files and folders.

The app is local-only (docs/adr/0001), so the dialog opens on the same
machine as the browser. Each dialog runs in its own short-lived process:
tkinter needs the main thread, and Streamlit runs scripts on worker threads.
"""

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


def pick_folder(initial_dir: str = "") -> str | None:
    """Ask the user for a folder. Returns None if they cancel."""
    return _ask("folder", initial_dir)
