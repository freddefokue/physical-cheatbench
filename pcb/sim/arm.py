"""Arm controller: what a vendor controller plus a thin motion library give a real cell.

- joint position control through the model's own actuators, with gravity compensation (bodies' gravcomp), as the
  Franka, UR and Interbotix/I2RT controllers do internally;
- inverse kinematics (damped least squares) on the arm's *nominal* kinematic model. A joint zero-offset error can be
  set per instance (`joint_offset`); then encoders report q_true + offset and IK-based moves miss by the resulting
  Cartesian error, exactly as on a miscalibrated real arm, while joint-space replays recorded on the same arm do not;
- min-jerk joint trajectories and straight-line Cartesian moves with joint and TCP speed limits;
- a protective stop: motion halts when contact forces on the robot (other than the gripper's grasp) exceed a limit.
"""
import mujoco
import numpy as np

from .core import OBJ


def min_jerk(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * t * (10 - 15 * t + 6 * t * t)


def orient(approach_local, closing_local, approach_world, closing_world):
    """Rotation of a TCP frame whose local approach/closing axes must point along the given world directions."""
    def basis(a, c):
        a = np.asarray(a, float) / np.linalg.norm(a)
        c = np.asarray(c, float) - np.dot(c, a) * a
        c /= np.linalg.norm(c)
        return np.column_stack([a, c, np.cross(a, c)])
    return basis(approach_world, closing_world) @ basis(approach_local, closing_local).T


class ProtectiveStop(Exception):
    pass


class Arm:
    def __init__(self, world, prefix, joints, actuators, tcp_site, approach, closing, grip_act=None, grip_open=None,
                 grip_closed=None, finger_bodies=(), vmax=None, tcp_speed=0.5, stop_force=80.0, home=None,
                 joint_offset=None, name="arm", width_to_ctrl=None, max_width=None):
        self.w, self.m, self.d = world, world.model, world.data
        self.name = name
        self.prefix = prefix
        self.jids = [world.id(OBJ.mjOBJ_JOINT, prefix + j) for j in joints]
        self.qadr = np.array([self.m.jnt_qposadr[j] for j in self.jids])
        self.dadr = np.array([self.m.jnt_dofadr[j] for j in self.jids])
        self.aids = np.array([world.id(OBJ.mjOBJ_ACTUATOR, prefix + a) for a in actuators])
        self.site = world.id(OBJ.mjOBJ_SITE, prefix + tcp_site)
        self.approach, self.closing = np.asarray(approach, float), np.asarray(closing, float)
        self.grip_aid = world.id(OBJ.mjOBJ_ACTUATOR, prefix + grip_act) if grip_act else None
        self.grip_open, self.grip_closed = grip_open, grip_closed
        # finger_bodies: one entry per finger, each a body name or a tuple of body names (pad, link, ...)
        self.finger_groups = [{world.body_id(prefix + b) for b in ((g,) if isinstance(g, str) else g)}
                              for g in finger_bodies]
        self.finger_bodies = set().union(*self.finger_groups) if self.finger_groups else set()
        n = len(self.jids)
        self.vmax = np.asarray(vmax if vmax is not None else [2.0] * n, float)
        self.tcp_speed = tcp_speed            # m/s cap for Cartesian moves (the cell's speed limit sets this)
        self.stop_force = stop_force
        self.lo = np.array([self.m.jnt_range[j][0] for j in self.jids])
        self.hi = np.array([self.m.jnt_range[j][1] for j in self.jids])
        self.offset = np.zeros(n) if joint_offset is None else np.asarray(joint_offset, float)
        self.robot_bodies = {i for i in range(self.m.nbody) if self.m.body(i).name.startswith(prefix)}
        self.allowed_contact = set()          # geom ids whose contact with the robot never trips the stop
        self.ctrl = self.d.qpos[self.qadr].copy()
        self.grip_ctrl = grip_open
        self.width_to_ctrl = width_to_ctrl      # opening width (m) -> gripper actuator command
        self.max_width = max_width
        self.home = np.asarray(home, float) if home is not None else self.ctrl.copy()
        self.scratch = mujoco.MjData(self.m)
        self.integral_iters = 4
        self.log = []                          # (time, kind, detail) of every motion, for the act log
        world.hooks.append(self._apply)

    # ---- low level ---------------------------------------------------------------------------------------------
    def _apply(self):
        self.d.ctrl[self.aids] = self.ctrl
        if self.grip_aid is not None and self.grip_ctrl is not None:
            self.d.ctrl[self.grip_aid] = self.grip_ctrl

    def set_joints(self, q):
        """Teleport to a joint configuration (scene setup only)."""
        q = np.asarray(q, float)
        self.d.qpos[self.qadr] = q
        self.d.qvel[self.dadr] = 0
        self.ctrl = q.copy()
        mujoco.mj_forward(self.m, self.d)

    def q_true(self):
        return self.d.qpos[self.qadr].copy()

    def q(self):
        """Encoder reading (includes the instance's joint zero-offset error)."""
        return self.q_true() + self.offset

    def tcp_true(self):
        return self.d.site_xpos[self.site].copy(), self.d.site_xmat[self.site].reshape(3, 3).copy()

    def fk(self, q_nominal):
        """TCP pose predicted by the nominal model for an encoder reading."""
        s = self.scratch
        s.qpos[:] = self.d.qpos
        s.qpos[self.qadr] = q_nominal
        mujoco.mj_kinematics(self.m, s)
        return s.site_xpos[self.site].copy(), s.site_xmat[self.site].reshape(3, 3).copy()

    def tcp(self):
        """TCP pose as the controller reports it (forward kinematics of the encoder reading)."""
        return self.fk(self.q())

    # ---- inverse kinematics on the nominal model -----------------------------------------------------------------
    def ik(self, pos, R=None, q0=None, iters=300, tol_p=2e-4, tol_r=2e-3):
        s = self.scratch
        best = None
        seeds = [self.q() if q0 is None else np.asarray(q0, float), self.home]
        for seed in seeds:
            q = np.clip(seed.copy(), self.lo, self.hi)
            jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
            for _ in range(iters):
                s.qpos[:] = self.d.qpos
                s.qpos[self.qadr] = q
                mujoco.mj_kinematics(self.m, s)
                mujoco.mj_comPos(self.m, s)
                p = s.site_xpos[self.site]
                ep = np.asarray(pos, float) - p
                if R is not None:
                    Rc = s.site_xmat[self.site].reshape(3, 3)
                    er = 0.5 * sum(np.cross(Rc[:, i], R[:, i]) for i in range(3))
                else:
                    er = np.zeros(3)
                if np.linalg.norm(ep) < tol_p and np.linalg.norm(er) < tol_r:
                    break
                mujoco.mj_jacSite(self.m, s, jp, jr, self.site)
                J = np.vstack([jp[:, self.dadr], jr[:, self.dadr]]) if R is not None else jp[:, self.dadr]
                e = np.concatenate([ep, 0.6 * er]) if R is not None else ep
                lam = 1e-3 if np.linalg.norm(e) < 0.05 else 1e-2
                dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(J.shape[0]), e)
                # gentle pull toward the rest posture in the null space keeps solutions tidy
                Jp = np.linalg.pinv(J)
                dq += 0.05 * (np.eye(len(q)) - Jp @ J) @ (self.home - q)
                q = np.clip(q + np.clip(dq, -0.3, 0.3), self.lo, self.hi)
            err = (np.linalg.norm(ep), np.linalg.norm(er))
            if best is None or err[0] + 0.05 * err[1] < best[1][0] + 0.05 * best[1][1]:
                best = (q.copy(), err)
            if err[0] < 1e-3 and err[1] < 1e-2:
                break
        return best

    def down(self, yaw=0.0, approach_world=(0, 0, -1)):
        """Target rotation for a top-down grasp whose fingers close along world direction yaw."""
        return orient(self.approach, self.closing, approach_world, (np.cos(yaw), np.sin(yaw), 0.0))

    # ---- motion ------------------------------------------------------------------------------------------------
    def _check_stop(self, extra_allowed=()):
        gb = self.m.geom_bodyid
        f6 = np.zeros(6)
        worst = (0.0, None)
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            b1, b2 = gb[c.geom1], gb[c.geom2]
            r1, r2 = b1 in self.robot_bodies, b2 in self.robot_bodies
            if r1 == r2:
                continue
            other = c.geom2 if r1 else c.geom1
            mine_body = b1 if r1 else b2
            if other in self.allowed_contact or other in extra_allowed:
                continue
            if mine_body in self.finger_bodies and self._holding_geom(other):
                continue
            mujoco.mj_contactForce(self.m, self.d, i, f6)
            if abs(f6[0]) > worst[0]:
                worst = (abs(f6[0]), self.m.geom(other).name or self.m.body(gb[other]).name)
        return worst

    def _finger_group(self, body):
        for k, g in enumerate(self.finger_groups):
            if body in g:
                return k
        return None

    def _holding_geom(self, gid):
        if len(self.finger_groups) < 2:
            return False
        ob = self.m.geom_bodyid[gid]
        touching = set()
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            b1, b2 = self.m.geom_bodyid[c.geom1], self.m.geom_bodyid[c.geom2]
            if b1 == ob and b2 in self.finger_bodies:
                touching.add(self._finger_group(b2))
            elif b2 == ob and b1 in self.finger_bodies:
                touching.add(self._finger_group(b1))
        return len(touching) >= 2

    def _follow(self, path, T, stop_force=None, allowed=(), settle=0.12, extra_stop=None):
        """Track a joint path (rows: true joint targets, first row = start) over T seconds with min-jerk timing."""
        path = np.asarray(path, float)
        k = len(path) - 1
        dt = self.m.opt.timestep
        n = max(1, int(np.ceil(T / dt)))
        limit = self.stop_force if stop_force is None else stop_force
        t0 = self.w.time
        for i in range(n):
            s = min_jerk((i + 1) / n) * k
            j = min(int(s), k - 1) if k > 0 else 0
            a = s - j
            self.ctrl = path[j] + a * (path[min(j + 1, k)] - path[j]) if k > 0 else path[0]
            self.w.step(1)
            if i % 5 == 0:
                f, what = self._check_stop(allowed)
                if extra_stop is not None:
                    fx = extra_stop()
                    if fx is not None and fx > f:
                        f, what = fx, "the held part (force estimate)"
                if f > limit:
                    self.ctrl = self.q_true()
                    self.w.settle(0.15)
                    self.log.append((t0, "protective_stop", {"force": round(f, 1), "contact": what}))
                    return {"status": "protective_stop", "force": round(f, 1), "contact": what,
                            "t": self.w.time - t0}
        if settle:
            self.w.settle(settle)
            # steady-state correction (the integral action of the joint servos): re-command until the encoders
            # read the target, unless something resists (contact) or the error is already small
            target = path[-1]
            for _ in range(self.integral_iters):
                err = target - self.q_true()
                if np.max(np.abs(err)) < 2e-4:
                    break
                f, _ = self._check_stop(allowed)
                if extra_stop is not None:
                    f = max(f, extra_stop() or 0.0)
                if f > 0.5 * limit:
                    break
                self.ctrl = self.ctrl + np.clip(err, -0.02, 0.02)
                self.w.settle(0.08)
        return {"status": "ok", "t": self.w.time - t0}

    def move_joints(self, q_target_nominal, speed=1.0, stop_force=None, allowed=(), min_time=0.3):
        """Min-jerk move to an encoder-frame target. Returns a dict with status and duration."""
        q_target = np.clip(np.asarray(q_target_nominal, float) - self.offset, self.lo, self.hi)   # true joint target
        q0 = self.ctrl.copy()
        dq = q_target - q0
        p0, _ = self.tcp_true()
        p1, _ = self.fk(q_target + self.offset)
        T = max(min_time, float(np.max(np.abs(dq) / (self.vmax * speed))),
                1.6 * float(np.linalg.norm(p1 - p0) / max(self.tcp_speed * speed, 1e-3)))
        return self._follow([q0, q_target], T, stop_force, allowed)

    def move_pose(self, pos, R=None, speed=1.0, **kw):
        q, err = self.ik(pos, R)
        if err[0] > 5e-3 or (R is not None and err[1] > 5e-2):
            return {"status": "unreachable", "ik_err_mm": round(err[0] * 1000, 1)}
        return self.move_joints(q, speed=speed, **kw)

    def move_linear(self, pos, R=None, speed=1.0, step=0.005, stop_force=None, allowed=(), extra_stop=None):
        """Straight-line Cartesian move (IK waypoints every `step` metres), as a robot's moveL. Peak TCP speed stays
        under the cell's limit (min-jerk timing peaks at 1.875x the mean speed)."""
        p0, R0 = self.tcp()
        R = R0 if R is None else R
        pos = np.asarray(pos, float)
        dist = float(np.linalg.norm(pos - p0))
        k = max(1, int(np.ceil(dist / step)))
        q = self.q()
        path = [self.ctrl.copy()]
        for i in range(1, k + 1):
            p = p0 + (pos - p0) * i / k
            q, err = self.ik(p, R, q0=q, iters=100)
            if err[0] > 5e-3:
                return {"status": "unreachable", "ik_err_mm": round(err[0] * 1000, 1)}
            path.append(np.clip(q - self.offset, self.lo, self.hi))
        T = max(0.2, 1.875 * dist / max(self.tcp_speed * speed, 1e-3))
        return self._follow(path, T, stop_force, allowed, extra_stop=extra_stop)

    # ---- gripper -----------------------------------------------------------------------------------------------
    def grip(self, close=True, secs=0.8):
        if self.grip_aid is None:
            return None
        self.grip_ctrl = self.grip_closed if close else self.grip_open
        self.w.settle(secs)
        return self.held()

    def open_to(self, width, secs=0.4):
        """Open (or close) the fingers to a commanded width, as real grippers accept a position command."""
        if self.grip_aid is None:
            return
        if self.width_to_ctrl is None or self.max_width is None:
            self.grip_ctrl = self.grip_open
        else:
            self.grip_ctrl = self.width_to_ctrl(min(max(width, 0.0), self.max_width))
        self.w.settle(secs)

    def held(self):
        """Name of the body held between the fingers (contact with at least two finger bodies), or None."""
        if len(self.finger_groups) < 2:
            return None
        counts = {}
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            b1, b2 = self.m.geom_bodyid[c.geom1], self.m.geom_bodyid[c.geom2]
            for f, o in ((b1, b2), (b2, b1)):
                if f in self.finger_bodies and o not in self.robot_bodies:
                    counts.setdefault(o, set()).add(self._finger_group(f))
        for o, fs in counts.items():
            if len(fs) >= 2:
                return self.m.body(self.m.body_rootid[o]).name or self.m.body(o).name
        return None
