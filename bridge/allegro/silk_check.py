"""Silkscreen audit and cleanup for an Allegro / OrCAD PCB Designer board.

    python bridge/allegro/silk_check.py            # report only
    python bridge/allegro/silk_check.py --clean    # delete the printable clutter
    python bridge/allegro/silk_check.py --clean --dry-run

WHY THIS EXISTS

A footprint carries up to five separate text items per part, and each one can
be instantiated on SILKSCREEN, ASSEMBLY *and* DISPLAY, top and bottom:

    REF DES            the one you want printed
    DEVICE TYPE        <device>_<package>_<class>_<value>_<part number>,
                       concatenated -- routinely over 1000 mil wide
    COMPONENT VALUE
    USER PART NUMBER
    TOLERANCE

Only REF DES belongs on silkscreen. The rest are documentation fields that
belong on ASSEMBLY, which is a drawing layer and is not printed on the board.
Measured on a real 53-part board: one DEVICE TYPE string on SILKSCREEN_TOP was
**1925 mil wide** -- wider than the board -- and ten parts carried four junk
strings each, all stacked at the same y, on top of each other and the pads.

None of this shows up in DRC. Silkscreen is not copper, so it violates no
spacing rule; the board is "clean" all the way to the fab, who then either
prints it or clips it, and either way the refdes underneath is unreadable.

WHAT IS KEPT, AND WHY THE KEEP-LIST IS NOT JUST "REF DES"

    REF DES            what the assembler reads
    PACKAGE GEOMETRY   the pin-1 marker lives here, usually as a bare "*"

Deleting PACKAGE GEOMETRY text would silently remove pin-1 indication -- an
orientation defect on exactly the parts (polarised, fine-pitch) where getting
it wrong is expensive. The keep-list is by CLASS, not by content, so a marker
drawn as something other than "*" is kept too.

ASSEMBLY and DISPLAY subclasses are never touched. ASSEMBLY is the assembly
drawing the vendor actually wants; DISPLAY is screen-only and is not exported.

DELETION IS BY dbid, IN A CAPPED LOOP

`axlDBGetAttachedText` returns a materialised list, but deleting from under an
iteration has bitten this project before (branch indices renumber on every
delete, handoff 5). So: delete, re-scan from scratch, repeat until a clean
pass, with an iteration cap. A loop against a live database that can only
terminate on success is how a repair loop once issued several hundred deletes.
"""
from __future__ import annotations

import sys
import argparse
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from allegro_client import AllegroBridge  # noqa: E402

# Text CLASSES that may legitimately appear on a silkscreen subclass.
# Everything else on silkscreen is documentation and is deleted by --clean.
#
# BOARD GEOMETRY is here because board-level text -- the title, a revision, a
# warning legend -- is authored deliberately and is not part of any footprint.
# It was added after --clean was written: the delete pass only ever walked
# symbol-attached text, so design-level text was invisible to it. That is a
# safe blind spot right up until the reader is taught to see design text too,
# at which point the title becomes "clutter on an unrecognised class" and is
# deleted. Both halves changed together for that reason.
SILK_KEEP_CLASSES = ("REF DES", "PACKAGE GEOMETRY", "BOARD GEOMETRY")

MAX_PASSES = 5


def _skill(br: AllegroBridge, expr: str) -> str:
    out = br.send(expr)
    if out.startswith("ERROR"):
        raise RuntimeError(f"{expr} -> {out}")
    return out


def _floats(text: str) -> list[float]:
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


def _records(raw: str) -> list[str]:
    """Split a SKILL list-of-lists into its top-level record strings."""
    recs, depth, cur = [], 0, ""
    for ch in raw.strip().strip('"')[1:-1]:
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


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------
def flush_caches(br: AllegroBridge) -> None:
    """design->symbols and ->bBox serve stale values after a GUI move."""
    br.send("axlDBTransactionCommit(axlDBTransactionStart())")


def text_inventory(br: AllegroBridge) -> dict[str, int]:
    raw = _skill(br, 'let((h r) h=makeTable("h" 0) '
                     'foreach(s axlDBGetDesign()->symbols '
                     'foreach(tt axlDBGetAttachedText(s) h[tt->layer]=h[tt->layer]+1)) '
                     'foreach(tt axlDBGetAttachedText(axlDBGetDesign()) '
                     'h[tt->layer]=h[tt->layer]+1) '
                     'r="" foreach(k h r=strcat(r sprintf(nil "[%s=%L]" k h[k]))) r)')
    out: dict[str, int] = {}
    for chunk in raw.strip('"').split("["):
        if "=" not in chunk:
            continue
        layer, _, n = chunk.rstrip("]").rpartition("=")
        try:
            out[layer] = int(n)
        except ValueError:
            pass
    return out


def silk_text(br: AllegroBridge, keep: bool) -> list[tuple]:
    """Silkscreen text, either the keep-list classes or everything else.

    Returned as (refdes, layer, text, x0, y0, x1, y1). Split into two queries
    because a single query for all silkscreen text on a busy board returns a
    line long enough to be worth not finding out about the hard way -- the
    bridge protocol is one line per response, with no chunking.
    """
    cls_test = " || ".join(
        f'rexMatchp("^{c}/" tt->layer)' for c in SILK_KEEP_CLASSES)
    want = cls_test if keep else f"!({cls_test})"
    # Symbol-attached text AND design-level text. The design is passed to
    # axlDBGetAttachedText the same way a symbol is; text created with
    # o_attach = nil hangs off the design and appears nowhere in ->symbols.
    raw = _skill(br, 'let( ((r nil)) foreach(s axlDBGetDesign()->symbols '
                     'foreach(tt axlDBGetAttachedText(s) '
                     'when(rexMatchp("SILKSCREEN" tt->layer) && ' + want + ' '
                     'r=cons(list(s->refdes tt->layer tt->text tt->bBox) r)))) '
                     'foreach(tt axlDBGetAttachedText(axlDBGetDesign()) '
                     'when(rexMatchp("SILKSCREEN" tt->layer) && ' + want + ' '
                     'r=cons(list("<board>" tt->layer tt->text tt->bBox) r))) r)')
    out = []
    for rec in _records(raw):
        q = rec.split('"')
        if len(q) < 6:
            continue
        refdes, layer, text = q[1], q[3], q[5]
        nums = _floats(q[6] if len(q) > 6 else "")
        if len(nums) >= 4:
            out.append((refdes, layer, text, *nums[:4]))
    return out


def pin_boxes(br: AllegroBridge) -> list[tuple]:
    """(refdes, pin number, x0, y0, x1, y1) -- pin bBox is the true pad extent."""
    raw = _skill(br, 'let( ((r nil)) foreach(s axlDBGetDesign()->symbols '
                     'foreach(p s->pins r=cons(list(s->refdes p->number p->bBox) r))) r)')
    out = []
    for rec in _records(raw):
        q = rec.split('"')
        if len(q) < 4:
            continue
        nums = _floats(q[4] if len(q) > 4 else "")
        if len(nums) >= 4:
            out.append((q[1], q[3], *nums[:4]))
    return out


def silk_graphics(br: AllegroBridge) -> list[tuple]:
    """(refdes, x0, y0, x1, y1) for silkscreen LINE work -- the body outlines.

    Text-vs-pad was the only overlap this tool originally checked, and it
    passed a board title that visibly collided with a component outline: the
    outline is `path` children on PACKAGE GEOMETRY/SILKSCREEN_TOP, not text
    and not a pad, so nothing in the check could see it. A human caught it by
    looking at the screen.

    bBox on a path is a bounding box, so an L-shaped or diagonal path claims
    more area than its ink covers. That makes this advisory, not a gate.

    ⛔ THREE objTypes, not two. Body outlines are drawn as `path` on some
    footprints, `shape` on others and **`polygon`** on others again -- the
    hand-built FILMCAP5MM uses polygon. Filtering on path|shape silently
    excluded every film cap on the board from the outline check. Found by
    enumerating one symbol's children rather than trusting the filter.

    ⛔ SKILL's rexMatchp has no `|` alternation. `rexMatchp("A|B" x)` does not
    error, it just never matches -- which reads as "no such objects exist".
    Test each alternative separately.
    """
    raw = _skill(br, 'let( ((r nil)) foreach(s axlDBGetDesign()->symbols '
                     'foreach(c s->children '
                     'when((c->objType=="path" || c->objType=="shape" || '
                     'c->objType=="polygon") && '
                     'rexMatchp("SILKSCREEN" c->layer) '
                     'r=cons(list(s->refdes c->bBox) r)))) r)')
    out = []
    for rec in _records(raw):
        q = rec.split('"')
        if len(q) < 2:
            continue
        nums = _floats(q[2] if len(q) > 2 else "")
        if len(nums) >= 4:
            out.append((q[1], *nums[:4]))
    return out


def _overlap(a: tuple, b: tuple) -> bool:
    """Rectangle intersection on (x0, y0, x1, y1)."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def report(br: AllegroBridge) -> int:
    flush_caches(br)

    print("=== 1. TEXT INVENTORY BY SUBCLASS ===")
    inv = text_inventory(br)
    for layer in sorted(inv, key=lambda k: (-inv[k], k)):
        mark = ""
        if "SILKSCREEN" in layer and not layer.startswith(SILK_KEEP_CLASSES):
            mark = "  <-- printed, and should not be"
        print(f"  {inv[layer]:4}  {layer}{mark}")

    print("\n=== 2. PRINTABLE CLUTTER ON SILKSCREEN ===")
    junk = silk_text(br, keep=False)
    if not junk:
        print("  none -- silkscreen carries only refdes and package geometry")
    else:
        widest = 0.0
        for refdes, layer, text, x0, y0, x1, y1 in sorted(junk):
            w = x1 - x0
            widest = max(widest, w)
            cls = layer.split("/")[0]
            print(f"  {refdes:5} {cls:18} {w:7.1f} mil  {text[:44]}")
        print(f"\n  {len(junk)} text objects, widest {widest:.0f} mil")

    print("\n=== 3. SILK TEXT / PAD OVERLAP ===")
    keep = silk_text(br, keep=True)
    refdes_text = [r for r in keep if r[1].startswith("REF DES")]
    pins = pin_boxes(br)
    hits: dict[str, list[str]] = {}
    # Everything kept on silkscreen is checked, not just refdes: a pin-1
    # marker or a board title sitting on a pad is the same defect, and only
    # the refdes case is fixable automatically.
    for rd, _layer, text, *tbox in keep:
        for prd, pnum, *pbox in pins:
            if _overlap(tuple(tbox), tuple(pbox)):
                hits.setdefault(text, []).append(f"{prd}.{pnum}")
    if not hits:
        print("  none")
    else:
        total = sum(len(v) for v in hits.values())
        for text in sorted(hits, key=lambda k: -len(hits[k])):
            pads = hits[text]
            print(f"  {text:6} over {len(pads):3} pad(s): "
                  f"{', '.join(pads[:8])}{' ...' if len(pads) > 8 else ''}")
        print(f"\n  {total} pad(s) under refdes text, {len(hits)} refdes involved")

    print("\n=== 3b. SILK TEXT OVER SILK TEXT ===")
    # Three overlapping pairs survived five consecutive clean audits because
    # this comparison did not exist -- the largest was 139 x 42 mil, plainly
    # visible on screen. The mover avoided *creating* collisions, which is not
    # the same as detecting them.
    pairs = []
    for i in range(len(keep)):
        for j in range(i + 1, len(keep)):
            a, b = keep[i], keep[j]
            if _overlap(tuple(a[3:]), tuple(b[3:])):
                ox = min(a[5], b[5]) - max(a[3], b[3])
                oy = min(a[6], b[6]) - max(a[4], b[4])
                pairs.append((ox * oy, a[2], b[2], ox, oy))
    if not pairs:
        print("  none")
    else:
        for _area, t1, t2, ox, oy in sorted(pairs, reverse=True):
            print(f"  {t1!r} x {t2!r}  overlap {ox:.0f} x {oy:.0f} mil")
        print(f"\n  {len(pairs)} overlapping pair(s)")

    print("\n=== 4. SILK TEXT OVER ANOTHER PART'S OUTLINE (advisory) ===")
    gfx = silk_graphics(br)
    clashes = []
    for rd, _layer, text, *tbox in keep:
        for grd, *gbox in gfx:
            # Text on its own part's outline is normal -- a 0805 refdes sits on
            # the body as a matter of course. Only a foreign outline, or board
            # text over any outline, is worth a human's attention.
            if grd == rd:
                continue
            if _overlap(tuple(tbox), tuple(gbox)):
                clashes.append((text, rd, grd))
    if not clashes:
        print("  none")
    else:
        seen = set()
        for text, rd, grd in clashes:
            if (text, grd) in seen:
                continue
            seen.add((text, grd))
            print(f"  {text!r} ({rd}) over {grd}'s outline")
        print(f"\n  {len(seen)} advisory overlap(s)")

    print("\n=== 5. PARTS WITH NO SILKSCREEN REFDES ===")
    labelled = {r[0] for r in refdes_text}
    allsyms = _skill(br, 'let( ((r nil)) foreach(s axlDBGetDesign()->symbols '
                          'r=cons(s->refdes r)) r)')
    every = [s for s in allsyms.split('"') if s.strip() and s.strip() not in "() "]
    missing = sorted(set(every) - labelled)
    print("  none" if not missing else f"  {len(missing)}: {' '.join(missing)}")

    return len(junk)


# --------------------------------------------------------------------------
# Clean
# --------------------------------------------------------------------------
def clean(br: AllegroBridge, dry_run: bool) -> int:
    cls_test = " || ".join(
        f'rexMatchp("^{c}/" tt->layer)' for c in SILK_KEEP_CLASSES)

    if dry_run:
        n = len(silk_text(br, keep=False))
        print(f"  --dry-run: would delete {n} silkscreen text object(s)")
        return 0

    # Writes are silently discarded while a GUI command is active, and the
    # cheapest discriminator is a save that returns nil (handoff 1).
    if _skill(br, "axlSaveDesign(?noConfirm t)").strip() in ("nil", '"nil"', ""):
        print("  axlSaveDesign returned nil -- a GUI command is active. "
              "Clear it in Allegro and re-run. Nothing was changed.")
        return 1

    total = 0
    for attempt in range(MAX_PASSES):
        raw = _skill(br, 'let((n) n=0 foreach(s axlDBGetDesign()->symbols '
                         'foreach(tt axlDBGetAttachedText(s) '
                         'when(rexMatchp("SILKSCREEN" tt->layer) && !(' + cls_test + ') '
                         'when(axlDeleteObject(tt) n=n+1)))) n)')
        deleted = int(_floats(raw)[0]) if _floats(raw) else 0
        total += deleted
        left = len(silk_text(br, keep=False))
        print(f"  pass {attempt + 1}: deleted {deleted}, {left} remaining")
        if left == 0:
            break
        if deleted == 0:
            print("  no progress this pass -- stopping rather than spinning")
            return 1
    else:
        print(f"  hit the {MAX_PASSES}-pass cap with work outstanding")
        return 1

    print(f"  {total} silkscreen text object(s) deleted")
    saved = _skill(br, "axlSaveDesign(?noConfirm t)")
    print(f"  save -> {saved}")
    return 0


# --------------------------------------------------------------------------
# Move refdes text off pads
# --------------------------------------------------------------------------
# Ring search, same shape as route_to_plane: try the nearest legal spot first
# and widen. Directions are ordered cardinals-first because a refdes reads
# best directly above or below its part, and a diagonal offset is more likely
# to sit ambiguously between two parts.
_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0),
         (1, 1), (-1, 1), (1, -1), (-1, -1)]


def _shift(box: tuple, dx: float, dy: float) -> tuple:
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def fix_overlap(br: AllegroBridge, dry_run: bool) -> int:
    flush_caches(br)
    pins = [tuple(p[2:]) for p in pin_boxes(br)]
    allsilk = silk_text(br, keep=True)
    keep = [r for r in allsilk if r[1].startswith("REF DES")]

    # Only refdes is moved automatically. A refdes can travel 400 mil and stay
    # readable; a pin-1 marker that wanders to the wrong end of a package is
    # worse than no marker at all, and a board title has a deliberate position.
    # Those are reported for a human instead of being shoved.
    manual = [r for r in allsilk if not r[1].startswith("REF DES")
              and any(_overlap(tuple(r[3:]), p) for p in pins)]
    for rd, layer, text, *_ in manual:
        print(f"  MANUAL  {layer.split('/')[0]} {text!r} on {rd} overlaps a pad "
              f"-- not moved automatically")

    # Live set of label boxes, updated as each move is applied, so two labels
    # cannot be moved onto each other. Seeded with EVERY kept silk object, not
    # just refdes, so a move cannot land on the board title or a pin-1 marker.
    boxes = {r[0]: tuple(r[3:]) for r in keep}
    fixed_obstacles = [tuple(r[3:]) for r in allsilk
                       if not r[1].startswith("REF DES")]

    def _bad(rd: str, box: tuple) -> bool:
        # A label is misplaced if it lands on a pad, on another label, or on
        # any non-refdes silk object (board title, pin-1 marker).
        #
        # Label-on-label was missing until three overlapping pairs -- one of
        # them 139 x 42 mil -- survived five consecutive clean audits. The
        # mover already avoided creating such a collision; nothing ever
        # checked for one that was there to begin with. Avoiding a defect you
        # never test for only works if you caused all of them.
        if any(_overlap(box, p) for p in pins):
            return True
        if any(_overlap(box, b) for k, b in boxes.items() if k != rd):
            return True
        return any(_overlap(box, o) for o in fixed_obstacles)

    bad = [rd for rd, box in boxes.items() if _bad(rd, box)]
    if not bad:
        print("  no refdes text overlaps a pad, a label or board text")
        return 1 if manual else 0

    moved, stuck = 0, []
    for rd in sorted(bad):
        box = boxes[rd]
        # Moving one half of an overlapping pair clears both. Re-test against
        # the live box set rather than the snapshot `bad` was computed from,
        # so the partner is left where it is instead of being shoved too.
        if not _bad(rd, box):
            print(f"  {rd:5} already clear -- partner moved")
            continue
        others = [b for k, b in boxes.items() if k != rd] + fixed_obstacles
        found = None
        for radius in range(20, 401, 10):
            for dx_u, dy_u in _DIRS:
                dx, dy = dx_u * radius, dy_u * radius
                cand = _shift(box, dx, dy)
                if any(_overlap(cand, p) for p in pins):
                    continue
                if any(_overlap(cand, o) for o in others):
                    continue
                found = (dx, dy, cand)
                break
            if found:
                break
        if not found:
            stuck.append(rd)
            continue

        dx, dy, cand = found
        print(f"  {rd:5} move ({dx:+.0f}, {dy:+.0f}) mil")
        if not dry_run:
            expr = ('let((s tt) s=car(setof(q axlDBGetDesign()->symbols '
                    f'q->refdes=="{rd}")) '
                    'tt=car(setof(x axlDBGetAttachedText(s) '
                    'x->layer=="REF DES/SILKSCREEN_TOP")) '
                    f'sprintf(nil "%L" axlTransformObject(tt ?move list({dx:.1f} {dy:.1f}))))')
            res = _skill(br, expr)
            if res.strip().strip('"') in ("nil", ""):
                print(f"        axlTransformObject returned nil -- not moved")
                stuck.append(rd)
                continue
        boxes[rd] = cand
        moved += 1

    if stuck:
        print(f"\n  {len(stuck)} could not be placed: {' '.join(stuck)}")
    if dry_run:
        print(f"\n  --dry-run: {moved} would move")
        return 0
    print(f"\n  {moved} refdes moved")
    print(f"  save -> {_skill(br, 'axlSaveDesign(?noConfirm t)')}")
    return 1 if stuck else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clean", action="store_true",
                    help="delete non-REF-DES, non-PACKAGE-GEOMETRY silkscreen text")
    ap.add_argument("--fix-overlap", action="store_true",
                    help="move refdes text off pads")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    with AllegroBridge() as br:
        if args.fix_overlap:
            rc = fix_overlap(br, args.dry_run)
            if not args.dry_run:
                print()
                report(br)
            return rc
        if args.clean:
            rc = clean(br, args.dry_run)
            if rc == 0 and not args.dry_run:
                print()
                report(br)
            return rc
        report(br)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(sys.argv[1:]))
