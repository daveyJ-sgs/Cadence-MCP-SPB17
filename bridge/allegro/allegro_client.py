#!/usr/bin/env python3
"""
allegro_client.py — external client for Allegro PCB Editor 17.4.

Counterpart to capture_bridge.py. Talks to allegro_helper.py, which Allegro
spawned via ipcBeginProcess, which relays to SKILL.

    python bridge/allegro/allegro_client.py "axlDBGetDesign()"
    python bridge/allegro/allegro_client.py --ping

Requires, once per Allegro session, at the Skill> prompt:

    load(".../bridge/allegro/allegroBridge.il")
    abStart()
"""

from __future__ import annotations

import socket
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9030


class AllegroBridgeError(RuntimeError):
    pass


class AllegroBridge:
    """One SKILL expression per call, one line back.

    Single-line in both directions, same as the Capture bridge: each side
    does one readline per exchange, so an embedded newline desynchronizes
    everything after it. The SKILL side flattens results before sending.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout: float = 130.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self._sock: socket.socket | None = None
        self._file = None

    def _channel(self):
        if self._sock is None:
            try:
                self._sock = socket.create_connection((self.host, self.port),
                                                      timeout=self.timeout)
            except OSError as exc:
                raise AllegroBridgeError(
                    f"Nothing listening on {self.host}:{self.port}.\n"
                    f"In Allegro at the Skill> prompt run:\n"
                    f'    load(".../bridge/allegro/allegroBridge.il")\n'
                    f"    abStart()"
                ) from exc
            self._file = self._sock.makefile("r", newline="\n")
        return self._sock, self._file

    def send(self, expr: str) -> str:
        if "\n" in expr or "\r" in expr:
            raise AllegroBridgeError(
                "expression contains a newline; requests must be one line"
            )
        sock, fh = self._channel()
        sock.sendall(expr.encode("utf-8") + b"\n")
        line = fh.readline()
        if line == "":
            self.close()
            raise AllegroBridgeError("connection closed by helper")
        r = line.rstrip("\r\n")
        if r == "__SKILL_GONE__":
            raise AllegroBridgeError("Allegro/SKILL side is gone")
        if r.startswith("__TIMEOUT__"):
            raise AllegroBridgeError(r)
        return r

    def ping(self) -> str:
        return self.send("__PING__")

    def close(self) -> None:
        for x in (self._file, self._sock):
            try:
                if x:
                    x.close()
            except OSError:
                pass
        self._sock, self._file = None, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    try:
        with AllegroBridge() as a:
            if argv[0] == "--ping":
                print(a.ping())
            else:
                print(a.send(" ".join(argv)))
    except AllegroBridgeError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
