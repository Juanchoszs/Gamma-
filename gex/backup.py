"""Back up data/ to remote storage through rclone.

This complements the data repository, which cannot hold everything: GitHub
rejects files over 100 MB, while Databento archives exceed that limit. rclone
has no such limit and supports Drive, OneDrive, B2, and S3 alike.

Two design choices:

**`copy`, not `sync`.** rclone `sync` mirrors local deletions remotely, so a
mistake could erase the backup. `copy` adds and updates without deleting,
which is the expected backup behavior.

**Scheduled, never continuous.** A desktop sync client would re-upload the
current day's price file on every write—every 30 seconds per symbol. A daily
run after the close avoids this waste.

One-time terminal setup:

    rclone config

Create a remote named `gexbackup`; authorization happens in the browser.
Verify it with `python -m gex.backup --check`.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess

from .config import SETTINGS

log = logging.getLogger(__name__)

REMOTE = "gexbackup"
REMOTE_PATH = "gex-data"

# The local git repository is already mirrored on GitHub; copying it would
# duplicate compressed content that re-uploads poorly.
EXCLUDES = [".git/**", "*.tmp", "*.lock"]


def rclone_path() -> str | None:
    return shutil.which("rclone")


def remote_configured(remote: str = REMOTE) -> bool:
    exe = rclone_path()
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "listremotes"], capture_output=True,
                             text=True, timeout=30)
        return f"{remote}:" in out.stdout
    except Exception:  # noqa: BLE001
        return False


def build_command(remote: str = REMOTE, dry_run: bool = False) -> list[str]:
    exe = rclone_path() or "rclone"
    cmd = [exe, "copy", str(SETTINGS.data_dir), f"{remote}:{REMOTE_PATH}",
           # Parquet files are already compressed; size-only avoids rereading
           # hundreds of megabytes unnecessarily.
           "--size-only",
           "--transfers", "4",
           "--checkers", "8",
           # Drive limits request throughput; exceeding it throttles rclone
           # and makes the run drag on.
           "--tpslimit", "10",
           "--retries", "3",
           "--stats", "30s",
           "--stats-one-line",
           "--log-level", "INFO"]
    for pattern in EXCLUDES:
        cmd += ["--exclude", pattern]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def run(remote: str = REMOTE, dry_run: bool = False) -> bool:
    """Run the backup. Return True if it completed successfully.

    Never raise: this is called by the scheduler, and a failed backup must not
    interrupt data collection.
    """
    if not rclone_path():
        log.warning("rclone introuvable — sauvegarde ignorée")
        return False
    if not remote_configured(remote):
        log.warning("Remote rclone '%s' non configuré — lancer `rclone config`",
                    remote)
        return False
    cmd = build_command(remote, dry_run)
    log.info("Sauvegarde vers %s: — %s", remote, SETTINGS.data_dir)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3 * 3600)
    except Exception:  # noqa: BLE001
        log.exception("Sauvegarde interrompue")
        return False
    tail = (res.stderr or res.stdout or "").strip().splitlines()[-4:]
    for line in tail:
        log.info("  %s", line)
    if res.returncode != 0:
        log.error("rclone a échoué (code %d)", res.returncode)
        return False
    log.info("Sauvegarde terminée")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default=REMOTE)
    parser.add_argument("--dry-run", action="store_true",
                        help="montre ce qui serait envoyé, sans rien envoyer")
    parser.add_argument("--check", action="store_true",
                        help="vérifie l'installation et la configuration")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.check:
        exe = rclone_path()
        print(f"rclone           : {exe or 'ABSENT'}")
        print(f"remote '{args.remote}' : "
              f"{'configuré' if remote_configured(args.remote) else 'NON CONFIGURÉ'}")
        print(f"source           : {SETTINGS.data_dir}")
        print(f"destination      : {args.remote}:{REMOTE_PATH}")
        if not remote_configured(args.remote):
            print(f"\nÀ faire : `rclone config`, créer un remote nommé "
                  f"'{args.remote}' (Google Drive = option `drive`).")
        return

    run(args.remote, args.dry_run)


if __name__ == "__main__":
    main()
