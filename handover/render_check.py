"""Can this machine render MuJoCo offscreen at v5's camera size (2560 x 1920)? Prints the backend and the time per frame."""
import os, time
import mujoco
XML = """<mujoco><visual><global offwidth="2560" offheight="1920"/></visual>
<worldbody><light pos="0 0 3"/><geom type="plane" size="1 1 .1"/><geom type="box" size=".1 .1 .1" pos="0 0 .1" rgba="1 0 0 1"/>
<camera name="c" pos="0 -1 1" xyaxes="1 0 0 0 .7 .7"/></worldbody></mujoco>"""
m = mujoco.MjModel.from_xml_string(XML); d = mujoco.MjData(m); mujoco.mj_forward(m, d)
r = mujoco.Renderer(m, 1920, 2560)
t = time.time()
for _ in range(5):
    r.update_scene(d, camera="c"); img = r.render()
print(f"MUJOCO_GL={os.environ.get('MUJOCO_GL')}  frame {img.shape}  {(time.time() - t) / 5:.3f} s per frame  (red pixels: {(img[..., 0] > 150).mean():.2%})")
r.close()
