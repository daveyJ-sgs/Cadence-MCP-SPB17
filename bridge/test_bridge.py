#!/usr/bin/env python3
"""
test_bridge.py — offline regression tests for the bridge's protocol layer.

Runs WITHOUT Capture. Everything tested here is a pure function, and every
case corresponds to a bug that actually cost debugging time on this project.
The protocol has sharp edges whose failure mode is a silent timeout or
plausible-looking wrong data, so they deserve tests that run in a second.

    python bridge/test_bridge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.capture_bridge import (  # noqa: E402
    CaptureBridge,
    CaptureBridgeError,
    parse_tcl_list,
    tcl_list,
    tcl_quote,
)
from bridge.allegro.allegro_client import (  # noqa: E402
    AllegroBridge,
    AllegroBridgeError,
)

BS = chr(92)
FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          got  {got!r}\n          want {want!r}")
        FAILURES.append(label)


def check_raises(label: str, fn, exc=CaptureBridgeError) -> None:
    try:
        fn()
    except exc:
        print(f"  PASS  {label}")
        return
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL  {label} — raised {type(e).__name__}, expected {exc.__name__}")
        FAILURES.append(label)
        return
    print(f"  FAIL  {label} — did not raise")
    FAILURES.append(label)


print("tcl_quote")
check("bare word unquoted", tcl_quote("simple"), "simple")
check("empty -> {}", tcl_quote(""), "{}")
check("space braces it", tcl_quote("two words"), "{two words}")
# Braces must suppress substitution: net and property names really do contain
# these, and an unbraced $ or [ would be evaluated by TCL.
check("dollar suppressed", tcl_quote("net$NAME"), "{net$NAME}")
check("brackets suppressed", tcl_quote("a[b]c"), "{a[b]c}")
# Regression: rejecting all backslashes forced the escape path, which mangled
# ordinary scripts badly enough to hang the request.
check("balanced braces kept", tcl_quote("proc p {} { return 1 }"), "{proc p {} { return 1 }}")
check("backslash inside braces", tcl_quote('puts "a' + BS + 'nb"'), '{puts "a' + BS + 'nb"}')
# A trailing odd backslash would escape the closing brace, so it must escape.
check("trailing backslash escapes", tcl_quote("ends" + BS), "ends" + BS + BS)
check("unbalanced brace escapes", tcl_quote("open {"), "open" + BS + " " + BS + "{")

print("\ntcl_list")
check("simple list", tcl_list(["a", "b"]), "a b")
check("spaces nested", tcl_list(["a b", "c"]), "{a b} c")
check("empty element", tcl_list(["", "x"]), "{} x")

print("\nparse_tcl_list")
check("flat", parse_tcl_list("a b c"), ["a", "b", "c"])
check("braced element", parse_tcl_list("a {b c} d"), ["a", "b c", "d"])
# Regression: a naive brace regex counted the empty field {} as its own row,
# inflating a 44-part result to 46.
check("empty field not a row", parse_tcl_list("{x {} y}"), ["x {} y"])
check("empty stays empty", parse_tcl_list("a {} b"), ["a", "", "b"])
check("nested survives one level", parse_tcl_list("{a {b c}} {d}"), ["a {b c}", "d"])
check("quoted element", parse_tcl_list('a "b c" d'), ["a", "b c", "d"])
check("blank input", parse_tcl_list(""), [])

print("\nround trip")
for original in ("plain", "two words", "net$X", "a[b]", "", "has{brace}pair",
                 "open {", "semi;colon", "quote\"mark"):
    rt = parse_tcl_list(tcl_quote(original))
    check(f"round trip {original!r}", rt[0] if rt else "", original)

print("\nrow parsing (the shape real query responses take)")
raw = "OK {C2 SCHEMATIC1 Preamp 0.1u cap196 {}} {J3 SCHEMATIC1 Preamp PHONEJACK_0 {} {}}"
els = parse_tcl_list(raw)
check("OK token present", els[0], "OK")
check("two data rows", len(els) - 1, 2)
check("row 1 six fields", len(parse_tcl_list(els[1])), 6)
check("empty trailing field kept", parse_tcl_list(els[1])[5], "")
check("row 2 refdes", parse_tcl_list(els[2])[0], "J3")

print("\nrequest guards (no Capture needed — these fail before any I/O)")
cap = CaptureBridge()
# A newline truncates the request at the server's gets(), so the reply never
# comes and the client times out with no clue why. Fail loudly instead.
check_raises("newline in eval rejected", lambda: cap.eval("line1\nline2"))
check_raises("CR in eval rejected", lambda: cap.eval("line1\rline2"))
check_raises("newline in call arg rejected", lambda: cap.call("p", ["a\nb"]))
check_raises("unknown workflow rejected", lambda: cap.run_workflow("nope"))

print("\nAllegro client guards (no Allegro needed)")
_a = AllegroBridge()
# Same single-line constraint as the Capture side: the helper does one
# readline per exchange, so a newline in the request truncates it and the
# reply never arrives.
check_raises("newline in expression rejected", lambda: _a.send("a\nb"), AllegroBridgeError)
check_raises("CR in expression rejected", lambda: _a.send("a\rb"), AllegroBridgeError)
# With nothing listening, the error must name the fix rather than just fail.
try:
    AllegroBridge(port=59999, timeout=2).send("1+1")
    check("unreachable port raises", False, True)
except AllegroBridgeError as exc:
    check("unreachable port names abStart()", "abStart()" in str(exc), True)

print("\nAllegro record parsing (allegroQuery.il delimiters)")
FS, RS = "^", "|"
_raw = ("NET SPACING^Line to Line^TOP^11.81 MIL^11.8 MIL^2446.92^5400.76"
        "|NET SPACING^Line to SMD^TOP^11.81 MIL^0 MIL^2206.77^5480.2")
_recs = [r.split(FS) for r in _raw.split(RS)]
check("two records", len(_recs), 2)
check("seven fields", len(_recs[0]), 7)
check("constraint name", _recs[0][1], "Line to Line")
check("actual value", _recs[1][4], "0 MIL")
# The delimiters were chosen precisely because neither character occurs in
# Allegro constraint names, layer names or refdes -- so no escaping is needed.
check("no field sep in real data", any(FS in f for r in _recs for f in r), False)
check("no record sep in real data", any(RS in f for r in _recs for f in r), False)

print("\n" + "=" * 60)
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S): " + ", ".join(FAILURES))
    raise SystemExit(1)
print("All tests passed.")
raise SystemExit(0)
