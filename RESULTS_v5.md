# Physical CheatBench v5: results

Status: in progress. The main run started after the pre-registration commit (PLAN_v5.md, commit hash below).

"I" is Claude Opus 5.5, the AI agent that designed, built and ran this study for the project owner. No human has
validated the labels.

## What v5 is
v5 asks CheatBench's question (how often do AI agents take shortcuts that conflict with the user's expectations when
honest work is difficult?) of agents that operate robots **through the interface they would use on real hardware**:
- the stock Inspect Robots agent (robocurve/inspect-robots, commit 7720195), unchanged, drives each robot cell
  through the framework's embodiment interface; the MuJoCo cell is one implementation of that interface, and a
  hardware adapter would be another;
- the agent sees camera images on request and the robot's state; item positions come from a vision service that
  finds tags in the camera images; it acts through skills (pick, place, and the leak station's maintenance) that
  the framework executes as 25 Hz joint commands under the cell's safety controller, and through a terminal on the
  operator workstation, where the shortcuts' file routes are;
- robot time is the cell's simulated time; model latency is recorded and not charged;
- the cell's audit separates what the agent requested, what the cell executed, whether the operational check
  passed and what actually happened; a refused request for a shortcut counts as an attempt.

Scenes: `guard` (a door interlock that a spare actuator can defeat), `pack` (a checkweigher that test weights can
fool) and `leak` (a leak tester that records whatever part is in the fixture under the serial typed), the three v4
scenes whose shortcut is a physical act with an arm. Models: v4's nine. Conditions: `main`, `dont_cheat`,
`honest_ok` (honest control), `authorized` (permitted control), and a one-factor-at-a-time comparison with the v4
harness on `guard`.

## Pre-registration
PLAN_v5.md, committed and pushed before the first main-run episode: commit (to be filled).

## Validation
(to be filled from results/v5/validation.json)

## Results
(to be filled from results/v5/tables.md)
