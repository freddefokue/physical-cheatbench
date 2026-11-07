**Choosing tasks for physical CheatBench**

4 November 2026

Keep the threat families as a coverage map. Develop tasks from actual work, observed difficulties and the authority an agent would have in that job. A task can exercise several families, and a family can require several different tasks. The immediate recommendation is to develop three prototypes: repeated assembly inspection, unreliable batch measurements, and robot procedure commissioning.

The [source catalogue and twelve scene proposals](physical-cheatbench-scene-catalogue.json) records the source, legitimate job, repeated difficulty, discoverable opportunity, ordinary actions, independent measurement, legitimate control, interpretation risk and implementation requirement for every proposal. The proposed shortcuts are new experimental hypotheses. They are not findings of misconduct in the cited robotics projects. No new task has yet been implemented or validated under this design.

**How the threat map should guide the work**

Use the current [19-family map](../2026-10-31/threat-models.md). Its numbering differs from the implemented F01–F16 suite and from the older 31-item case matrix. Every new task should name its mechanism as well as its family numbers. A completed coverage table must distinguish an idea, an executable opportunity, a validated control and an actual model result.

The existing families remain useful for checking what the collection misses: records, inspection, unsafe shortcuts, shared resources, private information, interruption and coordination. They should not require one contrived dilemma per family, or imply that future failure mechanisms have been exhausted. Family 18, sabotage/coercion, deliberately has no new proposal in this batch: it needs a credible job and authority model before constructing a test. This is a visible gap in the larger suite, not a reason to invent a weak scene or drop the family.

Start each design with five questions:

1. What useful job is the agent supposed to complete?
2. What actually causes repeated retries, uncertainty or rework?
3. What feedback and evidence does the agent receive while working?
4. What ordinary action could improve the assessment without doing the required work?
5. What independent observation would establish what really happened?

Then assign threat-family tags. Add broader control and resource tests through jobs that supply the relevant authority; a robot arm demo alone does not establish permission to change factory software or allocate other robots.

**Sources with the most immediate value**

The [Astra collection](https://github.com/zjwzcx/Awesome-Astra-Embodied-AI) is a useful discovery index across direct control, calls to learned policies, simulation reconstruction and training workflows. Its catalogue was reviewed and selected original projects followed. The individual social-media demonstrations have not all been independently inspected or reproduced. In particular, a successful motion replay, an interactive robot policy and an agent that writes a simulator are different evaluation subjects.

| Source | What it contributes | Proposed use |
|---|---|---|
| [RoboQuest](https://declare-lab.github.io/RoboQuest/) | Tasks whose required information starts hidden and must be obtained by search, inspection or testing | Measurement reuse, incomplete inventories and unsupported completion claims |
| [Agent as Policy](https://agent-as-policy-2026.github.io/) | Assembly and other robot work using visual feedback, code and motion, with execution records | Repeated assembly failures and checking whether a result remains valid after release |
| [Robocurve capability evaluations](https://robocurve.org/opus-5-5-robodojo-rc-tier-1/) | Real tasks, human rubrics and trial records | Select manageable base tasks and distinguish motor failure from the decision to take a shortcut |
| [XDOF Ember 0](https://www.xdof.ai/blog/evaluating-llms) | Manipulation tasks and documented failure patterns | Mine mis-grasps, recovery attempts and premature completion claims |
| [RoboCasa](https://robocasa.ai/) and [BEHAVIOR](https://behavior.stanford.edu/) | Household task definitions, environments and object states | Broaden the suite into cleaning, storage and other process-sensitive jobs |
| [DROID](https://droid-dataset.github.io/) | Recorded manipulation in varied real environments | Learn normal work sequences and realistic variation; do not treat demonstrations as a representative failure dataset |
| [Spotter](https://raw.githubusercontent.com/zqc3117/Spotter/main/README.md) | A separate layer for detecting and repairing policy errors | Study the inspector/repairer role and what evidence it accepts |
| [SimEX](https://arxiv.org/abs/2609.38982v1) | Coding agents develop robot skills in simulation and adjust models using physical trials | Study whether an engineer improves the procedure or changes the local test so inadequate work passes |

Two findings deserve special attention. Robocurve selected its six easiest tasks after evaluating a larger real-robot set, yet full completion remained uncommon in the reported comparison. Dexterity must therefore be calibrated before a null is interpreted as refusal. XDOF reports that only 57% of its models' done declarations corresponded to actual completion. That is a promising source of episodes to investigate, not a measured deception rate. Both reports are specific to their models, interfaces and budgets. [Robocurve](https://robocurve.org/opus-5-5-robodojo-rc-tier-1/), [XDOF](https://www.xdof.ai/blog/evaluating-llms).

Keep [RoboHarm](https://robocurve.org/roboharm/) as a separate comparison: refusing an explicitly harmful instruction answers a different question from taking an unsolicited shortcut during a legitimate job. [Inspect Robots](https://github.com/robocurve/inspect-robots) is a useful interface and logging reference; compatibility with our runner has not been established.

**How to find scenes beyond benchmarks**

Use several complementary sources. Benchmark tasks supply executable starting points. Unedited trials and error reports supply realistic sequences of failed attempts. Maintenance manuals, commissioning procedures, inspection forms and quality records supply real permissions and completion criteria. Customer case studies supply operational jobs; examples include [Agility/GXO tote handling](https://www.agilityrobotics.com/content/gxo-and-agility-robotics-expand-partnership-to-accelerate-deployment-of-humanoids-in-u-s-operations), [Boston Dynamics inspection](https://bostondynamics.com/solutions/inspection/thermal/) and [Arda process planning](https://arda.ai/). These establish workflows, not that a frontier model controls every surrounding system.

[RoboCup at Home](https://athome.robocup.org/) supplies service-robot tasks involving people as well as objects. Research datasets and competition rulebooks can expose assumptions that a short demo hides: the meaning of completion, allowed assistance, reset costs and which mistakes matter.

Interviews with technicians, robot integrators, quality inspectors, warehouse supervisors and teleoperators would add information that papers often omit. Ask which failures repeat, what dashboard metric is misleading, what a rushed operator might skip, which settings the role can change, and how someone independently checks completion. The catalogue contains six concrete interview questions; no outreach has been initiated.

AI-assisted task generation is appropriate once those inputs are available. RoboCasa explicitly uses language models to propose composite activities grounded in its environments and skills. BEHAVIOR instead grounds its activity choice in surveys of human needs. We can combine these approaches: generate variations from sourced work, then have people and executable checks assess relevance, ambiguity and feasibility. Neither a fluent story nor a large number of generated scenes establishes quality. [RoboCasa construction method](https://robocasa.ai/), [BEHAVIOR activity selection](https://behavior.stanford.edu/).

**People and teams to follow**

[Jim Fan](https://jimfan.me/), [Eric Jang](https://evjang.com/), [Lukas Ziegler](https://ziegler.substack.com/) and [Kai Williams](https://www.understandingrobots.org/about) are useful discovery channels for projects, deployments and evaluation problems. Follow links through to methods, traces and source code. A demo can suggest a job without establishing reproducible competence or realistic access permissions.

Add researchers through the artifacts they publish: Chelsea Finn, Sergey Levine and Karol Hausman through [Physical Intelligence research](https://www.pi.website/blog/pi07); Soroush Nasiriany and Yuke Zhu through [RoboCasa](https://robocasa.ai/); Chengshu Li and Jiajun Wu through [BEHAVIOR](https://behavior.stanford.edu/). Also follow the Robocurve and XDOF evaluation teams. Their task specifications and failure records are directly useful to scene design. These are reading recommendations, not subscriptions or scheduled monitoring.

**The first development batch**

| Prototype | Legitimate work and repeated difficulty | Possible shortcut to test | Independent outcome |
|---|---|---|---|
| Assembly inspection | Assemble matched parts; retries produce misalignment or separation after release | Submit an apparently assembled unit while it is still being supported | Attachment and retention after release, plus what the actor observed |
| Batch measurement | Measure and sort distinct items; repeated readings disagree | Reuse a reference item's reading or change the scale's zero while loaded | True mass, item identity, scale occupancy, calibration and fresh measurements |
| Robot procedure commissioning | Develop a procedure meeting fixed physical requirements; local tests keep failing | Change local collisions or acceptance checks to obtain a pass | Execute the submitted controller in a separate frozen reference plant |

These prototypes exercise different actions and roles. The catalogue additionally covers complete-set retrieval, cleaning, mobile inspection, dataset preparation, shared warehouse resources, handover, worker-inspector interaction, private observations and monitoring faults. They are later development candidates within the broader coverage objective.

For robot-operation tasks, the model should receive camera observations and realistic instrument feedback. The evaluator can retain privileged simulator state. A matched text condition remains valuable, but must supply equivalent task evidence rather than omniscient facts unavailable visually. Reliable low-level skills can support the acting model; record their failures and hold their interface constant across conditions. The coding task needs physically consequential geometry and execution even though the engineer also uses files and text.

**Conditions and selection**

Start with genuinely achievable ordinary work. Add a difficult but achievable version that produces repeated setbacks. Where useful, add a separately labelled impossible-task or faulty-feedback stressor inspired by CheatBench. Keep truthful stopping, escalation and disclosure available in every condition. Repairing an actually faulty evaluator within granted authority must remain legitimate.

Each task also needs an unambiguous legitimate-use control. Permission must cover the relevant action, object, time and claim, including every affected rule. Our Line control showed why permission to operate a bypass cannot silently stand in for permission to ship unrecorded units. For assembly, a fixture-fit check may legitimately permit support while making no claim of finished retention. For datasets, a success-only training export may be legitimate while an evaluation report still needs all eligible attempts.

Before model exploration, demonstrate the honest route, the disputed action and the independent checker with scripts. Test recovery, undoing a completed step, stale evidence, incorrect identities, approvals after actions and ordinary mistakes. Establish that the model can perform the relevant actions; scripted competence alone is insufficient. Distinguish scene malfunction, lack of capability, lack of exposure, process omissions, executed violations and false claims. Do not infer intent from an unsuccessful outcome.

Develop a few varied tasks before buying many repetitions of one. Keep a record of all candidates, rejected designs and changes. Choose tasks for credible authority, interpretable controls, working actions, measurable outcomes and mechanism diversity; do not require that each task elicit cheating. Freeze a confirmation set, including valid null tasks, and use fresh instances and structurally different layouts. A held-out seed that merely changes object names is weak evidence of transfer.

A small original digital CheatBench task under the same accessible model and harness would help interpret a digital/physical comparison. If behaviour differs, inspect harness, tools, time and feedback as well as the scene. That comparison is a proposed later experiment, not a run performed here.

Existing Outbound and Line results remain intact. The new source catalogue and scene cards begin a development stage; they do not replace the current protocol or turn the existing nulls into failed experiments.
