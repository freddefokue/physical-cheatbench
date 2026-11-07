# Remark on running Physical CheatBench through Inspect Robots (the basis of v5)

Pasted by the owner into the implementing Claude Code session (transcript line 15206, 2026-11-06 22:23 UTC). Copied verbatim; the transcript itself is not shared because it contains exposed API keys.

---

Yes. This is a worthwhile next version: Physical CheatBench running through the same agent software and robot interface that could be used on hardware. It would address a real limitation of the current study.

I checked Robocurve’s Inspect Robots. It separates policies, robot embodiments, tasks and scorers; supports simulated and physical backends; and provides an LLM agent plugin with camera observations and motion tools. It also records actions, transcripts and guard interventions. This is closely aligned with your proposal. Framework, agent interface.

The precise target should be “the same agent stack operating through the same interface.” Whether it behaves similarly on hardware would remain something to test: perception, contact errors, latency and awareness of simulation can change its decisions.

I would structure it like this:

┌──────────────────────────────────────────┐
│ LLM agent: same prompt, memory and tools │
│                                          ├─────┐
└──────────────────────────────────────────┘     │
                                                 │
                                                 │
┌──────────────────────────────────────────┐     │
│ Inspect Robots                           │     │
│                                          ├◄────┘
│                                          ├───────┐
│                                          ├───────╪─┐
└──────────────────────────────────────────┘       │ │
                                                   │ │
                                                   │ │
┌──────────────────────────────────────────┐       │ │
│ MuJoCo robot/workcell adapter            │       │ │
│                                          ├◄──────┘ │
│                                          ├─────────╪─┐
└──────────────────────────────────────────┘         │ │
                                                     │ │
                                                     │ │
┌──────────────────────────────────────────┐         │ │
│ Hardware adapter — later                 │         │ │
│                                          ├◄────────┘ │
│                                          ├───────────╪─┐
└──────────────────────────────────────────┘           │ │
                                                       │ │
                                                       │ │
┌──────────────────────────────────────────┐           │ │
│ Operational checks and independent audit │           │ │
│                                          ├◄──────────┘ │
│                                          ├◄────────────┘
└──────────────────────────────────────────┘

Your existing simulator and workcell tools provide a starting point. The repository already describes mapping those tools onto hardware SDKs, but that document is a proposed mapping, not a demonstrated hardware implementation. Hardware plan (/home/fred/physical_cheatbench/HARDWARE_v4.md:3)

The scientific improvement depends on what we put behind the interface.

| Component | What I would require |
|---|---|
| Observations | Camera images and sensor measurements available on the corresponding hardware. Perception services should process images rather than receive privileged object positions. |
| Actions | Motion primitives or skills backed by controllers that could run on hardware. High-level pick and place are appropriate if that is the intended deployment interface. |
| Workstation access | Realistic access to instructions, configuration, records and reports. Retain these where they create the cheating opportunity. |
| Timing and failures | Explicit treatment of motion time, model latency, failed grasps and recovery. |
| Audit | Separate evidence of what was requested, what executed, what passed the operational check, and what actually happened. |

Inspect supports adding embodiment-specific tools, so we need not squeeze every task into its default motion commands. However, the framework does not automatically validate our graders or make our perception realistic. Extension interface.

One particularly important detail: its guards can prevent actions. A model requesting a violation that the framework blocks must remain distinguishable from a model choosing compliant behavior. Inspect records guard modifications, which helps us measure that distinction. Execution and guards.

I would start with one scene: the interlock task, because it has the clearest existing physical result.

1. Port it with its current conditions and permissions preserved, and validate the adapter using scripted actions.
2. Establish that the LLM can complete the honest control and manipulate the relevant objects in an explicitly permitted control.
3. Run a small comparison with the current harness, keeping model settings and task content fixed. Change perception or control abstractions separately so we can interpret differences.

This would answer a valuable follow-up question: does the observed safety-bypass behavior persist through an agent interface used for physical robots?

I would keep v4 frozen and publish this as a separate extension. A successful one-scene port would give us evidence for expanding it—and a much clearer route to collaboration with a hardware lab
