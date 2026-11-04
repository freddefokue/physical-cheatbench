"""Workcell client library (runs inside the operator workstation).

Every cell tool (robot, station, and the station-specific tools) talks to the cell controller over a Unix socket.
Command line:  robot locate B1      Python:  import workcell; r = workcell.call("robot", "locate", "B1"); print(r.text)
Results carry .ok (bool), .text (what the command line prints) and .data (structured values, when the command has any).
"""
import json
import socket
import sys

SOCKET_PATH = "/run/workcell/cell.sock"


class Result:
    def __init__(self, d):
        self.ok = d.get("code", 1) == 0
        self.code = d.get("code", 1)
        self.text = d.get("text", "")
        self.data = d.get("data") or {}

    def __repr__(self):
        return f"Result(ok={self.ok}, text={self.text!r}, data={self.data!r})"


def call(tool, *args, timeout=600):
    """Send one command to the cell controller and wait for its result."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(SOCKET_PATH)
    except OSError as e:
        return Result({"code": 2, "text": f"{tool}: cell controller not reachable ({e})"})
    req = json.dumps({"tool": tool, "argv": [str(a) for a in args]}) + "\n"
    s.sendall(req.encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    try:
        return Result(json.loads(buf.decode()))
    except ValueError:
        return Result({"code": 2, "text": f"{tool}: malformed reply from cell controller"})


def robot(*args):
    return call("robot", *args)


def cli(tool):
    args = sys.argv[1:]
    as_json = False
    if "--json" in args:
        as_json = True
        args = [a for a in args if a != "--json"]
    r = call(tool, *args)
    if as_json:
        print(json.dumps({"ok": r.ok, "text": r.text, "data": r.data}))
    elif r.text:
        print(r.text)
    sys.exit(r.code)
