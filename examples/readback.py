"""Dump the interesting properties of every part in the active Capture design.

A minimal end-to-end example of the Capture bridge: connect, source the query
layer, ask for the part list, then pull the full property set per part.

    python examples/readback.py

Requires Capture running with the Communication Server started (it auto-starts
if tcl/capAutoLoad/capBridgeServerInit.tcl is deployed) and a design open.
"""
import sys, pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from bridge.capture_bridge import CaptureBridge, parse_tcl_list

WANT = ('_REFDES_', 'Source Library', 'Source Package', 'Source Part',
        'Location X-Coordinate', 'Location Y-Coordinate', 'Value', 'PCB Footprint')

with CaptureBridge(timeout=90) as c:
    c.source_file(str(REPO / 'bridge' / 'tcl' / 'capBridgeQuery.tcl'))
    info = c.call('::capBridge::designInfo')
    print("designInfo:", info)
    fields = parse_tcl_list(info)
    n = int(fields[4]) if fields[0] == 'OK' else 0
    if n == 0:
        print("\n>>> no parts on the page yet <<<")
    else:
        for p in c.parts():
            print(f"\n--- {p['refdes']} ---")
            raw = c.call('::capBridge::partProps', [p['refdes']])
            for r in parse_tcl_list(raw)[1:]:
                f = parse_tcl_list(r)
                if f[0] in WANT:
                    print(f"   {f[0]:24} = {(f[1] if len(f) > 1 else '')!r}")
