"""Launch the current ConTracktor working copy with its corrected local database."""

import os
import runpy
import sys
import traceback
from pathlib import Path


HERE = Path(__file__).resolve().parent
APPLICATION = HERE / "app.py"
DATABASE = HERE / "contractor_tracker_preview_135800.db"
ERROR_LOG = HERE / "launch_error.log"


def report_startup_error() -> None:
    details = traceback.format_exc()
    ERROR_LOG.write_text(details, encoding="utf-8")
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror(
            "ConTracktor",
            "ConTracktor could not start. The error was saved to:\n"
            f"{ERROR_LOG}",
            parent=root,
        )
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    os.chdir(HERE)
    os.environ["CONTRACTOR_DB_PATH"] = os.environ.get(
        "CONTRACTOR_LAUNCH_DB_PATH", str(DATABASE)
    )
    os.environ["CONTRACTOR_RECONCILIATION_PREVIEW"] = "1"
    sys.path.insert(0, str(HERE))
    try:
        runpy.run_path(str(APPLICATION), run_name="__main__")
    except Exception:
        report_startup_error()
        raise
