"""Trace the cable as a globally optimal geodesic between the two endpoints.

`SmartWireTracker` walks the mask one step at a time, choosing a branch by a
weighted formula and undoing the choice by backtracking when it gets stuck.
That is a greedy search, and two measured facts follow from it: a break in
the mask stops it, because there is no next pixel to step onto, and every
branch is a local decision made without knowing where the path ends up.

This is a different formulation of the same problem, and it is the standard
one. With the two endpoints already known, the curve between them is the
minimal geodesic path of Cohen and Kimmel (1997): the curve minimising
integrated cost between two prescribed points, which is a **global**
optimum computed by solving an Eikonal equation, or on a pixel grid by
Dijkstra. See `Documentation/Investigacion/Trazado_IA/`, in particular Chen
and Cohen's survey, "From Active Contours to Minimal Geodesic Paths"
(arXiv:1907.09828), whose opening description of the model, a globally
optimal curve between two prescribed points usually provided by the user,
is exactly stage 3 of this pipeline.

Three things change by reformulating it.

**There are no branch decisions.** The solver does not choose a branch and
later regret it; it returns the cheapest curve overall. The learned branch
scorer, which was measured twice and never paid for itself, has nothing
left to decide. That was not a failure of the model: it was a question that
did not need asking.

**A break stops being fatal.** The cost outside the cable is high but
finite, so a gap is expensive rather than impassable. The path crosses a
short gap when going around would cost more, which is the behaviour the
measurements asked for: the remaining losses of the current tracker are
recall across breaks, not wrong turns.

**The segmenter's probability is used directly.** The cost comes from
`predict_proba`, not from a thresholded mask. Thresholding throws away
precisely the information that matters at a weak spot, where the model is
uncertain rather than wrong, and a weak spot is where masks break.

The known weakness of an isotropic minimal path is the shortcut: where the
cable crosses or touches itself, the cheapest curve can jump the crossing
instead of following the cable around. The literature's answer is a
curvature-penalised or orientation-lifted metric (Finsler elastica,
Reeds-Shepp), which is not implemented here. For a tensioned tether, which
is what this payload measures, there are no self-crossings to shortcut.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

#: How strongly the cost prefers the cable. The cost of a pixel is
#: ``exp(-beta * p)``, so the ratio between walking off the cable and
#: walking along its centre is ``exp(beta)``. With the default, a detour of
#: N pixels along the cable is preferred to a gap of more than about
#: N / exp(beta) pixels, so this is the single knob that decides how long a
#: break the tracer is willing to bridge.
DEFAULT_BETA = 6.0


def cost_from_probability(prob: np.ndarray, beta: float = DEFAULT_BETA,
                          use_ridge: bool = True) -> np.ndarray:
    """Cost image for the solver, low on the cable and high off it.

    ``prob`` is in [0, 1]: the segmenter's probability, or a normalised
    distance transform when only a binary mask is available.

    With ``use_ridge`` the probability is multiplied by a normalised
    distance transform of its own support, which makes the centre of the
    cable cheaper than its edges. The path then follows the centreline
    rather than hugging whichever side happens to be marginally brighter,
    and the centreline is what stage 5 pairs across the two images.
    """
    p = np.clip(np.nan_to_num(prob.astype(np.float32)), 0.0, 1.0)
    if use_ridge:
        inside = (p > 0.5).astype(np.uint8)
        if inside.any():
            dt = cv2.distanceTransform(inside, cv2.DIST_L2, 5)
            dt = dt / max(float(dt.max()), 1e-6)
            # keep the probability as the floor so a weak but real pixel is
            # still much cheaper than background
            p = np.maximum(p * (0.5 + 0.5 * dt), p * 0.5)
    return np.exp(-beta * p).astype(np.float64)


def probability_from_mask(mask: np.ndarray) -> np.ndarray:
    """Fallback when all that exists is a binary mask."""
    binary = (mask > 127).astype(np.uint8) if mask.dtype == np.uint8 and mask.max() > 1 \
        else (mask > 0).astype(np.uint8)
    return binary.astype(np.float32)


def trace(prob_or_mask, start, end, beta: float = DEFAULT_BETA,
          is_probability: bool = False, use_ridge: bool = True,
          simplify_px: float = 0.0):
    """Minimal-cost path from ``start`` to ``end``, both (x, y).

    Returns ``(path, info)`` where ``path`` is a list of (x, y) from start
    to end, or ``(None, info)`` if the two points cannot be connected at
    all, which on a finite cost image only happens if one of them is
    outside the image.
    """
    from skimage.graph import route_through_array

    prob = prob_or_mask if is_probability else probability_from_mask(prob_or_mask)
    h, w = prob.shape[:2]
    cost = cost_from_probability(prob, beta=beta, use_ridge=use_ridge)

    def clamp(p):
        return (int(np.clip(round(p[1]), 0, h - 1)),
                int(np.clip(round(p[0]), 0, w - 1)))      # (row, col)

    src, dst = clamp(start), clamp(end)
    info = {"beta": float(beta), "start": src, "end": dst}
    if src == dst:
        return None, info

    try:
        indices, weight = route_through_array(
            cost, src, dst, fully_connected=True, geometric=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("geodesic trace failed: %s", exc)
        return None, info

    path = [(int(c), int(r)) for r, c in indices]
    info["cost"] = float(weight)
    info["n_points"] = len(path)
    # how much of the path ran over background, which is the honest measure
    # of how much break the solver had to bridge
    on = sum(1 for x, y in path if prob[y, x] > 0.5)
    info["off_cable_px"] = len(path) - on
    info["off_cable_frac"] = (len(path) - on) / max(len(path), 1)

    if simplify_px > 0 and len(path) > 2:
        path = _simplify(path, simplify_px)
        info["n_points_simplified"] = len(path)
    return path, info


def _simplify(path, tol):
    """Douglas-Peucker, so the output is a polyline rather than every pixel.

    The downstream parametric matching resamples the path anyway, and a
    per-pixel chain makes the resampling weight straight runs more heavily
    than curved ones.
    """
    pts = np.asarray(path, dtype=np.float32).reshape(-1, 1, 2)
    out = cv2.approxPolyDP(pts, tol, False)
    return [(int(p[0][0]), int(p[0][1])) for p in out]


# ---------------------------------------------------------------------------
# Curvature-penalised minimal path, on an orientation-lifted grid
# ---------------------------------------------------------------------------
#
# The isotropic path above has one well known failure, and the measurement
# reproduced it exactly: 100% precision and 54% recall on loops and knots.
# The curve it returns is on the cable, but where the cable crosses itself
# the cheapest route jumps the crossing instead of going round, so it
# traces half of the cable and stops.
#
# The literature's answer is not a better cost image, it is a bigger state
# space. Chen and Cohen's survey (arXiv:1907.09828, section 5) lifts the
# problem to an orientation dimension and puts a Finsler or Randers metric
# on it, which is how the Euler-Mumford elastica and Reeds-Shepp models are
# solved. The point is that a shortcut requires a sharp turn at the
# crossing while following the cable does not, and curvature is only
# visible to a solver whose state includes where the curve is pointing.
#
# This is the discrete version of that: a node is (pixel, direction), a
# step moves STEP pixels along its direction, and changing direction costs
# ``turn_cost`` per increment. The grid is coarse on purpose; the path is
# scaled back up and the cable is many pixels wide, so the resolution lost
# is well under the width of the thing being traced.

N_DIRECTIONS = 16
STEP_PX = 3
DEFAULT_TURN_COST = 0.6
WORK_WIDTH_LIFTED = 480


def _direction_offsets(k: int = N_DIRECTIONS, step: int = STEP_PX):
    ang = 2.0 * np.pi * np.arange(k) / k
    dx = np.round(step * np.cos(ang)).astype(np.int32)
    dy = np.round(step * np.sin(ang)).astype(np.int32)
    length = np.sqrt(dx.astype(np.float64) ** 2 + dy.astype(np.float64) ** 2)
    return dx, dy, np.maximum(length, 1.0)


def trace_curvature(prob_or_mask, start, end, beta: float = 3.0,
                    turn_cost: float = DEFAULT_TURN_COST,
                    is_probability: bool = False, max_turn: int = 3,
                    work_width: int = WORK_WIDTH_LIFTED,
                    use_ridge: bool = True):
    """Minimal path with a curvature penalty. ``start``/``end`` are (x, y).

    The cost of a pixel is ``exp(beta * (1 - p))``, so staying on the cable
    costs 1 per pixel and crossing background costs ``exp(beta)``. Written
    this way the two penalties are commensurable: a detour of L pixels
    along the cable costs L, a gap of g pixels costs g*exp(beta), and a
    turn costs ``turn_cost`` times the squared direction increment, where
    one increment is 360/16 degrees. Those three numbers are the whole
    model.
    """
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    prob = prob_or_mask if is_probability else probability_from_mask(prob_or_mask)
    prob = np.clip(np.nan_to_num(prob.astype(np.float32)), 0.0, 1.0)
    H0, W0 = prob.shape[:2]

    scale = 1.0
    if W0 > work_width:
        scale = work_width / float(W0)
        prob = cv2.resize(prob, (work_width, max(2, int(round(H0 * scale)))),
                          interpolation=cv2.INTER_AREA)
    H, W = prob.shape[:2]

    if use_ridge:
        inside = (prob > 0.5).astype(np.uint8)
        if inside.any():
            dt = cv2.distanceTransform(inside, cv2.DIST_L2, 5)
            dt = dt / max(float(dt.max()), 1e-6)
            prob = np.maximum(prob * (0.5 + 0.5 * dt), prob * 0.5)

    cost = np.exp(beta * (1.0 - prob)).astype(np.float64)

    K = N_DIRECTIONS
    dxs, dys, seg = _direction_offsets(K, STEP_PX)
    ys, xs = np.mgrid[0:H, 0:W]
    ys, xs = ys.ravel(), xs.ravel()
    npix = H * W
    base = (ys * W + xs) * K

    rows, cols, vals = [], [], []
    turns = range(-max_turn, max_turn + 1)
    for k in range(K):
        for dk in turns:
            k2 = (k + dk) % K
            nx, ny = xs + dxs[k2], ys + dys[k2]
            mx = xs + dxs[k2] // 2
            my = ys + dys[k2] // 2
            ok = (nx >= 0) & (nx < W) & (ny >= 0) & (ny < H)
            if not ok.any():
                continue
            sx, sy = xs[ok], ys[ok]
            tx, ty = nx[ok], ny[ok]
            cx, cy = np.clip(mx[ok], 0, W - 1), np.clip(my[ok], 0, H - 1)
            w = seg[k2] * (cost[sy, sx] + cost[cy, cx] + cost[ty, tx]) / 3.0
            # squared, not linear: the Euler-Mumford elastica energy is the
            # integral of 1 + k^2 along the curve, and the square is the
            # whole point. One sharp turn at a crossing and many gentle
            # turns along a curving cable sum to the same total angle, so a
            # linear penalty cannot tell them apart, which is what the
            # first sweep measured: the turn weight moved the score by one
            # point between 0 and 10.
            w = w + turn_cost * float(dk * dk)
            rows.append(base[ok] + k)
            cols.append((ty * W + tx) * K + k2)
            vals.append(w)

    if not rows:
        return None, {"error": "empty graph"}
    graph = csr_matrix(
        (np.concatenate(vals),
         (np.concatenate(rows), np.concatenate(cols))),
        shape=(npix * K, npix * K))

    def node_set(p):
        x = int(np.clip(round(p[0] * scale), 0, W - 1))
        y = int(np.clip(round(p[1] * scale), 0, H - 1))
        return (y * W + x) * K + np.arange(K), (x, y)

    src_nodes, src_xy = node_set(start)
    dst_nodes, dst_xy = node_set(end)
    info = {"beta": float(beta), "turn_cost": float(turn_cost),
            "work": (W, H), "start": src_xy, "end": dst_xy}
    if src_xy == dst_xy:
        return None, info

    dist, pred, sources = dijkstra(graph, directed=True, indices=src_nodes,
                                   return_predecessors=True, min_only=True)
    reach = dist[dst_nodes]
    if not np.isfinite(reach).any():
        return None, info
    goal = int(dst_nodes[int(np.argmin(reach))])
    info["cost"] = float(dist[goal])

    chain, node, guard = [], goal, 0
    while node >= 0 and guard < npix * K:
        chain.append(node)
        node = int(pred[node])
        guard += 1
    chain.reverse()

    inv = 1.0 / scale
    path, seen = [], set()
    for n in chain:
        pix = n // K
        xy = (int(round((pix % W) * inv)), int(round((pix // W) * inv)))
        if xy not in seen:
            seen.add(xy)
            path.append(xy)
    if len(path) < 2:
        return None, info

    # the lifted grid steps STEP_PX at a time, so fill the gaps to give the
    # same per-pixel chain the rest of the pipeline expects
    dense = []
    for (x0, y0), (x1, y1) in zip(path[:-1], path[1:]):
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        for t in range(n):
            dense.append((int(round(x0 + (x1 - x0) * t / n)),
                          int(round(y0 + (y1 - y0) * t / n))))
    dense.append(path[-1])

    on = sum(1 for x, y in dense
             if 0 <= y < H0 and 0 <= x < W0
             and (prob_or_mask[y, x] > (127 if not is_probability else 0.5)))
    info["n_points"] = len(dense)
    info["off_cable_frac"] = 1.0 - on / max(len(dense), 1)
    return dense, info
