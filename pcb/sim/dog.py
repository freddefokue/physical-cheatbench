"""Unitree Go1 walking under a learned joystick policy (MuJoCo Playground, `go1_policy.onnx`).

The policy is the one MuJoCo Playground deploys zero-shot on the real Go1 (sim-to-real): it maps proprioception
(local linear velocity, gyro, gravity direction, joint angles and velocities, last action) and a velocity command
(vx, vy, yaw rate) to joint position targets at 50 Hz. Walking, turning, stumbling and falling are all physics.

On top of it, `goto` is a simple path follower (what an inspection robot's navigation stack does between mission
waypoints): it turns toward the next point and walks, and it stops if the robot falls or stops making progress.
"""
import numpy as np
import onnxruntime as rt
import mujoco

from .core import PLAYGROUND

DEFAULT = np.array([0.1, 0.9, -1.8, -0.1, 0.9, -1.8, 0.1, 0.9, -1.8, -0.1, 0.9, -1.8])


def go1_xml():
    return str(PLAYGROUND / "go1" / "go1_mjx_feetonly.xml")


class Go1:
    def __init__(self, world, prefix="dog/", ctrl_dt=0.02):
        self.w, self.m, self.d = world, world.model, world.data
        self.p = prefix
        self.sess = rt.InferenceSession(str(PLAYGROUND / "go1_policy.onnx"), providers=["CPUExecutionProvider"])
        self.free = self.m.body_jntadr[world.body_id(prefix + "trunk")]          # the trunk's free joint
        self.qa = self.m.jnt_qposadr[self.free]
        self.va = self.m.jnt_dofadr[self.free]
        names = ["FR_hip", "FR_thigh", "FR_calf", "FL_hip", "FL_thigh", "FL_calf",
                 "RR_hip", "RR_thigh", "RR_calf", "RL_hip", "RL_thigh", "RL_calf"]
        self.jq = np.array([self.m.jnt_qposadr[world.id(mujoco.mjtObj.mjOBJ_JOINT, prefix + n + "_joint")]
                            for n in names])
        self.jv = np.array([self.m.jnt_dofadr[world.id(mujoco.mjtObj.mjOBJ_JOINT, prefix + n + "_joint")]
                            for n in names])
        self.aids = np.array([world.id(mujoco.mjtObj.mjOBJ_ACTUATOR, prefix + n) for n in names])
        self.imu = world.id(mujoco.mjtObj.mjOBJ_SITE, prefix + "imu")
        self.s_linvel = self.m.sensor(prefix + "local_linvel").adr[0]
        self.s_gyro = self.m.sensor(prefix + "gyro").adr[0]
        self.trunk = world.body_id(prefix + "trunk")
        self.nsub = max(1, int(round(ctrl_dt / self.m.opt.timestep)))
        self.cmd = np.zeros(3, np.float32)
        self.last = np.zeros(12, np.float32)
        self.k = 0
        self.fallen = False
        self.walk_time = 0.0
        world.hooks.append(self._hook)

    def _free_joint_name(self):
        for i in range(self.m.njnt):
            if self.m.jnt_type[i] == mujoco.mjtJoint.mjJNT_FREE and self.m.joint(i).name.startswith(self.p):
                return self.m.joint(i).name
        raise KeyError("no free joint for the dog")

    def place(self, x, y, yaw):
        self.d.qpos[self.qa:self.qa + 3] = [x, y, 0.278]
        self.d.qpos[self.qa + 3:self.qa + 7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        self.d.qpos[self.jq] = DEFAULT
        self.d.qvel[self.va:self.va + 6] = 0
        self.d.ctrl[self.aids] = DEFAULT
        mujoco.mj_forward(self.m, self.d)

    def _obs(self):
        R = self.d.site_xmat[self.imu].reshape(3, 3)
        g = R.T @ np.array([0, 0, -1.0])
        return np.hstack([self.d.sensordata[self.s_linvel:self.s_linvel + 3],
                          self.d.sensordata[self.s_gyro:self.s_gyro + 3], g, self.d.qpos[self.jq] - DEFAULT,
                          self.d.qvel[self.jv], self.last, self.cmd]).astype(np.float32)

    def _hook(self):
        self.k += 1
        if self.k % self.nsub:
            return
        a = self.sess.run(["continuous_actions"], {"obs": self._obs().reshape(1, -1)})[0][0]
        self.last = a.astype(np.float32)
        self.d.ctrl[self.aids] = a * 0.5 + DEFAULT
        if np.any(self.cmd != 0):
            self.walk_time += self.m.opt.timestep * self.nsub

    # ---- state ----------------------------------------------------------------------------------------------------
    def pose(self):
        p = self.d.qpos[self.qa:self.qa + 3].copy()
        q = self.d.qpos[self.qa + 3:self.qa + 7]
        yaw = np.arctan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
        return p, float(yaw)

    def upright(self):
        R = self.d.xmat[self.trunk].reshape(3, 3)
        return R[2, 2]

    def check_fall(self):
        p, _ = self.pose()
        if p[2] < 0.16 or self.upright() < 0.5:
            self.fallen = True
        return self.fallen

    # ---- motion ---------------------------------------------------------------------------------------------------
    def walk(self, vx, vy, wz, secs):
        self.cmd[:] = [np.clip(vx, -1.0, 1.5), np.clip(vy, -0.8, 0.8), np.clip(wz, -2.0, 2.0)]
        t_end = self.d.time + secs
        while self.d.time < t_end:
            self.w.step(self.nsub)
            if self.check_fall():
                break
        self.cmd[:] = 0
        self.w.settle(0.4)
        self.check_fall()

    def goto(self, x, y, yaw=None, timeout=60.0, speed=0.7):
        """Walk to (x, y) and optionally turn to yaw. Returns (status, distance left)."""
        t0 = self.d.time
        best, stall_t = 1e9, self.d.time
        while True:
            if self.check_fall():
                self.cmd[:] = 0
                return "fallen", None
            p, th = self.pose()
            dx, dy = x - p[0], y - p[1]
            dist = float(np.hypot(dx, dy))
            if dist < 0.12:
                break
            if dist < best - 0.05:
                best, stall_t = dist, self.d.time
            if self.d.time - stall_t > 6.0:
                self.cmd[:] = 0
                self.w.settle(0.4)
                return "blocked", dist
            if self.d.time - t0 > timeout:
                self.cmd[:] = 0
                self.w.settle(0.4)
                return "timeout", dist
            err = (np.arctan2(dy, dx) - th + np.pi) % (2 * np.pi) - np.pi
            wz = float(np.clip(2.0 * err, -1.2, 1.2))
            vx = float(speed * max(0.0, np.cos(err)) ** 3 * min(1.0, dist / 0.5 + 0.2))
            self.cmd[:] = [vx, 0.0, wz]
            self.w.step(self.nsub)
        if yaw is not None:
            for _ in range(400):
                _, th = self.pose()
                err = (yaw - th + np.pi) % (2 * np.pi) - np.pi
                if abs(err) < 0.06:
                    break
                self.cmd[:] = [0.0, 0.0, float(np.clip(2.0 * err, -1.0, 1.0))]
                self.w.step(self.nsub)
                if self.check_fall():
                    break
        self.cmd[:] = 0
        self.w.settle(0.5)
        return ("fallen" if self.check_fall() else "ok"), 0.0
