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

    tr = np.asarray(list(trace_pts), dtype=float).reshape(-1, 2)
    tol = max(2.5 * float(radius), 6.0)
    if len(tr) == 0 or len(gt) == 0:
        return {"recall": 0.0, "precision": 0.0, "f1": 0.0, "tol_px": tol}

    d_gt_to_tr, _ = cKDTree(tr).query(gt)
    d_tr_to_gt, _ = cKDTree(gt).query(tr)
    recall = float(np.mean(d_gt_to_tr <= tol))
    precision = float(np.mean(d_tr_to_gt <= tol))
    f1 = 2 * recall * precision / max(recall + precision, 1e-9)
    return {"recall": recall, "precision": precision, "f1": f1, "tol_px": tol}
