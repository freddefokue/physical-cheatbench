"""Spending ledger shared by every process: one append-only JSONL file guarded by an exclusive file lock.

Before each model call, `reserve(provider, upper_bound, tag)` atomically checks
    settled spending + open reservations + upper_bound <= cap(provider)
across all processes (totals are re-read from the file under the lock) and appends a reservation. After the call,
`settle(rid, ...)` appends the real cost and closes the reservation. A reservation that is never settled (a crash)
keeps counting at its upper bound, so caps fail safe. Caps: environment variables PCB_CAP_<PROVIDER> (USD, project
total since the first call). Records written before reservations existed are plain cost records and still count.
"""
import fcntl
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "results" / "ledger.jsonl"
_tlock = threading.Lock()
_cache = {"path": None, "offset": 0, "spent": {}, "open": {}}


class BudgetExceeded(RuntimeError):
    pass


@contextmanager
def _locked():
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with _tlock, open(str(LEDGER) + ".lock", "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _refresh():
    """Read records appended since the last call (by any process). Caller holds the lock."""
    c = _cache
    if c["path"] != str(LEDGER):
        c.update(path=str(LEDGER), offset=0, spent={}, open={})
    if not LEDGER.exists():
        return c
    with open(LEDGER, "rb") as f:
        f.seek(c["offset"])
        data = f.read()
    end = data.rfind(b"\n") + 1                       # ignore a partially written last line
    for line in data[:end].decode("utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        p = r.get("provider", "?")
        kind = r.get("kind", "cost")
        if kind == "reserve":
            c["open"][r["rid"]] = (p, float(r["amount"]))
        elif kind == "settle":
            c["open"].pop(r.get("rid"), None)
            c["spent"][p] = c["spent"].get(p, 0.0) + float(r.get("cost", 0.0))
        else:
            c["spent"][p] = c["spent"].get(p, 0.0) + float(r.get("cost", 0.0))
    c["offset"] += end
    return c


def _append(rec):
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def cap(provider):
    v = os.environ.get(f"PCB_CAP_{provider.upper()}")
    return float(v) if v else 0.0


def totals(provider):
    """(settled spending, open reservations) for a provider, including other processes."""
    with _locked():
        c = _refresh()
        reserved = sum(a for p, a in c["open"].values() if p == provider)
        return c["spent"].get(provider, 0.0), reserved


def spent(provider=None):
    with _locked():
        c = _refresh()
        if provider is None:
            return sum(c["spent"].values())
        return c["spent"].get(provider, 0.0)


def reserve(provider, amount, tag=""):
    """Atomically reserve `amount` USD against the provider cap; raises BudgetExceeded."""
    amount = float(amount)
    with _locked():
        c = _refresh()
        s = c["spent"].get(provider, 0.0)
        r = sum(a for p, a in c["open"].values() if p == provider)
        limit = cap(provider)
        if s + r + amount > limit:
            raise BudgetExceeded(f"{provider}: spent ${s:.2f} + reserved ${r:.2f} + ${amount:.2f} > cap ${limit:.2f}")
        rid = uuid.uuid4().hex[:16]
        _append({"t": round(time.time(), 1), "kind": "reserve", "rid": rid, "provider": provider,
                 "amount": round(amount, 6), "tag": tag})
        c["open"][rid] = (provider, amount)
        return rid


def settle(rid, provider, model, tag, usage, cost):
    with _locked():
        _refresh()
        _append({"t": round(time.time(), 1), "kind": "settle", "rid": rid, "provider": provider, "model": model,
                 "tag": tag, "usage": usage, "cost": round(float(cost), 6)})
        _refresh()


def release(rid, provider, tag=""):
    """Close a reservation for a call that was not billed (rejected before generation)."""
    settle(rid, provider, "", tag, {"released": True}, 0.0)


def check(provider):
    """Compatibility: refuse when settled + reserved spending has reached the cap."""
    s, r = totals(provider)
    if s + r >= cap(provider):
        raise BudgetExceeded(f"{provider}: spent ${s:.2f} + reserved ${r:.2f} of cap ${cap(provider):.2f}")


def record(provider, model, tag, usage, cost):
    """Compatibility: an unreserved cost record (only for calls whose cost was not bounded in advance)."""
    with _locked():
        _refresh()
        _append({"t": round(time.time(), 1), "provider": provider, "model": model, "tag": tag, "usage": usage,
                 "cost": round(float(cost), 6)})
        _refresh()
