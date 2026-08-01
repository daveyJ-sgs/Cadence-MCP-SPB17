"""Show one conductor layer at a time, or report what is currently visible.

    python bridge/allegro/layer_view.py --list     # report only, changes nothing
    python bridge/allegro/layer_view.py top        # layer 1 only
    python bridge/allegro/layer_view.py gnd        # layer 2 only  (split plane)
    python bridge/allegro/layer_view.py pwr        # layer 3 only
    python bridge/allegro/layer_view.py bottom     # layer 4 only
    python bridge/allegro/layer_view.py outer      # top + bottom
    python bridge/allegro/layer_view.py all        # everything back on

The GUI equivalent is **Display > Windows > Visibility** (confirmed by the
engineer 2026-08-01 -- it is a dockable window opened from that menu, not a
tab sitting in the right-hand panel). This script is not a replacement for it:
the window is the right tool for one-off ticking. This is for repeatable named
views, and for --list, which answers "why can I not see that trace" without
any clicking.

WHAT A VIEW TOUCHES

Only the conductor classes, and only the four etch subclasses:

    ETCH/<layer>        the copper
    PIN/<layer>         pads      -- pointless to hide, you lose what copper lands on
    VIA CLASS/<layer>   via pads

Silkscreen, assembly, refdes text, board outline and keepins are deliberately
NOT touched: that is `text_view.py`'s job, and the two scripts must not fight
over the same classes. ANTI ETCH is left alone too -- it is per-layer but it is
design intent, not something you toggle to see better.

READING THE STATE

`axlVisibleGet()` returns one record per CLASS, not per layer:

    (nil class "ETCH" visible t subclassinfo nil)

`visible` is `t` (all subclasses on), `nil` (all off), or **-1 (mixed)** -- and
only when it is mixed does `subclassinfo` fill in with the per-subclass detail:

    (nil class "ETCH" visible -1 subclassinfo (("BOTTOM" t) ("PWR" nil) ...))

So a class reading plain `t` means every one of its subclasses is on; do not
read the empty `subclassinfo` as "no information".

GETTING BACK EXACTLY WHAT YOU HAD

`all` turns everything on, which is not the same as putting back what was
there. On one board PIN/GND and VIA CLASS/GND were already off --
`all` would silently switch them on.

So every run stashes the prior state in the SKILL global `ppLayerSave` first.
Within the same Allegro session:

    axlVisibleSet(ppLayerSave)   axlVisibleUpdate(t)

restores it precisely, those two GND rows included. Verified 2026-08-01. The
global does not survive closing Allegro; `all` is the durable fallback.

⛔ VISIBILITY IS STORED IN THE .brd. Changing a view dirties the design and
Allegro will offer to save it. That is how the view persists, and it is also
why running this mid-edit makes the board look modified when the copper has
not changed. Harmless, but do not confuse it for an unsaved routing change.
"""
from __future__ import annotations

import sys
import pathlib
import argparse
import re

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from bridge.allegro.allegro_client import AllegroBridge  # noqa: E402

# This script is the only one here that prints its own docstring, and the
# docstring carries the same non-ASCII warning markers the rest of the repo
# uses. A stock Windows console is cp1252 and raises UnicodeEncodeError on
# them, so `layer_view.py` with no arguments -- the discovery path, the one a
# new user hits first -- would traceback instead of showing help.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Conductor layers, in stackup order. These are THIS board's names -- layer 2
# is "GND" and layer 3 is "PWR" because they were created that way in 7.23,
# not because Allegro calls them that.
LAYERS = ["TOP", "GND", "PWR", "BOTTOM"]

# Classes that get switched per layer.
CLASSES = ["ETCH", "PIN", "VIA CLASS"]

VIEWS = {
    "top": ["TOP"],
    "gnd": ["GND"],
    "pwr": ["PWR"],
    "power": ["PWR"],
    "bottom": ["BOTTOM"],
    "outer": ["TOP", "BOTTOM"],
    "inner": ["GND", "PWR"],
    "all": LAYERS,
}


def read_state(br):
    """{class: {subclass: bool}} for the conductor classes."""
    out = {}
    for cls in CLASSES:
        rec = br.send(f'car(setof(r axlVisibleGet() nth(2 r)=="{cls}"))')
        vis = re.search(r"visible\s+(\S+)", rec)
        vis = vis.group(1) if vis else "?"
        if vis == "t":
            out[cls] = {L: True for L in LAYERS}
        elif vis == "nil":
            out[cls] = {L: False for L in LAYERS}
        else:
            # Mixed -- subclassinfo is populated, e.g. (("PWR" nil) ("TOP" t))
            found = dict(re.findall(r'\("([^"]+)"\s+(t|nil)\)', rec))
            out[cls] = {L: found.get(L, "nil") == "t" for L in LAYERS}
    return out


def report(br, tag):
    st = read_state(br)
    print(f"  {tag}")
    print(f"    {'':11}" + "".join(f"{L:>9}" for L in LAYERS))
    for cls in CLASSES:
        row = "".join(f"{('on' if st[cls][L] else '--'):>9}" for L in LAYERS)
        print(f"    {cls:11}{row}")
    return st


def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("view", nargs="?", help=" | ".join(sorted(VIEWS)))
    ap.add_argument("--list", action="store_true",
                    help="report current visibility and exit, changing nothing")
    args = ap.parse_args(argv)

    if not args.list and not args.view:
        print(__doc__)
        return 2
    if args.view and args.view not in VIEWS:
        print(f"unknown view {args.view!r}; use: {' | '.join(sorted(VIEWS))}",
              file=sys.stderr)
        return 2

    with AllegroBridge() as br:
        print("ping:", br.ping())
        report(br, "current:")
        if args.list:
            return 0

        want = VIEWS[args.view]
        print(f"\n  view: {args.view}  ->  {' '.join(want)}\n")
        # Stash first, so axlVisibleSet(ppLayerSave) is an in-session undo.
        # Same convention as text_view.py; it does not survive closing Allegro.
        br.send("ppLayerSave = axlVisibleGet()")
        bad = 0
        for cls in CLASSES:
            for L in LAYERS:
                on = "t" if L in want else "nil"
                r = br.send(f'axlVisibleLayer("{cls}/{L}" {on})').strip()
                if r != "t":
                    bad += 1
                    print(f"    FAILED {cls}/{L} -> {r[:50]}")
        # t = redraw now rather than deferring to the next user interaction.
        br.send("axlVisibleUpdate(t)")
        print()
        report(br, "now:")
        if bad:
            print(f"\n  *** {bad} layer(s) did not take ***", file=sys.stderr)
            return 1
        print("\n  Visibility lives in the .brd, so the design now reads as "
              "modified.\n  Save it to keep the view; 'all' is the way back.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
