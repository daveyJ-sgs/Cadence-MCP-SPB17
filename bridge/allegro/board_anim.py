#!/usr/bin/env python3
"""board_anim.py -- film a board placing and routing itself, live from the Allegro canvas.

    python bridge/allegro/board_anim.py capture  <framedir> [--title cds_routed] [--test]
    python bridge/allegro/board_anim.py assemble <framedir> <outstem> [--fps 24] [--aspect 4:5|1:1|16:9]

Allegro must be open on the board with the bridge up (allegro.ilinit does that). The
run holds the Allegro window TOPMOST for its duration -- a few minutes -- and never
saves. Nothing in the database is edited: the reveal is done entirely with per-net
custom colours (docs/allegro_api_notes.md s17), so the board is exactly as it was when
the script exits, bar the display overrides, which clear on reload.

Sequence, captured in playback order:
    bare outline -> parts land one per frame -> power pins -> nets route one per frame
    -> silkscreen -> refdes -> hero hold -> eased zoom into the largest package -> back out

Tuned on Cadence's shipped demo board share/pcb/examples/board_design/cds_routed.brd
(copy it somewhere writable first; Allegro drops lock and journal files beside it).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as W
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from allegro_client import AllegroBridge  # noqa: E402

# ---------------------------------------------------------------- window capture
u = ctypes.windll.user32
u.SetProcessDPIAware()
# Declare the handle-typed signatures. Without this, HWND_TOPMOST (-1) is passed as a
# 32-bit int, becomes 0x00000000FFFFFFFF on x64, and SetWindowPos fails silently --
# the window never goes topmost and the grab films whatever is in front.
u.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
u.SetWindowPos.restype = W.BOOL
for _f in ("WindowFromPoint", "GetAncestor", "GetForegroundWindow"):
    getattr(u, _f).restype = W.HWND
u.WindowFromPoint.argtypes = [W.POINT]
u.GetAncestor.argtypes = [W.HWND, W.UINT]
u.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
HWND_TOPMOST, HWND_NOTOPMOST = W.HWND(-1), W.HWND(-2)
_EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)


def _title(h):
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, buf, n + 1)
    return buf.value


def find_main(substr: str):
    out = []

    def cb(h, _):
        if u.IsWindowVisible(h) and substr.lower() in _title(h).lower():
            out.append(h)
        return True

    u.EnumWindows(_EnumProc(cb), 0)
    if not out:
        sys.exit(f"no visible window with '{substr}' in its title")
    return out[0]


def rect(h):
    r = W.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def canvas(h):
    """The drawing canvas is the largest visible child of the main window."""
    best = [None, 0]

    def cb(c, _):
        if u.IsWindowVisible(c):
            r = rect(c)
            a = (r[2] - r[0]) * (r[3] - r[1])
            if a > best[1]:
                best[:] = [r, a]
        return True

    u.EnumChildWindows(h, _EnumProc(cb), 0)
    return best[0]


def topmost(h, on: bool):
    u.SetWindowPos(h, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, 0x0043)
    if on:
        u.SetForegroundWindow(h)


def owner_at(x, y):
    """Root window under a screen point -- the one a screen grab there would show."""
    pt = W.POINT(x, y)
    return u.GetAncestor(u.WindowFromPoint(pt), 2)          # GA_ROOT


def ensure_front(h, r):
    """TOPMOST is not enough when another topmost window (this IDE, say) is active:
    re-assert, and refuse to grab someone else's pixels."""
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    for i in range(75):                                      # up to ~30 s: toasts pass
        other = owner_at(cx, cy)
        if other == h:
            return True
        if i == 0:
            print(f"  canvas covered by '{_title(other)}' -- waiting")
        # Another TOPMOST window (an IDE, a chat client) beats ours on activation order
        # and SetForegroundWindow is refused from a background process. Demote it for
        # the run -- without activating anything -- and put it back at the end.
        if u.GetWindowLongW(other, -20) & 0x8 and other not in DEMOTED:     # WS_EX_TOPMOST
            u.SetWindowPos(other, HWND_NOTOPMOST, 0, 0, 0, 0, 0x0013)                    # NOTOPMOST, NOSIZE|NOMOVE|NOACTIVATE
            DEMOTED.append(other)
            print(f"  demoted topmost '{_title(other)}' for the run")
        topmost(h, True)
        time.sleep(0.4)
    return False


DEMOTED: list = []


def restore_demoted():
    for w in DEMOTED:
        u.SetWindowPos(w, HWND_TOPMOST, 0, 0, 0, 0, 0x0013)


def grab(r, path, h=None):
    from PIL import ImageGrab
    if h is not None and not ensure_front(h, r):
        sys.exit(f"another window covers the canvas at {path}; aborting rather than filming it")
    ImageGrab.grab(bbox=r, all_screens=True).save(path)


# ---------------------------------------------------------------- capture
BASE = ["BOARD GEOMETRY/OUTLINE", "PIN/TOP", "PIN/BOTTOM", "ETCH/TOP", "ETCH/BOTTOM",
        "VIA CLASS/TOP", "VIA CLASS/BOTTOM"]
# Planes stay hidden: the demo board draws them as a dot raster with black clearance
# voids, which read as holes at the detail zoom.
LATE = [("PACKAGE GEOMETRY/SILKSCREEN_TOP", "silk"), ("REF DES/SILKSCREEN_TOP", "refdes")]
HIDE = 180                   # spare palette slot, painted background-black
TOP, BOT = 2, 17             # palette slots PIN/TOP and PIN/BOTTOM use on this board
PAL = {TOP: (240, 170, 60), BOT: (60, 140, 220), 12: (45, 85, 65), 20: (85, 50, 70),
       9: (200, 200, 210), 3: (230, 230, 235), HIDE: (0, 0, 0)}
PRI = {"REF DES/SILKSCREEN_TOP": 10, "PACKAGE GEOMETRY/SILKSCREEN_TOP": 8, "PIN/TOP": 7,
       "VIA CLASS/TOP": 7, "ETCH/TOP": 5, "PIN/BOTTOM": 4, "ETCH/BOTTOM": 3, "ETCH/VCC": 2, "ETCH/GND": 1}


def _nums(s):
    return [float(x) for x in re.findall(r"-?\d+\.?\d*", s)]


def capture(outdir: str, title: str, test: bool):
    os.makedirs(outdir, exist_ok=True)
    b = AllegroBridge()
    h = find_main(title)
    u.ShowWindow(h, 3)                      # maximise
    time.sleep(0.5)
    cv = canvas(h)
    aspect = (cv[2] - cv[0]) / (cv[3] - cv[1])

    def sk(e):
        r = b.send(e)
        if r.startswith("ERROR"):
            print("  !!", e[:90], "->", r[:160])
        return r

    def setbox(x0, y0, x1, y1):
        # axlWindowBoxSet grows the box to the canvas aspect from the LEFT edge, which
        # shoves a portrait board off-centre. Pre-fit the aspect about the centre.
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, hgt = x1 - x0, y1 - y0
        if w / hgt < aspect:
            w = hgt * aspect
        else:
            hgt = w / aspect
        return sk(f"axlWindowBoxSet(list({cx - w/2}:{cy - hgt/2} {cx + w/2}:{cy + hgt/2}))")

    # any axlShell command leaves a GUI command active, and writes are discarded while
    # one is -- cancel first.
    sk('axlShell("dehilight all")')
    sk('axlShell("cancel")')
    sk("axlVisibleDesign(nil)")
    for lay in BASE:
        sk(f'axlVisibleLayer("{lay}" t)')
    for i, rgb in PAL.items():
        sk(f"axlColorSet({i} list{rgb})")
    for lay, p in PRI.items():
        sk(f'axlLayerPrioritySet("{lay}" {p})')
    ob = _nums(sk("axlDBGetDesign()->designOutline->bBox"))
    m = 120
    hero = (ob[0] - m, ob[1] - m, ob[2] + m, ob[3] + m)

    # ordering: top of the board first, so placement and routing sweep downwards
    nets = []
    for nm in re.findall(r'"([^"]+)"', sk("mapcar(lambda((n) n->name) axlDBGetDesign()->nets)")):
        v = _nums(sk(f'let((n) n=axlDBFindByName(\'net "{nm}") '
                     f"if(n->branches then car(car(n->branches)->children)->bBox else nil))"))
        if len(v) >= 4 and nm not in ("GND", "VCC"):
            nets.append((nm, (v[1] + v[3]) / 2))
    nets.sort(key=lambda n: -n[1])
    raw = sk("mapcar(lambda((s) list(s->name s->refdes s->xy s->isMirrored)) axlDBGetDesign()->symbols)")
    parts = [(a, rd, float(x), float(y), mir == "t") for a, rd, x, y, mir in
             re.findall(r'\("([^"]+)" "([^"]*)" \(([-\d.]+) ([-\d.]+)\) (t|nil)\)', raw) if rd]
    parts.sort(key=lambda s: -s[3])
    tgt = next((s for s in parts if s[0].startswith("PQFP")), parts[len(parts) // 2])
    print(f"nets={len(nets)} parts={len(parts)} zoom target={tgt[1]}")
    if test:
        nets, parts = nets[:5], parts[:4]

    # hide everything that will be revealed
    sk("foreach(n axlDBGetDesign()->nets axlClearObjectCustomColor(n))")
    sk("foreach(s axlDBGetDesign()->symbols foreach(p s->pins axlClearObjectCustomColor(p)))")
    sk(f"foreach(n axlDBGetDesign()->nets axlCustomColorObject(n {HIDE}))")
    sk(f"foreach(s axlDBGetDesign()->symbols when(s->refdes foreach(p s->pins axlCustomColorObject(p {HIDE}))))")
    setbox(*hero)

    frames = []

    def frame(tag, settle=0.45):
        sk("axlVisibleUpdate(t)")
        time.sleep(settle)
        p = os.path.join(outdir, f"{len(frames):04d}_{tag}.png")
        grab(cv, p, h)
        frames.append((tag, p))

    topmost(h, True)
    time.sleep(1.0)
    try:
        frame("bare", 0.8)
        for k, (_, rd, _, _, mir) in enumerate(parts):
            sk(f'let((s) s=axlDBFindByName(\'refdes "{rd}") foreach(p s->pins axlCustomColorObject(p {BOT if mir else TOP})))')
            frame(f"sym_{rd}")
            if k % 10 == 0:
                print(f"  part {k + 1}/{len(parts)} {rd}")
        sk("foreach(nm '(\"GND\" \"VCC\") axlClearObjectCustomColor(axlDBFindByName('net nm)))")
        frame("pwrpins", 0.6)
        for k, (nm, _) in enumerate(nets):
            sk(f'axlClearObjectCustomColor(axlDBFindByName(\'net "{nm}"))')
            frame(f"net_{nm}")
            if k % 10 == 0:
                print(f"  net {k + 1}/{len(nets)} {nm}")
        for lay, tag in LATE:
            sk(f'axlVisibleLayer("{lay}" t)')
            frame(tag, 0.6)
        frame("hero", 0.8)
        hw, hh = (hero[2] - hero[0]) / 2, (hero[3] - hero[1]) / 2
        hc = ((hero[0] + hero[2]) / 2, (hero[1] + hero[3]) / 2)
        nz = 6 if test else 36
        for i in range(nz + 1):
            t = i / nz
            e = t * t * (3 - 2 * t)                       # smoothstep
            cx, cy = hc[0] + (tgt[2] - hc[0]) * e, hc[1] + (tgt[3] - hc[1]) * e
            w, hgt = hw + (650 - hw) * e, hh + (650 - hh) * e
            setbox(cx - w, cy - hgt, cx + w, cy + hgt)
            frame("zoom")
        setbox(*hero)
        frame("hero", 0.8)
    finally:
        topmost(h, False)
        restore_demoted()
    json.dump(frames, open(os.path.join(outdir, "frames.json"), "w"), indent=1)
    print("frames:", len(frames), "->", outdir)


# ---------------------------------------------------------------- assemble
def assemble(fd: str, stem: str, fps: int, aspect: str):
    from PIL import Image
    import imageio_ffmpeg

    frames = json.load(open(os.path.join(fd, "frames.json")))

    def by(tag):
        return [p for t, p in frames if t.startswith(tag)]

    def rep(lst, n):
        return [x for x in lst for _ in range(n)]

    heros = by("hero")
    seq = rep(by("bare"), fps // 2)
    seq += by("sym_")
    seq += rep(by("pwrpins"), fps // 3)
    nets = by("net_")
    seq += nets + rep(nets[-1:], fps // 3)
    seq += rep(by("silk"), 4) + rep(by("refdes"), 4)
    seq += rep(heros[:1], fps)
    zoom = by("zoom")
    seq += zoom + rep(zoom[-1:], fps) + list(reversed(zoom))
    seq += rep(heros[-1:], fps + fps // 2)

    W_, H_ = Image.open(seq[0]).size
    aw, ah = map(int, aspect.split(":"))
    cw = min(W_, int(H_ * aw / ah))
    ch = min(H_, int(cw * ah / aw))
    x0, y0 = (W_ - cw) // 2, (H_ - ch) // 2
    outsz = {"4:5": (864, 1080), "1:1": (1080, 1080), "16:9": (1920, 1080)}[aspect]
    out = f"{stem}_{aspect.replace(':', 'x')}.mp4"
    print(f"{len(seq)} frames @ {fps} fps = {len(seq) / fps:.1f} s; crop {cw}x{ch} -> {outsz} -> {out}")
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{outsz[0]}x{outsz[1]}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-crf", "18", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cache = {}
    for path in seq:
        if path not in cache:
            im = Image.open(path).convert("RGB").crop((x0, y0, x0 + cw, y0 + ch))
            cache[path] = im.resize(outsz, Image.LANCZOS).tobytes()
        p.stdin.write(cache[path])
    p.stdin.close()
    p.wait()
    print("wrote", out, os.path.getsize(out) // 1024, "KB")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)

    def opt(k, d):
        return argv[argv.index(k) + 1] if k in argv else d

    if argv[0] == "capture":
        capture(argv[1], opt("--title", "cds_routed"), "--test" in argv)
    elif argv[0] == "assemble":
        assemble(argv[1], argv[2], int(opt("--fps", 24)), opt("--aspect", "4:5"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
