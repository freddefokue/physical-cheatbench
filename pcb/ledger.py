"""Spending ledger: every model call is appended (with its cost) before the next one may start; hard caps per provider.

Caps come from environment variables PCB_CAP_ANTHROPIC, PCB_CAP_OPENAI, PCB_CAP_OPENROUTER (USD for this project).
"""
import json
import os
import threading
import time
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "results" / "ledger.jsonl"
_lock = threading.Lock()
_spent = None


class BudgetExceeded(RuntimeError):
    pass


def _load():
    global _spent
    if _spent is None:
        _spent = {}
        if LEDGER.exists():
            for line in LEDGER.read_text().splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                _spent[r["provider"]] = _spent.get(r["provider"], 0.0) + float(r.get("cost", 0.0))
    return _spent


def cap(provider):
    v = os.environ.get(f"PCB_CAP_{provider.upper()}")
    return float(v) if v else 0.0


def spent(provider=None):
    with _lock:
        s = _load()
        return sum(s.values()) if provider is None else s.get(provider, 0.0)


def check(provider):
    with _lock:
        s = _load().get(provider, 0.0)
    c = cap(provider)
    if s >= c:
        raise BudgetExceeded(f"{provider}: spent ${s:.2f} of cap ${c:.2f}")


def record(provider, model, tag, usage, cost):
    with _lock:
        s = _load()
        s[provider] = s.get(provider, 0.0) + cost
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 1), "provider": provider, "model": model, "tag": tag,
                                "usage": usage, "cost": round(cost, 6)}) + "\n")
