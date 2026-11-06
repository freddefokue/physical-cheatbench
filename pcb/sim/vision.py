"""Cameras and perception services that work from rendered images, never from simulator state.

- capture(): an RGB frame with sensor noise, saved as JPEG (what a RealSense-class colour stream gives);
- detect(): a fiducial/label detector. An object is detected only if its tag is visible in a segmentation render of
  the same camera (enough unoccluded pixels); its reported pose is the true pose plus the camera's extrinsic
  calibration error and pixel noise. A label's text is reported only if the label is large enough in the image to be
  read. This is the behaviour of an AprilTag + OCR pipeline on a real cell: occluded, out-of-view or tiny things are
  not seen, and a miscalibrated camera reports systematically shifted positions.
"""
import numpy as np

from .core import jpeg_bytes


def capture(world, camera, w=640, h=480, rng=None, noise=2.5):
    img = world.render(camera, w, h).astype(np.float32)
    if rng is not None and noise:
        img += rng.normal(0, noise, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    return img, jpeg_bytes(img)


class Detector:
    """tags: name -> dict(body=..., tag_geoms=[geom names], label_geoms=[geom names], text=..., min_px=...)."""

    def __init__(self, world, tags, rng, calib_bias=None, pos_noise=0.0008, min_px=60, read_px=900):
        self.w = world
        self.rng = rng
        self.tags = {}
        for name, t in tags.items():
            self.tags[name] = dict(t)
            self.tags[name]["tag_ids"] = [world.geom_id(g) for g in t.get("tag_geoms", [])]
            self.tags[name]["label_ids"] = [world.geom_id(g) for g in t.get("label_geoms", [])]
        self.calib_bias = {} if calib_bias is None else calib_bias      # camera -> xyz bias in metres
        self.pos_noise = pos_noise
        self.min_px = min_px
        self.read_px = read_px

    def detect(self, camera):
        px = self.w.visible_geoms(camera)
        out = []
        bias = np.asarray(self.calib_bias.get(camera, (0, 0, 0)), float)
        for name, t in self.tags.items():
            n_tag = sum(px.get(g, 0) for g in t["tag_ids"])
            if n_tag < t.get("min_px", self.min_px):
                continue
            pos = self.w.body_pos(t["body"]) + bias + self.rng.normal(0, self.pos_noise, 3)
            yaw = self.w.body_yaw(t["body"]) + self.rng.normal(0, 0.01)
            n_lab = sum(px.get(g, 0) for g in t["label_ids"])
            out.append({"id": name, "pos": pos, "yaw": yaw, "pixels": n_tag,
                        "text": t.get("text") if (not t["label_ids"] or n_lab >= self.read_px) else None})
        return out, px
