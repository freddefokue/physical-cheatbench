"""Fiducial perception for v5: ArUco tags printed on item labels, found in rendered camera images.

What a real cell's vision service does with an RGB-D camera. It finds the tags in the colour image (OpenCV's ArUco
detector), reads the depth at each tag (here the depth along the camera ray through the tag's pixels, which is what a
depth image holds), and turns pixel and depth into a 3D position with the camera's calibration. Nothing is read from
the simulator's object poses: a tag that is occluded, too small or outside the image is not seen, and a position
carries the errors of corner detection and of the calibration (PLAN_v5.md, "Perception").
"""
import cv2
import mujoco
import numpy as np
from PIL import Image, ImageDraw

from pcb.sim.core import font

ARUCO = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
MARKER_FRAC = 0.66          # the marker's side as a fraction of the (square) label; the label's margin is its quiet zone


def tag_label(tag_id, lines, px=512, bg=(245, 245, 240), fg=(20, 20, 20), frac=MARKER_FRAC):
    """A square label: the ArUco tag centred (so its centre is the label's centre), text in the margins. frac: the
    marker's share of the label (larger on very small labels, which then carry little text)."""
    img = Image.new("RGB", (px, px), bg)
    side = int(px * frac)
    marker = Image.fromarray(cv2.aruco.generateImageMarker(ARUCO, int(tag_id), side)).convert("RGB")
    off = (px - side) // 2
    img.paste(marker, (off, off))
    d = ImageDraw.Draw(img)
    for k, line in enumerate(lines[:2]):
        s = int(off * 0.62)
        f = font(s)
        while d.textlength(line, font=f) > px * 0.94 and s > 8:
            s -= 2
            f = font(s)
        y = (off - s) / 2 if k == 0 else px - off + (off - s) / 2
        d.text(((px - d.textlength(line, font=f)) / 2, y), line, font=f, fill=fg)
    return img


class Camera:
    """A calibrated camera of the cell: intrinsics from its field of view, extrinsics from its mounting pose."""

    def __init__(self, world, name, width, height, bias=(0.0, 0.0, 0.0)):
        self.w, self.name, self.W, self.H = world, name, width, height
        self.cid = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_CAMERA, name)
        fovy = np.radians(world.model.cam_fovy[self.cid])
        self.f = (height / 2) / np.tan(fovy / 2)
        self.bias = np.asarray(bias, float)         # extrinsic calibration error (metres), as on a real cell

    def ray(self, u, v):
        """World origin and direction of the ray through pixel (u, v) (v down; MuJoCo cameras look along -z)."""
        d = self.w.data
        R = d.cam_xmat[self.cid].reshape(3, 3)
        dc = np.array([(u - self.W / 2) / self.f, -(v - self.H / 2) / self.f, -1.0])
        dw = R @ dc
        return d.cam_xpos[self.cid].copy(), dw / np.linalg.norm(dw)

    def depth_point(self, u, v):
        """The 3D point a depth image gives at pixel (u, v): the first surface along the ray."""
        o, dw = self.ray(u, v)
        gid = np.array([-1], dtype=np.int32)
        dist = mujoco.mj_ray(self.w.model, self.w.data, o, dw, None, 1, -1, gid)
        if dist < 0:
            return None
        return o + dist * dw + self.bias

    def plane_point(self, u, v, z):
        """Where the ray through (u, v) meets the horizontal plane at height z."""
        o, dw = self.ray(u, v)
        if abs(dw[2]) < 1e-6:
            return None
        t = (z - o[2]) / dw[2]
        return None if t <= 0 else o + t * dw + self.bias


class Vision:
    """registry: tag id -> item name. min_px: the smallest marker side (pixels) the detector accepts.

    OpenCV's default minimum marker perimeter is 3 % of the image's larger side, which in a high-resolution frame
    drops small tags whatever their size in pixels; the service sets it to 1 % and filters by min_px instead."""

    def __init__(self, world, cameras, registry, min_px=10.0):
        self.w = world
        self.cams = cameras                          # name -> Camera
        self.registry = dict(registry)
        self.min_px = min_px
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.minMarkerPerimeterRate = 0.01
        self.detector = cv2.aruco.ArucoDetector(ARUCO, params)

    def detect(self, name):
        """Detections in one camera: item -> {pos (top-centre of the tag), yaw, pixels, camera}."""
        cam = self.cams[name]
        img = self.w.render(name, cam.W, cam.H)
        gray = cv2.cvtColor(np.ascontiguousarray(img), cv2.COLOR_RGB2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        out = {}
        if ids is None:
            return out
        for c, i in zip(corners, ids.ravel()):
            item = self.registry.get(int(i))
            if item is None:
                continue
            q = c.reshape(4, 2)
            side = float(np.mean([np.linalg.norm(q[k] - q[(k + 1) % 4]) for k in range(4)]))
            if side < self.min_px:
                continue
            u, v = q.mean(axis=0)
            p = cam.depth_point(u, v)
            if p is None:
                continue
            # the tag's top edge (corner 0 -> corner 1) on the label plane gives the item's yaw
            a, b = cam.plane_point(*q[0], p[2]), cam.plane_point(*q[1], p[2])
            if a is None or b is None:
                continue
            yaw = float(np.arctan2(b[1] - a[1], b[0] - a[0]))
            if item not in out or side > out[item]["pixels"]:
                out[item] = {"pos": p, "yaw": yaw, "pixels": side, "camera": name}
        return out

    def perceive(self):
        """Merge the cameras: each item from the camera that sees its tag largest."""
        seen = {}
        for name in self.cams:
            for item, d in self.detect(name).items():
                if item not in seen or d["pixels"] > seen[item]["pixels"]:
                    seen[item] = d
        return seen
