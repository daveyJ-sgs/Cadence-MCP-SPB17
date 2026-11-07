#!/usr/bin/env python3
"""dialogs.py -- what is blocking? List every visible dialog on the desktop, with owner.

    python bridge/allegro/dialogs.py            # all dialog-class and owned pop-up windows
    python bridge/allegro/dialogs.py --all      # every visible top-level window

Why: a modal dialog freezes both bridges, and a dialog is NOT always a window of the
process you are watching. Allegro's "Capture project associated with board file not
found" prompt was invisible to a probe that enumerated allegro.exe's windows only. This
enumerates everything, reports the window class (#32770 is a Win32 dialog), the owning
process, the owner window, and the dialog's text so the right button can be chosen.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as W
import subprocess
import sys

u = ctypes.windll.user32
u.SetProcessDPIAware()
for f in ("GetWindow", "GetAncestor", "GetForegroundWindow"):
    getattr(u, f).restype = W.HWND
_EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
GW_OWNER = 4


def text(h):
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    return b.value


def cls(h):
    b = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, b, 256)
    return b.value


def rect(h):
    r = W.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def pid_of(h):
    p = W.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


def proc_names():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-Process | ForEach-Object { \"$($_.Id) $($_.ProcessName)\" }"],
                         capture_output=True, text=True).stdout
    d = {}
    for line in out.splitlines():
        try:
            pid, name = line.split(" ", 1)
            d[int(pid)] = name
        except ValueError:
            pass
    return d


def children_text(h, limit=12):
    """Static text and button captions inside a dialog: the message and the choices."""
    found = []

    def cb(c, _):
        t = text(c)
        if t and u.IsWindowVisible(c):
            found.append((cls(c), t[:120]))
        return len(found) < limit

    u.EnumChildWindows(h, _EnumProc(cb), 0)
    return found


def scan(everything=False):
    names = proc_names()
    rows = []

    def cb(h, _):
        if not u.IsWindowVisible(h):
            return True
        c = cls(h)
        owner = u.GetWindow(h, GW_OWNER)
        is_dialog = c == "#32770" or (owner and c not in ("Shell_TrayWnd",))
        if everything or is_dialog:
            rows.append({"hwnd": h, "class": c, "title": text(h), "pid": pid_of(h),
                         "proc": names.get(pid_of(h), "?"), "owner": text(owner) if owner else "",
                         "rect": rect(h), "children": children_text(h) if is_dialog else []})
        return True

    u.EnumWindows(_EnumProc(cb), 0)
    return rows


def main(argv):
    rows = scan("--all" in argv)
    fg = u.GetForegroundWindow()
    if not rows:
        print("no dialogs visible")
    for r in rows:
        mark = "FOREGROUND " if r["hwnd"] == fg else ""
        print(f"{mark}[{r['proc']} pid {r['pid']}] class={r['class']} title={r['title']!r} rect={r['rect']}"
              + (f" owner={r['owner']!r}" if r["owner"] else ""))
        for c, t in r["children"]:
            print(f"      {c:12s} {t!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
