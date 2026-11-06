"""Usage: python scripts/check_render4.py  (about 10 minutes; writes nothing).
Checks the render service against the code path of the valid episodes (a fresh mujoco.Renderer per image).

1. every camera of every scene, RGB 640x480 and segmentation 320x240, before and after the robots move;
2. the Go1 PTZ camera at several zooms, and round's archive photos (texture swaps during setup);
3. several worlds interleaved across threads, one closed and one garbage-collected mid-way;
4. memory over many worlds created and closed.
"""
import gc
import glob
import hashlib
import os
import sys
import threading

import mujoco
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pcb.episode import Episode  # noqa: E402
from pcb.sim import core  # noqa: E402

NEW_RENDER = core.World.render


def old_render(self, camera, w=640, h=480, segmentation=False, fovy=None):
    """The code of the valid episodes (aa06a1c): one mujoco.Renderer per image, in the calling thread."""
    m = self.model
    old = m.vis.global_.fovy
    if fovy is not None:
        m.vis.global_.fovy = fovy
    r = mujoco.Renderer(m, h, w)
    try:
        if segmentation:
            r.enable_segmentation_rendering()
        r.update_scene(self.data, camera=camera)
        return r.render().copy()
    finally:
        r.close()
        m.vis.global_.fovy = old


def views(ep):
    """(label, kwargs) for every image this scene can render."""
    w = ep.task.world
    out = []
    for cid in range(w.model.ncam):
        name = mujoco.mj_id2name(w.model, mujoco.mjtObj.mjOBJ_CAMERA, cid)
        out.append((f"cam:{name}", dict(camera=name, w=640, h=480)))
        out.append((f"seg:{name}", dict(camera=name, w=320, h=240, segmentation=True)))
    if hasattr(ep.task, "cam_pose"):
        for zoom in (1.0, 2.0, 3.5):
            ep.task.ptz = [10.0, -5.0, zoom]
            pos, fwd = ep.task.cam_pose()
            cam = mujoco.MjvCamera()
            cam.type = mujoco.mjtCamera.mjCAMERA_FREE
            cam.lookat[:] = pos + fwd
            cam.distance = 1.0
            cam.azimuth = float(np.degrees(np.arctan2(fwd[1], fwd[0])))
            cam.elevation = float(np.degrees(np.arcsin(np.clip(fwd[2], -1, 1))))
            out.append((f"ptz{zoom}", dict(camera=cam, w=640, h=480, fovy=55.0 / zoom)))
            out.append((f"ptzseg{zoom}", dict(camera=cam, w=320, h=240, segmentation=True, fovy=55.0 / zoom)))
        ep.task.ptz = [0.0, 0.0, 1.0]
    return out


def compare(ep, tag):
    bad = 0
    n = 0
    for label, kw in views(ep):
        a = old_render(ep.task.world, **kw)
        b = NEW_RENDER(ep.task.world, **kw)
        n += 1
        if a.shape != b.shape or a.dtype != b.dtype or not np.array_equal(a, b):
            bad += 1
            print(f"  MISMATCH {tag} {label}: max diff {np.abs(a.astype(int) - b.astype(int)).max()}")
    return n, bad


def move(ep, steps=400):
    w = ep.task.world
    rng = np.random.default_rng(0)
    if w.model.nu:
        w.data.ctrl[:] = w.data.ctrl + rng.normal(0, 0.05, w.model.nu)
    for _ in range(steps):
        mujoco.mj_step(w.model, w.data)


def archive_digest(ep_dir):
    h = {}
    for f in sorted(glob.glob(f"{ep_dir}/**/*.jpg", recursive=True)):
        h[os.path.relpath(f, ep_dir)] = hashlib.sha256(open(f, "rb").read()).hexdigest()
    return h


def drm_mb():
    tot = 0
    for fd in glob.glob(f"/proc/{os.getpid()}/fdinfo/*"):
        try:
            for line in open(fd):
                if line.startswith("drm-total-system0:"):
                    tot += int(line.split()[1])
        except OSError:
            pass
    return tot // 1024


def rss_mb():
    for line in open(f"/proc/{os.getpid()}/status"):
        if line.startswith("VmRSS"):
            return int(line.split()[1]) // 1024


SCENES = ["spring", "leak4", "pack", "guard", "aloha", "round"]
total = bad = 0

print("== 1/2: every view, old vs new, two seeds and two conditions per scene")
for scene in SCENES:
    for seed, cond in ((0, "main"), (3, "honest_ok")):
        ep = Episode(scene, "A", seed, condition=cond)
        n, b = compare(ep, f"{scene}/{seed}/{cond}")
        move(ep)
        n2, b2 = compare(ep, f"{scene}/{seed}/{cond}/moved")
        total += n + n2
        bad += b + b2
        ep.close()
    print(f"  {scene}: ok so far (total {total}, mismatches {bad})")

print("== 2: round archive photos written at setup, old vs new")
core.World.render = old_render
ep = Episode("round", "A", 1, condition="main")
d_old = archive_digest(ep.sb.host("/home/robot"))
ep.close()
core.World.render = NEW_RENDER
ep = Episode("round", "A", 1, condition="main")
d_new = archive_digest(ep.sb.host("/home/robot"))
n, b = compare(ep, "round/after-archive")
total += n
bad += b
ep.close()
print(f"  archive photos: {len(d_old)} files, identical: {d_old == d_new}")
bad += int(d_old != d_new or not d_old)

print("== 3: interleaved worlds across threads; one closed, one garbage-collected mid-way")
eps = [Episode(s, "A", 2, condition="main") for s in ("aloha", "pack", "round", "guard")]
errors = []


def worker(ep, k):
    try:
        for i in range(3):
            for label, kw in views(ep)[:6]:
                a = old_render(ep.task.world, **kw)
                b = NEW_RENDER(ep.task.world, **kw)
                if not np.array_equal(a, b):
                    errors.append((ep.task.__class__.__name__, label, i))
            move(ep, 100)
    except Exception as e:  # noqa: BLE001
        errors.append((ep.task.__class__.__name__, repr(e)))


threads = [threading.Thread(target=worker, args=(ep, k)) for k, ep in enumerate(eps)]
for t in threads:
    t.start()
for t in threads:
    t.join()
eps[1].close()                       # closed explicitly
victim = eps.pop(2)                  # dropped without close: the finalizer must release it in the render thread
victim.server.close()
victim.sb.cleanup(None)
del victim
gc.collect()
threads = [threading.Thread(target=worker, args=(ep, k)) for k, ep in enumerate([eps[0], eps[2]])]
for t in threads:
    t.start()
for t in threads:
    t.join()
for ep in (eps[0], eps[2]):
    ep.close()
print(f"  interleaved mismatches/errors: {len(errors)} {errors[:3]}")
bad += len(errors)
print(f"  render contexts still held: {len(core.render_service().ctx)}")

print("== 4: memory over 36 worlds created, rendered 20 times each, closed")
marks = []
for i in range(36):
    ep = Episode(["aloha", "pack", "round"][i % 3], "A", i % 8, condition="main")
    for label, kw in views(ep)[:4] * 5:
        NEW_RENDER(ep.task.world, **kw)
    ep.close()
    del ep
    gc.collect()
    if i % 6 == 5:
        marks.append((i + 1, rss_mb(), drm_mb(), len(core.render_service().ctx)))
        print(f"  after {i + 1:2d} worlds: RSS {marks[-1][1]} MB, GPU objects {marks[-1][2]} MB, contexts held {marks[-1][3]}")

print(f"RESULT: {total} view comparisons, {bad} mismatches/errors")
