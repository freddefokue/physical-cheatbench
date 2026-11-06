"""Evaluator version, recorded in every episode (PLAN_v4.md section 12, item 12).

4.0: the published v4 run (episodes have no evaluator_version field).
4.1: repaired after the reviews of 6-7 Nov 2026: photo provenance by content (round), trial state on joint-command acts
     and rounded recorded poses (aloha), ballast only when it loads the scale, extra units logged, order-file restores
     not counted as edits (pack), scene descriptions for judges and coders from the scene classes, and the
     classifier rules of pcb/classify4.py for 4.1.
"""
EVALUATOR_VERSION = "4.1"
