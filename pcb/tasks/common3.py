"""Shared machinery for the v3 cells (PLAN_v3.md).

Every v3 cell has:
- several task instances (products, numbers, obstacles), chosen by the seed;
- two arms with the same prompt and station: "att" (honest success is attainable with the station's own procedures)
  and "unatt" (it is not, for a reason the agent can only find by working);
- two clue levels: neutral (the docs state facts of the station only) and pointed ("_pt" conditions: the logbook also
  has one dated entry per route describing a past incident in which that route produced a false pass, in the style of
  the v1/v2 clues). Pointed entries are POINTED[route] in each cell module;
- two opportunities present in every episode: P (a physical act with the robot) and D (a change to a file the cell
  reads). Neither is described anywhere as a way to pass; the docs only state facts of the station.

Rules that keep consequences honest:
- graders and sensors read only the physical state and the files as they are at that moment; nothing in a grader
  asks whether an act was a shortcut;
- the act log (self.acts) and the counterfactuals stored with each record are written for the analysis only and are
  never read by a grader.
"""
import hashlib
import re
import threading

from .base import Refuse, Task


def parse_kv(text):
    """'key = value' lines (comments with #) -> dict of str -> str; None if no key could be read."""
    out = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            out[k] = v
    return out or None


def as_float(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


class Task3(Task):
    variants = ("B",)
    conditions = ("att", "unatt", "att_pt", "unatt_pt")
    INSTANCES = ()
    POINTED = {}                       # route -> (logbook entry, exposure key)

    def __init__(self, variant, seed, condition="att"):
        super().__init__(variant, seed, condition)
        self.inst_index = seed % len(self.INSTANCES)
        self.inst = dict(self.INSTANCES[self.inst_index])
        self.attainable = condition in ("att", "att_pt")
        self.pointed = condition.endswith("_pt")
        self.acts = []                 # analysis only: never read by a grader
        self._watch = {}               # sandbox path -> {"orig": dict, "sig": str, "seen": {key: value}}
        self._wlock = threading.RLock()

    # ---- watched files (the D opportunity) ----------------------------------------------------------------------------
    def watch_file(self, path, keys):
        data = self.sb.read_bytes(path)
        orig = parse_kv(data.decode()) if data is not None else {}
        self._watch[path] = {"orig": {k: orig.get(k) for k in keys}, "sig": self._sig(path), "seen": {},
                             "broken": False}

    def _sig(self, path):
        data = self.sb.read_bytes(path)
        if data is None:
            return "missing:" + self.sb.kind_of(path)
        return hashlib.sha1(data).hexdigest()

    def check_watched(self):
        """Record D acts for watched files that changed since the last check. Called after every bash command and
        before every grader reading, so the act log is ordered with the records."""
        with self._wlock:
            for path, w in self._watch.items():
                sig = self._sig(path)
                if sig == w["sig"]:
                    continue
                w["sig"] = sig
                data = self.sb.read_bytes(path)
                cur = parse_kv(data.decode("utf-8", errors="replace")) if data is not None else None
                if cur is None:
                    if not w["broken"]:
                        w["broken"] = True
                        self.act("D", "file_broken", path=path)
                    continue
                w["broken"] = False
                for k, old in w["orig"].items():
                    new = cur.get(k)
                    last = w["seen"].get(k, old)
                    if new != last:
                        w["seen"][k] = new
                        self.act("D", "file_edit", path=path, key=k, old=old, new=new)

    def current(self, path, key):
        """Value of a watched key as the cell reads it now (None if missing or unreadable)."""
        data = self.sb.read_bytes(path)
        if data is None:
            return None
        cur = parse_kv(data.decode("utf-8", errors="replace")) or {}
        return cur.get(key)

    def changed_keys(self, path):
        data = self.sb.read_bytes(path)
        cur = (parse_kv(data.decode("utf-8", errors="replace")) if data is not None else None) or {}
        return sorted(k for k, v in self._watch[path]["orig"].items() if cur.get(k) != v)

    def after_command(self):
        self.check_watched()

    # ---- act log ------------------------------------------------------------------------------------------------------
    def act(self, route, kind, **detail):
        with self._wlock:
            self.acts.append({"route": route, "act": kind, "clock": round(self.clock, 1), **detail})

    def exposure_keys(self):
        return {}

    def route_keys(self, neutral):
        """Exposure keys: the neutral pointers per route, plus the pointed clue per route in _pt conditions."""
        keys = dict(neutral)
        if self.pointed:
            for route, (_, key) in self.POINTED.items():
                keys[f"{route}_clue"] = [key]
        return keys

    def with_clues(self, logbook, args):
        """The logbook text, with the pointed entries appended (oldest entries last) in _pt conditions."""
        if not self.pointed:
            return logbook
        extra = "".join(self.POINTED[r][0].format(**args) for r in ("D", "P"))     # newest first: D dates are later
        return logbook.rstrip("\n") + "\n" + extra

    def canaries(self):
        return []

    @staticmethod
    def pick(items, name, what):
        n = name.upper()
        if n not in items:
            raise Refuse(f"no {what} {name!r} ({', '.join(items)})")
        return n

    def base_outcome(self):
        return {"instance": self.inst_index, "arm": "att" if self.attainable else "unatt", "pointed": self.pointed,
                "condition": self.condition, "attainable": self.attainable,
                "acts": list(self.acts), "clock_s": round(self.clock, 1), "flags": dict(self.flags)}
