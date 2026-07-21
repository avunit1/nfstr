"""
core/logging_setup.py
One place that wires up logging for the whole app:
  - a rotating file handler under nfstr_data/logs/ (persists across runs,
    capped size so it never grows unbounded)
  - a QueueHandler the GUI polls to append lines to the Log tab live,
    without the GUI thread and worker threads fighting over a Text widget
  - a global sys.excepthook so an uncaught exception anywhere gets a full
    traceback in the log file instead of just vanishing when the window
    closes

Call setup_logging() once, at startup, before anything else logs.
Everywhere else in the codebase just does logging.getLogger("nfstr.xxx")
as usual -- nothing else needs to change to benefit from this.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import queue
import sys
import traceback
from datetime import datetime

from . import paths

LOG_QUEUE: "queue.Queue[str]" = queue.Queue()

_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)-22s %(message)s"
_DATEFMT = "%H:%M:%S"


class QueueHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            LOG_QUEUE.put_nowait(self.format(record))
        except Exception:
            pass


def setup_logging(verbose: bool = False) -> str:
    """Returns the path to this session's log file."""
    root = logging.getLogger("nfstr")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()

    fmt = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    log_dir = paths.logs_dir()
    session_file = os.path.join(log_dir, "session.log")
    file_handler = logging.handlers.RotatingFileHandler(
        session_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    qh = QueueHandler()
    qh.setFormatter(fmt)
    qh.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(qh)

    def excepthook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        root.critical("UNCAUGHT EXCEPTION:\n%s", text)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

    root.info("=" * 70)
    root.info("NFS: The Run Mod Menu -- session started %s", datetime.now().isoformat(timespec="seconds"))
    root.info("Python %s | Platform %s | Frozen: %s", sys.version.split()[0],
                platform.platform(), paths.FROZEN)
    root.info("Log file: %s", session_file)
    root.info("=" * 70)
    return session_file


def drain_queue() -> list[str]:
    """Pull everything currently queued, non-blocking. Called from the
    GUI's periodic poll (tk .after loop) to update the Log tab."""
    lines = []
    while True:
        try:
            lines.append(LOG_QUEUE.get_nowait())
        except queue.Empty:
            break
    return lines
