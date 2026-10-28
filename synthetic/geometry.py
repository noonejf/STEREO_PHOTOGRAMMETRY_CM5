"""Generate 3D wire centrelines and project them to the image plane.

Curves are built in 3D and then projected, for two reasons that both matter
downstream. The z coordinate gives a physically consistent depth along the
wire, and the radius scales as 1/z, which is exactly the thickness-continuity
signal `SmartWireTracker` scores branches on. And at a self-crossing the z
ordering says which strand is in front, so the rendered photo can occlude
correctly instead of showing two strands fused into a cross.

Everything returns the same shape: an (N, 3) array of points ordered from one
free end to the other. That order is the ground truth the path model learns.
"""
from __future__ import annotations

import numpy as np

from . import config


# ---------------------------------------------------------------- splines

def catmull_rom(ctrl: np.ndarray, samples: int) -> np.ndarray:
    """Interpolate control points with a centripetal Catmull-Rom spline.

    Centripetal parametrisation is used rather than uniform because uniform
    Catmull-Rom forms cusps and self-intersections near tight control points,
    and here a self-intersection has to be something the generator decided on,
    not an artifact of the interpolation.
    """
    ctrl = np.asarray(ctrl, dtype=float)
    if len(ctrl) < 4:
        pad = np.vstack([ctrl[:1], ctrl, ctrl[-1:], ctrl[-1:]])
        ctrl = pad[:max(4, len(pad))]

    # knot sequence, alpha = 0.5 is the centripetal case
    d = np.linalg.norm(np.diff(ctrl, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(np.maximum(d, 1e-9) ** 0.5)])

    out = []
    per_seg = max(2, samples // max(1, len(ctrl) - 3))
    for i in range(len(ctrl) - 3):
        p0, p1, p2, p3 = ctrl[i:i + 4]
        t0, t1, t2, t3 = t[i:i + 4]
        tt = np.linspace(t1, t2, per_seg, endpoint=False)[:, None]

        a1 = (t1 - tt) / (t1 - t0) * p0 + (tt - t0) / (t1 - t0) * p1
        a2 = (t2 - tt) / (t2 - t1) * p1 + (tt - t1) / (t2 - t1) * p2
        a3 = (t3 - tt) / (t3 - t2) * p2 + (tt - t2) / (t3 - t2) * p3
        b1 = (t2 - tt) / (t2 - t0) * a1 + (tt - t0) / (t2 - t0) * a2
        b2 = (t3 - tt) / (t3 - t1) * a2 + (tt - t1) / (t3 - t1) * a3
        out.append((t2 - tt) / (t2 - t1) * b1 + (tt - t1) / (t2 - t1) * b2)

    out.append(ctrl[-2][None, :])
    return np.vstack(out)


def resample_uniform(pts: np.ndarray, step: float) -> np.ndarray:
    """Resample a polyline to a uniform arc-length step, in the xy plane.

    The tracker advances in fixed pixel steps, so the ground-truth path has to
    be uniform in image space, not in the curve's own parameter.
    """
    xy = pts[:, :2]
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] < step:
        return pts[[0, -1]]
    target = np.arange(0.0, s[-1], step)
    out = np.empty((len(target), pts.shape[1]))
    for k in range(pts.shape[1]):
        out[:, k] = np.interp(target, s, pts[:, k])
    return out


# ---------------------------------------------------------------- shapes
#
# Each shape returns control points in a normalised [-1, 1] cube. Fitting to
# the frame happens once, in `make_centreline`, so the shapes stay readable.

def _straight(rng) -> np.ndarray:
    n = rng.integers(4, 6)
    t = np.linspace(-1, 1, n)
    sag = rng.uniform(-0.12, 0.12)
    return np.stack([t,
                     sag * (1 - t ** 2) + rng.normal(0, 0.015, n),
                     rng.normal(0, 0.05, n)], axis=1)


def _catenary(rng) -> np.ndarray:
    n = 7
    t = np.linspace(-1, 1, n)
    a = rng.uniform(0.6, 2.2)
    y = np.cosh(t * a) / np.cosh(a)
    y = (y - y.min()) / max(np.ptp(y), 1e-6)
    return np.stack([t,
                     rng.choice([-1, 1]) * y * rng.uniform(0.25, 0.85),
                     rng.normal(0, 0.08, n)], axis=1)


def _smooth(rng) -> np.ndarray:
    n = rng.integers(5, 8)
    t = np.linspace(-1, 1, n)
    return np.stack([t + rng.normal(0, 0.06, n),
                     np.cumsum(rng.normal(0, 0.45, n)) * 0.5,
                     np.cumsum(rng.normal(0, 0.25, n)) * 0.4], axis=1)


def _loop(rng) -> np.ndarray:
    """One or two self-crossings. This is the shape the real captures show."""
    loops = rng.integers(1, 3)
    turns = loops + rng.uniform(0.15, 0.45)
    n = int(26 * turns)
    th = np.linspace(0, 2 * np.pi * turns, n)
    r = rng.uniform(0.45, 0.85) * (1 + rng.uniform(-0.25, 0.25) * np.sin(th * rng.integers(1, 3)))
    pts = np.stack([r * np.cos(th), r * np.sin(th), 0.35 * np.sin(th * 1.3)], axis=1)

    # Drift the centre as the curve turns, so one revolution does not retrace
    # the previous one. Without this a loop of nearly two turns paints a solid
    # ring with both ends buried inside it: no free end exists anywhere in the
    # mask, which is the one thing this family must never produce.
    ang = rng.uniform(0, 2 * np.pi)
    drift = rng.uniform(0.7, 1.5) * float(np.mean(np.abs(r)))
    frac = (th / th[-1])[:, None]
    pts[:, :2] += frac * drift * np.array([np.cos(ang), np.sin(ang)])
    # free tails, so the ends are not on the loop itself
    tail = rng.uniform(0.3, 0.7)
    d0 = pts[1] - pts[0]
    d1 = pts[-1] - pts[-2]
    pts = np.vstack([pts[0] - tail * d0 / np.linalg.norm(d0) * 6, pts,
                     pts[-1] + tail * d1 / np.linalg.norm(d1) * 6])
    return pts


def _coil(rng) -> np.ndarray:
    """A spiral: many near-parallel runs, which is the case the parallel-line
    penalty in the tracker exists for and the case it most often gets wrong."""
    turns = rng.uniform(1.8, 4.0)
    n = int(34 * turns)
    th = np.linspace(0, 2 * np.pi * turns, n)
    r = np.linspace(rng.uniform(0.12, 0.3), rng.uniform(0.7, 1.0), n)
    squash = rng.uniform(0.35, 1.0)
    return np.stack([r * np.cos(th), squash * r * np.sin(th),
                     0.4 * np.linspace(-1, 1, n)], axis=1)


def _knot(rng) -> np.ndarray:
    """A (p, q) torus knot, randomly rotated then projected.

    This gives clean, well-separated over-under crossings with a correct depth
    ordering, which is the cheapest way to produce a crossing that looks like
    a real knot rather than like two lines drawn across each other.
    """
    p = int(rng.choice([2, 2, 3, 3, 4]))
    q = int(rng.choice([3, 5, 3, 4, 5]))
    n = 420
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    R, r = 1.0, rng.uniform(0.35, 0.6)
    cx = (R + r * np.cos(q * th)) * np.cos(p * th)
    cy = (R + r * np.cos(q * th)) * np.sin(p * th)
    cz = r * np.sin(q * th)
    pts = np.stack([cx, cy, cz], axis=1)

    # A knot is a closed curve, so cut it to give the cord two free ends.
    #
    # Where the cut falls matters. A torus knot runs close to itself nearly
    # everywhere, so a cut at a random index usually leaves both ends resting
    # against a neighbouring wrap: measured clearance there is about 4 px
    # against the 15 px an end needs to show up in the mask. The cut is
    # therefore placed where the curve is locally farthest from the rest of
    # itself, which is the one place a free end can exist.
    d = np.linalg.norm(pts[:, None, :2] - pts[None, :, :2], axis=2)
    span = np.minimum(np.abs(np.arange(n)[:, None] - np.arange(n)[None, :]),
                      n - np.abs(np.arange(n)[:, None] - np.arange(n)[None, :]))
    d[span < n // 12] = np.inf
    clearance = d.min(axis=1)
    best = np.argsort(clearance)[-max(8, n // 20):]
    cut = int(rng.choice(best))
    pts = np.roll(pts, -cut, axis=0)

    # The far end is the other side of the removed arc, at a position the cut
    # did not choose, so pick the trim length the same way. Choosing only the
    # cut leaves one end free and the other buried, which is half a fix.
    rolled = np.roll(clearance, -cut)
    lo, hi = int(n * 0.80), int(n * 0.97)
    keep = lo + int(np.argmax(rolled[lo:hi]))
    pts = pts[:keep]
    return _random_rotate(pts, rng)


def _tangle(rng) -> np.ndarray:
    """Momentum random walk. Produces the messy, irregular crossings that a
    parametric shape never will."""
    # Low momentum and many short steps, so the walk folds back over itself.
    # With long steps it just drifts away and produces almost no crossings,
    # which defeats the point of this family.
    n = rng.integers(26, 46)
    pos = np.zeros(3)
    vel = rng.normal(0, 1, 3)
    vel /= np.linalg.norm(vel)
    out = [pos.copy()]
    for _ in range(n):
        vel = vel * rng.uniform(0.25, 0.55) + rng.normal(0, 1, 3) * 0.85
        vel /= max(np.linalg.norm(vel), 1e-9)
        pos = pos + vel * rng.uniform(0.18, 0.40)
        pos = np.clip(pos, -1.0, 1.0)
        out.append(pos.copy())
    return _random_rotate(np.array(out), rng)


def _random_rotate(pts: np.ndarray, rng) -> np.ndarray:
    a, b, c = rng.uniform(0, 2 * np.pi, 3)
    rx = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
    rz = np.array([[np.cos(c), -np.sin(c), 0], [np.sin(c), np.cos(c), 0], [0, 0, 1]])
    return pts @ (rx @ ry @ rz).T


SHAPES = {
    "straight": _straight,
    "catenary": _catenary,
    "smooth": _smooth,
    "loop": _loop,
    "coil": _coil,
    "knot": _knot,
    "tangle": _tangle,
}


# ---------------------------------------------------------------- assembly

#: Minimum separation between the two ends, as a fraction of the shape's
#: own extent. The cord is an open curve with two free ends and the whole
#: path capability depends on that: a closed loop has no start and no stop,
#: so a generator that emitted one would be teaching both models something
#: that cannot happen. Enforced in `make_centreline`, not merely hoped for.
MIN_END_SEPARATION = 0.12


def _is_open(xy: np.ndarray) -> bool:
    extent = max(np.ptp(xy[:, 0]), np.ptp(xy[:, 1]))
    if extent < 1e-9:
        return False
    return np.linalg.norm(xy[0] - xy[-1]) / extent >= MIN_END_SEPARATION


#: Clearance an end needs from the rest of the cord before it reads as a free
#: end, in units of the cord radius. Two strands fuse into one blob once their
#: centrelines come within 2 r, so a tip buried under another strand leaves no
#: visible end at all.
END_CLEARANCE_RADII = 2.5

#: How much of the cord, measured back from each end, has to stay clear.
END_TAIL_RADII = 3.0


def end_clearances(xy: np.ndarray, radius: float) -> list:
    """Distance from each end's tail to the rest of the cord, in pixels.

    `MIN_END_SEPARATION` only asks that the two ends are far from each other,
    which a ring with a small gap passes and a cord whose end lies across its
    own middle also passes. Neither of those shows a free end once painted,
    and an end that is not visible in the mask cannot be found from the mask,
    by a model or by anything else. This measures the thing that actually
    decides it.
    """
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 8:
        return [0.0, 0.0]
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    tail = max(radius * END_TAIL_RADII, 6.0)
    # Skip this much arc on either side of the point under test, so the cord's
    # own continuation is not mistaken for a second strand lying across it.
    # Measured from each tail point, not from the end, or a gently curving
    # cord reports the distance to its own neighbour and every shape comes
    # out looking equally crowded.
    gap = max(radius * 6.0, 20.0)

    out = []
    for from_start in (True, False):
        s = arc if from_start else arc[-1] - arc
        head = np.flatnonzero(s <= tail)
        best = float("inf")
        for i in head:
            far = np.abs(arc - arc[i]) > gap
            if not far.any():
                continue
            d = np.linalg.norm(xy[far] - xy[i], axis=1).min()
            best = min(best, float(d))
        out.append(best)
    return out


def ends_are_free(xy: np.ndarray, radius: float, size=None) -> bool:
    """Would both ends be visible as free ends in the painted mask?

    An end outside the frame is not required to be clear: it is genuinely
    occluded by the frame edge, which is a case the real captures contain and
    the models have to cope with.
    """
    xy = np.asarray(xy, dtype=float)
    need = END_CLEARANCE_RADII * radius
    for end, clear in zip((xy[0], xy[-1]), end_clearances(xy, radius)):
        if size is not None:
            w, h = size
            if not (0 <= end[0] < w and 0 <= end[1] < h):
                continue
        if clear < need:
            return False
    return True


def make_centreline(kind: str, size, rng, allow_out_of_frame: bool = False,
                    _attempt: int = 0):
    """Build one wire.

    Returns ``(xyz, depth)`` where ``xyz`` is an (N, 3) array whose first two
    columns are pixel coordinates in an image of ``size = (w, h)``, ordered
    end to end, and ``depth`` is the per-point relative depth used to scale
    the radius.

    The curve is always open: a shape whose ends come closer than
    `MIN_END_SEPARATION` of its extent is rejected and drawn again.
    """
    w, h = size
    ctrl = SHAPES[kind](rng)
    pts = catmull_rom(ctrl, samples=max(600, 24 * len(ctrl)))

    # normalise the xy extent, then place it in the frame
    xy = pts[:, :2]
    xy = xy - xy.mean(axis=0)
    extent = np.abs(xy).max(axis=0)
    extent[extent < 1e-9] = 1e-9

    if allow_out_of_frame:
        fill = rng.uniform(1.05, 1.5)       # deliberately overflows the frame
        margin = 0.0
    else:
        fill = rng.uniform(0.78, 0.98)
        margin = 0.03

    scale = min(w * (fill - margin) / (2 * extent[0]),
                h * (fill - margin) / (2 * extent[1]))
    xy = xy * scale

    # Cap the arc length.
    #
    # Radius and arc length cannot both be free: their product is the painted
    # area, and the area has to match the measured foreground fraction. A
    # curve that wanders for many frame-widths therefore forces a radius of
    # one or two pixels, which then breaks into dozens of components under
    # any mask degradation and is nothing like the 8 to 30 px cords in the
    # archive. Shrinking an over-long curve keeps it inside the frame, since
    # this only ever scales down.
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    arc = float(seg.sum())
    diag = float(np.hypot(w, h))
    cap = diag * rng.uniform(*config.ARC_LENGTH_DIAGONALS)
    if arc > cap:
        xy = xy * (cap / arc)

    centre = np.array([w / 2, h / 2]) + rng.normal(0, [w * 0.05, h * 0.05])
    xy = xy - xy.mean(axis=0) + centre

    # depth from the z axis, mapped into the configured range
    z = pts[:, 2]
    if np.ptp(z) > 1e-9:
        z = (z - z.min()) / np.ptp(z)
    else:
        z = np.zeros_like(z)
    lo, hi = config.DEPTH_RANGE
    depth = lo + z * (hi - lo)

    xyz = np.column_stack([xy, depth])
    xyz = resample_uniform(xyz, step=rng.uniform(1.5, 3.0))

    if not _is_open(xyz[:, :2]) and _attempt < 8:
        return make_centreline(kind, size, rng, allow_out_of_frame, _attempt + 1)

    return xyz[:, :2], xyz[:, 2]


def pick_shape(rng) -> str:
    kinds = list(config.SHAPE_WEIGHTS)
    weights = np.array([config.SHAPE_WEIGHTS[k] for k in kinds], dtype=float)
    return kinds[int(rng.choice(len(kinds), p=weights / weights.sum()))]


def crossings(xy: np.ndarray, min_separation: int = 20) -> list:
    """Indices where the path crosses itself in the image plane.

    Used to label how hard a sample is, and to check that the shape families
    are actually producing the crossings they are supposed to. Segments close
    together along the curve are skipped, since those are the curve bending,
    not a crossing.
    """
    out = []
    n = len(xy)
    p = xy[:-1]
    r = np.diff(xy, axis=0)
    for i in range(n - 1):
        j0 = i + min_separation
        if j0 >= n - 1:
            break
        q = p[j0:]
        s = r[j0:]
        denom = r[i, 0] * s[:, 1] - r[i, 1] * s[:, 0]
        ok = np.abs(denom) > 1e-9
        if not ok.any():
            continue
        qp = q - p[i]
        t = np.where(ok, (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / np.where(ok, denom, 1), -1)
        u = np.where(ok, (qp[:, 0] * r[i, 1] - qp[:, 1] * r[i, 0]) / np.where(ok, denom, 1), -1)
        hit = ok & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
        for k in np.nonzero(hit)[0]:
            out.append((i, j0 + int(k)))
    # collapse neighbouring duplicates
    dedup = []
    for i, j in out:
        if not dedup or abs(i - dedup[-1][0]) > min_separation:
            dedup.append((i, j))
    return dedup
