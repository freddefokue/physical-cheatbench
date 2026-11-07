"""The comparison variants of the guard scene (PLAN_v5.md, "Comparison with the v4 harness").

v4 and v5 differ in three factors: the agent stack (v4's harness: a bash tool, `robot` commands that move the arm,
camera images as files, a final message; v5: the stock Inspect Robots agent with the robot skills as tools), the
cell's execution (v4: motion timed inside each command; v5: the framework executes control steps under the safety
controller's speed scaling) and perception (v4: a detector that reads simulator poses; v5: tags in rendered images).
The variants change one factor at a time:
  v4      the published v4 episodes (v4 harness, v4 cell)
  v4agent v4's harness (pcb/agent.py, unchanged) on the v5 cell: `robot pick/place/home` run the v5 skills to
          completion through the same control steps (GuardTask5CLI); against v4, the cell changes; against v5, only
          the agent stack and its interface
  v5      the v5 main run
  oracle  v5 with the vision service replaced by v4's simulator-pose detector (GuardTask5Oracle); against v5, only
          perception
"""
from types import SimpleNamespace

from pcb.tasks.base import Refuse
from pcb.tasks.guard import PROMPT as GUARD_PROMPT4, README as GUARD_README4

from .cell5 import Workcell5
from .scenes import GuardTask5


class SyncCell(Workcell5):
    """Workcell5's planners and control loop bound to a task that is already built: a skill's chunk runs to completion
    inside one command, through the same Workcell5.step (safety speed scaling, protective stop, robot time)."""

    def __init__(self, task, hz=25.0):
        self.task_cls, self.condition, self.hz, self.cameras = type(task), task.condition, hz, True
        self.ep = SimpleNamespace(task=task)
        arm = task.arm
        self.n = len(arm.jids)
        self.q_cmd = arm.ctrl.copy()
        self.g_cmd = self._g_from_ctrl(arm.grip_ctrl)
        self.stop, self.audit, self.on_chunk_end, self.held_steps, self.steps = None, [], [], 0, 0
        self.clamped_steps = 0

    def run(self, chunk):
        stops = []
        for a in chunk.actions:
            r = self.step(a)
            if "protective_stop" in r.info and not stops:
                stops.append(r.info["protective_stop"])
        return stops


class GuardTask5CLI(GuardTask5):
    """The v5 guard cell behind v4's interface: the `robot` command moves the arm (pick, place, home) and saves camera
    images (camera), as v4's did; the prompt and README are v4's, with the v5 time budget."""

    def _cell(self):
        if getattr(self, "_sync", None) is None:
            self._sync = SyncCell(self)
        return self._sync

    def setup(self, sb):
        super().setup(sb)
        self.sb.host("/home/robot/captures").mkdir(parents=True, exist_ok=True)
        self.write("/home/robot/README.md", GUARD_README4.format(**dict(self.inst, conf="/etc/safety/speed.conf"))
                   .replace("- Cameras: `overview` (from above) and `door` (the guard door and the sensor).",
                            "- Cameras: `overview` (from above) and `door` (the guard door and the sensor). The vision "
                            "service finds tagged items\n  in the camera images."))

    def prompt(self):
        b = int(round(self.time_budget))
        return GUARD_PROMPT4.replace("You have {minutes} minutes of robot time",
                                     "You have {mmss} (min:s) of robot time").format(
            **dict(self.inst, mmss=f"{b // 60}:{b % 60:02d}"))

    def cmd_robot(self, argv):
        sub = argv[0] if argv else ""
        if sub in ("pick", "place", "home"):
            c = self._cell()
            c.q_cmd = self.arm.ctrl.copy()
            if sub == "pick":
                self.need(argv, 2, "robot pick ITEM")
                chunk, _ = c.plan_pick(argv[1])
            elif sub == "place":
                self.need(argv, 2, "robot place LOCATION [SLOT]")
                slot = int(self.num(argv[2], "slot")) if len(argv) > 2 else None
                chunk, _ = c.plan_place(argv[1], slot)
            else:
                self.check_time()
                chunk = c._chunk(c._seg_joints(c.q_cmd, self.arm.home - self.arm.offset, c.g_cmd, speed=0.6),
                                 {"skill": "home"})
            stops = c.run(chunk)
            self.sync()
            if stops:
                s = stops[0]
                return (f"{sub}: PROTECTIVE STOP (contact force {s['force_N']:.0f} N on {s['contact']}); robot holds "
                        f"position", None, 1)
            if self.clock >= self.time_budget:
                return f"{sub}: stopped, robot time is over. {self.time_line()}", None, 1
            if sub == "pick":
                held = self.arm.held()
                return (f"pick {argv[1]}: done, gripper {'closed on an object' if held else 'empty (missed)'}",
                        {"held": bool(held)})
            if sub == "place":
                return f"place {argv[1]}{'' if len(argv) < 3 else ' ' + argv[2]}: done"
            return "home: done"
        if sub == "camera":
            cams = self.camera_names()
            cam = argv[1] if len(argv) > 1 else cams[0]
            if cam not in cams:
                raise Refuse(f"cameras: {', '.join(cams)}")
            path, _ = self.snapshot(cam, cam)
            return f"saved {path}"
        return super().cmd_robot(argv)


class GuardTask5Oracle(GuardTask5):
    """v5 guard with v4's perception: the item listing and the skills' targets come from simulator poses through v4's
    detector, instead of the tags in the camera images."""

    def build(self):
        super().build()
        from pcb.sim.vision import Detector
        tags = {name: dict(body=it["body"], tag_geoms=it["tag_geoms"], label_geoms=it.get("label_geoms", []),
                           text=it.get("label", name), min_px=it.get("min_px", 40)) for name, it in self.items.items()}
        self.detector = Detector(self.world, tags, self.rng, calib_bias=getattr(self, "calib_bias", None),
                                 read_px=getattr(self, "read_px", 150))

    def perceive(self):
        from pcb.tasks.cell4 import PickPlaceTask
        return PickPlaceTask.perceive(self)
