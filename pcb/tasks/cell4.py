"""A pick-and-place workcell on top of Task4: the robot skills a real cell's integrator would provide.

Skills (each one runs the physics; nothing is teleported):
- `robot scene`: the cell's vision service. It lists the tagged items it can see in the cell cameras and the nearest
  named location of each, from a segmentation render of those cameras (an item hidden from every camera is not
  listed, as with a real tag detector);
- `robot pick <item>`: locate the item with the vision service, top-down grasp across its narrow side, lift. The
  gripper reports whether it closed on something (object detection by finger width), not what it holds;
- `robot place <location> [slot]`: carry the held item over the location and set it down on whatever is below
  (slot surface, container floor or other items), release and retract;
- `robot home`, `robot status`, `robot camera <name>`.
Scene modules declare items, locations, cameras and their devices.
"""
import numpy as np

from ..sim import robots
from ..sim.core import Builder, label_image
from ..sim.vision import Detector
from .base import Refuse
from .common4 import Task4



class PickPlaceTask(Task4):
    ARM = "ur5e"
    ARM_BASE = (0.0, 0.0, 0.0)
    ARM_YAW = 0.0
    CAMERAS = ("overview",)          # cameras the vision service uses
    PARK = None                      # (x, y, z) of the TCP where the arm parks clear of the cameras' view
    SAFE_Z = 0.22                    # transit height of the TCP above the bench (m)
    APPROACH = 0.08                  # approach/retract height above a grasp or drop point (m)
    tcp_speed = 0.5
    ITEM_FRICTION = (1.1, 0.01, 0.0002)

    # scene modules fill these in build_scene()
    def build_scene(self, b):
        raise NotImplementedError

    def arm_specs(self):
        """[(side, kind, prefix, base, yaw, park, home)]; one arm by default, two for bimanual cells."""
        return [("arm", self.ARM, "r/", self.ARM_BASE, self.ARM_YAW, self.PARK, None)]

    def build(self):
        self.items = {}              # name -> dict(body, half, label, tag_geoms, mass, ...)
        self.locations = {}          # name -> dict(pos=(x, y, z_surface), slots=[(x, y)], container=bool, ...)
        self.held_name = None
        b = Builder()
        b.floor()
        specs = self.arm_specs()
        for side, kind, prefix, base, yaw, park, home in specs:
            robots.attach(b, kind, prefix, base, yaw)
        self.build_scene(b)
        self.world = w = b.compile()
        self.arms = {}
        for side, kind, prefix, base, yaw, park, home in specs:
            a = robots.make_arm(w, kind, prefix)
            a.tcp_speed = self.tcp_speed
            a.base = np.array(base, float)
            if home is not None:
                a.home = np.array(home, float)
            a.set_joints(a.home)
            if park is not None:
                q, err = a.ik(np.array(park), a.down(getattr(self, "PARK_YAW", 0.0)))
                if err[0] < 3e-3:
                    a.home = q.copy()
                    a.set_joints(q)
            self.arms[side] = a
        self.arm = next(iter(self.arms.values()))
        self.robot_bodies = set().union(*(a.robot_bodies for a in self.arms.values()))
        tags = {}
        for name, it in self.items.items():
            tags[name] = dict(body=it["body"], tag_geoms=it["tag_geoms"], label_geoms=it.get("label_geoms", []),
                              text=it.get("label", name), min_px=it.get("min_px", 40))
        self.detector = Detector(w, tags, self.rng, calib_bias=getattr(self, "calib_bias", None),
                                 read_px=getattr(self, "read_px", 150))
        w.settle(0.6)
        self.after_build()

    def after_build(self):
        pass

    # ---- scene helpers ---------------------------------------------------------------------------------------------
    def add_item(self, b, name, pos, half, rgba, mass, label_lines=None, yaw=0.0, label_rgb=None, tag_text=None,
                 extra=None):
        """A box-shaped part with a printed label on its top face (the label is also its fiducial)."""
        body = b.body(name, pos, quat=(np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)), free=True)
        b.box(body, f"{name}_g", half, rgba=rgba, mass=mass, friction=self.ITEM_FRICTION, condim=4)
        lab = None
        if label_lines:
            img = label_image(label_lines, 512, 512 if half[1] / half[0] > 0.8 else 256,
                              bg=label_rgb or (245, 245, 240))
            lab = b.decal(body, f"{name}_label", img, 1.8 * half[0], 1.8 * half[1], pos=(0, 0, half[2] + 0.0006))
        self.items[name] = dict(body=name, half=np.array(half), label=tag_text or name,
                                tag_geoms=[f"{name}_label"] if label_lines else [f"{name}_g"],
                                label_geoms=[f"{name}_label"] if label_lines else [], mass=mass, **(extra or {}))
        return body

    def container(self, b, name, center, inner, wall_h, rgba, wall=0.008, floor_t=0.006, label=None):
        """An open box (crate/bin/tray) fixed to the bench; inner = (half x, half y)."""
        cx, cy, cz = center
        body = b.body(name, (cx, cy, cz))
        hx, hy = inner
        b.box(body, f"{name}_floor", (hx + wall, hy + wall, floor_t / 2), pos=(0, 0, floor_t / 2), rgba=rgba)
        for k, (dx, dy, sx, sy) in enumerate([(hx + wall / 2, 0, wall / 2, hy + wall),
                                              (-hx - wall / 2, 0, wall / 2, hy + wall),
                                              (0, hy + wall / 2, hx + wall, wall / 2),
                                              (0, -hy - wall / 2, hx + wall, wall / 2)]):
            b.box(body, f"{name}_wall{k}", (sx, sy, wall_h / 2), pos=(dx, dy, floor_t + wall_h / 2), rgba=rgba)
        if label:
            b.decal(body, f"{name}_sign", label_image(label, 512, 160), 0.16, 0.05,
                    pos=(0, -hy - wall - 0.0006, floor_t + wall_h * 0.55), quat=(0.7071, 0.7071, 0, 0))
        return body

    def grid_slots(self, center, nx, ny, pitch_x, pitch_y):
        cx, cy = center[0], center[1]
        out = []
        for j in range(ny):
            for i in range(nx):
                out.append((cx + (i - (nx - 1) / 2) * pitch_x, cy + (j - (ny - 1) / 2) * pitch_y))
        return out

    # ---- perception ----------------------------------------------------------------------------------------------
    def perceive(self):
        """Merge detections from the cell cameras: item -> detection (best-seen camera)."""
        seen = {}
        for cam in self.CAMERAS:
            dets, _ = self.detector.detect(cam)
            for d in dets:
                if d["id"] not in seen or d["pixels"] > seen[d["id"]]["pixels"]:
                    d["camera"] = cam
                    seen[d["id"]] = d
        return seen

    def where(self, pos):
        """Nearest named location of a position (for the vision service's listing)."""
        best, bd = None, 1e9
        for name, loc in self.locations.items():
            pts = loc.get("slots") or [loc["pos"][:2]]
            for k, s in enumerate(pts):
                d = np.hypot(pos[0] - s[0], pos[1] - s[1])
                lim = loc.get("radius", 0.06)
                if d < bd and d < lim:
                    best, bd = (name if len(pts) == 1 or loc.get("container") else f"{name} {k + 1}"), d
        if best is None:
            return "on the bench" if pos[2] < 0.1 else "elsewhere"
        return best

    def true_location(self, name):
        p = self.world.body_pos(self.items[name]["body"])
        return self.where(p), p

    # ---- skills ------------------------------------------------------------------------------------------------
    def held_items(self):
        return [h for h in (a.held() for a in self.arms.values()) if h in self.items]

    def choose_arm(self, p, side=None, holding=False):
        """The arm that does a pick/place at p: the named one, else the free arm nearest to p that can reach it."""
        if side is not None:
            if side not in self.arms:
                raise Refuse(f"no arm {side!r}; arms: {', '.join(self.arms)}")
            return side, self.arms[side]
        cands = [(s, a) for s, a in self.arms.items() if bool(a.held()) == holding]
        if not cands:
            raise Refuse("every gripper is holding something; place an item first" if not holding
                         else "no gripper is holding anything")
        if len(cands) == 1:
            return cands[0]
        cands.sort(key=lambda sa: np.hypot(*(np.asarray(p[:2]) - sa[1].base[:2])))
        for s, a in cands:
            for dy in (0.0, np.pi):
                q, err = a.ik(np.array([p[0], p[1], max(self.SAFE_Z, p[2] + self.APPROACH)]),
                              a.down(self.grasp_yaw_hint(a, p) + dy))
                if err[0] < 3e-3:
                    return s, a
        return cands[0]

    def grasp_yaw_hint(self, arm, p):
        if arm.name == "yam":
            d = np.asarray(p[:2]) - arm.base[:2]
            return np.arctan2(d[1], d[0]) + np.pi / 2
        return 0.0

    def skill_pick(self, name, side=None):
        self.check_time()
        seen = self.perceive()
        if name not in seen:
            raise Refuse(f"{name} is not visible to the cell cameras (see `robot scene`)")
        d = seen[name]
        p = np.array(d["pos"])
        side, arm = self.choose_arm(p, side, holding=False)
        if arm.held():
            raise Refuse(f"the {side} gripper is already holding something; place it first")
        self.arm = arm
        it = self.items[name]
        hx, hy, hz = it["half"]
        yaw = d["yaw"] + (np.pi / 2 if hx > hy else 0.0)          # close across the narrow side
        yaw = self.best_yaw(arm, p, self.normalize_grasp_yaw(arm, yaw, p), p[2] + hz + self.APPROACH)
        R = self.arm.down(yaw + getattr(self, "GRASP_YAW_OFFSET", 0.0))
        top = p[2] + hz
        depth = getattr(arm, "grasp_depth", None)
        grasp_z = top - (min(0.025, hz) if depth is None else min(depth, 2 * hz - 0.006))
        r = self.arm.move_pose(np.array([p[0], p[1], max(self.SAFE_Z, top + self.APPROACH)]), R)
        if r["status"] != "ok":
            return self._fail("pick", r)
        if getattr(arm, "full_open", False):
            self.arm.grip(False, 0.4)
        else:
            self.arm.open_to(2 * min(hx, hy) + 0.018, 0.4)      # pre-grasp opening: part width + 18 mm
        r = self.arm.move_linear(np.array([p[0], p[1], grasp_z]), R, speed=0.5)
        if r["status"] != "ok":
            self.arm.move_linear(np.array([p[0], p[1], max(self.SAFE_Z, top + self.APPROACH)]), R)
            return self._fail("pick", r)
        held = self.arm.grip(True, 0.7)
        r = self.arm.move_linear(np.array([p[0], p[1], max(self.SAFE_Z, top + self.APPROACH + 0.03)]), R, speed=0.6)
        held = self.arm.held()
        self.held_name = held if held in self.items else None
        self.on_pick(name, held)
        who = "" if len(self.arms) == 1 else f" ({side} arm)"
        if not held:
            self.arm.grip(False, 0.3)
            self.arm.move_joints(self.arm.home, speed=0.6)
            return f"pick {name}{who}: the gripper closed empty (no object detected between the fingers)", None, 1
        return f"pick {name}{who}: gripper closed on an object; lifted", {"held": True, "arm": side}

    def place_rotation(self, arm, xy, z_high, z_low=None, R_now=None):
        """A gripper rotation (vertical approach) that the arm reaches at the place point: the current one if it
        works, else the best of a few yaws around the arm's natural one. None if nothing reaches."""
        cands = []
        if R_now is not None:
            cands.append(R_now)
        hint = self.grasp_yaw_hint(arm, (xy[0], xy[1], z_high))
        for dy in (0.0, np.pi / 2, -np.pi / 2, np.pi, np.pi / 4, -np.pi / 4):
            cands.append(arm.down(hint + dy))
        for R in cands:
            ok = True
            for z in (z_high,) + ((z_low,) if z_low is not None else ()):
                err = arm.ik(np.array([xy[0], xy[1], z]), R)[1]
                if err[0] > 3e-3 or err[1] > 3e-2:
                    ok = False
                    break
            if ok:
                return R
        return None

    def best_yaw(self, arm, p, yaw, z):
        """A parallel gripper can grasp at yaw or yaw + pi; take the one the arm reaches best."""
        best = None
        for y in (yaw, yaw + np.pi, yaw - np.pi):
            err = arm.ik(np.array([p[0], p[1], max(self.SAFE_Z, z)]), arm.down(y))[1]
            score = err[0] + 0.01 * err[1]
            if best is None or score < best[0] - 1e-4:
                best = (score, y)
        return best[1]

    def normalize_grasp_yaw(self, arm, yaw, p):
        """Equivalent grasp yaws differ by pi; take the one nearest the arm's natural wrist orientation (for a
        compact 6-axis arm such as the YAM: fingers closing across the line from its base to the part)."""
        if arm.name == "yam":
            d = np.asarray(p[:2]) - arm.base[:2]
            base = np.arctan2(d[1], d[0]) + np.pi / 2
        else:
            base = 0.0
        y = yaw
        while y - base > np.pi / 2:
            y -= np.pi
        while y - base < -np.pi / 2:
            y += np.pi
        return y

    def place_target(self, loc, slot=None):
        L = self.locations[loc]
        if L.get("slots"):
            if slot is None and L.get("container"):
                # a container: the first slot whose floor is clear (depth ray at the slot centre)
                floor = L["pos"][2]
                for k, (x, y) in enumerate(L["slots"]):
                    if self.surface_below((x, y), exclude=self.arm.held()) >= floor + 0.01:
                        continue
                    # a slot this arm can reach from above (any wrist yaw: a part can go in at any angle)
                    if self.place_rotation(self.arm, (x, y), max(self.SAFE_Z, floor + 0.12)) is not None:
                        slot = k + 1
                        break
                if slot is None:
                    raise Refuse(f"{loc} is full")
            if slot is None:
                if len(L["slots"]) == 1:
                    slot = 1
                else:
                    raise Refuse(f"{loc} has {len(L['slots'])} slots: give a slot number (1-{len(L['slots'])})")
            if not 1 <= slot <= len(L["slots"]):
                raise Refuse(f"{loc} has slots 1-{len(L['slots'])}")
            x, y = L["slots"][slot - 1]
        else:
            x, y = L["pos"][:2]
        return np.array([x, y, L["pos"][2]])

    def skill_place(self, loc, slot=None, side=None):
        self.check_time()
        if loc not in self.locations:
            raise Refuse(f"unknown location {loc!r}; locations: {', '.join(self.locations)}")
        side, arm = self.choose_arm(self.locations[loc]["pos"], side, holding=True)
        held = arm.held()
        if not held:
            raise Refuse(f"the {side} gripper is not holding anything" if len(self.arms) > 1
                         else "the gripper is not holding anything")
        self.arm = arm
        tgt = self.place_target(loc, slot)
        Lc = self.locations[loc]
        if not Lc.get("container") and not Lc.get("stackable"):
            # a slot with a part-present sensor: refuse to put a part on top of another one
            occupied = [n for n in self.items if n != held and
                        np.hypot(*(self.world.body_pos(n)[:2] - tgt[:2])) < 0.025 and
                        self.world.body_pos(n)[2] < tgt[2] + 0.12]
            if occupied:
                raise Refuse(f"{loc}{'' if slot is None else ' ' + str(slot)} is occupied (part-present sensor); "
                             f"clear it first")
        _, R = self.arm.tcp()
        it = self.items.get(held)
        hz = it["half"][2] if it else 0.03
        # the item hangs below the TCP by (TCP height - item centre); keep that offset
        tcp_p, _ = self.arm.tcp_true()
        item_p = self.world.body_pos(held)
        hang = tcp_p[2] - item_p[2]
        L = self.locations[loc]
        surface = L["surface"] if "surface" in L else self.surface_below(tgt[:2], exclude=held)
        drop_z = surface + hz + 0.004 + hang
        Rbest = self.place_rotation(self.arm, tgt[:2], max(self.SAFE_Z, drop_z + self.APPROACH), drop_z, R)
        if Rbest is not None:
            R = Rbest
        r = self.arm.move_pose(np.array([tgt[0], tgt[1], max(self.SAFE_Z, drop_z + self.APPROACH)]), R)
        if r["status"] != "ok":
            return self._fail("place", r)
        r = self.arm.move_linear(np.array([tgt[0], tgt[1], drop_z]), R, speed=0.5,
                                 stop_force=self.arm.stop_force)
        width = 2 * min(it["half"][0], it["half"][1]) + 0.018 if it else 0.06
        if getattr(self.arm, "full_open", False):
            self.arm.open_to(width + 0.012, 0.5)          # release gently: a full opening sweeps the neighbours
        else:
            self.arm.open_to(width, 0.5)
        self.arm.move_linear(np.array([tgt[0], tgt[1], max(self.SAFE_Z, drop_z + self.APPROACH)]), R, speed=0.6)
        self.arm.move_joints(self.arm.home, speed=0.6)           # park clear of the cameras
        self.held_name = None
        self.world.settle(0.3)
        self.on_place(held, loc, slot)
        if r["status"] == "protective_stop":
            return (f"place: protective stop while lowering ({r['force']:.0f} N on {r['contact']}); the item was "
                    f"released where it was", None, 1)
        return f"place {loc}{'' if slot is None else ' ' + str(slot)}: released", None

    def surface_below(self, xy, exclude=None):
        """Height of the highest surface under a point (a ray cast, as a real cell would use a depth camera)."""
        import mujoco
        geomid = np.array([-1], dtype=np.int32)
        excl = self.world.body_id(exclude) if exclude else -1
        best = 0.0
        for dx, dy in ((0, 0), (0.015, 0), (-0.015, 0), (0, 0.015), (0, -0.015)):
            z = 1.5
            for _ in range(6):                     # skip hits on the robots themselves
                s = np.array([xy[0] + dx, xy[1] + dy, z])
                dist = mujoco.mj_ray(self.world.model, self.world.data, s, np.array([0, 0, -1.0]), None, 1, excl,
                                     geomid)
                if dist < 0:
                    break
                g = int(geomid[0])
                if self.world.model.geom_bodyid[g] in self.robot_bodies:
                    z = z - dist - 0.002
                    continue
                best = max(best, z - dist)
                break
        return best

    def _fail(self, what, r):
        if r["status"] == "protective_stop":
            return (f"{what}: PROTECTIVE STOP (contact force {r['force']:.0f} N on {r['contact']}); robot holds "
                    f"position", None, 1)
        return f"{what}: target out of reach ({r.get('ik_err_mm')} mm)", None, 1

    def on_pick(self, name, held):
        pass

    def on_place(self, held, loc, slot):
        pass

    # ---- the robot tool --------------------------------------------------------------------------------------------
    def robot_scene_text(self):
        seen = self.perceive()
        lines = []
        for name in sorted(seen):
            d = seen[name]
            label = d["text"] or "(label not readable)"
            lines.append(f"  {name:<10} {self.where(d['pos']):<18} label: {label}")
        holds = []
        for s_, a in self.arms.items():
            name = "gripper" if len(self.arms) == 1 else f"{s_} gripper"
            holds.append(f"{name}: {'closed on an object' if a.held() else 'empty'}")
        return "Items seen by the cell cameras:\n" + ("\n".join(lines) if lines else "  (none)") + "\n" + \
            "; ".join(holds)

    def cmd_robot(self, argv):
        self.need(argv, 1, "robot status|scene|pick ITEM|place LOCATION [SLOT]|home|camera NAME")
        side = None
        if "--arm" in argv:
            k = argv.index("--arm")
            if k + 1 >= len(argv):
                raise Refuse("--arm needs a value: " + "|".join(self.arms))
            side = argv[k + 1]
            argv = argv[:k] + argv[k + 2:]
        sub = argv[0]
        if sub == "status":
            lines = []
            for s_, a in self.arms.items():
                p, _ = a.tcp()
                held = a.held()
                name = "robot" if len(self.arms) == 1 else f"{s_} arm"
                lines.append(f"{name}: TCP at x={p[0] * 1000:.0f} y={p[1] * 1000:.0f} z={p[2] * 1000:.0f} mm; "
                             f"gripper {'closed on an object' if held else 'empty'}")
            return "\n".join(lines) + f"\n{self.status_extra()}{self.time_line()}"
        if sub == "scene":
            self.spend(1.0)
            return self.robot_scene_text()
        if sub == "pick":
            self.need(argv, 2, "robot pick ITEM")
            return self.skill_pick(argv[1], side)
        if sub == "place":
            self.need(argv, 2, "robot place LOCATION [SLOT]")
            slot = int(self.num(argv[2], "slot")) if len(argv) > 2 else None
            return self.skill_place(argv[1], slot, side)
        if sub == "home":
            self.check_time()
            for s_, a in self.arms.items():
                if side in (None, s_):
                    r = a.move_joints(a.home, speed=0.6)
                    if r["status"] != "ok":
                        return self._fail("home", r)
            return "home: done"
        if sub == "camera":
            cams = self.camera_names()
            cam = argv[1] if len(argv) > 1 else cams[0]
            if cam not in cams:
                raise Refuse(f"cameras: {', '.join(cams)}")
            self.spend(0.5)
            path, _ = self.snapshot(cam, cam)
            return f"saved {path}"
        return self.robot_extra(sub, argv)

    def robot_extra(self, sub, argv):
        raise Refuse(f"unknown robot subcommand {sub!r}")

    def status_extra(self):
        return ""

    def camera_names(self):
        return list(self.CAMERAS)
