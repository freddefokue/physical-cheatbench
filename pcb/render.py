"""Camera images for the cells: a MuJoCo scene rebuilt from the task's object list on each request.

Units in: millimetres and radians (cell frame: x right, y away from the robot base, z up from the table top).
Items: {"kind": "box"|"cyl", "pos": (x, y, z_centre), "size": half extents (box) or (radius, half height) (cyl),
        "yaw": rad, "rgba": (r, g, b, a), "texture": optional PNG path mapped onto a box}.
"""
import os

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

MM = 0.001
_LOCK = __import__("threading").Lock()     # one EGL render at a time


def _cam_quat(pos, look):
    pos, look = np.asarray(pos, float), np.asarray(look, float)
    fwd = look - pos
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    if np.linalg.norm(right) < 1e-6:
        right = np.cross(fwd, [0, 1.0, 0]) * -1
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    mat = np.stack([right, up, -fwd], axis=1)
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, mat.flatten())
    return q


def render(items, camera, size=(640, 480), table=(900, 700), robot_base=True):
    """camera = (pos_mm, lookat_mm, fovy_deg). Returns an HxWx3 uint8 array."""
    with _LOCK:
        return _render(items, camera, size, table, robot_base)


def _render(items, camera, size, table, robot_base):
    spec = mujoco.MjSpec()
    spec.compiler.degree = False
    spec.visual.headlight.ambient = [0.32, 0.32, 0.32]
    spec.visual.headlight.diffuse = [0.35, 0.35, 0.35]
    spec.visual.headlight.specular = [0.05, 0.05, 0.05]
    spec.visual.global_.offwidth = size[0]
    spec.visual.global_.offheight = size[1]
    wb = spec.worldbody
    wb.add_light(pos=[0.3, -0.2, 1.4], dir=[0, 0.2, -1], diffuse=[0.45, 0.45, 0.45], specular=[0.1, 0.1, 0.1])
    tw, th = table[0] * MM / 2, table[1] * MM / 2
    wb.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[tw, th, 0.01], pos=[0.35, 0.3, -0.01],
                rgba=[0.62, 0.64, 0.66, 1])
    wb.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[3, 3, 0.1], pos=[0, 0, -0.75], rgba=[0.25, 0.25, 0.27, 1])
    if robot_base:
        wb.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.07, 0.06], pos=[0, 0, 0.06],
                    rgba=[0.9, 0.55, 0.1, 1])
    textures = {}
    for i, it in enumerate(items):
        x, y, z = it["pos"]
        body = wb.add_body(pos=[x * MM, y * MM, z * MM], euler=[0, 0, float(it.get("yaw", 0.0))])
        rgba = list(it.get("rgba", (0.7, 0.7, 0.7, 1)))
        if len(rgba) == 3:
            rgba.append(1.0)
        if it["kind"] == "box":
            g = dict(type=mujoco.mjtGeom.mjGEOM_BOX, size=[s * MM for s in it["size"]], rgba=rgba)
        else:
            g = dict(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[it["size"][0] * MM, it["size"][1] * MM], rgba=rgba)
        tex = it.get("texture")
        if tex:
            if tex not in textures:
                tname = f"tex{len(textures)}"
                spec.add_texture(name=tname, type=mujoco.mjtTexture.mjTEXTURE_2D, file=str(tex))
                mat = spec.add_material(name=tname + "m")
                mat.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = tname
                mat.texuniform = False
                mat.texrepeat = [1, 1]
                textures[tex] = tname + "m"
            g["material"] = textures[tex]
            g["rgba"] = [1, 1, 1, 1]
        body.add_geom(**g)
    pos, look, fovy = camera
    wb.add_camera(name="cam", pos=[p * MM for p in pos], quat=_cam_quat([p * MM for p in pos],
                                                                         [p * MM for p in look]).tolist(), fovy=fovy)
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    r = mujoco.Renderer(model, height=size[1], width=size[0])
    try:
        r.update_scene(data, camera="cam")
        img = r.render().copy()
    finally:
        r.close()
    return img


def save_png(img, path):
    Image.fromarray(img).save(path)


def similarity(a, b):
    """Grader score between two images: normalised correlation of 64x48 greyscale thumbnails, mapped to [0, 1]."""
    def prep(x):
        im = Image.fromarray(x) if isinstance(x, np.ndarray) else x
        g = np.asarray(im.convert("L").resize((64, 48)), float)
        g -= g.mean()
        return g / (np.linalg.norm(g) + 1e-9)
    return float(max(0.0, (prep(a) * prep(b)).sum()))
