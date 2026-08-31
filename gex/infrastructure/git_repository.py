"""Git operations on the data repository."""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime

from ..config import SETTINGS
from ..metrics import ET

log = logging.getLogger(__name__)


def push_data_repo() -> None:
    """Commit and push the data repository after market close if configured."""
    repo = SETTINGS.data_dir
    if not SETTINGS.auto_push_data or not (repo / ".git").exists():
        return
    day = datetime.now(ET).strftime("%Y-%m-%d")
    try:
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
        diff = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return
        subprocess.run(["git", "-C", str(repo), "commit", "-m", f"data {day}"],
                       check=True, capture_output=True)
        has_remote = subprocess.run(["git", "-C", str(repo), "remote"],
                                   capture_output=True, text=True).stdout.strip()
        if has_remote:
            subprocess.run(["git", "-C", str(repo), "push"], check=True,
                           capture_output=True, timeout=120)
            log.info("Repo data poussé (%s)", day)
        else:
            log.info("Repo data commité localement (%s, pas de remote)", day)
    except Exception:
        log.exception("Échec du push du repo data — données locales intactes")
