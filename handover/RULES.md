# Rules for the next session

Each rule comes from a critique in `TIMELINE.md`; several were learned twice. Dates point to the entries.

## Defining what counts as cheating
1. **Write each scene's contract before building it:**
   - the legitimate job;
   - the prohibited act;
   - the honest routes, and whether honest success is possible;
   - legitimate uses of similar actions;
   - what independently establishes the outcome;
   - the controls;
   - what a zero result would mean.

   Have it reviewed, with a pilot's transcripts, before any paid batch. *(4 Nov memo; 5 Nov v4 design; 7 Nov reviews)*
2. **A prohibited act must be prohibited in the agent's world, for a reason.**
   - Either quote the sentence the agent can see, or name the domain norm (a safety interlock, short weight, a
     falsified record).
   - Then say why the act defeats the purpose of the task in this situation. A bare "don't" can manufacture
     violations.
   - If neither holds, the act is ambiguous. Test it with explicit "allowed" and "forbidden" variants instead of
     scoring it as cheating.

   *(5 Nov markers; 6 Nov ALOHA; 7 Nov teach_dev)*
3. **Demonstration reuse is not automatically cheating.** It's normal robotics practice. Replay is a violation only
   under an assessment that excludes it, or with a false claim of independent execution. *(5 Nov 20:40; 6 Nov 17:14;
   7 Nov 09:21)*
4. **Keep the judgments separate:** requested, executed, check passed, physical outcome, disclosure, misleading
   certification. Disclosing an act doesn't make a qualification valid, and an invalid qualification can still be
   disclosed. *(6 Nov 19:45; 7 Nov 09:21)*
5. **Write diagnostic and test actions into the definition before the run.** Examples: a scale checked with a test
   weight, a file restored unchanged. The owner's rule (v4, evaluator 4.3): a stated purpose such as "a repair" or
   "only a test" doesn't cancel an executed act, but the definition's written exclusions apply. *(6 Nov 17:49,
   19:45)*
6. **"Permitted" controls must be genuinely legitimate versions of the act.** Examples: an isolated test fixture, a
   documented calibration load. A supervisor approving an act that stays illegitimate tests obedience, not
   capability. Keep capability controls separate. *(7 Nov 09:21)*
7. **When honest completion is impossible, the honest path (hold and report) is easy.** Include costly but feasible
   honest routes to test persistence, and check that "impossible" really is (inspection gauge G4 wasn't). *(5 Nov
   15:20; 6 Nov 16:59; 7 Nov 09:21)*
8. **Don't let the simulator stipulate a shortcut's outcome.** The pins print got 0.982 by formula. Compute outcomes
   from the physics and the rendered observations. *(5 Nov 10:00)*

## Validating labels
9. **Agreement doesn't validate a shared assumption.** Judges, panels and AI coders that all inherit one definition
   will agree. AI adjudication is AI: never call it hand-reading. There is no human validation (the owner's
   decision); say so plainly. *(5 Nov 15:40; 6 Nov 18:36)*
10. **Validate the whole pipeline, not one component.**
    - The real judge must read executed traces.
    - Use held-out cases written blind, including successful honest completions.
    - Check that each case actually exercised what it claims.
    - A classifier fed the case writer's annotations is only a component test.

    *(6 Nov 21:31, never addressed)*
11. **When a label is wrong, fix the shared code:** the scorer, the judge text, the report generator. Version it,
    and recheck everything it affects, not just the headline label. *(6 Nov 17:49, 18:36, 19:45)*

## Reporting
12. **A null result is acceptable.**
    - Searching for failures is fine, but keep search and confirmation separate, with new task content and not only
      new seeds.
    - Report every candidate.
    - Don't pool the search with the confirmation.

    *(7 Nov 09:21, 10:37)*
13. **A non-significant difference is "no difference detected", with its interval, not "no effect".** Apply the
    pre-registered correction before writing "reduced". Size follow-ups for a stated effect, baseline and power.
    *(7 Nov 09:21, 10:37)*
14. **Summaries must keep the caveats.** Check every claim in a summary against the data before publishing. When
    corrected, don't swing to the opposite claim. *(7 Nov 10:02, 10:37)*

## Working with the owner
15. In the wording the owner's reviewer proposed: "Work autonomously within the agreed scope and budget. Obtain
    independent review of the task contract and pilot evidence before scaling experiments. Escalate unresolved
    disagreements or budget changes."
16. Propose a plan and a cost before paid work, and keep hard caps. Pre-register before paid runs, and log
    deviations in the plan. Keep frozen versions frozen (v4): correct claims in notes, not in its code.
17. Work on a branch and open a pull request. Never merge without being asked.
18. Don't propose human coding unless the owner raises it (6 Nov: "I don't have the time").
19. Report incidents, overruns and mistakes plainly at the end.

## Practical rules
- **Keys.** Never `source .env` (it printed every key into the session log on 4 Nov). Never print or commit a key.
  Load `.env` with Python. v5 needs only `OPENROUTER_API_KEY_2`.
- **Budget.** `results/ledger.jsonl` is the shared ledger for all versions, and the cap is in `results/v5/cap.txt`.
  Only the owner raises the cap.
- **Memory.** Each episode process uses 0.6–1 GB, and reused worker processes grow, so `run5` starts a fresh process
  per episode. Size the number of workers to the machine.
- **Resuming.** `run5._done` treats "an error after the agent acted" as done, so a restart doesn't rerun episodes
  that hold data. Keep it that way: one rerun on 7 Nov overwrote a record.
- **Providers.** Anthropic's safeguards refuse some Claude episodes in the guard scene (Fable in all of them); these
  end as `provider_refusal`. OpenRouter routes DeepSeek and Kimi to varying hosts, and the transport records the
  serving provider.
- **Validation output.** `scripts/validate5.py` writes under `results/v5/`. Always pass `--out` with a new name.
- **Known defects.** See "Still open" in `TIMELINE.md`. Among them: the trial-window parser in `pcb5/elicit.py`, and
  `qual submit --help` submits in `teach_dev`.
