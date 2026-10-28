"""Train the branch scorer (Model 2) and measure it against the current rule.

The model answers one question, asked once per branch point: of the candidate
continuations available here, which one does the wire actually take? It is a
pointwise binary classifier over candidates, and at run time the tracker
picks the candidate with the highest predicted probability. That is a drop-in
replacement for the fixed formula in `SmartWireTracker._sort_options`:

    direction continuity x1200 + thickness continuity x600
        + centeredness x300 - parallel-line penalty

The headline number is **top-1 accuracy per decision**, not pixel or row
accuracy, and it is always reported next to the same number for the existing
hand-tuned formula on the same held-out decisions. A learned scorer that does
not beat the rule it replaces is not worth shipping, and that comparison is
the only way to know.

Splitting is by *sample*, not by row and not by decision: candidate rows
within a decision are mutually exclusive, and decisions within one image
share the same wire, so anything finer leaks.
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402
from synthetic.branches import FEATURE_NAMES  # noqa: E402

MODEL_PATH = _ROOT / "data" / "models" / "path_model.pkl"
FEATURES_DIR = _ROOT / "data" / "synthetic" / "path" / "features"


def load_shards(d: Path):
    shards = sorted(Path(d).glob("shard_*.npz"))
    if not shards:
        return None
    X, y, g, sid = [], [], [], []
    gbase = 0
    for s in shards:
        z = np.load(s, allow_pickle=True)
        names = [str(n) for n in z["feature_names"]]
        if names != FEATURE_NAMES:
            raise SystemExit(
                f"{s.name} was harvested with a different feature set.\n"
                f"  file: {names}\n  code: {FEATURE_NAMES}\n"
                "Regenerate the path dataset; a model trained on one feature "
                "order and served another fails silently.")
        gg = z["group"].astype(np.int64) + gbase
        gbase = int(gg.max()) + 1 if len(gg) else gbase
        X.append(z["X"])
        y.append(z["y"])
        g.append(gg)
        sid.append(z["sample_id"])
    return (np.concatenate(X), np.concatenate(y).astype(np.int8),
            np.concatenate(g), np.concatenate(sid))


def top1(scores: np.ndarray, y: np.ndarray, group: np.ndarray):
    """Fraction of decisions where the highest-scored candidate is the right one."""
    order = np.argsort(group, kind="stable")
    s, yy, gg = scores[order], y[order], group[order]
    bounds = np.flatnonzero(np.diff(gg)) + 1
    hits = total = 0
    for a, b in zip(np.concatenate([[0], bounds]),
                    np.concatenate([bounds, [len(gg)]])):
        if b - a < 1 or yy[a:b].sum() != 1:
            continue
        total += 1
        hits += int(np.argmax(s[a:b]) == int(np.argmax(yy[a:b])))
    return hits / total if total else 0.0, total


def heuristic_scores(X: np.ndarray) -> np.ndarray:
    """The shipped formula, rebuilt from the harvested features.

    `heuristic_rank` already encodes it, but as a rank it cannot be compared
    across decisions. Recomputing the score keeps the baseline honest and
    independent of that column.
    """
    i = {n: k for k, n in enumerate(FEATURE_NAMES)}
    return (X[:, i["geo_continuity"]] * 1200.0
            + X[:, i["thickness_score"]] * 600.0
            + X[:, i["centeredness"]] * 300.0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--features-dir", default=str(FEATURES_DIR))
    ap.add_argument("--val-fraction", type=float, default=0.2)
    ap.add_argument("--trees", type=int, default=240)
    ap.add_argument("--max-depth", type=int, default=14)
    ap.add_argument("--min-leaf", type=int, default=20)
    ap.add_argument("--drop-rank", action="store_true",
                    help="train without the heuristic_rank feature, to see "
                         "what the model learns on its own")
    ap.add_argument("--out", default=str(MODEL_PATH))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    from sklearn.ensemble import RandomForestClassifier

    data = load_shards(Path(args.features_dir))
    if data is None:
        print(f"No feature shards in {args.features_dir}.\n"
              "Run: python -m synthetic.generate path --count 2000")
        return 1
    X, y, group, sid = data
    print(f"Loaded {len(X)} candidate rows, {len(np.unique(group))} decisions, "
          f"{len(np.unique(sid))} samples, {X.shape[1]} features")

    # split by sample
    rng = np.random.default_rng(args.seed)
    samples = np.unique(sid)
    rng.shuffle(samples)
    n_val = max(1, int(len(samples) * args.val_fraction))
    val_s = set(samples[:n_val].tolist())
    is_val = np.array([s in val_s for s in sid])
    print(f"  train {len(samples) - n_val} samples / {int((~is_val).sum())} rows | "
          f"held out {n_val} samples / {int(is_val.sum())} rows")

    cols = list(range(X.shape[1]))
    if args.drop_rank:
        cols = [c for c in cols if FEATURE_NAMES[c] != "heuristic_rank"]
    used = [FEATURE_NAMES[c] for c in cols]

    t0 = time.time()
    clf = RandomForestClassifier(n_estimators=args.trees, max_depth=args.max_depth,
                                 min_samples_leaf=args.min_leaf, n_jobs=-1,
                                 random_state=args.seed,
                                 class_weight="balanced_subsample")
    clf.fit(X[~is_val][:, cols], y[~is_val])
    print(f"  fitted in {time.time() - t0:.0f}s")

    # the comparison that decides whether this is worth shipping
    p_tr = clf.predict_proba(X[~is_val][:, cols])[:, 1]
    p_va = clf.predict_proba(X[is_val][:, cols])[:, 1]
    h_tr = heuristic_scores(X[~is_val])
    h_va = heuristic_scores(X[is_val])

    a_tr, n_tr = top1(p_tr, y[~is_val], group[~is_val])
    a_va, n_va = top1(p_va, y[is_val], group[is_val])
    b_tr, _ = top1(h_tr, y[~is_val], group[~is_val])
    b_va, _ = top1(h_va, y[is_val], group[is_val])

    print("\nTop-1 accuracy per decision:")
    print(f"  {'':<22}{'learned':>10}{'hand-tuned':>12}{'delta':>9}")
    print(f"  {'train':<22}{a_tr:>10.3f}{b_tr:>12.3f}{a_tr - b_tr:>+9.3f}   ({n_tr} decisions)")
    print(f"  {'held out':<22}{a_va:>10.3f}{b_va:>12.3f}{a_va - b_va:>+9.3f}   ({n_va} decisions)")

    # Where it matters most. Not by option count: `_analyze_flow_options`
    # returns 6 or 7 options at essentially every point, so that split
    # separates nothing. Local mask density is the usable proxy, because it
    # rises exactly where strands lie on top of each other.
    dens = X[:, FEATURE_NAMES.index("local_density")]
    cut = float(np.quantile(dens[is_val], 0.75))
    hard = is_val & (dens >= cut)
    ah = bh = None
    if hard.any():
        ah, nh = top1(clf.predict_proba(X[hard][:, cols])[:, 1], y[hard], group[hard])
        bh, _ = top1(heuristic_scores(X[hard]), y[hard], group[hard])
        print(f"  {'held out, dense (top 25%)':<22}{ah:>10.3f}{bh:>12.3f}{ah - bh:>+9.3f}   ({nh} decisions)")

    # Honesty check on the baseline. The shipped formula also subtracts 800
    # when a candidate sits more than 1.1 wire radii off the momentum axis
    # and parallel groups were detected. If that never happens on this data
    # the reconstruction above is the formula exactly; if it does, the
    # baseline here is optimistic and the comparison has to say so.
    lat = X[:, FEATURE_NAMES.index("lateral_dist")]
    elig = float((lat > 1.1).mean())
    print("")
    if elig < 1e-4:
        print("  baseline is the shipped formula exactly: no candidate in the "
              "set is far enough off-axis for the parallel-line penalty to fire")
    else:
        print(f"  CAVEAT: {100 * elig:.1f}% of candidates could attract the "
              "parallel-line penalty, which this baseline does not model, so "
              "the hand-tuned column is optimistic")

    chance = 1.0 / float(np.median(X[is_val][:, FEATURE_NAMES.index("n_options")]))
    print(f"  chance, at a median of "
          f"{np.median(X[is_val][:, FEATURE_NAMES.index('n_options')]):.0f} options: "
          f"{chance:.3f}")

    imp = sorted(zip(used, clf.feature_importances_), key=lambda t: -t[1])
    print("\n  feature importance: " + ", ".join(f"{n} {v:.2f}" for n, v in imp[:6]))

    verdict = ("the learned scorer beats the shipped formula on held-out decisions"
               if a_va > b_va + 0.005 else
               "the learned scorer does NOT beat the shipped formula; do not ship it")
    print(f"\nVerdict: {verdict}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        pickle.dump({
            "model": clf,
            "feature_names": used,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "n_rows": int(len(X)),
            "n_decisions": int(len(np.unique(group))),
            "n_samples": int(len(samples)),
            "top1_val": a_va,
            "top1_val_heuristic": b_va,
            "top1_val_hard": ah,
            "top1_val_hard_heuristic": bh,
            "trained_by": "synthetic.train_path",
            "beats_heuristic": bool(a_va > b_va + 0.005),
        }, fh)
    mb = out.stat().st_size / 1e6
    print(f"Saved {out} ({mb:.0f} MB)")
    if mb > 25:
        print(f"  WARNING: {mb:.0f} MB is too large to be useful. GitHub refuses "
              "a file over 100 MB, and this model is evaluated once per tracker "
              "step on a CM5. Retrain smaller:")
        print("    python -m synthetic.train_path --trees 60 --max-depth 10 "
              "--min-leaf 200")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
