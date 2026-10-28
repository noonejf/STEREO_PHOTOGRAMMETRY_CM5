"""Render a photograph from the painted buffers.

Only Model 1 sees pixels. The branch scorer sees a binary mask and nothing
else, so this module exists entirely for the segmenter, and its job is to
land inside the brightness and texture statistics measured off the real
archive rather than to look pretty.

Both families from the archive are reproduced:

    lab      grey table, one hard light, strong gradient, dust, cast shadow,
             pale braided cord
    orbital  near-black, no fill, no shadow, thin bright cord

The cord is shaded as a cylinder using the lateral buffer from `rasterize`,
which is what gives it a lit side, a shaded side and a specular line instead
of a flat painted stroke.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import config


def _lowfreq(shape, rng, octaves=3, seed_scale=18):
    """Smooth random field in 0..1, for illumination and table texture."""
    h, w = shape
    out = np.zeros((h, w), np.float32)
    amp = 1.0
    total = 0.0
    for o in range(octaves):
        s = max(2, seed_scale // (2 ** o))
        small = rng.normal(0, 1, (s, max(2, int(s * w / max(h, 1))))).astype(np.float32)
        out += amp * cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= 0.5
    out /= max(total, 1e-9)
    lo, hi = out.min(), out.max()
    return (out - lo) / max(hi - lo, 1e-9)


def _background(size, ap: config.Appearance, rng):
    w, h = size
    bg_mean = rng.uniform(*ap.bg_mean)
    bg_std = rng.uniform(*ap.bg_std)

    # one hard light: a broad gradient across the frame
    gx, gy = rng.normal(0, 1, 2)
    n = np.hypot(gx, gy) or 1.0
    xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    ys = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    ramp = (gx / n) * xs + (gy / n) * ys
    ramp = (ramp - ramp.min()) / max(np.ptp(ramp), 1e-9)
    strength = rng.uniform(*ap.gradient_strength)

    base = bg_mean * (1.0 - strength + strength * (0.35 + 1.3 * ramp))

    # Table texture. Most of the measured background std is the gradient
    # above, not texture: a real table is smooth. Giving texture the whole
    # std produced a camouflage pattern nothing like the captures, so it gets
    # a small share of it at a fine scale.
    tex = _lowfreq((h, w), rng, octaves=2, seed_scale=int(rng.integers(60, 160)))
    base = base + (tex - 0.5) * bg_std * 0.28

    # dust and specks
    n_specks = int(rng.uniform(*ap.specks) * (w * h) / 1e6)
    for _ in range(n_specks):
        x, y = rng.integers(0, w), rng.integers(0, h)
        r = int(rng.integers(1, 4))
        val = rng.uniform(-1, 1) * bg_std * 2.0
        cv2.circle(base, (int(x), int(y)), r, float(val), -1)

    return base.astype(np.float32), ramp.astype(np.float32), np.array([gx / n, gy / n])


def _cord(buffers, ap: config.Appearance, rng, light_dir, radius: float):
    """Shade the cord as a lit cylinder with an optional braid texture."""
    u = buffers["u"]
    s = buffers["s"]
    cov = buffers["cov"]

    wire_grey = rng.uniform(*ap.wire_grey)

    # cylinder normal across the wire: n = (u, sqrt(1 - u^2)) in the
    # cross-section frame. Lambert against a light tilted by phi.
    phi = rng.uniform(-1.0, 1.0)
    lam = np.clip(np.cos(np.arcsin(np.clip(u, -1, 1)) - phi), 0.0, 1.0)
    shade = 0.45 + 0.55 * lam

    # specular line, narrow and offset to the lit side
    spec_pos = np.sin(phi)
    spec = np.exp(-((u - spec_pos) ** 2) / (2 * rng.uniform(0.04, 0.16) ** 2))
    shade = shade + spec * rng.uniform(0.10, 0.45)

    # braid: the real cord is twisted, so brightness ripples along its length
    if rng.random() < 0.75:
        # Period scales with the cord radius. Fixed in pixels it beaded a
        # thin cord into a dotted line.
        period = rng.uniform(1.2, 3.4) * max(4.0, radius)
        depth_t = rng.uniform(0.05, 0.18)
        shade = shade * (1.0 + depth_t * np.sin(2 * np.pi * s / period))

    # Normalise so the mean brightness over the cord is exactly wire_grey.
    # Without this the cylinder shading, whose mean is about 0.78, and the
    # scene ramp drag the rendered cord to roughly three quarters of the
    # sampled value, and the measured contrast against the archive came out
    # 29 percent low.
    lit = cov > 0.5
    m = float(shade[lit].mean()) if lit.any() else 1.0
    cord = wire_grey * shade / max(m, 1e-6)
    return cord.astype(np.float32), wire_grey


def _shadow(cov, ap: config.Appearance, rng, light_dir):
    """Soft cast shadow, offset away from the light. Orbital gets none."""
    strength = rng.uniform(*ap.shadow_strength)
    if strength < 0.02:
        return None
    off = rng.uniform(6, 34)
    M = np.float32([[1, 0, -light_dir[0] * off], [0, 1, -light_dir[1] * off]])
    sh = cv2.warpAffine(cov, M, (cov.shape[1], cov.shape[0]))
    sh = cv2.GaussianBlur(sh, (0, 0), rng.uniform(4, 14))
    return (1.0 - strength * np.clip(sh, 0, 1)).astype(np.float32)


def render(buffers, size, family: str, rng, radius: float = 10.0,
           jpeg_quality: int | None = None):
    """Compose the photograph. Returns a BGR uint8 image and a note dict."""
    ap = config.FAMILIES[family]
    w, h = size
    cov = buffers["cov"]

    base, ramp, light_dir = _background(size, ap, rng)
    cord, wire_grey = _cord(buffers, ap, rng, light_dir, radius)

    img = base.copy()
    sh = _shadow(cov, ap, rng, light_dir)
    if sh is not None:
        img = img * sh

    # the cord also follows the scene illumination gradient
    cord = cord * (0.70 + 0.55 * ramp)
    img = img * (1.0 - cov) + cord * cov

    # colour: the lab cord is cream against a neutral table
    bgr = np.repeat(img[:, :, None], 3, axis=2)
    tint = np.array(ap.wire_tint, dtype=np.float32)
    bgr = bgr * (1.0 - cov[:, :, None]) + bgr * cov[:, :, None] * tint[None, None, :]

    # vignette
    vg = rng.uniform(*ap.vignette)
    if vg > 0.01:
        xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
        ys = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
        rad = np.sqrt(xs ** 2 + ys ** 2) / np.sqrt(2)
        bgr = bgr * (1.0 - vg * rad ** 2)[:, :, None]

    # optics and sensor, in the order the real chain applies them
    blur = rng.uniform(0.4, 2.4)
    bgr = cv2.GaussianBlur(bgr, (0, 0), blur)
    read_noise = rng.uniform(1.5, 7.0)
    shot = np.sqrt(np.clip(bgr, 0, None)) * rng.uniform(0.15, 0.6)
    bgr = bgr + rng.normal(0, 1, bgr.shape).astype(np.float32) * (read_noise + shot)

    out = np.clip(bgr, 0, 255).astype(np.uint8)

    notes = {
        "family": family,
        "wire_grey": round(float(wire_grey), 1),
        "blur_sigma": round(float(blur), 2),
        "read_noise": round(float(read_noise), 2),
        "vignette": round(float(vg), 3),
        "has_shadow": sh is not None,
    }

    if jpeg_quality:
        ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
        if ok:
            out = cv2.imdecode(enc, cv2.IMREAD_COLOR)
            notes["jpeg_quality"] = int(jpeg_quality)

    return out, notes
