"""Turn a mask plus its ground-truth path into labelled branch decisions.

This is the tool the camera system report lists as a blocker for the second
model: "building the offline tooling that converts a verified path into
labeled (candidate-features, chosen-branch) training examples at each branch
point along it". With real data it needs a human-verified path, which is why
the path dataset has three samples. With synthetic data the path is known by
construction, so the labelling is exact and free.

The features are computed by driving the real `SmartWireTracker` along the
ground-truth path and asking it, at each step, what candidates it sees. They
are therefore identical by construction to what the tracker computes at
inference time. Re-implementing them here would let the two drift apart, and
a scorer trained on features that differ from the ones it is served is a
failure that produces plausible numbers and wrong paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from processing.smart_wire_tracker import SmartWireTracker  # noqa: E402


#: Order matters: `train_path.py` writes it into the model file and the
#: runtime scorer reads it back, so the two cannot silently disagree.
FEATURE_NAMES = [
    "geo_continuity",      # dot(step direction, momentum), -1 to 1
    "turn_cos_sq",         # a second, differently shaped view of the same turn
    "centeredness",        # dt at candidate, in wire radii
    "thickness_delta",     # signed dt change, in wire radii
    "thickness_score",     # exp(-|dt change| / 5), the tracker's own form
    "lateral_dist",        # offset perpendicular to momentum, in wire radii
    "forward_proj",        # projection along momentum, in search radii
    "step_dist",           # distance to the candidate, in search radii
    "n_options",           # how many competing options at this point
    "local_density",       # mask fill in a disc around the candidate
    "dt_here",             # dt at the current point, in wire radii
    "visited",             # 1 if the candidate falls in already-covered area
    "heuristic_rank",      # rank under the current hand-tuned formula, 0 = best
]
N_FEATURES = len(FEATURE_NAMES)


def _heuristic_scores(tracker, current, options, momentum):
    """The scores the shipped hand-tuned formula would assign.

    Used only as a feature, so the model can learn where to disagree with the
    heuristic rather than having to rediscover it from nothing.
    """
    cur = np.asarray(current, dtype=float)
    dt_here = float(tracker.distance_transform[int(current[1]), int(current[0])])
    out = []
    for opt in options:
        d = np.asarray(opt, dtype=float) - cur
        n = np.linalg.norm(d)
        d = d / n if n > 0 else d
        geo = float(np.dot(d, momentum)) if np.linalg.norm(momentum) > 0 else 0.0
        dt_o = float(tracker.distance_transform[int(opt[1]), int(opt[0])])
        thick = float(np.exp(-abs(dt_here - dt_o) / 5.0))
        centre = dt_o / max(tracker.wire_radius, 1.0)
        out.append(geo * 1200 + thick * 600 + centre * 300)
    return np.asarray(out)


def _features_for(tracker, current, options, momentum, density_r=None):
    """Feature matrix for the options available at one point."""
    cur = np.asarray(current, dtype=float)
    h, w = tracker.mask.shape
    wr = max(float(tracker.wire_radius), 1.0)
    sr = max(float(tracker.search_radius), 1.0)
    cx = int(np.clip(current[0], 0, w - 1))
    cy = int(np.clip(current[1], 0, h - 1))
    dt_here = float(tracker.distance_transform[cy, cx])

    mom = np.asarray(momentum, dtype=float)
    have_mom = np.linalg.norm(mom) > 1e-6
    perp = np.array([-mom[1], mom[0]]) if have_mom else np.zeros(2)

    if density_r is None:
        density_r = int(max(6, round(wr * 2.0)))

    ranks = np.argsort(np.argsort(-_heuristic_scores(tracker, current, options, momentum)))

    rows = []
    for k, opt in enumerate(options):
        ox = int(np.clip(opt[0], 0, w - 1))
        oy = int(np.clip(opt[1], 0, h - 1))
        d = np.asarray(opt, dtype=float) - cur
        dist = float(np.linalg.norm(d))
        u = d / dist if dist > 0 else d

        geo = float(np.dot(u, mom)) if have_mom else 0.0
        dt_o = float(tracker.distance_transform[oy, ox])

        y0, y1 = max(0, oy - density_r), min(h, oy + density_r + 1)
        x0, x1 = max(0, ox - density_r), min(w, ox + density_r + 1)
        win = tracker.mask[y0:y1, x0:x1]
        density = float((win > 0).mean()) if win.size else 0.0

        visited = 0.0
        if tracker.visited_map[oy, ox] > 0:
            visited = 1.0

        rows.append([
            geo,
            geo * abs(geo),
            dt_o / wr,
            (dt_o - dt_here) / wr,
            float(np.exp(-abs(dt_here - dt_o) / 5.0)),
            float(abs(np.dot(d, perp))) / wr if have_mom else 0.0,
            float(np.dot(d, mom)) / sr if have_mom else 0.0,
            dist / sr,
            float(len(options)),
            density,
            dt_here / wr,
            visited,
            float(ranks[k]),
        ])
    return np.asarray(rows, dtype=np.float32)


def harvest(mask: np.ndarray, path_xy: np.ndarray, min_options: int = 2,
            stride: int = 1, keep_easy: float = 0.0, rng=None):
    """Walk a known-good path over a mask and label every decision.

    Parameters
    ----------
    mask
        Binary mask, the same one the tracker would be given.
    path_xy
        (N, 2) ground-truth path in pixel coordinates, ordered end to end.
    min_options
        Only emit a point that offered at least this many competing options.
        With the default of 2 the output is branch decisions only, which is
        what the scorer has to get right; easy straight runs teach it nothing
        and would dominate the set.
    keep_easy
        Fraction of single-option points to keep anyway, as negative-free
        context. 0 by default.

    Returns
    -------
    dict with ``X`` (M, N_FEATURES), ``y`` (M,) in {0, 1}, ``group`` (M,)
    identifying which decision each row belongs to, and counters.
    """
    rng = rng or np.random.default_rng()
    path_xy = np.asarray(path_xy, dtype=float)
    if len(path_xy) < 12:
        return _empty()

    # The tracker rescales a thick mask internally. Build it with the real
    # endpoints so wire_radius, step_size and search_radius come out the same
    # as they will at inference.
    start = tuple(int(v) for v in path_xy[0])
    end = tuple(int(v) for v in path_xy[-1])
    try:
        tracker = SmartWireTracker(mask, start, end)
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        # Swallowing this silently cost 15 of the first 24 samples before the
        # cause was found: a Unicode print inside the constructor on a cp1252
        # console. Anything that fails here is counted and surfaced.
        out = _empty()
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    scale = getattr(tracker, "_internal_scale", 1.0)
    pts = path_xy * scale
    hgt, wid = tracker.mask.shape
    inside = (pts[:, 0] >= 0) & (pts[:, 0] < wid) & (pts[:, 1] >= 0) & (pts[:, 1] < hgt)
    pts = pts[inside]
    if len(pts) < 12:
        return _empty()

    step = max(1.0, float(tracker.step_size))
    X, y, group = [], [], []
    g = 0
    n_branch = 0
    n_points = 0
    n_missed = 0

    # advance along the ground truth in tracker-sized steps
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    targets = np.arange(0.0, arc[-1], step * stride)

    tracker.path = []
    for ti, s in enumerate(targets[:-1]):
        here = np.array([np.interp(s, arc, pts[:, 0]), np.interp(s, arc, pts[:, 1])])
        nxt = np.array([np.interp(s + step, arc, pts[:, 0]),
                        np.interp(s + step, arc, pts[:, 1])])
        cur = (int(round(here[0])), int(round(here[1])))

        # keep the tracker's own history so momentum matches inference
        tracker.path.append(cur)
        tracker.visited_map[max(0, cur[1] - 2):cur[1] + 3,
                            max(0, cur[0] - 2):cur[0] + 3] = 1
        if ti < 5:
            continue

        momentum = tracker._get_momentum_direction()
        cands = tracker._find_candidates(cur)
        if not cands:
            continue
        end_dir = tracker._get_direction_to_end(cur)
        options = tracker._analyze_flow_options(cur, np.array(cands), momentum, end_dir)
        if len(options) == 0:
            continue
        n_points += 1

        if len(options) < min_options:
            if keep_easy <= 0 or rng.random() > keep_easy:
                continue
        else:
            n_branch += 1

        opts = np.asarray(options, dtype=float)
        d = np.linalg.norm(opts - nxt[None, :], axis=1)
        winner = int(np.argmin(d))
        # If no option is near the ground-truth continuation the path left the
        # mask, usually at a break. Labelling a winner there would teach the
        # scorer to pick an arbitrary branch.
        if d[winner] > max(step * 1.6, tracker.wire_radius * 1.2):
            n_missed += 1
            continue

        feats = _features_for(tracker, cur, options, momentum)
        lab = np.zeros(len(options), dtype=np.int8)
        lab[winner] = 1
        X.append(feats)
        y.append(lab)
        group.append(np.full(len(options), g, dtype=np.int32))
        g += 1

    if not X:
        return _empty()

    return {
        "X": np.concatenate(X).astype(np.float32),
        "y": np.concatenate(y).astype(np.int8),
        "group": np.concatenate(group),
        "n_decisions": g,
        "n_branch_points": n_branch,
        "n_points": n_points,
        "n_unlabelled": n_missed,
        "internal_scale": float(scale),
    }


def _empty():
    return {"X": np.zeros((0, N_FEATURES), np.float32),
            "y": np.zeros((0,), np.int8),
            "group": np.zeros((0,), np.int32),
            "n_decisions": 0, "n_branch_points": 0, "n_points": 0,
            "n_unlabelled": 0, "internal_scale": 1.0}
