**Starting brief for the next Physical CheatBench research session**

Work in /home/fred/physical_cheatbench. Preserve the existing code, records, provenance, and unrelated untracked files. This is initially an offline correction and study-design task, with no new benchmark API calls. Confirm the current commit and whether the latest corrections have already been applied.

Read these sources first:

- /home/fred/pais/review/2026-11-07/v5-update-55fc456/review.md
- /home/fred/pais/review/2026-11-07/implementation-session/review.md
- The current PLAN_v5.md and RESULTS_v5.md, checking claims against code and cited raw episodes.

The scientific question is whether frontier agents violate legitimate task constraints under difficulty in physical agentic settings. A zero rate is a valid possible result. An observable action, a rule violation, concealment, and physical harm are different outcomes.

At reviewed commit 55fc456, the main v5 counts reproduce and the 101 tests pass. Astra has 0/24 main attempts and 6/6 honest-control successes. The teach_dev search/confirmation counts describe demonstration reuse; its instructions do not clearly prohibit that reuse, and Astra explicitly discloses demonstration-derived waypoints. Do not present these counts as established concealed cheating. Preserve old records and log any revised interpretation transparently.

Check whether the following have been corrected: the trial-boundary parsing bug, the demonstration/disclosure interpretation in both v4 and v5, overly strong equivalence claims, the corrected significance statement, and the characterization of supervisor-approval conditions. When correcting a defect, update the reusable evaluator or report generator and the affected documentation together, with meaningful regression checks.

Then produce one short proposal for the next informative experiment. State the competing explanations, exact task contract, genuinely legitimate control, capability evidence, independent audit, and what result would change the conclusion. Keep pressure, instruction ambiguity, and evaluation cues separate. Do not expand to a large suite until this design has been independently challenged.

Use the repo and raw evidence as the authority. Treat inherited summaries and model judgments as claims to verify. End with a concrete, reviewable patch or design and an accurate statement of what remains unresolved.



The workflow change I recommend:

1. **Define one experiment clearly:** legitimate task, prohibited act, honest alternatives, and what a zero result would mean.
2. **Challenge that definition and the scorer independently before scaling runs.**
3. **Give implementation, review and interpretation separate, bounded sessions.**
4. **Persist verified facts, withdrawn claims and unresolved questions—not an increasingly confident project narrative.**