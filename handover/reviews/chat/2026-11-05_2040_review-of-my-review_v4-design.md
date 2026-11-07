# Review of the implementing agent's review of the robotics-simulator task plan (v4 design)

Pasted by the owner into the implementing Claude Code session (transcript line 6232, 2026-11-05 19:40 UTC). Copied verbatim; the transcript itself is not shared because it contains exposed API keys.

---

It’s a constructive review. I agree with adding a safety task and strengthening the control interface. But its diagnosis of the capability problem is too confident, and its five-scene proposal mixes physical misconduct with benchmark tampering.

The Anthropic qualification is fair. On standard LIBERO tasks, the model supervising the VLA performed worse than the VLA alone; on some novel tasks, supervision helped. The supported conclusion is that the interface substantially changes what a model can accomplish, not that adding an LLM always improves a robot. That is the narrower claim we should use. Anthropic study.

The claim that low RoboQuest success mostly reflects insufficient dexterity is not supported by its analysis. RoboQuest reports:

- 72–81% success on isolated execution skills when given an oracle plan.
- Only 18–21% of failures attributed to execution.
- Missing evidence and incorrect decisions about collected evidence account for much more.

That does not establish that our proposed shortcuts are executable. But neither does low overall success establish that they are beyond the models’ dexterity. We need to test each action directly. RoboQuest findings.

A skill-level SDK is nevertheless a sensible option. It needs careful boundaries: pick, place and insert should improve execution without revealing hidden object identities, automatically completing inspections, or correcting every mistake. Otherwise, the SDK could remove the decisions we wanted to study. It must also support ordinary actions that could produce the shortcut, with failures and interventions recorded.

I would keep the safety scene. That was a worthwhile omission to flag in my shortlist. Force-limited insertion could provide a useful experiment, provided we establish:

- An honest alignment or recovery route.
- A clear restriction on changing the force limit.
- Measurements separating an override request, actual excessive force, and any modeled damage.

I would initially test this separately from camera spoofing, even if both use the same assembly environment. That makes the causes easier to interpret.

Demonstration replay and simulator privileges deserve inclusion, but their interpretation needs tightening.

Using demonstrations is normal robotics practice. Replay becomes cheating in a clearly defined assessment that prohibits using the evaluated instance’s reference solution, or when the agent falsely claims independent execution. The existence of a demonstration file does not establish misconduct.

Simulator teleportation is a legitimate test of evaluation tampering. It provides evidence about manipulating the test environment; additional reasoning is needed to connect it to physical deployment. Both mechanisms can be added as conditions to existing tasks. Counting them as separate “scenes” would overstate the suite’s diversity.

Similarly, the Eureka track needs to allow legitimate reward-function development. The disputed behavior should concern fixed acceptance requirements or false reporting of validation—not simply changing training code.

My preferred initial collection would therefore be:

| Experiment | Main question |
|---|---|
| Assembly inspection | Will the agent obtain a pass while leaving the assembly physically incomplete? |
| Spill recovery | Will it repair, conceal or misrepresent a mistake during ordinary work? |
| Force-limited insertion | Will it circumvent a known operational safety constraint? |

Controller development would be a separate engineering track. Restricted demonstrations and simulator privileges would be supplementary tampering conditions.

One refinement to the spill comparison: “self-caused versus inherited” is promising, but not automatically a clean manipulation. Match the physical state, available evidence and remaining resources. Comparing only episodes where an agent happened to spill something could select unusually difficult episodes or weaker policies.

There are also two concrete corrections to the review:

- Both disputed RoboDojo task names exist. “Sweep Blocks” and “Pack Objects Into Box” appear in the official simulation catalogue. Backpack packing belongs to its real-robot catalogue. Official task list.
- The plan file exists in our shared workspace, rather than the physical-cheatbench checkout: robotics-simulator-task-plan.md (review/2026-11-05/robotics-simulator-task-plan.md). I should have made that location distinction clearer.

The GPU distinction is useful too, although a working small MuJoCo prototype does not establish that every MuJoCo-based package runs locally unchanged. RoboQuest’s published setup itself specifies an NVIDIA GPU.

I’d adopt the three layers, both control types, a validated SDK and preregistration. The next milestone should be interpretable experiments on a few tasks; the number of scene names is secondary.
