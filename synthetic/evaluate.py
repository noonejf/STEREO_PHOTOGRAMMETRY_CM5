"""Agreement between a traced path and the ground-truth centreline.

The tracker reports its own ``coverage``: the fraction of mask pixels its
path visits. That number measures completeness, not correctness, and on a
tangled cord the two come apart: a trace that takes the wrong strand at a
crossing and wanders can visit MORE of the mask than the true path does,
and in the first endpoint benchmark the classical detector repeatedly beat
the ceiling set by the true endpoints that way. A benchmark that rewards
wandering selects for the wrong product.

Synthetic scenes carry the true centreline, so correctness can be measured
directly:

- recall: fraction of true path points (inside the frame) that have a trace
  point within tolerance. Punishes stopping early and missing branches.
- precision: fraction of trace points within tolerance of the true path.
  Punishes wandering off the cord's real course.
- f1: harmonic mean, the single number to rank by.

Tolerance scales with the cord radius, since a trace is only ever as exact
as the ridge of the mask it walks.
"""
from __future__ import annotations

import numpy as np

try:
    from scipy.stats import spearmanr
    from scipy.spatial import cKDTree
except ImportError:  # pragma: no cover
    cKDTree = None


def _densify(tr, step=1.0):
    """Fill in the pixels between consecutive vertices before scoring.

    Without this the metric is blind to the one failure that matters most.
    A tracer that returns two points a hundred pixels apart has drawn a
    straight line across whatever lies between them, and scoring only the
    listed vertices never looks there: both ends sit on the cable, so the
    jump is free. Measured on one coil scene, the graph tracer returned a
    113 px jump straight across the spiral and still scored a perfect
    100.0, because the 93 pixels it invented were never in the list.

    Precision is what this restores. A jump now contributes a run of
    points far from the true centreline, which is exactly what it is.
    """
    if len(tr) < 2:
        return tr
    out = [tr[0]]
    for a, b in zip(tr[:-1], tr[1:]):
        d = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        n = int(d / step)
        if n > 1:
            t = np.linspace(0.0, 1.0, n + 1)[1:-1].reshape(-1, 1)
            out.extend(a + (b - a) * t)
        out.append(b)
    return np.asarray(out, dtype=float)


def parametric_agreement(trace_pts, gt_xy, size, radius: float,
                         n: int = 200) -> dict:
    """Score the trace the way stage 5 actually consumes it.

    `path_agreement` treats a trace as a **set** of points and asks how
    much of the cable it touches. Stage 5 treats it as a
    **parametrisation**: `compute_disparity_from_wire_paths` pairs the
    point at i% along the left path with the point at i% along the right
    one. A trace that covers every pixel of the cable in a scrambled
    order scores a perfect F1 and produces a correspondence that is
    nonsense, which is not a hypothetical: one knot scene scored 100.0
    while reversing direction 32 times.

    So both curves are resampled to ``n`` points by arc length and
    compared position by position. ``within`` is the fraction of those
    positions where the trace is within tolerance of where it should be,
    and it is the number to rank tracers by, because it is the only one
    that fails when either coverage or order fails. The trace is compared
    in both directions and the better one kept, since which end is called
    the start is a convention.
    """
    gt = np.asarray(gt_xy, dtype=float)
    w, h = size
    inside = (gt[:, 0] >= 0) & (gt[:, 0] < w) & (gt[:, 1] >= 0) & (gt[:, 1] < h)
    gt = gt[inside]
    tr = np.asarray(list(trace_pts), dtype=float).reshape(-1, 2)
    tol = max(2.5 * float(radius), 6.0)
    if len(tr) < 2 or len(gt) < 2:
        return {"within": 0.0, "median_px": float("inf"), "tol_px": tol}

    def resample(c, k):
        d = np.r_[0.0, np.cumsum(np.hypot(*np.diff(c, axis=0).T))]
        if d[-1] <= 0:
            return np.repeat(c[:1], k, axis=0)
        u = np.linspace(0.0, d[-1], k)
        return np.c_[np.interp(u, d, c[:, 0]), np.interp(u, d, c[:, 1])]

    g = resample(gt, n)
    best = None
    for cand in (resample(tr, n), resample(tr[::-1], n)):
        err = np.hypot(*(cand - g).T)
        score = (float(np.mean(err <= tol)), -float(np.median(err)))
        if best is None or score > best[0]:
            best = (score, err)
    (within, _), err = best

    # Order and pacing are two different failures and must be reported
    # separately, because conflating them reads as a catastrophe that is
    # not there. On one tangle the combined score said 8% while the
    # traversal order was essentially perfect, rank correlation 0.997:
    # the trace simply ran 11% longer than the centreline because it
    # wiggles, which shifts its pacing by 1.7% of the length, and 1.7% of
    # 2500 px is 42 px against a 10 px tolerance.
    #
    # `order` is the one that matters and the one that was broken: it
    # asks whether the trace visits the cable in sequence. Stage 5 pairs
    # i% of the left path with i% of the right, so a scrambled order
    # pairs the wrong points. Pacing differences do not have the same
    # effect, because both views are traced by the same code on similar
    # masks and their pacing moves together; what a pacing number
    # measured against the ground truth bounds is a worst case, not the
    # error stage 5 makes.
    tree = cKDTree(gt)
    _, idx = tree.query(tr)
    idx = np.asarray(idx, dtype=float)
    if len(idx) >= 3 and np.ptp(idx) > 0:
        rho = abs(float(spearmanr(np.arange(len(idx)), idx).statistic))
        d = np.diff(idx)
        d = d[np.abs(d) > 0]
        fwd = float(np.mean(d > 0)) if len(d) else 1.0
        monotone = max(fwd, 1.0 - fwd)
    else:
        rho, monotone = 0.0, 0.0

    return {"within": within, "median_px": float(np.median(err)),
            "order": rho, "monotone": monotone, "tol_px": tol}


def path_agreement(trace_pts, gt_xy, size, radius: float) -> dict:
    """Score a traced path against the true centreline.

    Args:
        trace_pts: (N, 2) trace in (x, y) pixels, as `SmartWireTracker.path`.
        gt_xy: (M, 2) true centreline in the same coordinates.
        size: (w, h) of the frame; ground truth outside it is not required.
        radius: cord radius in pixels; tolerance is ``max(2.5 * radius, 6)``.

    Returns:
        dict with recall, precision, f1 and the tolerance used. All zeros if
        the trace is empty.
    """
    if cKDTree is None:
        raise RuntimeError("scipy is required for path agreement")

    gt = np.asarray(gt_xy, dtype=float)
    w, h = size
    inside = (gt[:, 0] >= 0) & (gt[:, 0] < w) & (gt[:, 1] >= 0) & (gt[:, 1] < h)
    gt = gt[inside]

    tr = _densify(np.asarray(list(trace_pts), dtype=float).reshape(-1, 2))
    tol = max(2.5 * float(radius), 6.0)
    if len(tr) == 0 or len(gt) == 0:
        return {"recall": 0.0, "precision": 0.0, "f1": 0.0, "tol_px": tol}

    d_gt_to_tr, _ = cKDTree(tr).query(gt)
    d_tr_to_gt, _ = cKDTree(gt).query(tr)
    recall = float(np.mean(d_gt_to_tr <= tol))
    precision = float(np.mean(d_tr_to_gt <= tol))
    f1 = 2 * recall * precision / max(recall + precision, 1e-9)
    return {"recall": recall, "precision": precision, "f1": f1, "tol_px": tol}
