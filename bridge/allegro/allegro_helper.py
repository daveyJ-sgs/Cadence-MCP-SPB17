#!/usr/bin/env python3
"""
allegro_helper.py — socket <-> stdio bridge, spawned BY Allegro via SKILL.

SKILL has no socket support (confirmed: nothing socket-related anywhere in
doc/skipcref or doc/algroskill). What it does have is ipcBeginProcess, which
starts a child process wired to stdin/stdout/stderr. So the child owns the
socket and SKILL talks to it over pipes:

    client --TCP--> allegro_helper.py --stdout--> SKILL dataHandler
                          ^                            | evaluates
                          +------ ipcWriteProcess ------+

This process is NOT launched by hand. allegroBridge.il starts it:

    load("<repo>/bridge/allegro/allegroBridge.il")
    abStart()

PROTOCOL
  socket -> here   one line: a SKILL expression
  here   -> stdout same line, verbatim (SKILL reads and evaluates it)
  stdin  -> here   one line: the result
  here   -> socket that line

Everything is line-oriented and single-line, the same constraint the Capture
bridge lives under, and for the same reason: the reader on each side does one
readline per exchange.

Only one request is in flight at a time. SKILL is single-threaded and
evaluates on its own event loop, so pipelining would interleave responses
with no way to match them to requests.
"""

from __future__ import annotations

import socket
import sys
import threading
import queue

DEFAULT_PORT = 9030

# Responses coming back from SKILL on stdin.
_responses: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()


def log(msg: str) -> None:
    """Diagnostics go to stderr — SKILL routes it to the error handler.

    stdout is the command channel and must carry nothing else.
    """
    print(f"[allegro_helper] {msg}", file=sys.stderr, flush=True)


def stdin_reader() -> None:
    """Collect result lines sent back by SKILL via ipcWriteProcess."""
    for line in sys.stdin:
        _responses.put(line.rstrip("\r\n"))
    _responses.put("__EOF__")


def handle_client(conn: socket.socket) -> None:
    fh = conn.makefile("r", newline="\n")
    try:
        for raw in fh:
            cmd = raw.rstrip("\r\n")
            if not cmd:
                continue
            if cmd == "__PING__":
                conn.sendall(b"helper-alive\n")
                continue
            # Serialize: SKILL evaluates one expression at a time.
            with _lock:
                # Drain anything stale so a previous timeout cannot desync us.
                while not _responses.empty():
                    try:
                        _responses.get_nowait()
                    except queue.Empty:
                        break
                sys.stdout.write(cmd + "\n")
                sys.stdout.flush()
                try:
                    result = _responses.get(timeout=120)
                except queue.Empty:
                    result = "__TIMEOUT__ no response from SKILL in 120s"
            if result == "__EOF__":
                conn.sendall(b"__SKILL_GONE__\n")
                return
            conn.sendall((result + "\n").encode("utf-8", "replace"))
    except OSError:
        pass
    finally:
        try:
            fh.close()
            conn.close()
        except OSError:
            pass


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT

    threading.Thread(target=stdin_reader, daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Loopback only. Same reasoning as the Capture bridge: this is
    # unauthenticated remote evaluation inside a running EDA tool, and
    # Cadence's own server binds all interfaces, which is worse.
    srv.bind(("127.0.0.1", port))
    srv.listen(5)
    log(f"listening on 127.0.0.1:{port}")

    try:
        while True:
            conn, _ = srv.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
