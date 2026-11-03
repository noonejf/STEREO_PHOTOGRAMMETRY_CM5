"""Does the trace walk a doubled stretch of cable twice, once per strand?

Where the cord doubles back in a tight hairpin the two sides touch and
the mask fuses. The skeleton of that fusion is a single line up the
middle, so a tracer that follows the skeleton walks the stretch once and
reports half its length. Arc length in metres is one of the payload's
outputs, so this is a measurement error and not a drawing defect.

A doubled stretch is identified from the mask, not the skeleton: the
distance transform there reads about twice the cable's own radius,
because two cords of radius r with centres d apart make a shape of
half-width d/2 + r. The same arithmetic says where the strands are, at
plus and minus (DT - r) from the skeleton.

Reported per scene:

  wide px       skeleton pixels whose width says two strands
  covered       of those, how many have trace points on BOTH sides
  both sides    the fraction, which is the number this tool exists for
  len ratio     traced arc length against the true centreline

    python3 tools/check_fused_strands.py --count 20

Writes nothing but its report.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402
from synthetic import generate  # noqa: E402
from processing.endpoint_detector import EndpointDetector  # noqa: E402
from processing import graph_tracer as grt  # noqa: E402


def arclen(c):
    c = np.asarray(c, dtype=float)
    return float(np.sum(np.hypot(*np.diff(c, axis=0).T))) if len(c) > 1 else 0.0


def both_sides(graph, path, nominal, wide_factor, tol):
    """Fraction of wide skeleton pixels with trace points on either side.

    A skeleton pixel in a doubled stretch should have the trace passing on
    both of its flanks. Sidedness is measured against the local skeleton
    direction, so it does not depend on which way the walk went.
    """
    sk_y, sk_x = np.nonzero(graph.skel)
    if not len(sk_y):
        return 0.0, 0
    dt = graph.dt[sk_y, sk_x]
    wide = dt > wide_factor * nominal
    if not wide.any():
        return float("nan"), 0
    sx, sy = sk_x[wide].astype(float), sk_y[wide].astype(float)

    P = np.asarray(path, dtype=float)
    if len(P) < 3:
        return 0.0, int(wide.sum())
    from scipy.spatial import cKDTree
    tree = cKDTree(P)

    # local skeleton direction from the nearest few skeleton pixels
    sk_all = np.column_stack([sk_x, sk_y]).astype(float)
    sk_tree = cKDTree(sk_all)

    hit = 0
    for x, y in zip(sx, sy):
        _, nb = sk_tree.query([x, y], k=min(9, len(sk_all)))
        loc = sk_all[np.atleast_1d(nb)] - np.array([x, y])
        if len(loc) < 3:
            continue
        u, s, vt = np.linalg.svd(loc - loc.mean(axis=0), full_matrices=False)
        t = vt[0]
        n = np.array([-t[1], t[0]])
        near = P[tree.query_ball_point([x, y], r=tol)]
        if len(near) < 2:
            continue
        proj = (near - np.array([x, y])) @ n
        if (proj > 0.8).any() and (proj < -0.8).any():
            hit += 1
    return hit / float(wide.sum()), int(wide.sum())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--seed-base", type=int, default=50_000)
    ap.add_argument("--size", type=int, nargs=2, default=(960, 720))
    ap.add_argument("--wide-factor", type=float, default=grt.WIDE_FACTOR)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    rows = []
    for i in range(args.count):
        seed = args.seed_base + i
        mask, xy, meta, _ = generate.make_path_scene(seed, tuple(args.size))
        h, w = mask.shape[:2]
        r = float(meta.get("base_radius_px", 6.0))
        gt = np.asarray(xy, dtype=float)
        gt = gt[(gt[:, 0] >= 0) & (gt[:, 0] < w)
                & (gt[:, 1] >= 0) & (gt[:, 1] < h)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            a, b = EndpointDetector(mask, side="left").detect_endpoints(
                "skeleton", save_debug=False)
        path, _ = grt.trace(mask, a, b, wire_radius=r)
        graph = grt.SkeletonGraph(mask, r)
        nominal = (float(np.median(graph.dt[graph.skel > 0]))
                   if (graph.skel > 0).any() else r)
        frac, n_wide = both_sides(graph, path or [], nominal,
                                  args.wide_factor, max(3.0, 2.0 * nominal))
        ratio = arclen(path or []) / max(arclen(gt), 1e-9)
        rows.append((seed, meta["shape"], n_wide, frac, ratio))
        if args.verbose:
            print(f"  {seed} {meta['shape']:<9} wide {n_wide:5d} "
                  f"both sides {100 * frac:5.1f}%  len {ratio:.3f}", flush=True)

    have = [r_ for r_ in rows if r_[2] > 0 and np.isfinite(r_[3])]
    print(f"\n  {len(have)} of {len(rows)} scenes contain a doubled stretch")
    if have:
        f = np.array([r_[3] for r_ in have])
        n = np.array([r_[2] for r_ in have])
        print(f"  wide skeleton pixels per scene: median {int(np.median(n))}")
        print(f"  of those, walked on both sides: mean {100 * f.mean():.1f}%, "
              f"median {100 * np.median(f):.1f}%")
    lr = np.array([r_[4] for r_ in rows])
    print(f"  traced length against the truth: mean {lr.mean():.3f}")
    print("\n  both sides at 100% would mean every doubled stretch is walked "
          "once per strand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
