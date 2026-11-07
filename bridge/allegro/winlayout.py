#!/usr/bin/env python3
"""winlayout.py -- remember where the engineer's windows are, and put them back.

    python bridge/allegro/winlayout.py save  [name]     # snapshot every visible top-level window
    python bridge/allegro/winlayout.py restore [name]   # move/size them back; maximised stays maximised
    python bridge/allegro/winlayout.py show   [name]    # print what a snapshot holds
    python bridge/allegro/winlayout.py diff   [name]    # what has moved since the snapshot

Why: automation that launches a Cadence tool, pins a window TOPMOST for a capture, or
clicks into a Command box, disturbs the layout the engineer was working in. He asked that
it be put back. Snapshots are JSON in the user's SPB_Data folder (next to pcbenv), keyed
by window title, so a restore after a relaunch still finds the right window by title.
Only windows that still exist are touched; nothing is activated or raised.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as W
import json
import os
import sys
import time

u = ctypes.windll.user32
u.SetProcessDPIAware()
u.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
u.SetWindowPos.restype = W.BOOL
_EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
STORE = os.path.join(os.environ.get("HOME") or os.path.join(os.environ["APPDATA"], "SPB_Data"), "winlayouts")
SW_MAXIMIZE, SW_RESTORE, SW_SHOWNOACTIVATE = 3, 9, 4
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", W.UINT), ("flags", W.UINT), ("showCmd", W.UINT), ("ptMin", W.POINT),
                ("ptMax", W.POINT), ("rcNormal", W.RECT)]


def title(h):
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    return b.value


def placement(h):
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(wp)
    u.GetWindowPlacement(h, ctypes.byref(wp))
    r = wp.rcNormal
    return {"show": wp.showCmd, "rect": [r.left, r.top, r.right, r.bottom]}


def windows():
    out = {}

    def cb(h, _):
        t = title(h)
        if u.IsWindowVisible(h) and t and not u.GetWindow(h, 4):     # top-level, titled, unowned
            out.setdefault(t, h)
        return True

    u.EnumWindows(_EnumProc(cb), 0)
    return out


def key_for(t):
    """Stable key: Cadence titles carry the design name; keep it, drop nothing else."""
    return t


def save(name):
    os.makedirs(STORE, exist_ok=True)
    snap = {key_for(t): {"title": t, **placement(h)} for t, h in windows().items()}
    path = os.path.join(STORE, f"{name}.json")
    json.dump({"taken": time.strftime("%Y-%m-%d %H:%M:%S"), "windows": snap}, open(path, "w"), indent=1)
    print(f"saved {len(snap)} windows -> {path}")


def load(name):
    path = os.path.join(STORE, f"{name}.json")
    if not os.path.exists(path):
        sys.exit(f"no snapshot '{name}' in {STORE}")
    return json.load(open(path))


def restore(name):
    snap = load(name)["windows"]
    live = windows()
    done = 0
    for k, w in snap.items():
        h = live.get(w["title"]) or next((h for t, h in live.items() if t.startswith(w["title"][:40])), None)
        if not h:
            continue
        l, t_, r, b = w["rect"]
        if w["show"] == SW_MAXIMIZE:
            u.ShowWindow(h, SW_MAXIMIZE)
        else:
            if placement(h)["show"] == SW_MAXIMIZE:
                u.ShowWindow(h, SW_RESTORE)
            u.SetWindowPos(h, None, l, t_, r - l, b - t_, SWP_NOZORDER | SWP_NOACTIVATE)
        done += 1
    print(f"restored {done} of {len(snap)} windows from '{name}'")


def show(name):
    d = load(name)
    print("taken", d["taken"])
    for w in d["windows"].values():
        print(f"  {'MAX ' if w['show'] == SW_MAXIMIZE else '    '}{w['rect']}  {w['title'][:90]}")


def diff(name):
    snap = load(name)["windows"]
    live = windows()
    for w in snap.values():
        h = live.get(w["title"])
        if not h:
            print(f"  gone    {w['title'][:80]}")
            continue
        now = placement(h)
        if now["rect"] != w["rect"] or now["show"] != w["show"]:
            print(f"  moved   {w['rect']} -> {now['rect']}  {w['title'][:70]}")
    for t in live:
        if t not in snap:
            print(f"  new     {t[:80]}")


def main(argv):
    cmd = argv[0] if argv else "show"
    name = argv[1] if len(argv) > 1 else "default"
    {"save": save, "restore": restore, "show": show, "diff": diff}.get(cmd, lambda n: sys.exit(__doc__))(name)


if __name__ == "__main__":
    main(sys.argv[1:])
