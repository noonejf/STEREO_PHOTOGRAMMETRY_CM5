"""Features and labels for learning where a cord starts and ends.

Why this is not a tip classifier
--------------------------------
The shipped detector skeletonises the mask, finds pixels with exactly one
skeleton neighbour, and takes the geodesically farthest pair. Measured over
80 synthetic masks, that approach cannot work on a third of the cases: 47 of
138 true endpoints have no skeleton tip within two wire radii, and 44 of
those 47 sit squarely on the mask. They concentrate in the shapes that
matter, 83% of loop endpoints and 71% of knot endpoints, for one structural
reason. When the free end of the cord happens to lie across another part of
the cord, the skeleton merges through it and no tip is produced there. No
amount of tuning a tip finder recovers an endpoint that leaves no tip.

So every skeleton pixel is a candidate here, not just the tips, and the
model scores all of them. Inference takes the best-scoring pixel and then
the best one that is geodesically far from it, which is the constraint that
makes the pair an actual pair rather than two points on the same end.

Geodesic quantities come from a double sweep: breadth-first search from an
arbitrary skeleton pixel finds A, a sweep from A finds B, and a third sweep
gives the distance to B. On a tree-shaped skeleton max(dist_A, dist_B) is
the standard approximation of eccentricity, and it costs three sweeps rather
than all-pairs.
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np

try:
    from skimage.morphology import skeletonize
except ImportError:  # pragma: no cover
    skeletonize = None


FEATURE_NAMES = [
    "n_neighbours",      # 1 = tip, 2 = through, 3+ = junction
    "dt_rel",            # thickness here, in units of the mask's max
    "dt_local_rel",      # thickness here against the local mean: a bulge means overlap
    "ecc_rel",           # geodesic eccentricity, normalised by skeleton diameter
    "dist_a_rel",        # geodesic distance to sweep anchor A
    "dist_b_rel",        # geodesic distance to sweep anchor B
    "one_sidedness",     # how much the nearby skeleton lies to one side
    "skel_density",      # skeleton pixels in a local window
    "mask_density",      # mask fill in the same window
    "border_dist",       # distance to the nearest image edge
    "spur_len_rel",      # geodesic distance to the nearest junction
    "neigh_count_r",     # skeleton pixels within one wire radius
]
N_FEATURES = len(FEATURE_NAMES)

NEIGH8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def skeleton_of(mask: np.ndarray) -> np.ndarray:
    if skeletonize is None:
        raise RuntimeError("scikit-image is required for endpoint features")
    return skeletonize(mask > 127).astype(np.uint8)


def _bfs(skel_idx, neighbours, source: int) -> np.ndarray:
    """Hop distance from one skeleton pixel to every other, over 8-connectivity."""
    n = len(skel_idx)
    dist = np.full(n, -1, dtype=np.int32)
    dist[source] = 0
    q = deque([source])
    while q:
        u = q.popleft()
        du = dist[u] + 1
        for v in neighbours[u]:
            if dist[v] < 0:
                dist[v] = du
                q.append(v)
    return dist


def _build_graph(skel: np.ndarray):
    ys, xs = np.nonzero(skel)
    if len(ys) == 0:
        return None
    idx_of = {}
    for i, (y, x) in enumerate(zip(ys, xs)):
        idx_of[(int(y), int(x))] = i
    neighbours = [[] for _ in range(len(ys))]
    for i, (y, x) in enumerate(zip(ys, xs)):
        for dy, dx in NEIGH8:
            j = idx_of.get((int(y) + dy, int(x) + dx))
            if j is not None:
                neighbours[i].append(j)
    return np.stack([xs, ys], axis=1).astype(np.int32), neighbours


def geodesic_sweeps(points, neighbours):
    """Double sweep. Returns (dist_a, dist_b, diameter)."""
    n = len(points)
    d0 = _bfs(points, neighbours, 0)
    reach = np.flatnonzero(d0 >= 0)
    a = int(reach[np.argmax(d0[reach])]) if len(reach) else 0
    da = _bfs(points, neighbours, a)
    reach = np.flatnonzero(da >= 0)
    b = int(reach[np.argmax(da[reach])]) if len(reach) else 0
    db = _bfs(points, neighbours, b)
    diameter = float(max(da.max(), 1))
    # unreachable pixels belong to another fragment; treat them as far
    da = np.where(da < 0, diameter, da).astype(np.float32)
    db = np.where(db < 0, diameter, db).astype(np.float32)
    return da, db, diameter


def features(mask: np.ndarray):
    """Feature matrix for every skeleton pixel.

    Returns ``(X, points, info)`` where ``points`` is (N, 2) in (x, y) order
    and lines up row for row with ``X``.
    """
    binary = (mask > 127).astype(np.uint8)
    skel = skeleton_of(mask)
    built = _build_graph(skel)
    if built is None:
        return np.zeros((0, N_FEATURES), np.float32), np.zeros((0, 2), np.int32), {}
    points, neighbours = built
    n = len(points)

    dt = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    dt_max = max(float(dt.max()), 1.0)
    wire_r = max(dt_max, 3.0)

    da, db, diameter = geodesic_sweeps(points, neighbours)
    ecc = np.maximum(da, db)

    nb_count = np.array([len(v) for v in neighbours], dtype=np.float32)

    # distance to the nearest junction, so a short spur can be told from a
    # real end: a pruning artifact sits a few pixels from a branch point,
    # a cord end is far from one.
    junctions = np.flatnonzero(nb_count >= 3)
    if len(junctions):
        spur = np.full(n, diameter, np.float32)
        dq = deque()
        for j in junctions:
            spur[j] = 0.0
            dq.append(j)
        while dq:
            u = dq.popleft()
            for v in neighbours[u]:
                if spur[v] > spur[u] + 1:
                    spur[v] = spur[u] + 1
                    dq.append(v)
    else:
        spur = np.full(n, diameter, np.float32)

    h, w = binary.shape
    win = int(max(5, round(wire_r * 2.0)))
    rad = int(max(3, round(wire_r)))

    skel_f = skel.astype(np.float32)
    bin_f = binary.astype(np.float32)
    box = (2 * win + 1)
    skel_den = cv2.boxFilter(skel_f, -1, (box, box), normalize=True)
    mask_den = cv2.boxFilter(bin_f, -1, (box, box), normalize=True)
    boxr = (2 * rad + 1)
    skel_cnt = cv2.boxFilter(skel_f, -1, (boxr, boxr), normalize=False)
    dt_local = cv2.boxFilter(dt, -1, (box, box), normalize=True)

    xs, ys = points[:, 0], points[:, 1]

    # One-sidedness. Around a real end the cord's skeleton continues in one
    # direction only, so the mean unit vector to nearby skeleton pixels has
    # a large magnitude. Through the middle of a cord the two directions
    # cancel and it goes to zero. This is the feature that can still fire
    # where the end lies across another strand and no tip exists.
    one_sided = np.zeros(n, np.float32)
    tree = {}
    for i in range(n):
        tree.setdefault((ys[i] // max(rad, 1), xs[i] // max(rad, 1)), []).append(i)
    for i in range(n):
        cy, cx = ys[i] // max(rad, 1), xs[i] // max(rad, 1)
        cand = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cand.extend(tree.get((cy + dy, cx + dx), ()))
        if len(cand) < 2:
            one_sided[i] = 1.0
            continue
        d = points[cand].astype(np.float32) - points[i].astype(np.float32)
        nrm = np.linalg.norm(d, axis=1)
        keep = (nrm > 1e-6) & (nrm <= rad)
        if keep.sum() < 2:
            one_sided[i] = 1.0
            continue
        u = d[keep] / nrm[keep][:, None]
        one_sided[i] = float(np.linalg.norm(u.mean(axis=0)))

    X = np.stack([
        nb_count,
        dt[ys, xs] / dt_max,
        dt[ys, xs] / np.maximum(dt_local[ys, xs], 1e-6),
        ecc / diameter,
        da / diameter,
        db / diameter,
        one_sided,
        skel_den[ys, xs],
        mask_den[ys, xs],
        np.minimum.reduce([xs, ys, w - 1 - xs, h - 1 - ys]).astype(np.float32) / max(min(h, w), 1),
        spur / diameter,
        skel_cnt[ys, xs],
    ], axis=1).astype(np.float32)

    info = {"diameter": diameter, "wire_radius": wire_r,
            "n_skeleton": n, "n_tips": int((nb_count == 1).sum())}
    return X, points, info


def harvest(mask: np.ndarray, path_xy: np.ndarray, tol_radii: float = 2.0):
    """Label every skeleton pixel as endpoint or not.

    A pixel is positive when it lies within ``tol_radii`` wire radii of one of
    the two true path ends. ``reachable`` says, per end, whether any skeleton
    pixel qualified: the ones that do not are the cases no mask-based
    detector can recover, and they are counted rather than quietly dropped.
    """
    X, points, info = features(mask)
    if len(X) == 0:
        return {"X": X, "y": np.zeros((0,), np.int8), "points": points,
                "info": info, "reachable": [False, False]}

    path_xy = np.asarray(path_xy, dtype=float)
    tol = max(8.0, tol_radii * info["wire_radius"])
    y = np.zeros(len(points), dtype=np.int8)
    reachable = []
    for end in (path_xy[0], path_xy[-1]):
        d = np.linalg.norm(points.astype(float) - end[None, :], axis=1)
        near = d <= tol
        reachable.append(bool(near.any()))
        if near.any():
            # only the single closest pixel is positive, so the model learns a
            # point rather than a blob, but everything inside the tolerance is
            # excluded from the negatives by the caller via `ambiguous`
            y[int(np.argmin(d))] = 1

    ambiguous = np.zeros(len(points), dtype=bool)
    for end in (path_xy[0], path_xy[-1]):
        d = np.linalg.norm(points.astype(float) - end[None, :], axis=1)
        ambiguous |= (d <= tol) & (y == 0)

    return {"X": X, "y": y, "points": points, "info": info,
            "reachable": reachable, "ambiguous": ambiguous}


def predict_pair(model, feature_names, mask, min_separation_frac: float = 0.35,
                 top_k: int = 12):
    """Score every skeleton pixel and return the two endpoints.

    The pair is chosen jointly: among the ``top_k`` best-scoring pixels,
    take the pair with the highest summed score whose geodesic separation is
    at least ``min_separation_frac`` of the skeleton diameter. The earlier
    version was greedy, best pixel first and then the best far-away one, and
    its failure mode was exactly the one that matters: when the single best
    pixel sits on the wrong strand of a crossing, every choice after it is
    already lost. Joint selection lets a slightly weaker first pick win when
    it comes with a strong, well-separated partner.

    The separation constraint is what makes the pair an actual pair rather
    than two points on the same end.
    """
    X, points, info = features(mask)
    if len(X) < 2:
        return None, None, info
    keep = [FEATURE_NAMES.index(n) for n in feature_names]
    score = model.predict_proba(X[:, keep])[:, 1]

    built = _build_graph(skeleton_of(mask))
    if built is None:
        return None, None, info
    pts, neighbours = built

    k = min(top_k, len(score))
    cand = np.argsort(score)[-k:][::-1]
    need = min_separation_frac * info["diameter"]

    best, best_sum = None, -1.0
    for a in cand:
        d_a = _bfs(pts, neighbours, int(a)).astype(np.float32)
        d_a = np.where(d_a < 0, info["diameter"], d_a)
        for b in cand:
            if b == a or d_a[b] < need:
                continue
            ssum = float(score[a] + score[b])
            if ssum > best_sum:
                best_sum, best = ssum, (int(a), int(b))

    if best is None:
        # nothing satisfies the separation, fall back to the greedy pair
        first = int(np.argmax(score))
        second = int(np.argmax(np.where(np.arange(len(score)) != first,
                                        score, -1.0)))
        best = (first, second)

    first, second = best
    p1 = (int(points[first][0]), int(points[first][1]))
    p2 = (int(points[second][0]), int(points[second][1]))
    info["score_first"] = float(score[first])
    info["score_second"] = float(score[second])
    return p1, p2, info
