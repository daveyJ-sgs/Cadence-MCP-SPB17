"""Load the board-specific configuration these tools need.

    from bridge.allegro.board_profile import load
    cfg = load()            # -> dict from board.json

WHY THIS EXISTS

The checkers and routers in this repo are generic -- they know how to measure
creepage, find floating copper, drop pins onto a plane. What they cannot know
is *which* nets carry mains, where the mounting holes are, which refdes are a
stereo pair, or where the .brd file lives. That is design data, and design
data does not belong in a tooling repo.

So it lives in `board.json` at the repo root, which is **gitignored**.
`board.example.json` is committed and shows the shape with neutral values.

Copy the example, fill it in, and the tools work. Without it they refuse to
run rather than silently checking nothing -- an unconfigured check that
reports "pass" is worse than no check at all.
"""
from __future__ import annotations

import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG = REPO / "board.json"
EXAMPLE = REPO / "board.example.json"


class NoBoardProfile(RuntimeError):
    pass


def load(section: str | None = None):
    """The whole profile, or one section of it."""
    if not CONFIG.exists():
        raise NoBoardProfile(
            f"no board profile at {CONFIG}\n"
            f"  copy {EXAMPLE.name} to {CONFIG.name} and fill it in.\n"
            f"  it is gitignored: board specifics stay out of this repo.")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if section is None:
        return cfg
    if section not in cfg:
        raise NoBoardProfile(f"{CONFIG.name} has no '{section}' section")
    return cfg[section]


def board_path() -> pathlib.Path:
    return pathlib.Path(load()["board"])


def snapshot_dir() -> pathlib.Path:
    cfg = load()
    if cfg.get("snapshots"):
        return pathlib.Path(cfg["snapshots"])
    return board_path().parent / "snapshots"
