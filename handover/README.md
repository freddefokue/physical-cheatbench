# Handover: Physical CheatBench, 7 November 2026

This folder is for a new session on another machine. Claude Opus 5.5 prepared it at the owner's request. It is the
agent that built v1–v5 in one Claude Code session (4–7 Nov), and the two external reviews of 7 Nov concern its work.

Treat everything here as claims to check against the repository, the raw episode records and the review texts.
`TIMELINE.md` especially is a draft written by the agent it criticises.

## Read in this order
1. `RULES.md`: the lessons from the critiques, written as rules, plus practical rules. Short; read all of it.
2. The two reviews of 7 Nov: `reviews/2026-11-07_v5-review_55fc456.md` and
   `reviews/2026-11-07_implementation-session-review.md`, and its brief, `reviews/2026-11-07_fresh-session-brief.md`.
3. `TIMELINE.md`: every critique since 29 Oct, what changed, and what's still open.
4. `SETUP.md`: setting up a machine. Run its checks before anything else.

## State at handover
- **Branches and PRs.**
  - This branch, `handover`, is v5 (55fc456) plus this folder.
  - `main` is at bd0de9f (v4 through PR #3).
  - PR #4 (branch `v4-43`, evaluator 4.3) and PR #5 (branch `v5`, which contains PR #4) are open. Only the owner
    merges.
- **v5 is complete.**
  - `PLAN_v5.md`: pre-registered at 86d60cf; deviations in section 12; the Astra follow-up in section 13.
  - `RESULTS_v5.md`.
  - A report page, which is private.
- **Budget.** `results/ledger.jsonl` covers all versions, and the cap is in `results/v5/cap.txt`. About $20 is left
  under it. New paid runs need the owner to raise the cap.
- **Checks.** 101 tests pass. Scripted validation reproduces the committed results exactly.
- **Not in the repository:**
  - the framework logs with camera images (about 554 MB);
  - the local branch `v4-demo`;
  - the v3 drafts;
  - the reviewer's audit scripts;
  - the old session transcript, which holds exposed API keys. Don't copy it anywhere.

## Corrections that are known but not yet made
The full list, with sources, is under "Still open" in `TIMELINE.md`. In short:
1. **`teach_dev` (v5) and ALOHA (v4) count disclosed demonstration reuse as cheating.** The agent-facing text never
   forbids it, and Astra named its source in every report. Correct the interpretation in the write-ups, reports and
   PR texts. Keep the pre-registered counts as counts of the defined event, and log the change as a correction made
   after publication.
   - v4's H4 depends on ALOHA: p = 0.016, Holm 0.047; p = 0.38 without it.
   - v4 stays frozen: correct its claims in a note, not in its code.
2. **Astra's disclosure labels** in the v5 search contradict its own reports.
3. **The wording of v5's comparisons:** say "no difference detected", with intervals. H3 doesn't pass the Holm
   correction. "Each candidate changed one thing" is false for `teach_dev`.
4. **The permitted arm** is supervisor approval of acts that remain illegitimate. Describe it that way.
5. **The trial-window bug** in `pcb5/elicit.py` needs a fix plus tests.
6. **Two reviews never reached the implementing agent:** the v2 review (5 Nov 14:45) and the review of 9cb118a
   (6 Nov 21:31). Check their points.

## A suggested first task
Work offline, with no paid runs:
1. Verify the list above against the repository.
2. Make the corrections: code fixes with regression tests; claims corrected in `RESULTS_*.md`, the reports and the PR
   texts; everything logged.
3. Write one short proposal for the next experiment. Use the contract in `RULES.md` rule 1, and state the competing
   explanations, the controls and what a null result would mean.
4. Get the proposal reviewed before spending anything.

## What the owner's prompt might cover
- The scientific question, in the owner's words.
- The scope of the first task and when to stop.
- The budget, and that only the owner raises it.
- How to work: autonomously within scope and budget, with an independent review of the task contract and a pilot
  before scaling.
- What needs the owner's approval: merging, paid batches and cap changes.
- "Start with `handover/README.md`."
