"""Copy the board to a dated snapshot, keyed to the git commit that made it.

    python bridge/allegro/snapshot.py            # take one
    python bridge/allegro/snapshot.py --list     # what exists

WHY

A repair loop once ran away and issued several hundred
deletes against the live database. The scripts were all in git; the board was
not, and had exactly one live copy. Recovery worked only because a save
happened to have landed 25 minutes earlier -- luck, not design.

Allegro keeps no rolling .brd backup. The two files in the folder dated
Jul 30 are pre-ECO copies the netlist import made, two days and 70 KB behind.

So: snapshot at milestones. It is a file copy. It costs nothing and it turns
"close without saving" from a gamble into a routine.

WHAT IT RECORDS

    <board>_20260801-1221_48f7cd7.brd

date-time, and the SHORT HASH OF HEAD at the moment of the copy. That is the
whole point: the board and the scripts that produced it move together, so a
snapshot can always be paired with the code that understands it. A snapshot
taken with a dirty tree is tagged `-dirty`, because then the pairing is a
guess rather than a fact.

The board is deliberately NOT committed to git. It is a 600 KB binary that
changes on every save, and the repo is kept clean of design specifics.
"""
from __future__ import annotations

import sys
import shutil
import pathlib
import argparse
import subprocess
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
from bridge.allegro import board_profile  # noqa: E402

# Where the board lives is design data, so it comes from board.json rather
# than being written into this repo. See board.example.json.
BOARD = board_profile.board_path()
SNAPS = board_profile.snapshot_dir()


def git(*args):
    try:
        return subprocess.run(("git", "-C", str(REPO)) + args,
                              capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except Exception:
        return ""


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--note", default="", help="appended to the filename")
    args = ap.parse_args(argv)

    SNAPS.mkdir(exist_ok=True)
    if args.list:
        snaps = sorted(SNAPS.glob("*.brd"))
        if not snaps:
            print("  no snapshots yet")
        for s in snaps:
            st = s.stat()
            print(f"  {s.name:44} {st.st_size:>9,} "
                  f"{datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M}")
        print(f"\n  live: {BOARD.name} {BOARD.stat().st_size:,} "
              f"{datetime.fromtimestamp(BOARD.stat().st_mtime):%Y-%m-%d %H:%M}")
        return 0

    if not BOARD.exists():
        print(f"no board at {BOARD}", file=sys.stderr)
        return 1

    head = git("rev-parse", "--short", "HEAD") or "nogit"
    if git("status", "--porcelain"):
        head += "-dirty"
    stamp = datetime.fromtimestamp(BOARD.stat().st_mtime).strftime("%Y%m%d-%H%M")
    note = f"_{args.note}" if args.note else ""
    dest = SNAPS / f"{BOARD.stem}_{stamp}_{head}{note}.brd"

    if dest.exists():
        print(f"  {dest.name} already exists -- board unchanged since then")
        return 0
    shutil.copy2(BOARD, dest)
    print(f"  {dest.name}\n  {dest.stat().st_size:,} bytes -> {SNAPS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
