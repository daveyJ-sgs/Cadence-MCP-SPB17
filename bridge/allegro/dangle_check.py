"""Find cline endpoints that terminate on nothing.

    python bridge/allegro/dangle_check.py

RUN THIS AFTER EVERY ROUTING PASS, AND AFTER EVERY PART MOVE.

Neither of the checks we had would catch a floating trace:

  * DRC counts spacing violations. Copper going nowhere violates no spacing.
  * net->unconnected counts pins not reachable from the rest of the net. A
    stub that starts ON a pin and ends in mid-air leaves that pin perfectly
    connected, so the count does not move.

Both read 0 on a board with dead copper on it. On 2026-08-01 they read 0
while U5's OUT and OUTS sat 0.32 and 0.37 mil away from their traces -- the
positive rail was open at the regulator and nothing said so. It was spotted
by eye, on screen, by the engineer.

Two failure modes, and this catches both:

  NEAR-MISS   endpoint within 12 mil of a pin it was clearly meant to hit.
              Always a coordinate error -- the usual cause is routing to a
              number copied out of a design note instead of pin->xy. Allegro
              bonds a cline to a pad only on the EXACT point; landing inside
              the pad is not enough.

  floating    endpoint far from anything. Usually a trace left behind by a
              part move: clines do not follow the parts they connect.

For every chain endpoint, ask whether it lands on a pin, a via, another path
on the same net and layer, or inside a shape on the same net and layer. An
endpoint shared with the adjacent segment of its own path is interior, not
an end, and is skipped.
"""
import sys
import pathlib
import re

ROOT = pathlib.Path(r"C:\Users\16023\Documents\Claude_projs\Cadence")
sys.path.insert(0, str(ROOT))
from bridge.allegro.allegro_client import AllegroBridge  # noqa: E402

TOL = 0.05        # mil -- "same point"
NEAR = 12.0       # mil -- close enough to look intentional, which is the trap


def sexp(s):
    """Parse the helper's flattened SKILL list output into nested lists."""
    toks = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', s)
    def walk(i):
        out = []
        while i < len(toks):
            t = toks[i]
            if t == "(":
                sub, i = walk(i + 1)
                out.append(sub)
            elif t == ")":
                return out, i + 1
            else:
                out.append(t.strip('"'))
                i += 1
        return out, i
    v, _ = walk(0)
    return v[0] if len(v) == 1 and isinstance(v[0], list) else v


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pt(p):
    if not isinstance(p, list) or len(p) != 2:
        return None
    a, b = num(p[0]), num(p[1])
    return None if a is None or b is None else (a, b)


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def seg_dist(p, a, b):
    """Distance from p to segment ab."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 == 0:
        return dist(p, a)
    t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2
    t = max(0.0, min(1.0, t))
    return dist(p, (a[0] + t * vx, a[1] + t * vy))


def main():
    with AllegroBridge() as br:
        br.send("axlDBTransactionCommit(axlDBTransactionStart())")
        names = sexp(br.send('mapcar(lambda((n) n->name) axlDBGetDesign()->nets)'))
        print(f"{len(names)} nets\n")

        findings = []
        stats = {"paths": 0, "ends": 0}

        for net in names:
            br.send(f'ppN = car(setof(n axlDBGetDesign()->nets n->name=="{net}"))')
            nb = br.send("length(ppN->branches)").strip()
            nb = int(nb) if nb.isdigit() else 0
            if nb == 0:
                continue

            pins, vias, paths, shape_layers = [], [], [], {}
            # append() here takes exactly 2 args, so apply()-flattening the
            # branch lists fails on a 1-branch net. Walk them from Python.
            for bi in range(nb):
                br.send(f"ppK = nth({bi} ppN->branches)->children")
                pins += [p for p in (pt(x) for x in sexp(br.send(
                    'mapcar(lambda((c) c->xy) setof(c ppK c->objType=="pin"))'
                ))) if p]
                vias += [p for p in (pt(x) for x in sexp(br.send(
                    'mapcar(lambda((c) c->xy) setof(c ppK c->objType=="via"))'
                ))) if p]

                raw = sexp(br.send(
                    'mapcar(lambda((c) list(c->layer mapcar(lambda((s) '
                    's->startEnd) c->segments))) '
                    'setof(c ppK c->objType=="path"))'))
                for entry in raw:
                    if not isinstance(entry, list) or len(entry) != 2:
                        continue
                    layer = entry[0] if isinstance(entry[0], str) else "?"
                    segs = []
                    for se in entry[1]:
                        if isinstance(se, list) and len(se) == 2:
                            a, b = pt(se[0]), pt(se[1])
                            if a and b:
                                segs.append((a, b))
                    if segs:
                        paths.append((layer, segs))

                # Remember WHICH branch each shape layer was found in. ppK is
                # rebound every iteration, so testing against it after the loop
                # only ever searches the last branch -- which reported seven
                # phantom "floating" endpoints on a plane net's own thermal
                # spokes the moment it had more than one branch.
                for s in sexp(br.send('mapcar(lambda((c) c->layer) '
                                      'setof(c ppK c->objType=="shape"))')):
                    if isinstance(s, str):
                        shape_layers.setdefault(s, []).append(bi)
            stats["paths"] += len(paths)

            for i, (layer, segs) in enumerate(paths):
                ends = [segs[0][0], segs[-1][1]]
                for e in ends:
                    stats["ends"] += 1
                    # interior of its own chain? (closed loop / shared vertex)
                    own = sum(1 for a, b in segs
                              if dist(e, a) < TOL or dist(e, b) < TOL)
                    if own > 1:
                        continue

                    best, what = 1e9, None
                    for p in pins:
                        d = dist(e, p)
                        if d < best:
                            best, what = d, "pin"
                    for v in vias:
                        d = dist(e, v)
                        if d < best:
                            best, what = d, "via"
                    for j, (L2, s2) in enumerate(paths):
                        if j == i or L2 != layer:
                            continue
                        for a, b in s2:
                            d = seg_dist(e, a, b)
                            if d < best:
                                best, what = d, f"path#{j}"
                    if best < TOL:
                        continue
                    in_shape = False
                    for bi in shape_layers.get(layer, []):
                        r = br.send(
                            f'axlGeoPointInShape({e[0]}:{e[1]} car(setof('
                            f'c nth({bi} ppN->branches)->children '
                            f'c->objType=="shape" && '
                            f'c->layer=="{layer}")) nil)').strip()
                        if r not in ("nil", ""):
                            in_shape = True
                            break
                    if in_shape:
                        continue
                    findings.append((net, layer, e, best, what, len(segs)))

        print(f"{stats['paths']} paths, {stats['ends']} chain endpoints\n")
        if not findings:
            print("no dangling endpoints")
            return
        print(f"*** {len(findings)} DANGLING ENDPOINT(S) ***\n")
        findings.sort(key=lambda f: (f[0], f[3]))
        for net, layer, e, d, what, n in findings:
            tag = "NEAR-MISS" if d < NEAR else "floating"
            print(f"  {net:16} {layer:12} ({e[0]:8.2f},{e[1]:8.2f})  "
                  f"{n} seg  nearest {what} {d:7.2f} mil   {tag}")


if __name__ == "__main__":
    main()
