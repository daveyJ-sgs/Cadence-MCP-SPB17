"""
capture_bridge.py — external control channel for OrCAD Capture 17.4.

Talks to Capture's built-in TCL Communication Server over a plain TCP socket.
No Tk, no screenshots, no GUI automation: structured request in, structured
response out, executed inside the live Capture process against the real design
database.

SERVER SIDE (run once per Capture session, in Capture's Command Window):

    package require capCommServer
    ::capCommServer::StartServer
    puts [::capCommServer::IsServerRunning]        ;# expect 1

The server implementation lives at
    <CDS_ROOT>/tools/capture/tclscripts/capCommunicationServer/tcl/capCommServer.tcl
and is pure core TCL (`socket -server`) — it does NOT require Tk or the
Tk-based dashboard, which matters because this install has no ActiveTCL and
any Tk call crashes Capture.

-----------------------------------------------------------------------------
PROTOCOL — learned by reading capCommServer.tcl and confirmed live
-----------------------------------------------------------------------------

Request : one line of text, a TCL list of exactly two elements:

              procName {arg1 arg2 ...}

          NO outer braces around the whole thing. Wrapping the request as
          `{procName args}` makes it a single list element, so the server
          reads procName as the entire string and the socket handle lands in
          the wrong slot -- the reply then fails inside a bare `catch` and you
          get a silent timeout with no error.

Response: one line, the proc's return value.

Dispatch: the server calls `$procName $arguments` -- ALWAYS exactly one
          argument, the argument list. Every callable proc must therefore
          accept exactly one parameter, which is why every method Cadence
          ships is written `proc Name { pList }` and unpacks it with lindex.
          A zero-arg proc fails with an arity error.

Errors  : any failure inside the proc is swallowed and returned as the literal
          string "Server method failed", with no detail. Procs intended for
          remote use should catch internally and return their own structured
          error text, or debugging over this channel is miserable.

Scope   : dispatch is `$procName $args` with no namespace restriction, so ANY
          proc in Capture's interpreter is callable -- including `eval`, which
          makes this a general-purpose remote execution channel rather than a
          fixed API. Confirmed: 4163 Dbo* database commands are reachable.

CRITICAL: responses MUST be single-line. The server does `puts $sock $value`
          and the client does a single `gets`. Any embedded newline
          desynchronizes the stream and every later reply is off by one line.
          Return TCL lists; never return preformatted multi-line reports.
"""

from __future__ import annotations

import socket
from typing import Iterable, Sequence

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9020

#: The server's generic failure string. Carries no detail about the cause.
SERVER_ERROR = "Server method failed"


class CaptureBridgeError(RuntimeError):
    """A request failed, or Capture reported a method failure."""


class CaptureNotListening(CaptureBridgeError):
    """Nothing is listening. Capture isn't running, or the server isn't started."""


def tcl_quote(value: object) -> str:
    """Render a Python value as a single TCL list element.

    Braces are used where possible since they suppress all substitution --
    important because design names and property values routinely contain
    characters TCL would otherwise interpret ($ and [ especially).
    """
    s = str(value)
    if s == "":
        return "{}"
    if not any(c in s for c in ' \t\n\r{}[]$"\\;'):
        return s
    # Braces are preferred: they suppress substitution entirely and keep the
    # payload readable on the wire. Inside braces a backslash is passed
    # through literally, which is exactly what a TCL script payload wants, so
    # backslashes are fine -- EXCEPT a trailing run of odd length, where the
    # last one would escape the closing brace.
    #
    # An earlier version rejected any payload containing a backslash and fell
    # through to the escape-everything path below, which mangled ordinary
    # scripts like `puts "a\nb"` badly enough to hang the request.
    if _braces_balanced(s) and not _ends_with_odd_backslashes(s):
        return "{" + s + "}"
    out = []
    for c in s:
        if c in '{}[]$"\\;' or c.isspace():
            out.append("\\")
        out.append(c)
    return "".join(out)


def _ends_with_odd_backslashes(s: str) -> bool:
    n = 0
    for c in reversed(s):
        if c != "\\":
            break
        n += 1
    return n % 2 == 1


def _braces_balanced(s: str) -> bool:
    depth = 0
    for c in s:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def tcl_list(items: Iterable[object]) -> str:
    """Render a Python iterable as a TCL list."""
    return " ".join(tcl_quote(i) for i in items)


def parse_tcl_list(s: str) -> list[str]:
    """Split one level of a TCL list into its elements.

    Responses come back as TCL lists, so any element containing spaces is
    brace-wrapped and nested rows are braces within braces. Regex is not
    good enough here: an empty field renders as `{}` and naive brace matching
    counts it as a row of its own, silently inflating record counts.

    Call repeatedly to descend nesting levels.
    """
    items: list[str] = []
    i, n = 0, len(s)
    while i < n:
        while i < n and s[i] in " \t\n\r":
            i += 1
        if i >= n:
            break
        if s[i] == "{":
            depth, i = 1, i + 1
            start = i
            while i < n and depth > 0:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == "{":
                    depth += 1
                elif s[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            items.append(s[start:i])
            i += 1
        elif s[i] == '"':
            i += 1
            start = i
            while i < n and s[i] != '"':
                if s[i] == "\\":
                    i += 2
                    continue
                i += 1
            items.append(_unescape(s[start:i]))
            i += 1
        else:
            start = i
            while i < n and s[i] not in " \t\n\r":
                if s[i] == "\\":
                    i += 2
                    continue
                i += 1
            items.append(_unescape(s[start:i]))
    return items


def _unescape(s: str) -> str:
    """Resolve TCL backslash escapes.

    Applied to bare and quoted elements only -- NOT to brace-quoted ones,
    where TCL performs no substitution and a backslash is a literal
    character. Without this, a value that had to be escaped on the way out
    comes back still carrying its backslashes and no longer equals what was
    sent.
    """
    if "\\" not in s:
        return s
    out = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n:
            out.append(s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


class CaptureBridge:
    """A connection to Capture's Communication Server.

    The server keeps its readable fileevent registered after handling a
    request, so one connection can carry many requests. `persistent=False`
    opens a fresh socket per call, which is slower but immune to any
    stream desync caused by a proc that accidentally returns multiple lines.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 30.0,
        persistent: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.persistent = persistent
        self._sock: socket.socket | None = None
        self._file = None

    # -- connection ---------------------------------------------------------

    def _connect(self) -> tuple[socket.socket, object]:
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except (ConnectionRefusedError, OSError) as exc:
            raise CaptureNotListening(
                f"Nothing listening on {self.host}:{self.port}. In Capture's "
                f"Command Window run:\n"
                f"    package require capCommServer\n"
                f"    ::capCommServer::StartServer"
            ) from exc
        return sock, sock.makefile("r", newline="\n")

    def _channel(self):
        if not self.persistent:
            return self._connect()
        if self._sock is None:
            self._sock, self._file = self._connect()
        return self._sock, self._file

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock, self._file = None, None

    def __enter__(self) -> "CaptureBridge":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- core request -------------------------------------------------------

    def _request(self, proc: str, payload: str, retry: bool = True) -> str:
        """Send `proc <payload-as-one-list-element>` and read one response line.

        The request line is a two-element TCL list. `payload` becomes element
        two verbatim -- it is quoted exactly once here, so callers must pass
        the raw payload string and must NOT pre-brace it. Adding a second
        layer of braces makes the braces themselves part of the value, which
        is a confusing failure: `eval {{info patchlevel}}` asks TCL to run a
        command whose name is literally "info patchlevel".
        """
        # The server reads ONE line per request with `gets`. A newline anywhere
        # in the payload truncates the request mid-stream: the server waits for
        # a reply it will never send and the client just times out with no
        # error. Catch it here, where the message can actually say what to do.
        if "\n" in payload or "\r" in payload:
            raise CaptureBridgeError(
                f"{proc}: payload contains a newline. Requests must be a single "
                f"line -- join statements with '; ', or put the code in a .tcl "
                f"file and use source_file()."
            )

        request = f"{proc} {tcl_quote(payload)}"
        sock, fh = self._channel()
        try:
            sock.sendall(request.encode("utf-8") + b"\n")
            line = fh.readline()
        except (OSError, socket.timeout) as exc:
            self.close()
            if retry and self.persistent:
                # A persistent connection can be left desynchronized by an
                # earlier multi-line response. Reconnecting resets the stream.
                return self._request(proc, payload, retry=False)
            raise CaptureBridgeError(f"{proc}: transport failure: {exc}") from exc
        finally:
            if not self.persistent:
                try:
                    fh.close()
                    sock.close()
                except OSError:
                    pass

        if line == "":
            self.close()
            raise CaptureBridgeError(
                f"{proc}: no response (connection closed by Capture). A request "
                f"framed with outer braces causes exactly this -- the reply is "
                f"attempted against an empty socket handle inside a bare catch."
            )

        # Capture is on Windows and terminates lines with CRLF.
        response = line.rstrip("\r\n")
        # Return values are TCL lists, so a value containing spaces arrives
        # brace-wrapped -- the failure string always does.
        if response.strip("{}") == SERVER_ERROR:
            raise CaptureBridgeError(
                f"{proc}: Capture reported '{SERVER_ERROR}'. The server gives no "
                f"detail. Most common causes: the proc is not defined; it does "
                f"not take exactly one argument; or it raised an error internally."
            )
        return response

    def call(self, proc: str, args: Sequence[object] = ()) -> str:
        """Invoke `proc` in Capture with `args` and return its response line.

        The server hands the proc exactly one argument -- the whole argument
        list -- so `proc` must be declared to take one parameter, and unpack
        it with lindex the way Cadence's shipped methods do.
        """
        return self._request(proc, tcl_list(args))

    # -- conveniences -------------------------------------------------------

    def eval(self, script: str) -> str:
        """Evaluate an arbitrary TCL script inside Capture.

        `eval` takes a single argument, so it satisfies the dispatch convention
        and acts as a universal escape hatch to the full interpreter.
        Keep the result single-line.

        The script is sent as the raw payload rather than as a one-element
        list: `eval` wants the script itself, not a list wrapping it.
        """
        return self._request("eval", script)

    def eval_flat(self, script: str) -> str:
        """Evaluate TCL whose result may span multiple lines.

        The protocol allows exactly one response line, so a multi-line result
        desynchronizes the stream: this reply is truncated and every later
        reply is off by one. This wraps the script so newlines in the RESULT
        collapse to spaces before it is sent back.

        [format %c 10] produces the newline character without putting a
        backslash escape in the payload, which keeps the quoting simple.
        """
        return self._request(
            "eval", "join [split [" + script + "] [format %c 10]] { }"
        )

    def ping(self) -> bool:
        """True if Capture answers. Uses the TCL patchlevel as a cheap probe."""
        return bool(self.eval("info patchlevel"))

    def tcl_version(self) -> str:
        return self.eval("info patchlevel")

    def dbo_command_count(self) -> int:
        """How many Dbo* database commands the interpreter exposes."""
        return int(self.eval("llength [info commands Dbo*]"))

    def define_proc(self, name: str, body: str, params: str = "pList") -> None:
        """Define a proc inside Capture over the wire.

        Defaults to the one-parameter signature the dispatcher requires.
        """
        self.eval(f"proc {name} {{{params}}} {{{body}}}")

    def source_file(self, path: str) -> str:
        """Have Capture source a .tcl file from disk.

        Cheaper and far more robust than pushing a large script through eval:
        no quoting to escape and no single-line constraint on the file itself.
        """
        return self.eval(f"source {tcl_quote(path)}")

    # -- structured queries (require capBridgeQuery.tcl to be sourced) ------

    PART_FIELDS = ("refdes", "schematic", "page", "value", "footprint", "part_number")

    def _rows(self, proc: str) -> list[list[str]]:
        """Call a capBridge query and return its rows, minus the OK token."""
        elements = parse_tcl_list(self.call(proc))
        if not elements:
            return []
        if elements[0] == "ERROR":
            raise CaptureBridgeError(f"{proc}: {' '.join(elements[1:])}")
        return [parse_tcl_list(row) for row in elements[1:]]

    def parts(self) -> list[dict[str, str]]:
        """Every placed part instance, as dicts keyed by PART_FIELDS."""
        return [
            dict(zip(self.PART_FIELDS, row + [""] * (len(self.PART_FIELDS) - len(row))))
            for row in self._rows("::capBridge::parts")
        ]

    def pages(self) -> list[dict[str, str]]:
        """Schematic/page structure with a part count per page."""
        return [
            dict(zip(("schematic", "page", "part_count"), row))
            for row in self._rows("::capBridge::pages")
        ]

    def nets(self) -> list[dict[str, object]]:
        """Every flat net with its pin count."""
        return [
            {"net": r[0], "pin_count": int(r[1])}
            for r in self._rows("::capBridge::nets")
            if len(r) >= 2
        ]

    def connectivity(self) -> list[dict[str, object]]:
        """Every flat net with the reference designators it connects.

        This is the netlist in the form an agent actually wants to reason
        about: net -> the parts on it.
        """
        out: list[dict[str, object]] = []
        for r in self._rows("::capBridge::connectivity"):
            if len(r) < 2:
                continue
            refs = parse_tcl_list(r[2]) if len(r) > 2 else []
            out.append({"net": r[0], "pin_count": int(r[1]), "refdes": refs})
        return out

    WORKFLOWS = ("preNetlistCheck", "bomScrubber", "hsNetAudit", "netNamingAudit")

    def run_workflow(self, name: str) -> list[str]:
        """Run one of the four Capture workflows and return its printed output.

        The workflows report via `puts` to Capture's Command Window, which an
        external caller cannot see. capBridgeQuery installs a namespace-local
        `puts` inside ::pcbWorkflows that tees every line into a buffer, so the
        full report comes back here as a list of lines. The output still
        appears in the Command Window as usual.
        """
        if name not in self.WORKFLOWS:
            raise CaptureBridgeError(f"unknown workflow {name!r}; expected one of {self.WORKFLOWS}")
        elements = parse_tcl_list(self.call("::capBridge::runWorkflow", [name]))
        if elements and elements[0] == "ERROR":
            raise CaptureBridgeError(f"runWorkflow {name}: {' '.join(elements[1:])}")
        return elements[1:]

    @staticmethod
    def triage(lines: Iterable[str]) -> dict[str, list[str]]:
        """Split workflow output into errors and warnings."""
        out: dict[str, list[str]] = {"errors": [], "warnings": []}
        for ln in lines:
            s = ln.strip()
            if s.startswith("ERROR"):
                out["errors"].append(s)
            elif s.startswith("WARN"):
                out["warnings"].append(s)
        return out

    def has_active_design(self) -> bool:
        """True if a design is currently active.

        Returns False when Capture is running with no design open, or when the
        active window is not a design window.
        """
        handle = self.eval(
            "set s $::DboSession_s_pDboSession; DboSession -this $s; "
            "set d [$s GetActiveDesign]; set d"
        )
        return handle not in ("NULL", "", "0")


def _main(argv: Sequence[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Talk to OrCAD Capture's TCL Communication Server.")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="report connectivity and interpreter state")
    e = sub.add_parser("eval", help="evaluate a TCL script inside Capture")
    e.add_argument("script")
    c = sub.add_parser("call", help="invoke a proc with arguments")
    c.add_argument("proc")
    c.add_argument("args", nargs="*")

    ns = p.parse_args(argv)
    try:
        with CaptureBridge(ns.host, ns.port) as cap:
            if ns.cmd == "status":
                print(f"connected      : {ns.host}:{ns.port}")
                print(f"tcl version    : {cap.tcl_version()}")
                print(f"Dbo* commands  : {cap.dbo_command_count()}")
                print(f"active design  : {cap.has_active_design()}")
            elif ns.cmd == "eval":
                print(cap.eval(ns.script))
            elif ns.cmd == "call":
                print(cap.call(ns.proc, ns.args))
    except CaptureBridgeError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
