"""Turn a centreline into a mask, a depth buffer and a soft coverage map.

The mask is what the path model trains on, so its *statistics* have to match
what the top-hat segmenter actually produces in a dark room: a ragged
boundary, occasional pinholes, and sometimes a clean break where the
illumination fell away. A generator that emits crisp vector strokes would
train the branch scorer on a world that does not exist.

The depth buffer exists so the photo renderer can occlude correctly at a
self-crossing: the nearer strand passes over, as it does in the real captures.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import config

#: Supersampling factor used while painting. Painting at 2x and downsampling
#: gives an anti-aliased coverage map, which is what makes a one-pixel-wide
#: wire look like a wire instead of a staircase.
SS = 2


#: Hard bounds on the painted radius, in output pixels. The lower bound is
#: the real hard case: at 3.5 m the flight tether projects to 1.47 px, so a
#: thin wire is not a degenerate sample, it is the one that matters. The upper
#: bound keeps the 1/depth scaling from inflating an already-thick wire past
#: anything the archive contains (measured maximum 30 px).
RADIUS_LIMITS = (2.5, 34.0)


def radii_along(depth: np.ndarray, base_radius: float) -> np.ndarray:
    """Radius at each sample, scaling as 1/depth.

    This is the thickness-continuity signal the tracker scores on, so it has
    to vary the way perspective makes it vary and not randomly.
    """
    r = base_radius / np.clip(depth, 1e-3, None)
    return np.clip(r, *RADIUS_LIMITS)


def radius_for_foreground(xy: np.ndarray, size, fg_target: float) -> float:
    """Pick the base radius that lands the mask on a target foreground share.

    Foreground fraction is the statistic that has to match the archive: it
    sets the class balance Model 1 trains against, and it is what the
    tracker's own rescaling keys off. Radius and arc length cannot both be
    sampled freely, since the product of the two is the area, so arc length
    is set by the shape and the radius follows from it here.

    A long, dense shape therefore comes out thin. That is correct rather than
    a defect: the archive contains no dense tangles, so for those shapes the
    radius hits its floor and the realised foreground fraction runs above the
    measured band. `generate.py` records the realised value per sample.
    """
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    arc = float(seg.sum())
    if arc < 1.0:
        return RADIUS_LIMITS[0]
    w, h = size
    r = fg_target * w * h / (2.0 * arc)
    return float(np.clip(r, *RADIUS_LIMITS))


def paint(xy: np.ndarray, depth: np.ndarray, size, base_radius: float):
    """Paint the wire.

    Returns ``(coverage, zbuf, sbuf, ubuf)``:

    ``coverage``  float 0..1, anti-aliased by supersampling
    ``zbuf``      depth of the nearest strand, ``+inf`` on background
    ``sbuf``      arc length along the wire, which the braid texture reads
    ``ubuf``      lateral position across the wire in -1..1, which is what
                  lets the photo renderer shade the cord as a cylinder with a
                  lit side and a shaded side instead of a flat stroke

    The last two exist only for appearance. The mask does not need them, but
    without them a rendered cord does not look like the real captures, and
    Model 1 is the one model here that does see pixels.
    """
    w, h = size
    cov = np.zeros((h * SS, w * SS), dtype=np.float32)
    zbuf = np.full((h * SS, w * SS), np.inf, dtype=np.float32)
    sbuf = np.zeros((h * SS, w * SS), dtype=np.float32)
    ubuf = np.zeros((h * SS, w * SS), dtype=np.float32)

    r = radii_along(depth, base_radius) * SS
    pts = (xy * SS).astype(np.int32)

    # tangent and its perpendicular at every sample
    tang = np.gradient(xy, axis=0)
    tn = np.linalg.norm(tang, axis=1, keepdims=True)
    tang = tang / np.maximum(tn, 1e-9)
    perp = np.stack([-tang[:, 1], tang[:, 0]], axis=1)

    # arc length along the curve, in output pixels
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])

    # Painter's algorithm, far to near, so the nearest strand wins the z test.
    order = np.argsort(-depth)
    for i in order:
        x, y = int(pts[i, 0]), int(pts[i, 1])
        ri = int(round(r[i]))
        if ri < 1 or x < -ri or y < -ri or x > w * SS + ri or y > h * SS + ri:
            continue
        # stamp into a local window rather than the whole frame
        x0, x1 = max(0, x - ri), min(w * SS, x + ri + 1)
        y0, y1 = max(0, y - ri), min(h * SS, y + ri + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.ogrid[y0:y1, x0:x1]
        dx = xx - x
        dy = yy - y
        inside = dx * dx + dy * dy <= ri * ri
        win_z = zbuf[y0:y1, x0:x1]
        closer = inside & (depth[i] < win_z)
        win_z[closer] = depth[i]
        cov[y0:y1, x0:x1][inside] = 1.0
        # lateral coordinate, only where this strand is the visible one
        lat = (dx * perp[i, 0] + dy * perp[i, 1]) / max(ri, 1)
        sb = sbuf[y0:y1, x0:x1]
        ub = ubuf[y0:y1, x0:x1]
        sb[closer] = arc[i]
        ub[closer] = np.clip(lat, -1.0, 1.0)[closer]

    cov = cv2.resize(cov, (w, h), interpolation=cv2.INTER_AREA)
    zbuf = cv2.resize(zbuf, (w, h), interpolation=cv2.INTER_NEAREST)
    sbuf = cv2.resize(sbuf, (w, h), interpolation=cv2.INTER_NEAREST)
    ubuf = cv2.resize(ubuf, (w, h), interpolation=cv2.INTER_NEAREST)
    return cov, zbuf, sbuf, ubuf


def degrade(cov: np.ndarray, rng, strength: float = 1.0, radius: float = 10.0):
    """Apply the three defects real masks have.

    ``strength`` scales all three together, so a caller can ask for a clean
    mask (0.0) or a bad one (1.0) without knowing the individual knobs.

    Every defect is sized relative to ``radius``, not in absolute pixels.
    That matters: a 10 px break is a nick in a 30 px cord and a complete
    severance of a 3 px one. Sizing them absolutely fragmented thin wires
    into dozens of components, where the real archive has one connected
    component in 25 of its 26 masks.
    """
    h, w = cov.shape
    mask = (cov > 0.5).astype(np.uint8)
    notes = {}
    radius = max(float(radius), 1.0)

    # 1. ragged boundary: displace the edge with low-frequency noise
    amp = min(rng.uniform(*config.EDGE_RAGGEDNESS), 0.22 * radius) * strength
    if amp > 0.05:
        small = rng.normal(0, 1, (max(2, h // 24), max(2, w // 24))).astype(np.float32)
        field = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
        field = cv2.GaussianBlur(field, (0, 0), 3.0)
        dt_in = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        dt_out = cv2.distanceTransform(1 - mask, cv2.DIST_L2, 5)
        signed = dt_in - dt_out
        mask = ((signed + field * amp) > 0).astype(np.uint8)
    notes["edge_amp"] = round(float(amp), 2)

    # 2. pinholes inside the wire, sized as a fraction of its radius
    rate = rng.uniform(*config.PINHOLE_RATE) * strength
    fg = np.flatnonzero(mask.ravel())
    if rate > 0 and radius >= 4.0 and len(fg):
        k = int(len(fg) * rate)
        if k:
            hit = rng.choice(fg, size=k, replace=False)
            holes = np.zeros(mask.size, np.uint8)
            holes[hit] = 1
            holes = holes.reshape(mask.shape)
            # Fixed small kernel. Scaling it with the radius turned speckle
            # into bites that severed the cord: pinholes alone accounted for
            # 16 of 20 fragmented masks in a 80-sample check.
            holes = cv2.dilate(holes, np.ones((3, 3), np.uint8))
            mask[holes > 0] = 0
    notes["pinhole_rate"] = round(float(rate), 5)

    # 3. full breaks across the wire, where the illumination fell away.
    #
    # Most samples get none. A break is the defect that changes the topology,
    # so it is the one that has to stay rare enough to match the archive: one
    # mask in 26 shows a second component.
    nbreaks = 0
    if rng.random() < config.BREAK_PROBABILITY * strength:
        nbreaks = int(rng.integers(config.BREAK_COUNT[0], config.BREAK_COUNT[1] + 1))
    ys, xs = np.nonzero(mask)
    for _ in range(nbreaks):
        if len(xs) == 0:
            break
        k = rng.integers(0, len(xs))
        bw = max(1, int(round(radius * rng.uniform(*config.BREAK_WIDTH_RADII))))
        cv2.circle(mask, (int(xs[k]), int(ys[k])), bw, 0, -1)
    notes["breaks"] = nbreaks

    n_lab, _ = cv2.connectedComponents(mask)
    notes["components"] = int(n_lab - 1)
    return mask * 255, notes


def rasterize(xy: np.ndarray, depth: np.ndarray, size, rng,
              base_radius: float | None = None, degrade_strength: float = 1.0):
    """Full mask pipeline.

    Returns ``(mask_u8, buffers, info)`` where ``buffers`` is the dict of
    coverage, zbuf, sbuf and ubuf that the photo renderer consumes.
    """
    if base_radius is None:
        fg_target = rng.uniform(*config.FOREGROUND_FRACTION)
        base_radius = radius_for_foreground(xy, size, fg_target)
    cov, zbuf, sbuf, ubuf = paint(xy, depth, size, base_radius)
    mask, notes = degrade(cov, rng, degrade_strength, radius=base_radius)
    notes["base_radius_px"] = round(float(base_radius), 2)
    notes["foreground_fraction"] = round(float((mask > 127).mean()), 5)
    buffers = {"cov": cov, "z": zbuf, "s": sbuf, "u": ubuf}
    return mask, buffers, notes


def visible_path(xy: np.ndarray, size) -> np.ndarray:
    """Boolean flag per sample: is this point inside the frame?

    A path that leaves the frame has a ground truth that the tracker cannot
    possibly follow, so the harvester has to know which part is observable.
    """
    w, h = size
    return (xy[:, 0] >= 0) & (xy[:, 0] < w) & (xy[:, 1] >= 0) & (xy[:, 1] < h)
