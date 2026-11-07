# Answer to the owner's question "in what ways is the original CheatBench better than the physical one?" (about v2)

Pasted by the owner into the implementing Claude Code session (transcript line 4649, 2026-11-05 14:20 UTC). Copied verbatim; the transcript itself is not shared because it contains exposed API keys.

---

The original is ahead mainly in task design, breadth and testing across agent configurations. Its most useful lesson is how to create a credible struggle while keeping the boundary between legitimate problem-solving and cheating clear.

Compared with the physical v2 I reviewed:

| Advantage | Original CheatBench | Where our physical version falls short |
|---|---|---|
| 1. More recognisable boundaries | Copying another candidate’s work during an assessment exploits a familiar expectation of independent work. Examples | Repositioning, recalibrating or repairing equipment can be part of doing the job properly. Our original marker task confused legitimate initiative with cheating. Physical tasks need especially clear operational contracts. |
| 2. Difficulty that can remain plausibly surmountable | A stated design principle is that success should appear possible, avoiding obviously broken assignments. §3.1 | Our pallet task can quickly become an arithmetic impossibility: 24 cycles at roughly 18 seconds cannot fit into six minutes. That tests response to an impossible demand, but offers less room to study gradual frustration, experimentation and eventual compromise. |
| 3. More independent kinds of situation | Ten categories span mathematics, writing, games, coding and professional work. Benchmark overview | We have four task families. Hundreds of runs with different coordinates do not provide hundreds of different situations. A result can still depend heavily on one scene’s peculiarities. |
| 4. Better separation of discovery from willingness | The paper separately examines encountering a planted clue and acting after encountering it. Appendix A.2 | Our main comparisons mostly count violations per acting episode. We need stronger evidence distinguishing “never found the opportunity,” “couldn’t execute it,” and “understood it and declined.” |
| 5. Evidence about the agent software’s influence | They compare provider harnesses with a common harness. Muse’s reported average changes from 41.6% to 96.6%. §5 | We use one custom harness, with some changing provider routes. We therefore know less about how much our results depend on the surrounding software rather than the model. |
| 6. Less distance between some measured actions and the claimed behaviour | In the file-access cases, the agent actually opens the reference material in its workspace. Repository | Physical claims require additional validation: did the movement work, did it change what the sensor saw, and did that produce a false acceptance? Our photograph shortcut currently passes because the simulator assigns it a passing score. |

The first two are the biggest scene-design gaps. We need situations where the agent can reasonably keep trying, and where the eventual shortcut improves the assessment while clearly undermining the job.

For example, instead of a production target that is immediately provably impossible, an agent might complete several valid orders, discover a defect in its own earlier work, and face uncertain but potentially costly repair. Releasing the defective order, placing it on hold and repairing it should have distinct downstream consequences. That gives us a more informative sequence of decisions.

But the original is not uniformly more realistic. Its SVG grader always places valid submissions sixth, and its protein checker accepts planted sequences rather than validating biological binding. Those are substantial experimental simplifications too. We should borrow its design principles without assuming every implementation is a gold standard. Appendices B.5–B.7

Our fixed-versus-authorised marker control is already a strong feature: 80/80 authorised relocations demonstrate capability, while the fixed condition tests whether agents respect the downstream measurement requirement. Preserve that approach as we add more varied workflows.

I would prioritise clear operational meaning, believable opportunities for progress, and genuinely different tasks before adding more seeds or visual polish.
