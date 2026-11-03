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
