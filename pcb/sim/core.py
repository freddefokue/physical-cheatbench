"""World composition, physics stepping, rendering and textured props.

A World is compiled once per episode from an MjSpec. Robots are attached from MuJoCo Menagerie with a name prefix.
Everything the agent can see is rendered from cameras placed where a real cell would mount them.
"""
import io
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

MENAGERIE = Path(os.environ.get("PCB_MENAGERIE", Path.home() / ".cache/pcb/mujoco_menagerie"))
PLAYGROUND = Path(os.environ.get("PCB_PLAYGROUND", Path.home() / ".cache/pcb/playground"))
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

G = mujoco.mjtGeom
OBJ = mujoco.mjtObj


def font(px, bold=True):
    for p in (FONT_PATHS if bold else FONT_PATHS[::-1]):
        if os.path.exists(p):
            return ImageFont.truetype(p, px)
    return ImageFont.load_default()


def quat_z(yaw):
    return [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]


def rot_to_quat(R):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, float).flatten())
    return q


def png_bytes(arr_or_img):
    img = arr_or_img if isinstance(arr_or_img, Image.Image) else Image.fromarray(arr_or_img)
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def jpeg_bytes(arr, quality=88):
    b = io.BytesIO()
    Image.fromarray(arr).save(b, format="JPEG", quality=quality)
    return b.getvalue()


def label_image(lines, w=512, h=256, bg=(245, 245, 240), fg=(20, 20, 20), border=(30, 30, 30), sizes=None):
    """A printed label: one or more text lines centred on a white card with a dark border."""
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([3, 3, w - 4, h - 4], outline=border, width=6)
    sizes = sizes or [int(h * 0.30)] + [int(h * 0.17)] * (len(lines) - 1)
    total = sum(s * 1.15 for s in sizes)
    y = (h - total) / 2
    for line, s in zip(lines, sizes):
        f = font(s)
        while d.textlength(line, font=f) > w * 0.92 and s > 8:
            s -= 2
            f = font(s)
        d.text(((w - d.textlength(line, font=f)) / 2, y), line, font=f, fill=fg)
        y += s * 1.15
    return img


class Builder:
    """Thin helpers over MjSpec for scene construction. Textures are kept in memory (spec.assets)."""

    def __init__(self, timestep=0.002, offscreen=(1280, 960)):
        s = self.spec = mujoco.MjSpec()
        s.option.timestep = timestep
        s.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
        s.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        s.option.impratio = 10
        s.visual.global_.offwidth, s.visual.global_.offheight = offscreen
        s.visual.quality.shadowsize = 4096
        s.visual.headlight.ambient = [0.25, 0.25, 0.25]
        s.visual.headlight.diffuse = [0.35, 0.35, 0.35]
        s.stat.extent = 2.0
        self.assets = {}
        self.n = 0
        self.textures = set()

    # ---- assets -------------------------------------------------------------------------------------------------
    def texture(self, name, img):
        if name in self.textures:
            return name
        fname = f"{name}.png"
        self.assets[fname] = png_bytes(img)
        self.spec.add_texture(name=name, type=mujoco.mjtTexture.mjTEXTURE_2D, file=fname)
        self.textures.add(name)
        return name

    def material(self, name, rgba=(1, 1, 1, 1), texture=None, specular=0.3, shininess=0.3, reflectance=0.0,
                 texrepeat=None, texuniform=False):
        kw = dict(name=name, rgba=list(rgba), specular=specular, shininess=shininess, reflectance=reflectance)
        m = self.spec.add_material(**kw)
        if texture:
            m.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = texture
            if texrepeat:
                m.texrepeat = list(texrepeat)
            m.texuniform = texuniform
        return name

    def quad_mesh(self, name, w, h):
        """A w x h rectangle in its local xy plane, facing +z, with texture coordinates (for labels, dials, signs)."""
        a, b = w / 2, h / 2
        verts = [-a, -b, 0, a, -b, 0, a, b, 0, -a, b, 0]
        self.spec.add_mesh(name=name, uservert=verts, userface=[0, 1, 2, 0, 2, 3],
                           usertexcoord=[0, 1, 1, 1, 1, 0, 0, 0], inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
        return name

    def uid(self, base):
        self.n += 1
        return f"{base}_{self.n}"

    # ---- props ------------------------------------------------------------------------------------------------
    def body(self, name, pos, quat=(1, 0, 0, 0), parent=None, free=False, mocap=False):
        parent = parent if parent is not None else self.spec.worldbody
        b = parent.add_body(name=name, pos=list(pos), quat=list(quat), mocap=mocap)
        if free:
            b.add_freejoint(name=f"{name}_free")
        return b

    @staticmethod
    def box(body, name, half, pos=(0, 0, 0), rgba=(0.6, 0.6, 0.6, 1), mass=None, material=None, friction=None,
            contype=1, conaffinity=1, quat=(1, 0, 0, 0), group=0, condim=None):
        kw = dict(name=name, type=G.mjGEOM_BOX, size=list(half), pos=list(pos), rgba=list(rgba), quat=list(quat),
                  contype=contype, conaffinity=conaffinity, group=group)
        if mass is not None:
            kw["mass"] = mass
        if material:
            kw["material"] = material
        if friction is not None:
            kw["friction"] = list(friction)
        if condim is not None:
            kw["condim"] = condim
        return body.add_geom(**kw)

    @staticmethod
    def cyl(body, name, r, half_h, pos=(0, 0, 0), rgba=(0.6, 0.6, 0.6, 1), mass=None, material=None,
            friction=None, quat=(1, 0, 0, 0), contype=1, conaffinity=1, group=0, condim=None):
        kw = dict(name=name, type=G.mjGEOM_CYLINDER, size=[r, half_h, 0], pos=list(pos), rgba=list(rgba),
                  quat=list(quat), contype=contype, conaffinity=conaffinity, group=group)
        if mass is not None:
            kw["mass"] = mass
        if material:
            kw["material"] = material
        if friction is not None:
            kw["friction"] = list(friction)
        if condim is not None:
            kw["condim"] = condim
        return body.add_geom(**kw)

    def decal(self, body, name, img, w, h, pos, quat=(1, 0, 0, 0)):
        """A printed label/sign/dial face (no collision) on a body: w x h metres, facing the body's local +z
        unless rotated by quat."""
        tex = self.texture(f"tex_{name}", img)
        mat = self.material(f"mat_{name}", texture=tex, specular=0.05, shininess=0.0)
        mesh = self.quad_mesh(f"mesh_{name}", w, h)
        return body.add_geom(name=name, type=G.mjGEOM_MESH, meshname=mesh, material=mat, pos=list(pos),
                             quat=list(quat), contype=0, conaffinity=0, mass=0, group=1)

    def light(self, pos, direction=(0, 0, -1), diffuse=0.6, castshadow=True, name=None):
        return self.spec.worldbody.add_light(name=name or self.uid("light"), pos=list(pos), dir=list(direction),
                                             diffuse=[diffuse] * 3, specular=[0.1] * 3, castshadow=castshadow)

    def camera(self, name, pos, target, fovy=55.0, parent=None, up=(0, 0, 1)):
        """Camera at pos looking at target (MuJoCo cameras look along their local -z, with +y up)."""
        pos, target = np.asarray(pos, float), np.asarray(target, float)
        fwd = target - pos
        fwd /= np.linalg.norm(fwd)
        upv = np.asarray(up, float)
        if abs(np.dot(fwd, upv)) > 0.99:
            upv = np.array([0.0, 1.0, 0.0])
        x = np.cross(fwd, upv)
        x /= np.linalg.norm(x)
        y = np.cross(x, fwd)
        parent = parent if parent is not None else self.spec.worldbody
        return parent.add_camera(name=name, pos=list(pos), xyaxes=list(x) + list(y), fovy=fovy)

    def floor(self, size=6.0, rgb1=(0.42, 0.42, 0.40), rgb2=(0.38, 0.38, 0.37)):
        self.spec.add_texture(name="floor_tex", type=mujoco.mjtTexture.mjTEXTURE_2D,
                              builtin=mujoco.mjtBuiltin.mjBUILTIN_CHECKER, rgb1=list(rgb1), rgb2=list(rgb2),
                              width=512, height=512, mark=mujoco.mjtMark.mjMARK_EDGE, markrgb=[0.3, 0.3, 0.3])
        self.material("floor_mat", texture="floor_tex", texrepeat=(8, 8), texuniform=True, specular=0.1)
        return self.spec.worldbody.add_geom(name="floor", type=G.mjGEOM_PLANE, size=[size, size, 0.1],
                                            material="floor_mat", friction=[0.9, 0.005, 0.0001])

    def attach_robot(self, rel_file, prefix, pos, quat=(1, 0, 0, 0), gravcomp=True, child=None, child_site=None,
                     child_prefix=None, edit=None):
        """Attach a Menagerie robot at pos/quat. Optional child (e.g. a gripper) attached at child_site first.
        edit(spec) may modify the robot spec before attachment (e.g. add a tool or a TCP site)."""
        rs = mujoco.MjSpec.from_file(str(MENAGERIE / rel_file))
        if child:
            cs = mujoco.MjSpec.from_file(str(MENAGERIE / child))
            rs.attach(cs, site=rs.site(child_site), prefix=child_prefix or "g/")
        if edit:
            edit(rs)
        if gravcomp:
            for b in rs.bodies:
                if b.name != "world":
                    b.gravcomp = 1.0
        frame = self.spec.worldbody.add_frame(pos=list(pos), quat=list(quat))
        self.spec.attach(rs, frame=frame, prefix=prefix)
        return rs

    def compile(self):
        self.spec.assets = dict(self.assets)
        return World(self.spec)


class _RenderService:
    """One thread per process owns every GL context. Creating and freeing a mujoco.Renderer per image leaks GPU-driver
    memory (about 0.3-1.3 MB per image, measured on 6 Nov 2026), and the cell controller serves each command on a new
    thread; so renders are queued to this thread, which keeps one renderer per (world, size, kind)."""

    def __init__(self):
        import queue
        import threading
        self.q = queue.Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="pcb-render")
        self.thread.start()

    def _loop(self):
        while True:
            fn, args, ev, box = self.q.get()
            try:
                box["out"] = fn(*args)
            except Exception as e:  # noqa: BLE001  (re-raised in the caller's thread)
                box["err"] = e
            ev.set()

    def call(self, fn, *args):
        import threading
        if threading.current_thread() is self.thread:
            return fn(*args)
        ev, box = threading.Event(), {}
        self.q.put((fn, args, ev, box))
        ev.wait()
        if "err" in box:
            raise box["err"]
        return box["out"]


_RENDER = None


def render_service():
    global _RENDER
    if _RENDER is None:
        _RENDER = _RenderService()
    return _RENDER


class World:
    def __init__(self, spec):
        self.spec = spec
        self.model = spec.compile()
        self.data = mujoco.MjData(self.model)
        self.hooks = []          # called before every physics step (controllers, sensors)
        self.extra_time = 0.0     # modelled durations not simulated step by step (e.g. a test cycle at rest)
        mujoco.mj_forward(self.model, self.data)

    # ---- names and ids ----------------------------------------------------------------------------------------
    def id(self, objtype, name):
        i = mujoco.mj_name2id(self.model, objtype, name)
        if i < 0:
            raise KeyError(f"{objtype} {name!r} not in model")
        return i

    def body_id(self, name):
        return self.id(OBJ.mjOBJ_BODY, name)

    def geom_id(self, name):
        return self.id(OBJ.mjOBJ_GEOM, name)

    def joint_qadr(self, name):
        return self.model.jnt_qposadr[self.id(OBJ.mjOBJ_JOINT, name)]

    def joint_dadr(self, name):
        return self.model.jnt_dofadr[self.id(OBJ.mjOBJ_JOINT, name)]

    # ---- state ------------------------------------------------------------------------------------------------
    @property
    def time(self):
        return self.data.time + self.extra_time

    def step(self, n=1):
        m, d = self.model, self.data
        for _ in range(n):
            for h in self.hooks:
                h()
            mujoco.mj_step(m, d)

    def settle(self, secs):
        self.step(max(1, int(round(secs / self.model.opt.timestep))))

    def body_pos(self, name):
        return self.data.xpos[self.body_id(name)].copy()

    def body_mat(self, name):
        return self.data.xmat[self.body_id(name)].reshape(3, 3).copy()

    def body_yaw(self, name):
        R = self.body_mat(name)
        return float(np.arctan2(R[1, 0], R[0, 0]))

    def set_free_pose(self, body, pos, quat=(1, 0, 0, 0)):
        jid = self.model.body_jntadr[self.body_id(body)]
        a = self.model.jnt_qposadr[jid]
        self.data.qpos[a:a + 3] = pos
        self.data.qpos[a + 3:a + 7] = quat
        v = self.model.jnt_dofadr[jid]
        self.data.qvel[v:v + 6] = 0
        mujoco.mj_forward(self.model, self.data)

    def contacts(self):
        """List of (geom1 name, geom2 name, normal force N) for current contacts."""
        out = []
        f6 = np.zeros(6)
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            mujoco.mj_contactForce(self.model, self.data, i, f6)
            out.append((self.model.geom(c.geom1).name, self.model.geom(c.geom2).name, abs(f6[0])))
        return out

    def bodies_in_contact(self, body_a, body_b):
        ia, ib = self.body_id(body_a), self.body_id(body_b)
        gb = self.model.geom_bodyid
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            b1, b2 = gb[c.geom1], gb[c.geom2]
            if {b1, b2} == {ia, ib}:
                return True
        return False

    # ---- rendering --------------------------------------------------------------------------------------------
    def _renderer(self, w, h, segmentation):
        """Called in the render thread only: a cached renderer for this world, size and kind."""
        cache = self.__dict__.setdefault("_renderers", {})
        key = (w, h, bool(segmentation))
        r = cache.get(key)
        if r is None:
            r = mujoco.Renderer(self.model, h, w)
            if segmentation:
                r.enable_segmentation_rendering()
            cache[key] = r
        return r

    def _render_in_thread(self, camera, w, h, segmentation, fovy=None):
        r = self._renderer(w, h, segmentation)
        old = self.model.vis.global_.fovy
        if fovy is not None:
            self.model.vis.global_.fovy = fovy
        try:
            r.update_scene(self.data, camera=camera)
            return r.render().copy()
        finally:
            self.model.vis.global_.fovy = old

    def render(self, camera, w=640, h=480, segmentation=False, fovy=None):
        """camera: a camera name or an MjvCamera; fovy applies to a free MjvCamera (zoom)."""
        return render_service().call(self._render_in_thread, camera, w, h, segmentation, fovy)

    def close_renderers(self):
        def _close():
            for r in self.__dict__.get("_renderers", {}).values():
                try:
                    r.close()
                except Exception:  # noqa: BLE001
                    pass
            self.__dict__["_renderers"] = {}
        render_service().call(_close)

    def visible_geoms(self, camera, w=320, h=240):
        """Pixel counts per geom id visible from a camera (from a segmentation render)."""
        seg = self.render(camera, w, h, segmentation=True)
        ids, types = seg[..., 0], seg[..., 1]
        mask = types == int(OBJ.mjOBJ_GEOM)
        vals, counts = np.unique(ids[mask], return_counts=True)
        scale = (640 * 480) / (w * h)                      # report in pixels of a 640x480 frame
        return {int(v): int(c * scale) for v, c in zip(vals, counts)}
