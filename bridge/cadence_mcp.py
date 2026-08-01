#!/usr/bin/env python3
"""
cadence_mcp.py — MCP server exposing OrCAD Capture 17.4 as agent tools.

Wraps capture_bridge.py so any MCP client can query and (optionally) modify a
live Capture design through structured tool calls, rather than screenshots.

    Client  --JSON-RPC/stdio-->  this server  --TCP 9020-->  Capture

DEPENDENCY-FREE BY DESIGN. MCP over stdio is newline-delimited JSON-RPC 2.0,
which the standard library covers, so there is nothing to pip install on a
machine whose main job is running EDA tools.

USAGE
    python bridge/cadence_mcp.py                 # read-only (default)
    python bridge/cadence_mcp.py --allow-write   # enables mutation tools

Register with Claude Code:
    claude mcp add cadence -- python C:/path/to/bridge/cadence_mcp.py

PREREQUISITE — Capture must be running with the server started:
    package require capCommServer
    ::capCommServer::StartServer
(or deploy tcl/capAutoLoad/capBridgeServerInit.tcl to start it automatically,
loopback-only, on every launch.)

WRITE TOOLS ARE OFF BY DEFAULT. An agent that can silently alter a schematic
is a materially different risk from one that can only read it, so mutation is
opt-in per invocation rather than a runtime argument the model can set.
stdout carries protocol traffic ONLY; all diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Callable

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from bridge.capture_bridge import (  # noqa: E402
    CaptureBridge,
    CaptureBridgeError,
    parse_tcl_list,
)
from bridge.allegro.allegro_client import (  # noqa: E402
    AllegroBridge,
    AllegroBridgeError,
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "cadence-capture", "version": "0.1.0"}

QUERY_TCL = (
    __import__("pathlib").Path(__file__).resolve().parent / "tcl" / "capBridgeQuery.tcl"
)
QUERY_IL = (
    __import__("pathlib").Path(__file__).resolve().parent / "allegro" / "allegroQuery.il"
)


def log(msg: str) -> None:
    """Diagnostics to stderr. stdout is reserved for JSON-RPC."""
    print(f"[cadence-mcp] {msg}", file=sys.stderr, flush=True)


class Session:
    """Lazily-connected bridge that re-sources the query layer as needed.

    Capture may be restarted independently of this process, so the connection
    is established on demand and torn down on error rather than held open and
    assumed healthy.
    """

    def __init__(self) -> None:
        self._cap: CaptureBridge | None = None

    def get(self) -> CaptureBridge:
        if self._cap is None:
            cap = CaptureBridge(timeout=120)
            cap.ping()
            if QUERY_TCL.exists():
                cap.source_file(str(QUERY_TCL).replace("\\", "/"))
            self._cap = cap
        return self._cap

    def reset(self) -> None:
        if self._cap is not None:
            try:
                self._cap.close()
            except Exception:
                pass
        self._cap = None


SESSION = Session()


# --------------------------------------------------------------------------
# Tool implementations. Each returns a plain string; the caller wraps it.
# --------------------------------------------------------------------------

def t_status(_: dict) -> str:
    cap = SESSION.get()
    lines = [
        f"tcl version   : {cap.tcl_version()}",
        f"Dbo* commands : {cap.dbo_command_count()}",
        f"active design : {cap.has_active_design()}",
    ]
    try:
        info = parse_tcl_list(cap.call("::capBridge::designInfo"))
        if info and info[0] == "OK":
            lines += [
                f"design        : {info[1]}",
                f"schematics    : {info[2]}",
                f"pages         : {info[3]}",
                f"parts         : {info[4]}",
            ]
    except CaptureBridgeError as exc:
        lines.append(f"designInfo    : {exc}")
    return "\n".join(lines)


def t_parts(args: dict) -> str:
    parts = SESSION.get().parts()
    page = args.get("page")
    if page:
        parts = [p for p in parts if p["page"] == page]
    if not parts:
        return "No parts matched."
    hdr = f"{'REFDES':8} {'PAGE':14} {'VALUE':14} {'FOOTPRINT':22} PART NUMBER"
    rows = [
        f"{p['refdes']:8} {p['page']:14} {p['value']:14} {p['footprint']:22} {p['part_number']}"
        for p in parts
    ]
    return f"{len(parts)} parts\n\n" + hdr + "\n" + "\n".join(rows)


def t_nets(_: dict) -> str:
    nets = SESSION.get().nets()
    rows = "\n".join(f"{n['net']:16} {n['pin_count']:>3} pins" for n in nets)
    orphans = [n["net"] for n in nets if n["pin_count"] == 0]
    single = [n["net"] for n in nets if n["pin_count"] == 1]
    out = f"{len(nets)} nets\n\n{rows}"
    if orphans:
        out += f"\n\nORPHANED (0 pins): {', '.join(orphans)}"
    if single:
        out += f"\nSINGLE-NODE (1 pin): {', '.join(single)}"
    return out


def t_connectivity(args: dict) -> str:
    conns = SESSION.get().connectivity()
    want = args.get("net")
    if want:
        conns = [c for c in conns if c["net"] == want]
        if not conns:
            return f"No net named {want!r}."
    rows = []
    for c in sorted(conns, key=lambda x: -int(x["pin_count"])):
        refs = ", ".join(sorted(set(c["refdes"])))
        rows.append(f"{c['net']:16} {c['pin_count']:>3} pins   {refs}")
    return f"{len(conns)} nets\n\n" + "\n".join(rows)


def t_part_properties(args: dict) -> str:
    refdes = args["refdes"]
    raw = SESSION.get().call("::capBridge::partProps", [refdes])
    els = parse_tcl_list(raw)
    if els and els[0] == "ERROR":
        return f"ERROR: {' '.join(els[1:])}"
    rows = []
    for r in els[1:]:
        f = parse_tcl_list(r)
        value = f[1] if len(f) > 1 else ""
        rows.append(f"  {f[0]:24} = {value!r}")
    return f"Properties of {refdes}:\n" + "\n".join(rows)


def t_hanging_wires(_: dict) -> str:
    els = parse_tcl_list(SESSION.get().call("::capBridge::hangingWires"))
    if els and els[0] == "ERROR":
        return f"ERROR: {' '.join(els[1:])}"
    rows = [parse_tcl_list(r) for r in els[1:]]
    if not rows:
        return "No hanging wire endpoints found."
    out = [f"{len(rows)} hanging wire endpoint(s):", ""]
    for r in rows:
        # Capture schematic coordinates are internal units, conventionally
        # 1/100 inch. Shown both ways; treat the inch figure as indicative.
        try:
            inches = f"  (~{int(r[1])/100:.2f}in, {int(r[2])/100:.2f}in)"
        except ValueError:
            inches = ""
        out.append(f"  page={r[0]:14} x={r[1]:>6} y={r[2]:>6}  {r[3]}{inches}")
    out.append(
        "\nA wire whose BOTH endpoints appear here, a unit or two apart, is a "
        "stray fragment — the usual cause of an orphaned (0-pin) auto-named net."
    )
    return "\n".join(out)


def t_run_workflow(args: dict) -> str:
    name = args["workflow"]
    cap = SESSION.get()
    lines = cap.run_workflow(name)
    t = cap.triage(lines)
    head = f"{name}: {len(t['errors'])} ERROR, {len(t['warnings'])} WARN"
    note = ""
    if name == "bomScrubber":
        note = (
            "\n(note: bomScrubber emits a table rather than ERROR/WARN prefixes, "
            "so the counts above under-report it; read the full output.)"
        )
    return head + note + "\n\n" + "\n".join(lines)


def t_set_part_property(args: dict) -> str:
    els = parse_tcl_list(
        SESSION.get().call(
            "::capBridge::setPartProp",
            [args["refdes"], args["property"], args["value"]],
        )
    )
    if els and els[0] == "ERROR":
        return f"ERROR: {' '.join(els[1:])}"
    # OK refdes prop old new
    return (
        f"Set {els[1]}.{els[2]}\n"
        f"  was : {els[3]!r}\n"
        f"  now : {els[4]!r}\n"
        f"Not yet saved — call capture_save_design to persist."
    )


def t_save_design(_: dict) -> str:
    els = parse_tcl_list(SESSION.get().call("::capBridge::saveDesign"))
    if els and els[0] == "ERROR":
        return f"ERROR: {' '.join(els[1:])}"
    return f"Saved design {els[2] if len(els) > 2 else ''}."


# --------------------------------------------------------------------------
# Allegro PCB Editor — separate bridge, separate lifecycle.
#
# Capture and Allegro are independent processes; either can be closed or
# restarted without the other. Each session connects lazily and resets on
# error rather than being held open and assumed healthy.
# --------------------------------------------------------------------------

class AllegroSession:
    def __init__(self) -> None:
        self._a: AllegroBridge | None = None

    def get(self) -> AllegroBridge:
        if self._a is None:
            a = AllegroBridge(timeout=120)
            a.ping()
            if QUERY_IL.exists():
                a.send('load("{}")'.format(str(QUERY_IL).replace("\\", "/")))
            self._a = a
        return self._a

    def reset(self) -> None:
        if self._a is not None:
            try:
                self._a.close()
            except Exception:
                pass
        self._a = None


ALLEGRO = AllegroSession()

#: Delimiters used by allegroQuery.il — neither character appears in Allegro
#: constraint names, layer names or refdes, so no escaping is needed.
_FS, _RS = "^", "|"


def _arecords(expr: str) -> list[list[str]]:
    """Run an Allegro query and split its delimited response into records."""
    raw = ALLEGRO.get().send(expr).strip('"')
    if raw.startswith("ERROR"):
        raise AllegroBridgeError(raw.replace(_FS, " "))
    if not raw:
        return []
    return [r.split(_FS) for r in raw.split(_RS)]


def _pad(row: list[str], n: int) -> list[str]:
    return row + [""] * (n - len(row))


def t_allegro_status(_: dict) -> str:
    recs = _arecords("aqBoard()")
    if not recs:
        return "No active board."
    f = _pad(recs[0], 7)
    labels = ("board", "active DRCs", "waived DRCs", "placed symbols",
              "symbol defs", "padstacks", "nets")
    return "\n".join(f"{k:15}: {v}" for k, v in zip(labels, f))


def t_allegro_drcs(args: dict) -> str:
    recs = _arecords("aqDrcs()")
    if not recs:
        return "No DRC violations."
    # Dedup on (constraint, location): a DRC marks EACH participating figure,
    # so one physical problem appears once per figure (max 2).
    seen: set = set()
    uniq: list[list[str]] = []
    by_name: dict[str, int] = {}
    for r in recs:
        p = _pad(r, 7)
        by_name[p[1]] = by_name.get(p[1], 0) + 1
        key = (p[1], p[5], p[6])
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    out = [f"{len(recs)} DRC records, {len(uniq)} distinct locations", "", "BY CONSTRAINT:"]
    out += [f"  {v:5}  {k}" for k, v in sorted(by_name.items(), key=lambda kv: -kv[1])]
    if args.get("detail"):
        out += ["", "DETAIL (deduplicated):"]
        out += [f"  {r[1]:32} exp {r[3]:>10}  act {r[4]:>10}  @ ({r[5]},{r[6]})"
                for r in uniq[:200]]
    return "\n".join(out)


def t_allegro_symbols(_: dict) -> str:
    recs = _arecords("aqSymbols()")
    if not recs:
        return "No placed symbols."
    out = [f"{len(recs)} placed symbols", "",
           f"{'REFDES':10} {'SYMBOL':30} {'X':>10} {'Y':>10} LAYER"]
    for r in recs:
        p = _pad(r, 6)
        out.append(f"{p[0] or '(none)':10} {p[1]:30} {p[2]:>10} {p[3]:>10} {p[4]}")
    return "\n".join(out)


def t_allegro_nets(_: dict) -> str:
    recs = _arecords("aqNets()")
    if not recs:
        return "No nets."
    rows = []
    for r in recs:
        p = _pad(r, 2)
        rows.append((p[0], int(p[1]) if p[1].isdigit() else 0))
    rows.sort(key=lambda x: -x[1])
    out = [f"{len(rows)} nets", ""]
    out += [f"  {n:26} {c:>4} pins" for n, c in rows]
    orphan = [n for n, c in rows if c == 0]
    single = [n for n, c in rows if c == 1]
    if orphan:
        out += ["", "ORPHANED (0 pins): " + ", ".join(orphan)]
    if single:
        out += ["SINGLE-NODE (1 pin): " + ", ".join(single)]
    return "\n".join(out)


def t_allegro_eval(args: dict) -> str:
    return ALLEGRO.get().send(args["expression"])


READ_TOOLS: dict[str, tuple[Callable[[dict], str], str, dict]] = {
    "capture_status": (
        t_status,
        "Connection and active-design summary for the running OrCAD Capture session.",
        {"type": "object", "properties": {}},
    ),
    "capture_list_parts": (
        t_parts,
        "List placed parts with refdes, page, value, footprint and part number.",
        {
            "type": "object",
            "properties": {"page": {"type": "string", "description": "Optional page name filter."}},
        },
    ),
    "capture_list_nets": (
        t_nets,
        "List every net with its pin count; flags orphaned and single-node nets.",
        {"type": "object", "properties": {}},
    ),
    "capture_connectivity": (
        t_connectivity,
        "Netlist as net -> connected reference designators.",
        {
            "type": "object",
            "properties": {"net": {"type": "string", "description": "Optional single net name."}},
        },
    ),
    "capture_part_properties": (
        t_part_properties,
        "All effective properties of one part. Use this to discover exact property "
        "names before writing — Capture uses spaces, e.g. 'PCB Footprint'.",
        {
            "type": "object",
            "properties": {"refdes": {"type": "string"}},
            "required": ["refdes"],
        },
    ),
    "capture_hanging_wires": (
        t_hanging_wires,
        "Find wire endpoints that connect to nothing. Locates the physical cause "
        "of orphaned (0-pin) nets, which cannot be found by name because "
        "page-level nets are unnamed.",
        {"type": "object", "properties": {}},
    ),
    "allegro_status": (
        t_allegro_status,
        "Summary of the board open in Allegro PCB Editor: name, DRC counts, "
        "symbol/padstack/net counts.",
        {"type": "object", "properties": {}},
    ),
    "allegro_drcs": (
        t_allegro_drcs,
        "DRC violations grouped by constraint. Deduplicates the double-reporting "
        "caused by each violation marking both participating figures. Pass "
        "detail=true for per-violation locations.",
        {"type": "object", "properties": {"detail": {"type": "boolean"}}},
    ),
    "allegro_symbols": (
        t_allegro_symbols,
        "Placed footprint instances with refdes, symbol name and location.",
        {"type": "object", "properties": {}},
    ),
    "allegro_nets": (
        t_allegro_nets,
        "Board nets with pin counts; flags orphaned and single-node nets.",
        {"type": "object", "properties": {}},
    ),
    "allegro_eval": (
        t_allegro_eval,
        "Evaluate a SKILL expression in Allegro. Escape hatch for queries the "
        "typed tools do not cover. Must be a single line.",
        {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    ),
    "capture_run_workflow": (
        t_run_workflow,
        "Run a design-audit workflow and return its full report.",
        {
            "type": "object",
            "properties": {
                "workflow": {
                    "type": "string",
                    "enum": list(CaptureBridge.WORKFLOWS),
                }
            },
            "required": ["workflow"],
        },
    ),
}

WRITE_TOOLS: dict[str, tuple[Callable[[dict], str], str, dict]] = {
    "capture_set_part_property": (
        t_set_part_property,
        "Set a property on a part. Returns the previous value so the change can be "
        "undone. Does NOT save; call capture_save_design afterwards.",
        {
            "type": "object",
            "properties": {
                "refdes": {"type": "string"},
                "property": {"type": "string", "description": "Exact name, e.g. 'PCB Footprint'."},
                "value": {"type": "string"},
            },
            "required": ["refdes", "property", "value"],
        },
    ),
    "capture_save_design": (
        t_save_design,
        "Persist the active design to disk. Irreversible — back up the project first.",
        {"type": "object", "properties": {}},
    ),
}


def build_tools(allow_write: bool) -> dict:
    tools = dict(READ_TOOLS)
    if allow_write:
        tools.update(WRITE_TOOLS)
    return tools


# --------------------------------------------------------------------------
# JSON-RPC / MCP plumbing
# --------------------------------------------------------------------------

def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def result(msg_id: Any, payload: dict) -> None:
    send({"jsonrpc": "2.0", "id": msg_id, "result": payload})


def error(msg_id: Any, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def serve(allow_write: bool) -> int:
    tools = build_tools(allow_write)
    log(f"ready; {len(tools)} tools; write={'ENABLED' if allow_write else 'disabled'}")

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        msg_id = msg.get("id")

        # Notifications carry no id and must not be answered.
        if msg_id is None and method and method.startswith("notifications/"):
            continue

        try:
            if method == "initialize":
                requested = (msg.get("params") or {}).get("protocolVersion")
                result(
                    msg_id,
                    {
                        "protocolVersion": requested or PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": SERVER_INFO,
                    },
                )
            elif method == "ping":
                result(msg_id, {})
            elif method == "tools/list":
                result(
                    msg_id,
                    {
                        "tools": [
                            {"name": n, "description": d, "inputSchema": s}
                            for n, (_, d, s) in tools.items()
                        ]
                    },
                )
            elif method == "tools/call":
                params = msg.get("params") or {}
                name = params.get("name")
                args = params.get("arguments") or {}
                entry = tools.get(name)
                if entry is None:
                    known = ", ".join(tools)
                    hint = ""
                    if not allow_write and name in WRITE_TOOLS:
                        hint = " (write tools require --allow-write)"
                    result(
                        msg_id,
                        {
                            "content": [{"type": "text", "text": f"Unknown tool {name!r}{hint}. Available: {known}"}],
                            "isError": True,
                        },
                    )
                else:
                    fn = entry[0]
                    try:
                        text = fn(args)
                        is_err = text.startswith("ERROR")
                    except CaptureBridgeError as exc:
                        SESSION.reset()
                        text = (
                            f"Capture bridge error: {exc}\n\n"
                            "If Capture was restarted, the Communication Server must be "
                            "started again:\n"
                            "  package require capCommServer\n"
                            "  ::capCommServer::StartServer"
                        )
                        is_err = True
                    except AllegroBridgeError as exc:
                        ALLEGRO.reset()
                        text = (
                            f"Allegro bridge error: {exc}\n\n"
                            "If Allegro was restarted, the bridge must be started again "
                            "at the Skill> prompt:\n"
                            '  load(".../bridge/allegro/allegroBridge.il")\n'
                            "  abStart()"
                        )
                        is_err = True
                    except Exception as exc:  # noqa: BLE001
                        SESSION.reset()
                        log(traceback.format_exc())
                        text = f"Unexpected error: {exc!r}"
                        is_err = True
                    result(
                        msg_id,
                        {"content": [{"type": "text", "text": text}], "isError": is_err},
                    )
            elif msg_id is not None:
                error(msg_id, -32601, f"Method not found: {method}")
        except Exception as exc:  # noqa: BLE001
            log(traceback.format_exc())
            if msg_id is not None:
                error(msg_id, -32603, f"Internal error: {exc!r}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--allow-write",
        action="store_true",
        help="Expose mutation tools (set property, save design). Off by default.",
    )
    ns = ap.parse_args()
    return serve(ns.allow_write)


if __name__ == "__main__":
    raise SystemExit(main())
