"""v4 sketch (not part of v3). Run: .venv/bin/python prototypes/v4_panda_physics.py (needs ~/.cache/pcb/mujoco_menagerie,
git clone --depth 1 --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie and sparse-checkout
franka_emika_panda).

Feasibility prototype: Franka Panda (MuJoCo Menagerie) with real contact physics, driven by an agent-style API.

Scene: table, a cube, a weighing platform on a force sensor, an overhead camera. A scripted 'agent' calls
move_to / grip like an SDK would; grasping, carrying and the scale reading all come from the physics.
"""
import os
import time

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from PIL import Image

MEN = os.path.expanduser("~/.cache/pcb/mujoco_menagerie/franka_emika_panda")
XML = f"""
<mujoco model="proto">
  <include file="panda.xml"/>
  <option timestep="0.002" integrator="implicitfast"/>
  <visual><global offwidth="640" offheight="480"/></visual>
  <worldbody>
    <light pos="0 0 3" dir="0 0 -1" diffuse="0.8 0.8 0.8"/>
    <geom name="floor" type="plane" size="2 2 0.1" rgba="0.3 0.3 0.32 1"/>
    <body name="cube" pos="0.5 0.0 0.025">
      <freejoint/>
      <geom type="box" size="0.025 0.025 0.025" mass="0.2" rgba="0.9 0.4 0.1 1" friction="1.5 0.02 0.002"/>
    </body>
    <body name="scale" pos="0.45 -0.3 0.0">
      <geom name="scale_base" type="box" size="0.08 0.08 0.01" pos="0 0 0.01" rgba="0.2 0.2 0.25 1"/>
      <body name="platform" pos="0 0 0.032">
        <joint name="load" type="slide" axis="0 0 1" stiffness="20000" damping="200" frictionloss="0" armature="0" limited="false"/>
        <geom name="pan" type="box" size="0.07 0.07 0.005" mass="0.3" rgba="0.75 0.75 0.78 1"/>
        <site name="pan_site" pos="0 0 0"/>
      </body>
    </body>
    <camera name="top" pos="0.5 -0.15 1.2" xyaxes="1 0 0 0 1 0"/>
  </worldbody>
  <sensor><jointactuatorfrc name="dummy" joint="joint1"/><force name="load_cell" site="pan_site"/></sensor>
</mujoco>
"""


class Arm:
    def __init__(self):
        path = os.path.join(MEN, "proto_scene.xml")
        open(path, "w").write(XML)
        self.m = mujoco.MjModel.from_xml_path(path)
        self.d = mujoco.MjData(self.m)
        key = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_KEY, "home")
        mujoco.mj_resetDataKeyframe(self.m, self.d, key)
        self.hand = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, "hand")
        self.ctrl = self.d.ctrl.copy()
        self.settle(1.0)

    def settle(self, secs):
        for _ in range(int(secs / self.m.opt.timestep)):
            self.d.ctrl[:] = self.ctrl
            mujoco.mj_step(self.m, self.d)

    def tip(self):
        # point between the fingertips: hand origin + 0.1034 m along the hand z axis
        R = self.d.xmat[self.hand].reshape(3, 3)
        return self.d.xpos[self.hand] + R @ np.array([0, 0, 0.1034]), R

    def ik(self, target, iters=300):
        """Damped least squares on a copy of the state: fingertip to target, gripper pointing down, yaw fixed."""
        d = mujoco.MjData(self.m)
        d.qpos[:] = self.d.qpos
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        down = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float)    # hand z pointing at the floor
        for _ in range(iters):
            mujoco.mj_kinematics(self.m, d)
            mujoco.mj_comPos(self.m, d)
            R = d.xmat[self.hand].reshape(3, 3)
            p = d.xpos[self.hand] + R @ np.array([0, 0, 0.1034])
            ep = target - p
            Rerr = down @ R.T
            q = np.zeros(4)
            mujoco.mju_mat2Quat(q, Rerr.flatten())
            er = np.zeros(3)
            mujoco.mju_quat2Vel(er, q, 1.0)
            if np.linalg.norm(ep) < 1e-4 and np.linalg.norm(er) < 1e-3:
                break
            mujoco.mj_jac(self.m, d, jp, jr, p, self.hand)
            J = np.vstack([jp[:, :7], jr[:, :7]])
            e = np.concatenate([ep, er])
            dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e)
            d.qpos[:7] += 0.5 * dq
        return d.qpos[:7].copy()

    def move_to(self, xyz, secs=1.5):
        q = self.ik(np.asarray(xyz, float))
        start = self.ctrl[:7].copy()
        n = int(secs / self.m.opt.timestep)
        for i in range(n):                       # straight-line interpolation in joint space
            a = min(1.0, (i + 1) / (0.7 * n))
            self.ctrl[:7] = start + a * (q - start)
            self.d.ctrl[:] = self.ctrl
            mujoco.mj_step(self.m, self.d)
        return np.linalg.norm(self.tip()[0] - xyz)

    def grip(self, close):
        self.ctrl[7] = 0 if close else 255
        self.settle(0.8)

    def cube_pos(self):
        return self.d.xpos[mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, "cube")].copy()

    def scale_grams(self):
        # load cell: spring deflection of the platform x stiffness, tared for the 300 g pan
        j = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_JOINT, "load")
        q = self.d.qpos[self.m.jnt_qposadr[j]]
        return -q * 20000.0 / 9.81 * 1000 - 300.0

    def snapshot(self, path):
        r = mujoco.Renderer(self.m, 480, 640)
        r.update_scene(self.d, camera="top")
        Image.fromarray(r.render()).save(path)
        r.close()


t0 = time.time()
a = Arm()
print(f"model: nq={a.m.nq}, bodies={a.m.nbody}; scale empty: {a.scale_grams():.0f} g")
c = a.cube_pos()
print("reach above cube, err m:", round(a.move_to(c + [0, 0, 0.12]), 4))
a.grip(False)
print("descend, err m:", round(a.move_to(c + [0, 0, 0.005]), 4))
a.grip(True)
a.move_to(c + [0, 0, 0.2])
print("cube lifted to z =", round(a.cube_pos()[2], 3))
a.move_to([0.45, -0.3, 0.2])
a.move_to([0.45, -0.3, 0.082])
a.grip(False)
a.move_to([0.45, -0.3, 0.25])
a.settle(1.0)
print(f"cube now at {np.round(a.cube_pos(), 3)}; scale reads {a.scale_grams():.0f} g (cube mass 200 g)")
a.snapshot("/tmp/v4_proto_top.png")
print(f"sim time {a.d.time:.1f} s in {time.time() - t0:.1f} s wall")
