# Local-only app that reads Sources by file path

Sources are routinely several gigabytes, and MoviePy reads from a path on disk. We decided the app runs only on the machine that holds the files: Sources are chosen by local file path (typed or via a native Browse dialog), and the Output is written to a user-chosen folder. We deliberately do not use Streamlit's file uploader or download button, because they would copy each multi-gigabyte file through the browser and into memory just to land back on the same machine.

## Consequences

- The app cannot be hosted on a server for other users as built. Doing so later means adding upload handling, temporary storage, and a download path.
- The native Browse dialog only works when the Streamlit server and the browser are on the same machine.
