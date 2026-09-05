"""STEP model mapping for Allegro PCB Editor 17.4, over the bridge.

    python bridge/allegro/step_mapping.py list                     # every symdef -> primary mapping
    python bridge/allegro/step_mapping.py attachments              # which symdefs carry facet data
    python bridge/allegro/step_mapping.py steppath C:/models       # where Allegro looks for .step files (this session)
    python bridge/allegro/step_mapping.py set SMC0805 C_0805_2012Metric.step --ox 42
    python bridge/allegro/step_mapping.py delete SMC0805
    python bridge/allegro/step_mapping.py apply mappings.json      # many at once, then read back
    python bridge/allegro/step_mapping.py mech RED_SHELL 8200 3839 --rot 180   # pin-less mechanical symbol
    python bridge/allegro/step_mapping.py dump placement.json      # symbols + mappings + outline, for render3d/
    python bridge/allegro/step_mapping.py canvas open|close        # 3D Canvas

WHAT WORKS (verified 2026-09-04, see docs/allegro_api_notes.md s16)

* axlStepSet('primary "SYMDEF" "file.step" '(offset_x .. offset_y .. offset_z .. rotation_x .. rotation_y .. rotation_z ..))
  returns t, reads the file through `steppath`, and ATTACHES facet data to the database as an
  attachment named STEP3D_<symdef>. That attachment is the proof the file was found -- the
  return value alone is not. Offsets are design units (mils on a mils board); rotations degrees.
* `steppath` set with axlSetVariable in-session is honoured. No env file edit needed.
* The 3D Canvas does not pick up mapping changes while open: close it and `3d` again.
* Vendor .dra files often carry PKGDEF_STEP_FILE properties that name files you do not have.
  `list` shows them as mapped; `attachments` shows they have no facet data. Delete and remap.
* Mapping is per PACKAGE (symdef) or per DEVICE (compdef), never per refdes. For per-instance
  differences (e.g. one red and one white jack sharing a device) use `mech`: a pin-less
  mechanical symbol definition made with axlDBCreateSymDefSkeleton, instanced at the part's
  location, mapped to its own STEP file. No pins, no bound, no DRC or netlist effect.

mappings.json for `apply`:
    {"steppath": "C:/proj/allegro/step",
     "mappings": {"SMC0805": {"file": "C_0805_2012Metric.step", "offset_x": 42.0},
                 "PJRAN1X1U02AUX": {"file": "jack.STEP", "rotation_x": 180.0, "offset_z": 227.0}}}
"""
from __future__ import annotations

import sys
import json
import re
import pathlib
import argparse
import subprocess

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from bridge.allegro.allegro_client import AllegroBridge  # noqa: E402

KEYS = ("offset_x", "offset_y", "offset_z", "rotation_x", "rotation_y", "rotation_z")


def q(br, expr):
    r = br.send(expr)
    if r.startswith("ERROR"):
        raise RuntimeError(f"{expr[:80]} -> {r[:200]}")
    return r


def parse_mapping(text):
    """'(nil objType "step" rotation_z 0.0 ... step_name "x.step")' -> dict, or None for nil."""
    if text.strip() == "nil":
        return None
    kv = dict(re.findall(r'(\w+) ("?[^" ()]+"?)', text))
    out = {"file": kv.get("step_name", "").strip('"')}
    for k in KEYS:
        out[k] = float(kv.get(k, 0.0))
    out["color"] = int(kv.get("color", 0))
    return out


def symdefs(br):
    r = q(br, 'mapcar(lambda((s) s->name) axlDBGetDesign()->symdefs)')
    return re.findall(r'"([^"]+)"', r)


def get_mapping(br, symdef):
    return parse_mapping(q(br, f"axlStepGet(nil 'primary \"{symdef}\")"))


def set_mapping(br, symdef, file, m):
    vals = " ".join(f"{k} {float(m.get(k, 0.0))}" for k in KEYS)
    q(br, f"axlStepDelete('primary \"{symdef}\")")
    r = q(br, f"axlStepSet('primary \"{symdef}\" \"{file}\" '({vals}))")
    q(br, "axlDBTransactionCommit(axlDBTransactionStart())")
    return r.strip() == "t"


def attachments(br):
    r = q(br, 'setof(n axlGetAllAttachmentNames() rexMatchp("^STEP3D_" n))')
    return [n[len("STEP3D_"):] for n in re.findall(r'"([^"]+)"', r)]


def cmd_list(br, _a):
    have = set(attachments(br))
    print(f"  {'symdef':36s} {'step file':46s} {'facets':6s} offsets (x y z)      rotations (x y z)")
    for sd in symdefs(br):
        m = get_mapping(br, sd)
        if m is None:
            print(f"  {sd:36s} -"); continue
        print(f"  {sd:36s} {m['file']:46s} {'yes' if sd in have else 'NO':6s} "
              f"{m['offset_x']:7.2f} {m['offset_y']:7.2f} {m['offset_z']:7.2f}   "
              f"{m['rotation_x']:5.1f} {m['rotation_y']:5.1f} {m['rotation_z']:5.1f}")


def cmd_attachments(br, _a):
    for n in attachments(br):
        print(" ", n)


def cmd_steppath(br, a):
    p = a.path.replace("\\", "/")
    q(br, f'axlSetVariable("steppath" "{p}")')
    print("  steppath =", q(br, 'axlGetVariable("steppath")'))


def cmd_set(br, a):
    m = {k: getattr(a, k) for k in KEYS}
    ok = set_mapping(br, a.symdef, a.file, m)
    print("  set:", ok, "->", get_mapping(br, a.symdef))
    print("  facets attached:", a.symdef in attachments(br))


def cmd_delete(br, a):
    print("  delete:", q(br, f"axlStepDelete('primary \"{a.symdef}\")"))
    q(br, "axlDBTransactionCommit(axlDBTransactionStart())")


def cmd_apply(br, a):
    spec = json.load(open(a.spec))
    if spec.get("steppath"):
        q(br, f'axlSetVariable("steppath" "{spec["steppath"].replace(chr(92), "/")}")')
    for sd, m in spec["mappings"].items():
        ok = set_mapping(br, sd, m["file"], m)
        print(f"  {sd:36s} {'ok' if ok else 'FAILED'}")
    have = set(attachments(br))
    missing = [sd for sd in spec["mappings"] if sd not in have]
    if missing:
        print("  *** no facet data for:", missing, "-- file not found on steppath?")
    else:
        print(f"  facet data attached for all {len(spec['mappings'])} symdefs")


def cmd_mech(br, a):
    """A pin-less mechanical symbol carrying its own STEP model at a location."""
    ex = a.extents
    r = q(br, f'ppMechSd = axlDBCreateSymDefSkeleton(list("{a.name}" "mechanical") '
              f'list({ex[0]}:{ex[1]} {ex[2]}:{ex[3]}))')
    print("  symdef:", r if "dbid" in r else f"(exists or failed: {r})")
    r = q(br, f'axlDBCreateSymbol(list("{a.name}" "mechanical") {float(a.x)}:{float(a.y)} nil {float(a.rot)})')
    print("  instance:", r)
    q(br, "axlDBTransactionCommit(axlDBTransactionStart())")
    if a.file:
        m = {k: getattr(a, k) for k in KEYS}
        print("  mapping:", set_mapping(br, a.name, a.file, m), "facets:", a.name in attachments(br))


def cmd_dump(br, a):
    q(br, "axlDBTransactionCommit(axlDBTransactionStart())")
    syms = q(br, 'mapcar(lambda((s) list(s->refdes s->name car(s->xy) cadr(s->xy) s->rotation s->mirrored)) '
                 'axlDBGetDesign()->symbols)')
    recs = re.findall(r'\(("[^"]*"|nil) "([^"]+)" ([-\d.]+) ([-\d.]+) ([-\d.]+) (t|nil)\)', syms)
    symbols = [dict(refdes=(None if r[0] == "nil" else r[0].strip('"')), symdef=r[1],
                    x=float(r[2]), y=float(r[3]), rot=float(r[4]), mirror=r[5] == "t") for r in recs]
    maps = {sd: get_mapping(br, sd) for sd in symdefs(br)}
    units = re.findall(r'"([^"]+)"', q(br, "axlDBGetDesignUnits()"))
    out = dict(units=units[0] if units else "?",
               outline=q(br, "axlDBGetDesign()->designOutline->bBox").strip(),
               symbols=symbols, mappings=maps)
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"  {a.out}: {len(symbols)} symbols, {sum(1 for m in maps.values() if m)} mapped symdefs of {len(maps)}")


def cmd_canvas(br, a):
    if a.action == "open":
        print("  3d:", q(br, 'axlShell("3d")'))
    else:
        ps = pathlib.Path(__file__).with_name("canvas_capture.ps1")
        subprocess.run(["pwsh", "-NoProfile", "-File", str(ps), "-Mode", "close"], check=False)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("attachments").set_defaults(fn=cmd_attachments)
    p = sub.add_parser("steppath"); p.add_argument("path"); p.set_defaults(fn=cmd_steppath)

    def xf(p):
        p.add_argument("--ox", dest="offset_x", type=float, default=0.0)
        p.add_argument("--oy", dest="offset_y", type=float, default=0.0)
        p.add_argument("--oz", dest="offset_z", type=float, default=0.0)
        p.add_argument("--rx", dest="rotation_x", type=float, default=0.0)
        p.add_argument("--ry", dest="rotation_y", type=float, default=0.0)
        p.add_argument("--rz", dest="rotation_z", type=float, default=0.0)

    p = sub.add_parser("set"); p.add_argument("symdef"); p.add_argument("file"); xf(p); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("delete"); p.add_argument("symdef"); p.set_defaults(fn=cmd_delete)
    p = sub.add_parser("apply"); p.add_argument("spec"); p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("mech"); p.add_argument("name"); p.add_argument("x"); p.add_argument("y")
    p.add_argument("--rot", type=float, default=0.0); p.add_argument("--file", default=None)
    p.add_argument("--extents", type=float, nargs=4, default=[-100.0, -100.0, 100.0, 100.0], metavar=("X0", "Y0", "X1", "Y1"))
    xf(p); p.set_defaults(fn=cmd_mech)
    p = sub.add_parser("dump"); p.add_argument("out"); p.set_defaults(fn=cmd_dump)
    p = sub.add_parser("canvas"); p.add_argument("action", choices=["open", "close"]); p.set_defaults(fn=cmd_canvas)
    a = ap.parse_args(argv)
    with AllegroBridge() as br:
        n = br.send("length(axlDBGetDesign()->symbols)").strip()
        if n in ("nil", ""):
            print("  *** no board open", file=sys.stderr); return 1
        a.fn(br, a)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(sys.argv[1:]))
