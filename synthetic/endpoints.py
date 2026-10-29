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


def _farthest_tip_pair(pts, neighbours, nb_count):
    """The pair the shipped detector would pick: geodesically farthest tips.

    Recomputed here from the same graph rather than imported, so the learned
    decoder can hold the classical answer as a candidate and compare the two
    under one scoring rule.
    """
    tips = np.flatnonzero(nb_count <= 1.0)
    if len(tips) < 2:
        return None
    d0 = _bfs(pts, neighbours, int(tips[0])).astype(np.float32)
    a = int(tips[np.argmax(np.where(d0[tips] < 0, 0.0, d0[tips]))])
    da = _bfs(pts, neighbours, a).astype(np.float32)
    b = int(tips[np.argmax(np.where(da[tips] < 0, 0.0, da[tips]))])
    return None if a == b else (a, b)


def score_candidates(model, feature_names, mask, candidates,
                     min_separation_frac: float = 0.35,
                     geodesic_weight: float = 1.0):
    """Choose the best pair out of a shortlist somebody else proposed.

    This is the opposite arrangement to `predict_pair`, and the one that
    survives contact with the pipeline. There the model scores every
    skeleton pixel, which lets it find an end that leaves no tip but also
    lets it answer with a pixel in the middle of the cord, where the tracker
    starts with two directions to choose from and loses half the cable.
    Here the shipped detector proposes its clustered skeleton tips and the
    model only decides which two of them are the ends.

    The decision gets easier and the failure gets cheaper at the same time.
    Easier, because picking two out of a handful of candidates is a far
    smaller problem than picking two out of several thousand pixels, and it
    is the problem the classical rule is actually weak at: it takes the
    geodesically farthest pair, which is wrong whenever a pruning spur
    reaches further than a real end. Cheaper, because every possible answer
    is a skeleton tip, so the worst case is another one of the candidates
    the classical detector was already choosing between.

    **The classical criterion is kept, not discarded.** A pair is ranked by
    ``score_a + score_b + geodesic_weight * d_ab / diameter``, so the
    geodesic span the shipped detector maximises is one term and the
    model's opinion is the other. At a large weight this reproduces the
    classical choice exactly; at zero it is the model alone.

    Keeping it matters because of what the candidates are. The median mask
    here has **one** skeleton tip: on a loop or a knot the free end lies
    across another strand and the skeleton runs straight through it, so
    frequently no candidate is a true end at all. The model is then
    choosing among negatives and has no basis for it, while the geodesic
    rule still returns two points that span the cable, which is a good
    seed even when it is not the end. Measured with the model alone, that
    is where it loses: knots 74.4 against 80.4, tangles 82.7 against 93.7.

    ``candidates`` are (x, y) in the coordinates of ``mask``. Returns
    ``(p1, p2, info)``, or ``(None, None, info)`` when there is nothing
    sensible to say, in which case the caller keeps its own answer.
    """
    X, points, info = features(mask)
    info["n_candidates"] = len(candidates)
    if len(X) < 2 or len(candidates) < 2:
        return None, None, info

    built = _build_graph(skeleton_of(mask))
    if built is None:
        return None, None, info
    pts, neighbours = built

    # a candidate is a skeleton pixel already, but it is produced by a
    # separate skeletonisation pass, so map by nearest rather than trust it
    idx = []
    for cx, cy in candidates:
        d = ((points[:, 0] - float(cx)) ** 2 +
             (points[:, 1] - float(cy)) ** 2)
        j = int(np.argmin(d))
        if d[j] <= 64.0 and j not in idx:   # within 8 px
            idx.append(j)
    info["n_mapped"] = len(idx)
    if len(idx) < 2:
        return None, None, info

    keep = [FEATURE_NAMES.index(n) for n in feature_names]
    score = model.predict_proba(X[idx][:, keep])[:, 1]

    need = min_separation_frac * info["diameter"]
    diameter = max(info["diameter"], 1.0)
    best, best_val = None, -1e18
    for ai, a in enumerate(idx):
        d_a = _bfs(pts, neighbours, int(a)).astype(np.float32)
        d_a = np.where(d_a < 0, 0.0, d_a)
        for bi, b in enumerate(idx):
            if b == a or d_a[b] < need:
                continue
            val = (float(score[ai] + score[bi])
                   + geodesic_weight * float(d_a[b]) / diameter)
            if val > best_val:
                best_val, best = val, (ai, bi)

    if best is None:
        # no two candidates are far enough apart. The separation rule is
        # there to stop both ends landing on the same end of the cord, and
        # when nothing clears it the mask is degenerate rather than the
        # model wrong, so the caller keeps its own pair.
        return None, None, info

    ai, bi = best
    info["score_first"] = float(score[ai])
    info["score_second"] = float(score[bi])
    info["best_sum"] = float(score[ai] + score[bi])
    info["best_value"] = float(best_val)
    info["geodesic_weight"] = float(geodesic_weight)
    p1 = (int(points[idx[ai]][0]), int(points[idx[ai]][1]))
    p2 = (int(points[idx[bi]][0]), int(points[idx[bi]][1]))
    return p1, p2, info


def predict_pair(model, feature_names, mask, min_separation_frac: float = 0.35,
                 top_k: int = 12, min_one_sided: float = 0.30,
                 tip_snap_steps: float = 2.5, tip_score_ratio: float = 0.5,
                 gate: bool = True, classical_margin: float = 1.5):
    """Score every skeleton pixel and return the two endpoints.

    The pair is chosen jointly: among the candidate pixels, take the pair
    with the highest summed score whose geodesic separation is at least
    ``min_separation_frac`` of the skeleton diameter. Greedy selection, best
    pixel first and then the best far-away one, fails exactly where it
    matters: when the single best pixel sits on the wrong strand of a
    crossing, every later choice is already lost.

    **What the candidate set excludes is what makes this usable.** Scoring
    accuracy is not the quantity the pipeline cares about; the seed's effect
    on the trace is, and the two come apart. A classical miss lands on a
    skeleton tip, which is a safe place to start even when it is the wrong
    end, because the tracker can only walk forwards from there. A learned
    miss used to land in the *middle* of the cord, where the tracker has two
    directions to choose from and immediately commits to one, losing the
    other half. Measured end to end, that asymmetry cost more than the
    better accuracy won: F1 83.7 against the classical detector's 88.1.

    So a candidate now has to look like an end before its score is
    considered. ``one_sidedness`` is already in the feature set and measures
    precisely this: near a real end the skeleton continues in one direction
    only and it approaches 1, while through the middle of a cord the two
    directions cancel and it approaches 0. Candidates below
    ``min_one_sided`` are dropped unless they are skeleton tips, and a
    winner that is not itself a tip is pulled onto a nearby tip when one
    scores comparably.

    **And it defers by default.** Gating alone still lost, 86.4 against
    88.1, because it answered every mask instead of only the ones it is
    better at. Broken down by shape the division is sharp and it is the one
    the model was built for: where an end lies across another strand and
    leaves no skeleton tip it wins clearly (loops 91.4 against 87.1 with a
    92.6 ceiling, coils 100.0 against 89.7), and where tips are plentiful
    but numerous it loses (knots 67.9 against 80.4). The shape label is not
    available at run time, but the thing that actually distinguishes the two
    regimes is: whether the classical pair of farthest tips already looks
    like a pair of ends. So that pair is scored by the same model, and the
    learned answer is used only when it beats the classical one by
    ``classical_margin``. Otherwise the function abstains and the shipped
    detector runs untouched.

    An abstention is not a failure here, it is the design. The two
    detectors fail in different currencies: a classical miss lands on a
    skeleton tip, where the tracker can still only walk forwards, while a
    learned miss lands mid-cord, where it immediately commits to one of two
    directions and loses the other half of the cable. Deferring unless the
    evidence is strong buys the wins on tipless ends without paying for the
    losses elsewhere.
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

    nb_count = X[:, FEATURE_NAMES.index("n_neighbours")]
    one_sided = X[:, FEATURE_NAMES.index("one_sidedness")]
    is_tip = nb_count <= 1.0
    end_like = is_tip | (one_sided >= min_one_sided)
    info["n_end_like"] = int(end_like.sum())

    order = np.argsort(score)[::-1]
    if gate:
        pool = [int(i) for i in order if end_like[i]][:top_k]
    else:
        pool = [int(i) for i in order[:top_k]]

    classical = _farthest_tip_pair(pts, neighbours, nb_count)
    classical_sum = (float(score[classical[0]] + score[classical[1]])
                     if classical is not None else None)
    info["gated"] = bool(gate)
    info["pool"] = len(pool)
    info["classical_sum"] = classical_sum

    if len(pool) < 2:
        # the model is pointing nowhere end-like. Abstaining here is not a
        # failure, it is the whole point of the gate: the classical
        # detector's mistakes are recoverable and this one's are not.
        info["abstain"] = True
        return None, None, info

    need = min_separation_frac * info["diameter"]
    dist_cache = {}
    best, best_sum = None, -1.0
    for a in pool:
        d_a = dist_cache.get(a)
        if d_a is None:
            d_a = _bfs(pts, neighbours, int(a)).astype(np.float32)
            d_a = np.where(d_a < 0, info["diameter"], d_a)
            dist_cache[a] = d_a
        for b in pool:
            if b == a or d_a[b] < need:
                continue
            ssum = float(score[a] + score[b])
            if ssum > best_sum:
                best_sum, best = ssum, (int(a), int(b))

    if best is None:
        # nothing in the pool is far enough from anything else. The mask is
        # degenerate rather than the model wrong, so the shipped detector,
        # which has its own pruning, is the honest answer.
        info["abstain"] = True
        return None, None, info

    info["best_sum"] = float(best_sum)
    if classical_sum is not None and best_sum <= classical_margin * classical_sum:
        # the farthest-tip pair already scores comparably. There is no
        # evidence here that this is one of the masks the model is better
        # at, and the classical detector's mistakes are the recoverable
        # kind, so say nothing.
        info["abstain"] = True
        info["deferred_to_classical"] = True
        return None, None, info

    first, second = best

    # pull a non-tip winner onto a tip that scores nearly as well. This keeps
    # the model's one real advantage, finding an end that leaves no tip,
    # while refusing a mid-cord seed whenever a genuine end is right there.
    snap_r = max(3.0, tip_snap_steps * info["wire_radius"])
    fixed = []
    for idx in (first, second):
        if is_tip[idx]:
            fixed.append(idx)
            continue
        d = dist_cache.get(idx)
        if d is None:
            d = _bfs(pts, neighbours, int(idx)).astype(np.float32)
            d = np.where(d < 0, info["diameter"], d)
        near_tips = np.flatnonzero(is_tip & (d <= snap_r))
        near_tips = [t for t in near_tips
                     if score[t] >= tip_score_ratio * score[idx]]
        if near_tips:
            fixed.append(int(max(near_tips, key=lambda t: score[t])))
            info["snapped_to_tip"] = info.get("snapped_to_tip", 0) + 1
        else:
            fixed.append(idx)
    first, second = fixed[0], fixed[1]
    if first == second:
        info["abstain"] = True
        return None, None, info

    p1 = (int(points[first][0]), int(points[first][1]))
    p2 = (int(points[second][0]), int(points[second][1]))
    info["score_first"] = float(score[first])
    info["score_second"] = float(score[second])
    info["abstain"] = False
    return p1, p2, info
