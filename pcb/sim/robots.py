"""Robot catalogue: how each Menagerie robot is attached to a scene and wrapped in an Arm controller.

Joint speed limits are the manufacturers' published maxima (rad/s); the cells run them at a fraction (speed=...).
Protective-stop forces follow typical collaborative settings for each robot class.
"""
import mujoco
import numpy as np

from .arm import Arm

PANDA_HOME = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785]
UR5E_HOME = [-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0.0]


def _panda_tcp(spec):
    spec.body("hand").add_site(name="tcp", pos=[0, 0, 0.1034])


def _panda_probe(spec):
    """Panda without the hand, carrying a hardened flat probe (25 mm diameter) behind a 6-axis force/torque sensor."""
    link7 = spec.body("link7")
    tool = link7.add_body(name="probe", pos=[0, 0, 0.107])
    tool.add_site(name="ft_site", pos=[0, 0, 0])
    tool.add_geom(name="ft_sensor", type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.035, 0.0125, 0], pos=[0, 0, 0.0125],
                  rgba=[0.15, 0.15, 0.17, 1], mass=0.3)                       # ATI-style sensor body
    tool.add_geom(name="probe_shaft", type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.008, 0.04, 0], pos=[0, 0, 0.065], rgba=[0.7, 0.7, 0.72, 1],
                  mass=0.1)
    tool.add_geom(name="probe_tip", type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.006, 0, 0], pos=[0, 0, 0.107],
                  rgba=[0.55, 0.55, 0.6, 1], mass=0.03, friction=[0.6, 0.005, 0.0001])   # hardened ball-nose tip
    tool.add_site(name="tcp", pos=[0, 0, 0.113])
    spec.add_sensor(name="ft_force", type=mujoco.mjtSensor.mjSENS_FORCE, objtype=mujoco.mjtObj.mjOBJ_SITE,
                    objname="ft_site")
    spec.add_sensor(name="ft_torque", type=mujoco.mjtSensor.mjSENS_TORQUE, objtype=mujoco.mjtObj.mjOBJ_SITE,
                    objname="ft_site")


def _yam_grip(spec):
    """The Menagerie YAM gripper servo (kp 100 N/m) squeezes about 2.5 N, too little to carry a 200 g part through a
    move; set it to a 25 N squeeze limit, the order of the real gripper's rated force."""
    a = spec.actuator("gripper")
    kp, kv = 1000.0, 30.0
    a.gainprm[0] = kp
    a.biasprm[1], a.biasprm[2] = -kp, -kv
    a.forcelimited = 1
    a.forcerange = [-25.0, 25.0]


def attach(builder, kind, prefix, pos, yaw=0.0):
    q = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
    if kind == "panda":
        builder.attach_robot("franka_emika_panda/panda.xml", prefix, pos, q, edit=_panda_tcp)
    elif kind == "panda_probe":
        builder.attach_robot("franka_emika_panda/panda_nohand.xml", prefix, pos, q, edit=_panda_probe)
    elif kind == "ur5e":
        builder.attach_robot("universal_robots_ur5e/ur5e.xml", prefix, pos, q, child="robotiq_2f85/2f85.xml",
                             child_site="attachment_site", child_prefix="g/")
    elif kind == "yam":
        builder.attach_robot("i2rt_yam/yam.xml", prefix, pos, q, edit=_yam_grip)
    else:
        raise ValueError(kind)


def make_arm(world, kind, prefix, **kw):
    if kind == "panda":
        a = Arm(world, prefix, [f"joint{i}" for i in range(1, 8)], [f"actuator{i}" for i in range(1, 8)], "tcp",
                approach=(0, 0, 1), closing=(0, 1, 0), grip_act="actuator8", grip_open=255.0, grip_closed=0.0,
                finger_bodies=("left_finger", "right_finger"), vmax=[2.175] * 4 + [2.61] * 3, home=PANDA_HOME,
                width_to_ctrl=lambda wd: 255.0 * wd / 0.08, max_width=0.08,
                stop_force=kw.pop("stop_force", 70.0), name=kind, **kw)
    elif kind == "panda_probe":
        a = Arm(world, prefix, [f"joint{i}" for i in range(1, 8)], [f"actuator{i}" for i in range(1, 8)], "tcp",
                approach=(0, 0, 1), closing=(1, 0, 0), vmax=[2.175] * 4 + [2.61] * 3, home=PANDA_HOME,
                stop_force=kw.pop("stop_force", 70.0), name=kind, **kw)
    elif kind == "ur5e":
        a = Arm(world, prefix, ["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint",
                                "wrist_2_joint", "wrist_3_joint"],
                ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"], "g/pinch",
                approach=(0, 0, 1), closing=(0, 1, 0), grip_act="g/fingers_actuator", grip_open=0.0,
                grip_closed=255.0,
                finger_bodies=(("g/left_pad", "g/left_silicone_pad"), ("g/right_pad", "g/right_silicone_pad")),
                vmax=[3.14] * 6, home=UR5E_HOME, width_to_ctrl=lambda wd: 255.0 * (1 - wd / 0.085), max_width=0.085,
                stop_force=kw.pop("stop_force", 120.0), name=kind, **kw)
    elif kind == "yam":
        a = Arm(world, prefix, [f"joint{i}" for i in range(1, 7)], [f"joint{i}" for i in range(1, 7)], "grasp_site",
                approach=(0, 0, 1), closing=(1, 0, 0), grip_act="gripper", grip_open=0.041, grip_closed=0.0,
                finger_bodies=(("link_left_finger", "lf_rot", "lf_down"), ("link_right_finger", "rf_rot", "rf_down")),
                vmax=[3.0] * 6, width_to_ctrl=lambda wd: wd / 2.0, max_width=0.075,
                stop_force=kw.pop("stop_force", 40.0), name=kind, **kw)
    else:
        raise ValueError(kind)
    # where the fingers close relative to the TCP site: the YAM's grasp site sits about 30 mm above the finger
    # pads' contact zone, so it grasps 30 mm below an item's top and needs the gripper fully open to descend
    a.grasp_depth = 0.032 if kind == "yam" else None
    a.full_open = kind == "yam"
    return a
