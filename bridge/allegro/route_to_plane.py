"""Drop isolated SMD pins onto a plane: one via each, shortest clear stub.

    python bridge/allegro/route_to_plane.py --net <PLANE_NET>            # plan
    python bridge/allegro/route_to_plane.py --net <PLANE_NET> --apply

Nothing is saved. Run place_check.py and dangle_check.py, then save.

WHY A TOOL AND NOT N HAND-PLACED VIAS

A through-hole pin reaches an inner-layer pour by itself -- the barrel passes
through it and Allegro ties it with thermal relief. An SMD pad does not. Every
SMD pin on a plane net therefore needs its own via, and on a board of any size
that is a dozen or more, each in a different local mess of pads, clines and
other vias.

A dozen judgement calls by hand is a dozen chances to be 2 mil out. This reads
the actual obstacle geometry and searches.

SAME-NET VIAS DO NOT VOID THE PLANE

A foreign-net via punches an isolating void; measured on one board, six foreign
vias took a pour from 20 voids to 26. A via on the plane's OWN net gets a
thermal tie instead, so these cost the plane almost nothing -- which matters
when signal has to reference that pour, because every void is a discontinuity
under it.

MIRROR PAIRS GET THE SAME OFFSET, NOT INDEPENDENTLY-OPTIMAL ONES

Where a design has matched channels, they are usually a TRANSLATION rather than
a reflection. A paired set of pins is therefore routed with one shared (dx,dy)
chosen to clear both neighbourhoods, even where one side alone could have done
better: a few mil of improvement on one channel is worth less than the two
being identical by construction.

Which pins are paired is design data and comes from board.json.
Unpaired pins are searched on their own.

THE SEARCH

Candidates on rings at increasing radius, 24 directions each, nearest first.
A candidate must clear, by CLEAR mil, every piece of foreign copper:

  * pad rectangles of every pin not on this net
  * every via not on this net
  * every cline segment on the stub's layer, inflated by half its width

and the stub is checked along its whole length, not just at its endpoint. Same
-net geometry is ignored: it is not a clearance, it is a connection.

Mounting holes are vias too and are enormous (130 mil drill), so via radius is
taken from the padstack name rather than assumed.
"""
from __future__ import annotations

import sys
import math
import pathlib
import argparse
import re

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from bridge.allegro.allegro_client import AllegroBridge  # noqa: E402
from bridge.allegro import board_profile  # noqa: E402

LAYER = "ETCH/TOP"          # where the stub lives
VIA = "TVIA10A"
VIA_R = 10.0                # TVIA10A pad radius
STUB_W = 20.0               # narrower than POWER's 30 so it fits between pads
CLEAR = 10.0                # every spacing rule on this board is 10 mil
MARGIN = 1.0                # extra, so nothing lands exactly on the limit

# Channels are translated by 1050 mil in y, so paired pins share one offset.
#
# A pair is a pair by GEOMETRY, not by pin number. Two parts of the same role
# on opposite channels can carry the net on pin 1 and pin 2 respectively,
# because they were drawn in opposite orientations in the schematic -- so
# their pads sit at different x and the channels are not a clean translation.
# Listing a net's pins in x order before routing it is how that shows up.
def pairs_for(net):
    """Pins that share one via offset, from board.json. [] if unconfigured."""
    try:
        return [tuple(t) for t in board_profile.load("plane_pairs").get(net, [])]
    except board_profile.NoBoardProfile:
        return []


def q(br, expr):
    return br.send(" ".join(expr.split()))


def load(br, net, layer):
    """(target pins, foreign pads, foreign vias, foreign cline segments)."""
    raw = q(br, '''let(((r nil)) foreach(s axlDBGetDesign()->symbols
        foreach(p s->pins r=cons(sprintf(nil "%s.%s;%L;%f;%f;%f;%f;%f;%f;%s"
            s->refdes p->number p->net->name
            xCoord(p->xy) yCoord(p->xy)
            xCoord(car(p->bBox)) yCoord(car(p->bBox))
            xCoord(cadr(p->bBox)) yCoord(cadr(p->bBox))
            if(p->isThrough "T" "S")) r))) buildString(r "~"))''')
    targets, pads = [], []
    for rec in raw.strip('"').split("~"):
        f = rec.split(";")
        if len(f) != 9:
            continue
        # The helper escapes quotes on the way back, so %L arrives as
        # \"NETNAME\" -- strip the backslash as well or nothing matches.
        name, pnet = f[0], f[1].strip('\\"')
        x, y, x1, y1, x2, y2 = (float(v) for v in f[2:8])
        if pnet == net:
            if f[8] == "S":
                targets.append((name, x, y))
        else:
            pads.append((x1, y1, x2, y2))

    raw = q(br, f'''let(((r nil)) foreach(n axlDBGetDesign()->nets
        foreach(b n->branches foreach(c b->children
          when(c->objType=="via" && n->name!="{net}"
            r=cons(sprintf(nil "%f;%f;%L" xCoord(c->xy) yCoord(c->xy)
                           c->definition->name) r))))) buildString(r "~"))''')
    vias = []
    for rec in raw.strip('"').split("~"):
        f = rec.split(";")
        if len(f) != 3:
            continue
        nm = f[2].strip('\\"').upper()
        r = 75.0 if "HOLE" in nm else VIA_R
        vias.append((float(f[0]), float(f[1]), r))

    raw = q(br, f'''let(((r nil)) foreach(n axlDBGetDesign()->nets
        foreach(b n->branches foreach(c b->children
          when(c->objType=="path" && n->name!="{net}"
            foreach(s c->segments
              r=cons(sprintf(nil "%f;%f;%f;%f;%f;%L"
                xCoord(car(s->startEnd)) yCoord(car(s->startEnd))
                xCoord(cadr(s->startEnd)) yCoord(cadr(s->startEnd))
                s->width c->layer) r)))))) buildString(r "~"))''')
    # ⛔ Segments are collected from EVERY layer, not just the stub's.
    # The stub is planar and only cares about its own layer, but the via is a
    # THROUGH via and punches all of them. The first version of this loaded
    # the stub's layer only and cheerfully placed a via directly on top of a
    # supply spine running on an inner layer.
    segs = {}
    for rec in raw.strip('"').split("~"):
        f = rec.split(";")
        if len(f) == 6:
            a = tuple(float(v) for v in f[:4])
            segs.setdefault(f[5].strip('\\"'), []).append(
                (a[0], a[1], a[2], a[3], float(f[4])))
    return targets, pads, vias, segs


def already_tied(br, net):
    """{"R20.2", ...} for pins that already reach the plane.

    ⛔ WITHOUT THIS THE SCRIPT IS NOT RE-RUNNABLE. It targets every SMD pin on
    the net, so a second run lays a second via and a second stub on top of the
    first. Coincident same-net copper passes DRC, passes dangle_check, leaves
    `unconnected` at 0 and is invisible on screen -- on 2026-08-01 a re-run
    duplicated every plane drop on the net and the only symptom was the
    via count.

    A pin is already tied if its branch contains a via or the pour shape.
    """
    br.send(f'ppT = car(setof(n axlDBGetDesign()->nets n->name=="{net}"))')
    nb = br.send("length(ppT->branches)").strip()
    done = set()
    for bi in range(int(nb) if nb.isdigit() else 0):
        k = f"nth({bi} ppT->branches)->children"
        n = br.send(f'length(setof(c {k} c->objType=="via" || '
                    f'c->objType=="shape"))').strip()
        if not (n.isdigit() and int(n) > 0):
            continue
        raw = br.send(f'let(((r nil)) foreach(c {k} when(c->objType=="pin" '
                      f'r=cons(sprintf(nil "%s.%s" c->parent->refdes '
                      f'c->number) r))) buildString(r " "))')
        done |= {t.strip('\\"') for t in raw.strip('"').split() if "." in t}
    return done


def d_pt_seg(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def d_seg_seg(a, b, c, d):
    """Min distance between segments ab and cd (0 if they cross)."""
    def cross(o, p, r):
        return (p[0] - o[0]) * (r[1] - o[1]) - (p[1] - o[1]) * (r[0] - o[0])
    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(d_pt_seg(*a, *c, *d), d_pt_seg(*b, *c, *d),
               d_pt_seg(*c, *a, *b), d_pt_seg(*d, *a, *b))


def d_seg_rect(a, b, r):
    """Distance from segment ab to axis-aligned rect r; 0 if it touches."""
    x1, y1, x2, y2 = r
    for p in (a, b):
        if x1 <= p[0] <= x2 and y1 <= p[1] <= y2:
            return 0.0
    edges = [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
             ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]
    return min(d_seg_seg(a, b, e[0], e[1]) for e in edges)


def clearance(pin, via, pads, vias, segs):
    """Worst clearance of the whole via+stub against foreign copper.

    `segs` is {layer: [...]}. The stub is tested only on LAYER; the via is
    tested on every layer, because it goes through all of them.
    """
    worst = 1e9
    a, b = pin, via
    for r in pads:
        worst = min(worst, d_seg_rect(a, b, r) - STUB_W / 2)
        worst = min(worst, d_seg_rect(b, b, r) - VIA_R)
    for vx, vy, vr in vias:
        worst = min(worst, d_pt_seg(vx, vy, *a, *b) - STUB_W / 2 - vr)
        worst = min(worst, math.dist((vx, vy), b) - VIA_R - vr)
    for layer, lst in segs.items():
        for sx1, sy1, sx2, sy2, w in lst:
            worst = min(worst,
                        d_pt_seg(*b, sx1, sy1, sx2, sy2) - VIA_R - w / 2)
            if layer == LAYER:
                worst = min(worst, d_seg_seg(a, b, (sx1, sy1), (sx2, sy2))
                            - STUB_W / 2 - w / 2)
    return worst


def candidates():
    for rad in range(55, 165, 5):
        for k in range(24):
            ang = math.radians(k * 15)
            yield rad, (round(math.cos(ang) * rad, 2), round(math.sin(ang) * rad, 2))


def solve(pin_list, pads, vias, segs):
    """One offset that clears every pin in the group. Nearest wins."""
    best = None
    for rad, (dx, dy) in candidates():
        ok = True
        worst = 1e9
        for name, x, y in pin_list:
            c = clearance((x, y), (x + dx, y + dy), pads, vias, segs)
            if c < CLEAR + MARGIN:
                ok = False
                break
            worst = min(worst, c)
        if ok:
            best = (rad, dx, dy, worst)
            break
    return best


def flush(br):
    br.send("axlDBTransactionCommit(axlDBTransactionStart())")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", required=True)
    ap.add_argument("--layer", default="ETCH/GND", help="plane layer (unused "
                    "for geometry; the via is a through via)")
    ap.add_argument("--skip", default="", help="comma-separated pins to leave "
                    "alone, e.g. R14.2,R18.1")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    with AllegroBridge() as br:
        flush(br)
        print("ping:", br.ping())
        targets, pads, vias, segs = load(br, args.net, LAYER)
        tied = already_tied(br, args.net)
        skipped_done = sorted(t[0] for t in targets if t[0] in tied)
        targets = [t for t in targets if t[0] not in skip and t[0] not in tied]
        if skipped_done:
            print(f"  already tied, left alone: {' '.join(skipped_done)}")
        by_name = {t[0]: t for t in targets}
        print(f"  {len(targets)} SMD pins on {args.net}, "
              f"{len(pads)} foreign pads, {len(vias)} foreign vias, "
              f"{sum(len(v) for v in segs.values())} foreign segments on "
              f"{len(segs)} layer(s)")
        if skip:
            print(f"  skipping: {' '.join(sorted(skip))}")

        groups, taken = [], set()
        for a, b in pairs_for(args.net):
            if a in by_name and b in by_name:
                groups.append([by_name[a], by_name[b]])
                taken |= {a, b}
        for t in targets:
            if t[0] not in taken:
                groups.append([t])

        plan, failed = [], []
        for g in groups:
            got = solve(g, pads, vias, segs)
            label = "+".join(n for n, _, _ in g)
            if not got:
                failed.append(label)
                print(f"  {label:16} NO CLEAR POSITION FOUND")
                continue
            rad, dx, dy, worst = got
            tag = "pair" if len(g) > 1 else "single"
            print(f"  {label:16} {tag:6} offset ({dx:+7.2f},{dy:+7.2f}) "
                  f"= {rad:3d} mil   worst clearance {worst:5.1f}")
            for name, x, y in g:
                plan.append((name, (x, y), (x + dx, y + dy)))
        if failed:
            print(f"\n  *** {len(failed)} group(s) unplaced: "
                  f"{' '.join(failed)} ***", file=sys.stderr)
            return 1

        print(f"\n  {len(plan)} vias + {len(plan)} stubs")
        if not args.apply:
            return 0

        d0 = br.send("length(axlDBGetDesign()->drcs)").strip()
        for name, pin, via in plan:
            r = br.send(f'axlDBCreateVia("{VIA}" {via[0]}:{via[1]} '
                        f'"{args.net}" nil 0.0)')
            if "dbid" not in r:
                print(f"  *** via for {name} failed: {r[:60]}", file=sys.stderr)
                return 1
        flush(br)
        for name, pin, via in plan:
            r = br.send(f'axlDBCreateLine(list({pin[0]}:{pin[1]} '
                        f'{via[0]}:{via[1]}) {STUB_W} "{LAYER}" "{args.net}")')
            ok = "dbid" in r
            print(f"  {name:8} ({pin[0]:.0f},{pin[1]:.0f}) -> "
                  f"({via[0]:.0f},{via[1]:.0f})  {'ok' if ok else r[:50]}")
            if not ok:
                return 1
        flush(br)
        br.send(f'ppN = car(setof(x axlDBGetDesign()->nets x->name=="{args.net}"))')
        print(f"\n  DRC {d0} -> {br.send('length(axlDBGetDesign()->drcs)').strip()}"
              f"   {args.net} unconn "
              f"{br.send('ppN->unconnected').strip()}  branches "
              f"{br.send('ppN->nBranches').strip()}")
        print("\n  NOT saved. Run place_check.py and dangle_check.py first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
