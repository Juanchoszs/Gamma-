"""Shared file and console logging for dashboard tasks."""
from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import DATA_DIR

# Store logs beside the configured data directory.
LOG_DIR = DATA_DIR.parent / "logs"
LOG_FILE = LOG_DIR / "gex.log"
REPORTS_FILE = LOG_DIR / "reports.md"

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO, console: bool = True) -> None:
    """Configure the root logger with console and rotating-file handlers."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3,
                             encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(fh)
    if console and not any(isinstance(h, logging.StreamHandler)
                           and not isinstance(h, RotatingFileHandler)
                           for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(sh)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def write_report(title: str, body: str, source: str = "tâche planifiée") -> Path:
    """Append a timestamped report to logs/reports.md."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## {stamp} — {title}\n\n*source : {source}*\n\n{body.strip()}\n"
    with REPORTS_FILE.open("a", encoding="utf-8") as f:
        f.write(entry)
    return REPORTS_FILE


def read_reports(last_n: int = 5) -> str:
    """Return the most recent reports."""
    if not REPORTS_FILE.exists():
        return "Aucun rapport enregistré."
    blocks = REPORTS_FILE.read_text(encoding="utf-8").split("\n## ")
    tail = blocks[-last_n:] if len(blocks) > last_n else blocks
    return "\n## ".join(b for b in tail if b.strip())
