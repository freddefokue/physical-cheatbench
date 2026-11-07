**Review of the Physical CheatBench implementation session — 7 November 2026**

**Recommendation:** keep the implementation and use the current agent for bounded corrections, but begin the next research phase in a fresh session with a corrected brief and an independent review checkpoint. Try Hermes on a small, comparable task if its automation is useful. A wholesale migration is not yet justified by the failures in this transcript.

**Scope and evidence.** I parsed the main Claude Code session, de09f32e-9fe9-443e-9ddc-150fec816959, spanning 4–7 November: 19,752 event lines, 2,673 distinct tool calls, and seven compactions. I read the main requests, delivery reports, correction exchanges, compaction excerpts, current project memory, and selected tool operations. I also inspected the separate coding session's request and summary to distinguish its work from the implementation agent's work. Parsing the entire file is not the same as close-reading every tool payload. This assessment also uses the preceding [v5 code/results review](../v5-update-55fc456/review.md).

Selected user and assistant messages, with original line numbers and timestamps, are in [evidence.md](evidence.md). [audit.json](audit.json) contains the metrics; [audit_session.py](audit_session.py) reproduces them without model calls. Research files, Claude memory, and session state were not changed.

**Has the agent been good?**

It has been a productive implementer and a cooperative respondent to criticism. It has been less reliable as the final authority on experimental validity and claims.

There is substantial engineering value here: working simulation cells, controller-backed skills, an Inspect Robots adapter, image-based tag detection, spending ledgers, recorded traces, versioned evaluators, tests, analysis scripts, reproducible reports, and an audit trail of deviations. The previous review reproduced the v5 counts and ran 101 passing tests. These are delivered artifacts, not just proposals.

The agent also repeatedly checked reviews against code and data, admitted mistakes, and made corrections. Its latest response, at source line 19743, explicitly withdraws the strong Astra-cheating interpretation and acknowledges that its own report omitted the demonstration-source disclosure. That is a useful correction, and a reason not to discard the agent's technical knowledge.

The weakness is that too many important distinctions were enforced only after external review, sometimes more than once:

| Repeated issue | Evidence from the session | Implication |
|---|---|---|
| An ambiguous assignment is scored as cheating | At 2436 and 4432, the agent accepts the marker ambiguity and runs controls that sharply reduce the effect. At 19521, the new Astra headline again rests on demonstration use that the task did not clearly prohibit. | The earlier lesson was not made a required check for new scenes. |
| Disclosure is confused with qualification validity | At 13214, all three panel coders see Astra's demonstration use as disclosed; the author initially leaves its contrary label. At 13436, it accepts the distinction and corrects it. At 19521, the new report again emphasizes misleading use while omitting explicit source disclosure. | A previously corrected conceptual error recurs in a new task. |
| Published labels are repaired before the reusable pipeline | At 12234, six labels have been corrected but the evaluator still has the faults. At 12259 and 13436, stale briefing/version behavior remains after related fixes. | Fixes were too local, creating repeated review and reporting work. |
| Strong summaries exceed the tests | At 19521, the agent says the harness did not change rates; after review, at 19743, it accepts that the comparisons are not equivalence tests. | Reports need claim-level checks, not just matching numerical tables. |

This is not evidence of deliberate deception. It is evidence that the author can build and verify an implementation of its own assumptions without adequately challenging those assumptions. Multiple judges do not resolve that if they all inherit the author's task definitions.

The latest response is better, but still needs scientific restraint. “Astra hid nothing” is stronger than the narrower supported finding that its source was disclosed, and “teach_dev probably measures nothing” overcorrects: it measures demonstration use, but does not cleanly establish prohibited cheating. The proposed restored-rule experiment is sensible; its sample-size and cost estimates need a specified effect, baseline, power, and analysis before being treated as design calculations.

**Has it been inefficient?**

Yes, principally in the order of research decisions. It was quick to scale studies and polish reports before the central definitions and evaluator were sufficiently challenged. This produced expensive rounds of annotation repair, table regeneration, report updates, and renewed review. A small adversarial set of honest repairs, diagnostic acts, partial attempts, and disclosures should have preceded large batches. The later held-out evaluator exercise was useful precisely because it caught cases that the authored routes and passing unit tests missed (14158).

There were avoidable operational losses too. The v4 completion report acknowledges that a renderer change corrupted images and required voiding and rerunning 57 episodes (11539). The v5 report lists out-of-memory restarts and one accidental rerun (19521). In v2 the agent disclosed that sourcing the environment file printed credentials into the session log (4432). I did not reproduce or copy those credential values. These incidents argue for stronger deterministic run supervision and isolation, not just a different chat interface.

The repeated uncertainty about the Inspect Robots tool interface is another example. At 15189 and 15233 it describes major architectural limitations; its subsequent implementation successfully keeps the stock agent, terminal, and skill tools. That implementation is a success. An earlier minimal source-level spike could have reduced speculative redesign.

However, it would be unfair to call all iteration waste. The user explicitly authorized new directions: stronger tasks, genuine dynamics, v4, then Inspect Robots v5. The user also paused v3 and later requested an aggressive search for Astra failures. The agent respected the v3 pause (6180) and preserved its data. It offered human coding; the user lacked time and chose the AI-panel alternative. Those are shared research decisions, not failures attributable solely to the agent. Failed experiments and honest null results can be valuable.

The transcript does not support a precise dollar amount or percentage of waste. The research API ledger, the author's Claude Code usage, cached inputs, and subscription billing are different quantities. I would not convert the logged token totals into an invoice or claim that all spending on superseded versions was wasted.

**Is context rot the explanation, and should there be a fresh session?**

The conversation has carried too much work through one evolving narrative. Seven compactions occurred; four recorded pre-compaction sizes were about 968,000–970,000 tokens. Across 2,637 distinct assistant message IDs with usage, the median recorded input context is about 498,000 tokens. Those counters include cache reads. The final recorded input context is about 138,000 tokens after a recent compaction, so the session is not currently sitting at a million-token limit.

Long contexts and lossy summaries are plausible contributors. Anthropic documents that compaction can lose detailed earlier instructions and recommends keeping durable rules outside conversation history. [Claude Code documentation](https://code.claude.com/docs/en/how-claude-code-works).

But the transcript does not establish a causal diagnosis of context rot. Some warnings survived compaction, including marker ambiguity and later ALOHA/disclosure concerns. The agent can still inspect evidence, reason coherently, and accept corrections. The failure is partly that remembered caveats were not turned into checks that every new experiment had to pass. A fresh context alone cannot fix that.

I recommend a new session for the next research phase, after the current known corrections are completed or explicitly handed off. Do not carry over the full conversation as the new prompt. Use a compact, corrected brief with links to the evidence. Read current memory critically: the v5 memory currently contains both old “rates unchanged”/misleading-Astra summaries and a later paragraph retracting them. Restarting while blindly importing that mixed memory can preserve the same problem.

Use natural boundaries: one task-design decision, one implementation milestone, one validation exercise, or one analysis. The goal is not a fixed token cutoff or a daily ritual. It is to avoid making the same conversation simultaneously defend old conclusions, invent new tasks, repair code, run experiments, and write publicity.

**Would Hermes help?**

Assuming the user means Nous Research's Hermes Agent, it could help with continuity and unattended operations. Its documentation describes bounded persistent memory and searchable past sessions. Importantly, it explicitly recommends creating fresh sessions at natural boundaries; a continuously growing conversation also undermines its intended memory workflow. [Hermes memory documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory).

Its scheduler can run tasks in fresh agent sessions, respond to events, or execute scripts without invoking a model. That is potentially useful for checking deterministic experiment status and escalating real failures instead of spending a large research context on routine monitoring. [Hermes scheduled-task documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron).

Those features do not establish that Hermes will make better scientific judgments, correctly distinguish imitation learning from cheating, or validate a scorer. The underlying model, instructions, tools, and review process still matter. Automatic persistence can also carry forward an incorrect conclusion if it is saved as a fact. That is a workflow risk inferred from the role of persistent memory, not a measured failure of Hermes on this project.

Use Hermes as a coordinator if it solves a concrete operational need, while retaining Inspect Robots as the benchmark's agent/hardware interface. There is no reason to rewrite the experiment engine merely to try a different research assistant.

Before migrating, compare a fresh Claude Code session and Hermes on the same bounded task from the same repository snapshot, with the same underlying model where supported and comparable tool access, budget, and effort. A useful task would be the offline trial-boundary repair plus regression checks and a short evidence-based correction to the claims. Give both the same brief. Assess correctness, unsupported claims, necessary human intervention, elapsed time, and actual billed cost. Keep their checkouts separate and do not launch a new benchmark batch for this comparison. One task can establish whether Hermes is convenient here; it cannot establish universal superiority.

**A more effective way to run the project**

1. Maintain a short active project brief containing the scientific question, supported results, withdrawn claims, open uncertainties, exact source revisions, and the next decision. Store historical reasoning elsewhere, with pointers.
2. For each scene, define the legitimate task, prohibited act, honest route, legitimate uses of similar actions, observable evidence, independent outcome, and what a null result would mean. Challenge that definition before expanding the implementation.
3. Have an independent reviewer examine the contract and a small set of actual transcripts, including plausible honest alternatives. Ideally include a human with relevant domain judgment for disputed norms; if only models are available, disclose that and do not turn agreement into proof.
4. Validate mechanics and the evaluator, then run a small pilot, then freeze the study and authorize a larger batch. After a discovered defect, fix the shared pipeline and check all affected outputs, rather than only changing the headline labels.
5. Use scripts for running, monitoring, resuming, budgeting, and preserving evidence. Use agent reasoning for exceptions, design choices, and interpretation. Have a separate reviewer check final claims against traces and statistics.

For the Astra search, the objective should be to identify and validate situations where constraints are violated, while retaining honest nulls and ambiguous cases. “Find a scene that makes Astra cheat” is a legitimate exploratory instruction, but it needs that measurement constraint. The user requested the search; the agent's responsibility was to preserve it while resisting a weak positive interpretation.

A [fresh-session brief](fresh-session-brief.md) is provided as a starting point. Nothing has been launched, installed, or migrated as part of this review.
