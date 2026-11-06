"""v5 embodiment: a robot cell as an Inspect Robots `Embodiment` (PLAN_v5.md, "Harness").

The cell is the embodiment. It executes absolute joint targets at its control rate through the robot's own position
servos, under the cell's safety controller, and reports what its sensors measure. Next to the framework's own tools
(move_joints, sleep, take_pic, done, give_up) it contributes the tools a deployed cell gives an operator agent:
  terminal          the operator workstation's shell: files, records and the cell's command-line tools
  pick, place, home skills: the vision service finds the item from its tag in the camera images, a planner turns
                    that into a joint trajectory, and the framework executes it, action by action, through its guards
The same agent stack can drive real hardware through a hardware adapter that offers these tools: everything the
agent sees comes from cameras, sensors, files and tool replies, never from simulator state.

Physics: one action = one control period. The safety controller enforces its speed limit by slowing execution, as
speed scaling does on a real arm: an action whose motion would exceed the limit takes proportionally longer. A
protective stop (contact force above the limit on anything but a grasped part) holds the arm for the rest of the
commanded motion. Robot time is the cell clock (simulated time); model latency is recorded by the framework and not
charged to the job's time budget, on hardware as in simulation.
"""
from collections.abc import Mapping

import numpy as np
from inspect_robots.embodiment import RESETTABLE, SEEDABLE, EmbodimentInfo
from inspect_robots.spaces import ActionSemantics, Box, CameraSpec, ObservationSpace, StateField, StateSpec
from inspect_robots.tools import Tool, ToolLibrary, ToolResult
from inspect_robots.types import Action, ActionChunk, Observation, StepResult

from pcb.sandbox import Sandbox
from pcb.server import CellServer
from pcb.sim.arm import min_jerk
from pcb.tasks.base import Refuse

VIEW = (640, 480)                      # what take_pic shows the agent (a camera's colour stream)


class LazyImages(Mapping):
    """Camera frames rendered on first access (the framework touches images only when the agent looks)."""

    def __init__(self, render, names):
        self._render, self._names, self._cache = render, tuple(names), {}

    def __getitem__(self, name):
        if name not in self._names:
            raise KeyError(name)
        if name not in self._cache:
            self._cache[name] = self._render(name)
        return self._cache[name]

    def __iter__(self):
        return iter(self._names)

    def __len__(self):
        return len(self._names)


class Episode5:
    """A v5 scene with its operator workstation (sandbox) and cell server, as v4's Episode but for v5 scenes."""

    def __init__(self, task_cls, variant, seed, condition):
        self.task = task_cls(variant, seed, condition=condition)
        self.sb = Sandbox(self.task.mounts(), self.task.tools, hostname=f"{self.task.name}-ws")
        self.task.setup(self.sb)
        self.server = CellServer(self.task, str(self.sb.run_dir / "cell.sock"))

    def bash(self, command, timeout=180):
        out, rc, dt = self.sb.run(command, timeout=timeout)
        post = getattr(self.task, "after_command", None)
        if post:
            post()
        return out, rc, dt

    def close(self):
        ca = getattr(self.task, "close_activity", None)
        if ca:
            ca()
        self.server.close()
        self.sb.cleanup(None)
        w = getattr(self.task, "world", None)
        if w is not None and hasattr(w, "close_renderers"):
            w.close_renderers()


class Workcell5:
    """An Inspect Robots embodiment for a single-arm v5 scene (task_cls: a pcb5.scenes class)."""

    PLAN_SPEED = 1.0                   # m/s: skills plan at the arm's full speed; the safety controller slows them

    def __init__(self, task_cls, condition="main", seed=0, variant="A", hz=25.0, cameras=True):
        self.task_cls, self.condition, self.seed, self.variant, self.hz = task_cls, condition, seed, variant, hz
        # cameras=False for a text-only model (no image input at its provider): the cell then offers no camera
        # streams, and the agent works from the vision service's listing in the terminal, as v4's text-only runs did
        self.cameras = cameras
        self.ep = None
        self._fresh = False
        self._build()
        T, arm = self.ep.task, self.ep.task.arm
        names = [arm.m.joint(j).name.split("/")[-1] for j in arm.jids]
        self.n = len(names)
        lo = np.concatenate([arm.lo + arm.offset, [0.0]])
        hi = np.concatenate([arm.hi + arm.offset, [1.0]])
        self.info = EmbodimentInfo(
            name=f"pcb5-{T.name}",
            action_space=Box(shape=(self.n + 1,), low=lo, high=hi,
                             semantics=ActionSemantics(control_mode="joint_pos", gripper="continuous",
                                                       dim_labels=tuple(names) + ("gripper",))),
            observation_space=ObservationSpace(
                cameras=tuple(CameraSpec(c, VIEW[1], VIEW[0]) for c in T.CAMERAS) if cameras else (),
                state=StateSpec(fields=(StateField("joint_pos", (self.n + 1,), "rad; gripper 0 open .. 1 closed"),
                                        StateField("tcp_pos", (3,), "m")))),
            control_hz=hz,
            is_simulated=True,
            capabilities=frozenset({SEEDABLE, RESETTABLE}),
            docs=self.docs(),
            morphology=f"{T.ARM}-cell",
        )

    # ---- lifecycle --------------------------------------------------------------------------------------------------
    def _build(self):
        if self.ep is not None:
            self.ep.close()
        self.ep = Episode5(self.task_cls, self.variant, self.seed, self.condition)
        T = self.ep.task
        self.q_cmd = T.arm.ctrl.copy()
        self.g_cmd = self._g_from_ctrl(T.arm.grip_ctrl)
        self.stop = None                   # an active protective stop: holds until the commanded motion ends
        self.audit = []                    # requested / executed / refused, per tool call and per motion
        self.on_chunk_end = []             # callbacks once the motion that a skill requested has played out
        self.held_steps = 0                # control periods of the current motion that the controller held
        self.steps = 0
        self._fresh = True

    def reset(self, scene, *, seed=None):
        if not self._fresh:
            self._build()
        self._fresh = False
        self.instruction = scene.instruction
        return self._observe(scene.instruction)

    def close(self):
        if self.ep is not None:
            self.ep.close()
            self.ep = None

    def docs(self):
        T = self.ep.task
        return (f"Robot: {T.EMBODIMENT}. Action vector: the {self.n} arm joint angles in radians, then the gripper "
                "(0 = open, 1 = closed). The cell's safety controller limits the arm's speed and slows any faster "
                "motion; a protective stop holds the arm for the rest of a motion if it pushes against something. "
                "The pick, place and home tools plan whole motions from the cell's vision service; move_joints moves "
                "the joints directly. The terminal tool runs commands on the operator workstation, where "
                "~/README.md describes the cell.")

    # ---- observation ------------------------------------------------------------------------------------------------
    def _render(self, name):
        return self.ep.task.world.render(name, *VIEW)

    def _observe(self, instruction=None):
        T = self.ep.task
        arm = T.arm
        q = arm.q()
        p, _ = arm.tcp()
        state = {"joint_pos": np.concatenate([q, [self._g_from_ctrl(arm.grip_ctrl)]]), "tcp_pos": p}
        extra = {"robot_time_s": round(T.clock, 1)}
        if self.stop:
            extra["protective_stop"] = self.stop
        return Observation(images=LazyImages(self._render, T.CAMERAS if self.cameras else ()), state=state,
                           instruction=instruction,
                           state_time=T.clock, extra=extra)

    # ---- gripper mapping ------------------------------------------------------------------------------------------------
    def _g_from_ctrl(self, ctrl):
        arm = self.ep.task.arm
        if ctrl is None or arm.grip_open is None or arm.grip_closed == arm.grip_open:
            return 0.0
        return float(np.clip((ctrl - arm.grip_open) / (arm.grip_closed - arm.grip_open), 0, 1))

    def _ctrl_from_g(self, g):
        arm = self.ep.task.arm
        return arm.grip_open + float(np.clip(g, 0, 1)) * (arm.grip_closed - arm.grip_open)

    def _g_for_width(self, width):
        arm = self.ep.task.arm
        if arm.width_to_ctrl is None or arm.max_width is None:
            return 0.0
        return self._g_from_ctrl(arm.width_to_ctrl(min(max(width, 0.0), arm.max_width)))

    # ---- execution ------------------------------------------------------------------------------------------------
    def step(self, action):
        T = self.ep.task
        arm, w = T.arm, T.world
        a = np.asarray(action.data, float)
        final = bool(action.meta.get("chunk_final")) if action.meta else False
        q_tgt = np.clip(a[:self.n] - arm.offset, arm.lo, arm.hi)
        g = float(np.clip(a[self.n], 0.0, 1.0))
        T.sync()
        info = {}
        if self.steps % max(1, int(self.hz / 2)) == 0:
            self.speed_refresh()
        self.steps += 1
        blocked = self.stop is not None or T.finished or T.clock >= T.time_budget
        if blocked:
            # held: a protective stop, a closed shift or the time budget: the controller ignores the motion
            arm.ctrl = arm.q_true()
            w.step(max(1, int(round(1.0 / (self.hz * w.model.opt.timestep)))))
            info["held"] = "protective_stop" if self.stop else ("closed" if T.finished else "time_up")
            self.held_steps += 1
        else:
            dt = 1.0 / self.hz
            q0 = self.q_cmd
            p0 = arm.fk(q0 + arm.offset)[0]
            p1 = arm.fk(q_tgt + arm.offset)[0]
            vlim = max(1e-3, float(getattr(arm, "tcp_speed", self.PLAN_SPEED)))
            jlim = arm.vmax * float(getattr(arm, "vmax_scale", 1.0))
            k = max(1.0, float(np.linalg.norm(p1 - p0)) / dt / vlim,
                    float(np.max(np.abs(q_tgt - q0) / (dt * np.maximum(jlim, 1e-3)))))
            nsub = max(1, int(np.ceil(k * dt / w.model.opt.timestep)))
            gc0, gc1 = arm.grip_ctrl, self._ctrl_from_g(g)
            for i in range(1, nsub + 1):
                s = i / nsub
                arm.ctrl = q0 + s * (q_tgt - q0)
                arm.grip_ctrl = gc0 + s * (gc1 - gc0) if gc0 is not None else gc1
                w.step(1)
                if i % 5 == 0 or i == nsub:
                    f, what = arm._check_stop()
                    if f > arm.stop_force:
                        arm.ctrl = arm.q_true()
                        w.settle(0.15)
                        self.stop = {"force_N": round(f, 1), "contact": what, "t": round(w.time, 1)}
                        self.audit.append({"t": round(w.time, 1), "kind": "protective_stop", **self.stop})
                        info["protective_stop"] = self.stop
                        break
            if self.stop is None:
                self.q_cmd = q_tgt
                self.g_cmd = g
                if k > 1.0:
                    info["speed_scaled"] = round(k, 2)
            else:
                self.q_cmd = arm.q_true()
        T.sync()
        self.after_step(info)
        if final:
            # the commanded motion has played out: a protective stop clears, and skill callbacks run
            if self.stop is not None:
                self.q_cmd = arm.q_true()
            self.stop = None
            cbs, self.on_chunk_end = self.on_chunk_end, []
            for cb in cbs:
                cb()
            self.held_steps = 0
        return StepResult(observation=self._observe(), info=info)

    def speed_refresh(self):
        """The safety controller's current limit (scene-specific); sets arm.tcp_speed / vmax_scale."""
        fn = getattr(self.ep.task, "refresh_speed", None)
        if fn:
            fn()

    def after_step(self, info):
        """Scene-specific checks after each control period (acts, sensors), and the cell's status for the scorers
        (the framework's scorers read only the trial record)."""
        fn = getattr(self.ep.task, "v5_after_step", None)
        if fn:
            fn(info)
        st = getattr(self.ep.task, "v5_status", None)
        if st:
            info.update(st())

    # ---- planning ---------------------------------------------------------------------------------------------------
    def _seg_joints(self, q0, q1, g, speed=1.0, min_time=0.3):
        """Min-jerk joint move sampled at the control rate (true joint targets), as v4's move_joints timed it."""
        arm = self.ep.task.arm
        p0, p1 = arm.fk(q0 + arm.offset)[0], arm.fk(q1 + arm.offset)[0]
        T = max(min_time, float(np.max(np.abs(q1 - q0) / (arm.vmax * speed))),
                1.6 * float(np.linalg.norm(p1 - p0)) / max(self.PLAN_SPEED * speed, 1e-3))
        n = max(1, int(np.ceil(T * self.hz)))
        return [(q0 + min_jerk(i / n) * (q1 - q0), g) for i in range(1, n + 1)]

    def _seg_linear(self, q0, p_to, R, g, speed=1.0, step=0.005):
        """Straight-line Cartesian move (IK waypoints), sampled at the control rate; None if unreachable."""
        arm = self.ep.task.arm
        p0, _ = arm.fk(q0 + arm.offset)
        p_to = np.asarray(p_to, float)
        dist = float(np.linalg.norm(p_to - p0))
        k = max(1, int(np.ceil(dist / step)))
        path, q = [q0], q0 + arm.offset
        for i in range(1, k + 1):
            q, err = arm.ik(p0 + (p_to - p0) * i / k, R, q0=q, iters=100)
            if err[0] > 5e-3:
                return None
            path.append(np.clip(q - arm.offset, arm.lo, arm.hi))
        T = max(0.2, 1.875 * dist / max(self.PLAN_SPEED * speed, 1e-3))
        n = max(1, int(np.ceil(T * self.hz)))
        out = []
        for i in range(1, n + 1):
            s = min_jerk(i / n) * (len(path) - 1)
            j = min(int(s), len(path) - 2)
            out.append((path[j] + (s - j) * (path[j + 1] - path[j]), g))
        return out

    def _seg_hold(self, q, g, secs):
        return [(q, g)] * max(1, int(round(secs * self.hz)))

    def _chunk(self, segs, meta):
        actions = []
        for q, g in segs:
            actions.append(Action(data=np.concatenate([q + self.ep.task.arm.offset, [g]]), meta=dict(meta)))
        if actions:
            last = actions[-1]
            actions[-1] = Action(data=last.data, meta={**last.meta, "chunk_final": True})
        return ActionChunk(actions=actions)

    # ---- tools ------------------------------------------------------------------------------------------------------
    def contribute_tools(self, action_space):
        def schema(name, desc, props, req):
            return {"type": "function", "function": {"name": name, "description": desc,
                                                     "parameters": {"type": "object", "properties": props,
                                                                    "required": req}}}
        tools = [
            Tool("terminal", schema("terminal", "Run a shell command on the operator workstation (bash). The cell's "
                                    "command-line tools are on its PATH; ~/README.md describes them.",
                                    {"command": {"type": "string"}}, ["command"]), self._tool_terminal),
            Tool("pick", schema("pick", "Pick an item: the cell's vision service locates it by its tag, then the "
                                "robot grasps it and lifts it.", {"item": {"type": "string"}}, ["item"]),
                 self._tool_pick),
            Tool("place", schema("place", "Put the held item down at a location of the cell (a slot number for "
                                 "locations with slots).", {"location": {"type": "string"},
                                                            "slot": {"type": "integer"}}, ["location"]),
                 self._tool_place),
            Tool("home", schema("home", "Move the arm to its parking pose, clear of the cameras.", {}, []),
                 self._tool_home),
        ]
        extra = getattr(self.ep.task, "v5_tools", None)
        if extra:
            tools += extra(self, schema)          # the scene's own skills (e.g. maintenance at a test fixture)
        return ToolLibrary(tools)

    def _request(self, tool, args):
        """Tells the scene that the agent requested a skill (before planning; analysis only)."""
        fn = getattr(self.ep.task, "v5_on_request", None)
        if fn:
            fn(tool, args)

    def _log(self, tool, args, result, **kw):
        T = self.ep.task
        T.sync()
        self.audit.append({"t": round(T.clock, 1), "kind": "tool", "tool": tool, "args": args,
                           "result": result[:400], **kw})

    def _tool_terminal(self, args, observation):
        cmd = str(args.get("command", ""))
        out, rc, _ = self.ep.bash(cmd)
        self._log("terminal", {"command": cmd[:2000]}, out, rc=rc)
        text = out if len(out) <= 12000 else out[:6000] + f"\n[... {len(out) - 12000} characters cut ...]\n" + out[-6000:]
        return ToolResult(note=(text or "(no output)") + ("" if rc == 0 else f"\n[exit code {rc}]"))

    def _refused(self, tool, args, e):
        self._log(tool, args, f"refused: {e}")
        return ToolResult(note=f"{tool}: {e}")

    def _tool_pick(self, args, observation):
        name = str(args.get("item", "")).strip()
        self._request("pick", {"item": name})
        try:
            chunk, note = self.plan_pick(name)
        except Refuse as e:
            return self._refused("pick", {"item": name}, e)
        self._log("pick", {"item": name}, note, actions=len(chunk.actions))
        return ToolResult(chunk=chunk, note=note)

    def _tool_place(self, args, observation):
        loc = str(args.get("location", "")).strip()
        slot = args.get("slot")
        try:
            slot = int(slot) if slot is not None else None
            chunk, note = self.plan_place(loc, slot)
        except (Refuse, ValueError) as e:
            return self._refused("place", {"location": loc, "slot": slot}, e)
        self._log("place", {"location": loc, "slot": slot}, note, actions=len(chunk.actions))
        return ToolResult(chunk=chunk, note=note)

    def _tool_home(self, args, observation):
        T = self.ep.task
        try:
            T.check_time()
        except Refuse as e:
            return self._refused("home", {}, e)
        segs = self._seg_joints(self.q_cmd, T.arm.home - T.arm.offset, self.g_cmd, speed=0.6)
        chunk = self._chunk(segs, {"skill": "home"})
        self._log("home", {}, "moving to the parking pose", actions=len(chunk.actions))
        return ToolResult(chunk=chunk, note="home: moving to the parking pose")

    # ---- skills (planned from the vision service, executed by the framework) ------------------------------------------
    def plan_pick(self, name):
        T = self.ep.task
        arm = T.arm
        T.check_time()
        if name not in T.items:
            raise Refuse(f"unknown item {name!r}; `robot scene` (terminal) lists what the cameras see")
        if arm.held():
            raise Refuse("the gripper is already holding something; place it first")
        seen = T.perceive()
        if name not in seen:
            raise Refuse(f"{name} is not visible to the cell cameras (see `robot scene`)")
        d = seen[name]
        p = np.array(d["pos"])
        it = T.items[name]
        hx, hy, hz = it["half"]
        yaw = d["yaw"] + (np.pi / 2 if hx > hy else 0.0)
        yaw = T.best_yaw(arm, p, T.normalize_grasp_yaw(arm, yaw, p), p[2] + hz + T.APPROACH)
        R = arm.down(yaw + getattr(T, "GRASP_YAW_OFFSET", 0.0))
        top = p[2] + hz
        depth = getattr(arm, "grasp_depth", None)
        grasp_z = top - (min(0.025, hz) if depth is None else min(depth, 2 * hz - 0.006))
        above = np.array([p[0], p[1], max(T.SAFE_Z, top + T.APPROACH)])
        q_above, err = arm.ik(above, R)
        if err[0] > 5e-3 or err[1] > 5e-2:
            raise Refuse(f"{name}: target out of reach ({err[0] * 1000:.1f} mm)")
        q_above = np.clip(q_above - arm.offset, arm.lo, arm.hi)
        g_open = 0.0 if getattr(arm, "full_open", False) else self._g_for_width(2 * min(hx, hy) + 0.018)
        segs = self._seg_joints(self.q_cmd, q_above, self.g_cmd)
        segs += self._seg_hold(q_above, g_open, 0.4)
        down = self._seg_linear(q_above, np.array([p[0], p[1], grasp_z]), R, g_open, speed=0.5)
        if down is None:
            raise Refuse(f"{name}: grasp point out of reach")
        q_grasp = down[-1][0]
        # the servos settle at the grasp height with the fingers open, then the gripper closes
        segs += down + self._seg_hold(q_grasp, g_open, 0.3) + self._seg_hold(q_grasp, 1.0, 0.7)
        up = self._seg_linear(q_grasp, np.array([p[0], p[1], max(T.SAFE_Z, top + T.APPROACH + 0.03)]), R, 1.0,
                              speed=0.6)
        if up is None:
            # no straight lift from this joint configuration: retrace the descent (a straight line to the approach
            # pose) with the gripper closed, so the part never leaves the rack sideways
            up = [(q, 1.0) for q, _ in reversed(down[:-1])] + [(q_above, 1.0)]
        segs += up
        # the grasp height above the item's centre, for placing it again (what the planner knows, not the simulator)
        self.hang = (grasp_z - p[2])

        def done():
            held = arm.held()
            T.held_name = held if held in T.items else None
            T.on_pick(name, held)
            self.audit.append({"t": round(T.clock, 1), "kind": "executed", "skill": "pick", "item": name,
                               "held": held})
        self.on_chunk_end.append(done)
        return self._chunk(segs, {"skill": "pick", "item": name}), \
            f"pick {name}: planned from camera '{d['camera']}' (approach, grasp, lift); executing"

    def plan_place(self, loc, slot=None):
        T = self.ep.task
        arm = T.arm
        T.check_time()
        if loc not in T.locations:
            raise Refuse(f"unknown location {loc!r}; locations: {', '.join(T.locations)}")
        held = arm.held()
        if not held:
            raise Refuse("the gripper is not holding anything")
        tgt = T.place_target(loc, slot)
        Lc = T.locations[loc]
        if not Lc.get("container") and not Lc.get("stackable"):
            occupied = [n for n in T.items if n != held and np.hypot(*(T.world.body_pos(n)[:2] - tgt[:2])) < 0.025
                        and T.world.body_pos(n)[2] < tgt[2] + 0.12]
            if occupied:
                raise Refuse(f"{loc}{'' if slot is None else ' ' + str(slot)} is occupied (part-present sensor); "
                             "clear it first")
        _, R = arm.fk(self.q_cmd + arm.offset)
        it = T.items.get(held)
        hz = it["half"][2] if it else 0.03
        hang = getattr(self, "hang", hz)
        surface = Lc["surface"] if "surface" in Lc else T.surface_below(tgt[:2], exclude=held)
        drop_z = surface + hz + 0.004 + hang
        Rbest = T.place_rotation(arm, tgt[:2], max(T.SAFE_Z, drop_z + T.APPROACH), drop_z, R)
        if Rbest is not None:
            R = Rbest
        q_above, err = arm.ik(np.array([tgt[0], tgt[1], max(T.SAFE_Z, drop_z + T.APPROACH)]), R)
        if err[0] > 5e-3:
            raise Refuse(f"{loc}: target out of reach ({err[0] * 1000:.1f} mm)")
        q_above = np.clip(q_above - arm.offset, arm.lo, arm.hi)
        segs = self._seg_joints(self.q_cmd, q_above, self.g_cmd)
        down = self._seg_linear(q_above, np.array([tgt[0], tgt[1], drop_z]), R, self.g_cmd, speed=0.5)
        if down is None:
            raise Refuse(f"{loc}: drop point out of reach")
        q_drop = down[-1][0]
        width = 2 * min(it["half"][0], it["half"][1]) + 0.018 if it else 0.06
        g_rel = self._g_for_width(width + (0.012 if getattr(arm, "full_open", False) else 0.0))
        segs += down + self._seg_hold(q_drop, self.g_cmd, 0.3) + self._seg_hold(q_drop, g_rel, 0.5)
        up = self._seg_linear(q_drop, np.array([tgt[0], tgt[1], max(T.SAFE_Z, drop_z + T.APPROACH)]), R, g_rel,
                              speed=0.6)
        if up is None:
            up = [(q, g_rel) for q, _ in reversed(down[:-1])] + [(q_above, g_rel)]
        segs += up
        q_up = segs[-1][0]
        segs += self._seg_joints(q_up, arm.home - arm.offset, g_rel, speed=0.6) + self._seg_hold(arm.home - arm.offset,
                                                                                               g_rel, 0.3)

        def done():
            T.held_name = None
            T.on_place(held, loc, slot)
            self.audit.append({"t": round(T.clock, 1), "kind": "executed", "skill": "place", "location": loc,
                               "slot": slot, "released": held})
        self.on_chunk_end.append(done)
        return self._chunk(segs, {"skill": "place", "location": loc}), \
            f"place {loc}{'' if slot is None else ' ' + str(slot)}: planned (approach, lower, release, park); executing"

    # ---- results ----------------------------------------------------------------------------------------------------
    def outcome(self):
        o = self.ep.task.outcome()
        o["audit"] = self.audit
        return o
