"""Placement checker for an OrCAD PCB Designer / Allegro board, over the bridge.

Reads the live board and reports the things that are tedious to verify by eye
and mechanical to verify by machine:

  1. DRC count and violation types
  2. Every placed part's margin to the place keepin
  3. Part-to-part bounding-box overlap
  4. Mains creepage -- measured distance from primary-side copper to the
     nearest non-primary pin, and to the nearest mounting hole
  5. Distance from a noise aggressor (e.g. a mains transformer) to named
     sensitive nets, reported per channel
  6. Channel symmetry -- whether paired parts sit at matching offsets

Usage:
    python bridge/allegro/place_check.py                 # uses the profile below
    python bridge/allegro/place_check.py --profile none  # geometry checks only

Everything except the mounting holes is read from the board. Hole positions
are configured, because standalone vias are not reachable from any design
attribute (`design->vias` does not exist) and the selection API is
interactive -- which blocks the bridge. Configuring them is the honest
option; an unconfigured run says so rather than silently skipping the check.
"""
from __future__ import annotations

import math
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from allegro_client import AllegroBridge  # noqa: E402
from bridge.allegro import board_profile  # noqa: E402


# --------------------------------------------------------------------------
# Design profile. Edit for a different board; the geometry checks need none of it.
# --------------------------------------------------------------------------
# Everything this checker needs to know about the SPECIFIC board -- which nets
# carry mains, where the mounting holes are, which net is the sensitive input
# on each channel, which refdes are a stereo pair -- is design data, and design
# data does not live in a tooling repo. It comes from `board.json`, which is
# gitignored; `board.example.json` shows the shape.
#
# The keys are documented there. Briefly:
#   primary_nets      creepage is measured from these to everything else
#   mounting_holes    (x, y, pad_radius); configured because standalone vias
#                     are not reachable from the API (see the docstring)
#   aggressor         part whose stray field is measured to the sensitive nets
#   channel_net_pairs same net role on each channel, compared for length
#                     asymmetry -- a net much longer on ONE channel is both a
#                     pickup risk and a matching problem, and it shows up in
#                     no absolute total
#   symmetry_pairs    parts expected to sit at matching offsets
def _profile() -> dict:
    cfg = board_profile.load("place_check")
    return {
        "primary_nets": set(cfg["primary_nets"]),
        "mounting_holes": [tuple(h) for h in cfg["mounting_holes"]],
        "aggressor": cfg["aggressor"],
        "sensitive": cfg["sensitive"],
        "channel_net_pairs": [tuple(t) for t in cfg["channel_net_pairs"]],
        "symmetry_pairs": [tuple(t) for t in cfg["symmetry_pairs"]],
    }


PROFILE = _profile()

MIL_TO_MM = 0.0254


# --------------------------------------------------------------------------
# Board queries
# --------------------------------------------------------------------------
def _skill(br: AllegroBridge, expr: str) -> str:
    out = br.send(expr)
    if out.startswith("ERROR"):
        raise RuntimeError(f"{expr} -> {out}")
    return out


def _floats(text: str) -> list[float]:
    """Pull every number out of a SKILL list response, in order."""
    out, tok = [], ""
    for ch in text:
        if ch in "-.0123456789":
            tok += ch
        else:
            if tok:
                try:
                    out.append(float(tok))
                except ValueError:
                    pass
                tok = ""
    if tok:
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


def read_board(br: AllegroBridge) -> dict:
    board: dict = {}

    # Flush the read caches FIRST. design->symbols and a symbol's ->xy,
    # ->rotation and ->bBox all serve stale values after the GUI has moved
    # something, with no error and no indication (see handoff 7.3/7.4). An
    # empty transaction forces the refresh.
    #
    # This was missing until 2026-07-30, when the user moved T1 by 510 mil and
    # this script went on reporting the old body centre -- and therefore an
    # aggressor distance and channel imbalance computed against a board that
    # no longer existed. A checker reporting stale geometry is worse than no
    # checker, because it reads as confirmation.
    br.send("axlDBTransactionCommit(axlDBTransactionStart())")

    board["module"] = _skill(br, 'axlGetVariable("module")').strip('"')
    board["drc_count"] = int(_floats(_skill(br, "length(axlDBGetDesign()->drcs)"))[0])

    drcs = _skill(br, 'mapcar(lambda((d) d->name) axlDBGetDesign()->drcs)')
    board["drc_names"] = [s for s in drcs.replace("(", " ").replace(")", " ").split('"') if s.strip()]

    for key, expr in (("outline", "axlDBGetDesign()->designOutline->bBox"),
                      ("keepin_place", "axlDBGetDesign()->keepinPlace->bBox"),
                      ("keepin_route", "axlDBGetDesign()->keepinRoute->bBox")):
        try:
            v = _floats(_skill(br, expr))
            board[key] = tuple(v[:4]) if len(v) >= 4 else None
        except RuntimeError:
            board[key] = None

    # Symbols: refdes, bBox. Returned one record per line-safe chunk.
    raw = _skill(br, 'let( ((r nil)) foreach(s axlDBGetDesign()->symbols '
                     'r=cons(list(s->refdes s->bBox) r)) r)')
    board["symbols"] = _parse_symbols(raw)

    raw = _skill(br, 'let( ((r nil)) foreach(s axlDBGetDesign()->symbols foreach(p s->pins '
                     'r=cons(list(s->refdes p->number car(p->xy) cadr(p->xy) '
                     'if(p->net p->net->name "-")) r))) r)')
    board["pins"] = _parse_pins(raw)
    return board


def _records(raw: str) -> list[str]:
    """Split a SKILL list-of-lists into its top-level record strings."""
    recs, depth, cur = [], 0, ""
    for ch in raw.strip()[1:-1]:
        if ch == "(":
            depth += 1
            if depth == 1:
                cur = ""
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                recs.append(cur)
                continue
        if depth >= 1:
            cur += ch
    return recs


def _parse_symbols(raw: str) -> dict[str, tuple]:
    out = {}
    for rec in _records(raw):
        parts = rec.split('"')
        if len(parts) < 2:
            continue
        nums = _floats(rec[rec.find(parts[1]) + len(parts[1]):])
        if len(nums) >= 4:
            out[parts[1]] = tuple(nums[:4])
    return out


def _parse_pins(raw: str) -> list[tuple]:
    out = []
    for rec in _records(raw):
        q = [s for s in rec.split('"')]
        if len(q) < 4:
            continue
        refdes, number = q[1], q[3]
        net = q[5] if len(q) > 5 else ""
        nums = _floats(q[4] if len(q) > 4 else "")
        if len(nums) >= 2:
            out.append((refdes, number, nums[0], nums[1], net))
    return out


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
def _bbox_gap(box: tuple, px: float, py: float) -> float:
    x0, y0, x1, y1 = box
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return math.hypot(dx, dy)


def _boxes_overlap(a: tuple, b: tuple) -> float:
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    return min(ox, oy) if ox > 0 and oy > 0 else 0.0


def run_checks(board: dict, profile: dict) -> int:
    problems = 0
    p = print

    p(f"\nBoard: {board['module']}")
    p(f"Placed parts: {len(board['symbols'])}    Pins: {len(board['pins'])}")

    p("\n=== 1. DRC ===")
    if board["drc_count"] == 0:
        p("  0 violations")
    else:
        problems += 1
        p(f"  {board['drc_count']} violations")
        for name in sorted(set(board["drc_names"])):
            p(f"    {board['drc_names'].count(name):3} x {name}")

    p("\n=== 2. PLACE KEEPIN MARGIN ===")
    ki = board.get("keepin_place")
    if not ki:
        p("  no place keepin found -- skipped")
    else:
        rows = []
        for ref, box in board["symbols"].items():
            m = min(box[0] - ki[0], box[1] - ki[1], ki[2] - box[2], ki[3] - box[3])
            rows.append((m, ref))
        for m, ref in sorted(rows):
            flag = "  *** OUTSIDE ***" if m < 0 else ("  (tight)" if m < 50 else "")
            if m < 0:
                problems += 1
            p(f"  {ref:5} {m:9.1f} mil{flag}")

    # NOTE: s->bBox includes the SILKSCREEN REFDES TEXT, not just the package.
    # Measured 2026-07-30: SMR0805 reports 506 x 191 mil where the pads span
    # ~120 x 80, and DFN12_DD reports 1925 x 148 -- thinner than the real part.
    # So this test flags LABEL collisions as part overlaps and is advisory only.
    # Allegro's own "Package to Package Spacing" DRC (section 1) is the
    # authority: a run with 32 overlaps here had just 3 real violations.
    p("\n=== 3. LABEL / BODY OVERLAP (advisory -- bBox includes refdes text) ===")
    refs = sorted(board["symbols"])
    hits = []
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            ov = _boxes_overlap(board["symbols"][a], board["symbols"][b])
            if ov > 0:
                hits.append((ov, a, b))
    if not hits:
        p("  none")
    else:
        # Deliberately does NOT increment `problems`: section 1 decides that.
        p(f"  {len(hits)} pair(s) with overlapping bounding boxes.")
        p("  These are mostly refdes-text collisions; check section 1 for real DRCs.")
        for ov, a, b in sorted(hits, reverse=True)[:8]:
            p(f"    {a} / {b}  {ov:.1f} mil")
        if len(hits) > 8:
            p(f"    ... and {len(hits) - 8} more")

    p("\n=== 4. MAINS CREEPAGE ===")
    prim_nets = profile.get("primary_nets") or set()
    prim = [x for x in board["pins"] if x[4] in prim_nets]
    if not prim:
        p("  no primary nets configured or present -- skipped")
    else:
        other = [x for x in board["pins"] if x[4] not in prim_nets and x[4] not in ("", "-")]
        if other:
            d, a, b = min(((math.hypot(a[2] - b[2], a[3] - b[3]), a, b)
                           for a in prim for b in other), key=lambda t: t[0])
            p(f"  to nearest non-primary pin : {a[0]}.{a[1]} -> {b[0]}.{b[1]}"
              f"  {d:.0f} mil = {d * MIL_TO_MM:.1f} mm")
        holes = profile.get("mounting_holes") or []
        if not holes:
            p("  mounting holes NOT CONFIGURED -- hole creepage not checked")
        else:
            d, a, h = min(((math.hypot(a[2] - hx, a[3] - hy) - hr, a, (hx, hy))
                           for a in prim for hx, hy, hr in holes), key=lambda t: t[0])
            p(f"  to nearest mounting hole   : {a[0]}.{a[1]} -> {h}"
              f"  {d:.0f} mil = {d * MIL_TO_MM:.1f} mm")

    p("\n=== 5. PART TO MOUNTING HOLE ===")
    holes = profile.get("mounting_holes") or []
    if not holes:
        p("  mounting holes NOT CONFIGURED -- skipped")
    else:
        rows = []
        for ref, box in board["symbols"].items():
            for hx, hy, hr in holes:
                rows.append((_bbox_gap(box, hx, hy) - hr, ref, (hx, hy)))
        for d, ref, h in sorted(rows)[:5]:
            flag = "  *** COLLIDES ***" if d < 0 else ""
            if d < 0:
                problems += 1
            p(f"  {ref:5} -> hole {str(h):18} {d:8.1f} mil{flag}")

    p("\n=== 6. AGGRESSOR DISTANCE ===")
    agg = profile.get("aggressor")
    if not agg or agg not in board["symbols"]:
        p("  aggressor not placed -- skipped")
    else:
        box = board["symbols"][agg]
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        p(f"  {agg} body centre: ({cx:.0f}, {cy:.0f})")
        # Report BOTH nearest-pin and mean-over-pins. Nearest alone is
        # misleading: after the 2026-07-30 placement the nearest pin on each
        # input net became its op-amp, placed symmetrically, giving 0.1 dB --
        # while the jacks, also on those nets, still differ by ~790 mil and
        # leave ~1.0 dB. Quoting only the nearest figure overstates the fix.
        nearest, means = {}, {}
        for chan, net in (profile.get("sensitive") or {}).items():
            hits = [x for x in board["pins"] if x[4] == net]
            if not hits:
                p(f"  {chan:6} net {net}: not found")
                continue
            ds = [math.hypot(cx - x[2], cy - x[3]) for x in hits]
            nearest[chan] = min(ds)
            means[chan] = sum(ds) / len(ds)
            far = max(ds)
            p(f"  {chan:6} net {net:10} nearest {min(ds):6.0f}  mean {means[chan]:6.0f}"
              f"  farthest {far:6.0f} mil  ({len(ds)} pins)")

        # |B| of a magnetic dipole falls as 1/r^3 and induced voltage is
        # proportional to B, so this is a field ratio: 20*log10, no square root.
        def _imbalance(label, d):
            if len(d) != 2:
                return
            (n1, d1), (n2, d2) = sorted(d.items(), key=lambda kv: kv[1])
            p(f"  imbalance ({label:7}): {n1} closer by {d2 - d1:4.0f} mil"
              f"  -> ~{20 * math.log10((d2 / d1) ** 3):.1f} dB more coupling")

        _imbalance("nearest", nearest)
        _imbalance("mean", means)

    # ---- connection length -------------------------------------------------
    # Minimum spanning tree over each net's pins: a good proxy for ratsnest
    # length, and the best single number for "is this placement any good"
    # before routing starts.
    p("\n=== 6b. CONNECTION LENGTH (MST per net) ===")
    bynet: dict[str, list] = {}
    for x in board["pins"]:
        if x[4] not in ("", "-"):
            bynet.setdefault(x[4], []).append(x)

    def _mst(pts) -> float:
        if len(pts) < 2:
            return 0.0
        inside, outside, total = [0], list(range(1, len(pts))), 0.0
        while outside:
            d, j = min(((math.hypot(pts[i][2] - pts[j][2], pts[i][3] - pts[j][3]), j)
                        for i in inside for j in outside), key=lambda t: t[0])
            total += d
            inside.append(j)
            outside.remove(j)
        return total

    lens = sorted(((_mst(v), k, len(v)) for k, v in bynet.items()), reverse=True)
    tot = sum(L for L, _, _ in lens)
    p(f"  total {tot:.0f} mil = {tot / 1000:.1f} in over {len(lens)} nets")
    for L, k, n in lens[:6]:
        p(f"    {k:16} {n:2d} pins  {L:6.0f} mil")

    # Read the ratios with node impedance in mind -- they are not equally
    # meaningful. A large ratio on a run that sits downstream of a series
    # isolation resistor, driven at low impedance, is usually benign, and
    # "fixing" it by moving that resistor often just moves the length
    # somewhere else while pulling the resistor away from the pin it protects.
    # The same ratio on a high-impedance input is a real problem.
    # And a length can be the PRICE OF SOMETHING ELSE rather than an oversight:
    # shortening one input run may mean sliding its amplifier hundreds of mil
    # closer to the aggressor this script measures in the section above. Check
    # that before "fixing" an asymmetry reported here.
    cpairs = profile.get("channel_net_pairs") or []
    if cpairs:
        p("  left/right asymmetry:")
        for a_net, b_net in cpairs:
            la, lb = _mst(bynet.get(a_net, [])), _mst(bynet.get(b_net, []))
            if la and lb:
                ratio = max(la, lb) / min(la, lb)
                flag = "   <-- check" if ratio > 1.5 else ""
                p(f"    {a_net:12} {la:6.0f}   {b_net:12} {lb:6.0f} mil"
                  f"   ratio {ratio:.2f}{flag}")

    p("\n=== 7. CHANNEL SYMMETRY ===")
    pairs = profile.get("symmetry_pairs") or []
    if not pairs:
        p("  no pairs configured -- skipped")
    for a, b in pairs:
        if a not in board["symbols"] or b not in board["symbols"]:
            p(f"  {a}/{b}: not both placed -- skipped")
            continue
        ba, bb = board["symbols"][a], board["symbols"][b]
        ca = ((ba[0] + ba[2]) / 2, (ba[1] + ba[3]) / 2)
        cb = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        p(f"  {a}@({ca[0]:.0f},{ca[1]:.0f})  {b}@({cb[0]:.0f},{cb[1]:.0f})"
          f"   dx={cb[0]-ca[0]:.0f}  dy={cb[1]-ca[1]:.0f}")

    p("\n" + "=" * 58)
    p("CLEAN" if problems == 0 else f"{problems} issue group(s) need attention")
    return problems


def main(argv: list[str]) -> int:
    profile = PROFILE
    if "--profile" in argv and argv[argv.index("--profile") + 1:]:
        if argv[argv.index("--profile") + 1] == "none":
            profile = {}
    try:
        with AllegroBridge() as br:
            board = read_board(br)
    except Exception as exc:  # noqa: BLE001 - report, do not traceback at the user
        print(f"could not read board: {exc}", file=sys.stderr)
        print("Is OrCAD PCB Designer running with the bridge started?", file=sys.stderr)
        return 2
    return 1 if run_checks(board, profile) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
