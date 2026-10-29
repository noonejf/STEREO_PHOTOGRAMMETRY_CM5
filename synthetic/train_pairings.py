"""Train the crossing-pairing model used by `processing/graph_tracer.py`.

The graph tracer asks one question at each node of the mask's skeleton:
which two of the branches meeting here are the same strand passing
through. The shipped answer is geometry, tangent agreement plus width
agreement. This trains a replacement on labels that are exact, because
the generator knows the true centreline and therefore the true pairing.

Measured before any model was fitted, which is the order this project
works in: handing the tracer the **true** pairing lifts the end-to-end
true-path F1 from 94.6 to 96.9 overall, and from 83.4 to 97.2 on knots.
That is the budget. A model is only written with ``beats_geometric`` set
if it actually collects some of it end to end, not if it merely wins at
classifying pairs, which is the mistake that cost two earlier models.

    python3 -m synthetic.train_pairings --count 600
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402  (console encoding fix)
from synthetic import generate, pairings  # noqa: E402
from synthetic.evaluate import path_agreement  # noqa: E402
from processing import graph_tracer as grt  # noqa: E402

MODEL_PATH = _ROOT / "data" / "models" / "pair_model.pkl"
SEED_BASE = 800_000          # never overlaps the benchmark seeds (50k, 60k)


def harvest_many(count, seed_base, size, verbose_every=50):
    X, y, groups = [], [], []
    t0 = time.time()
    for i in range(count):
        mask, xy, meta, _ = generate.make_path_scene(seed_base + i, size)
        r = float(meta.get("base_radius_px", 6.0))
        try:
            graph = grt.SkeletonGraph(mask, r)
            xi, yi, _ = pairings.harvest(graph, xy)
        except Exception:                      # noqa: BLE001
            continue
        if len(xi) == 0:
            continue
        X.append(xi)
        y.append(yi)
        groups.append(np.full(len(xi), i, np.int32))
        if verbose_every and (i + 1) % verbose_every == 0:
            n = sum(len(a) for a in X)
            print(f"  harvest {i + 1}/{count}  {n} pairs  "
                  f"{(i + 1) / max(time.time() - t0, 1e-6):.1f}/s", flush=True)
    if not X:
        return (np.zeros((0, pairings.N_FEATURES), np.float32),
                np.zeros((0,), np.int8), np.zeros((0,), np.int32))
    return np.concatenate(X), np.concatenate(y), np.concatenate(groups)


def end_to_end(model, count, seed_base, size, max_scenes=40):
    """Trace with the geometric rule and with the model, and compare."""
    from processing.endpoint_detector import EndpointDetector
    import contextlib
    import io as _io

    geo, learned, shapes = [], [], []
    for i in range(min(count, max_scenes)):
        mask, xy, meta, _ = generate.make_path_scene(seed_base + i, size)
        h, w = mask.shape[:2]
        r = float(meta.get("base_radius_px", 6.0))
        shapes.append(meta["shape"])
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            det = EndpointDetector(mask, side="left")
            a, b = det.detect_endpoints(method="skeleton", save_debug=False)

        p, _ = grt.trace(mask, a, b, wire_radius=r)
        geo.append(path_agreement(p or [], xy, (w, h), r)["f1"])

        fn = make_score_fn(model)
        p, _ = grt.trace(mask, a, b, wire_radius=r, score_fn=fn)
        learned.append(path_agreement(p or [], xy, (w, h), r)["f1"])
    return np.asarray(geo), np.asarray(learned), shapes


def make_score_fn(model, threshold=0.0):
    """Wrap a fitted model as a `graph_tracer` score function."""
    def score(graph, nid, e1, e2):
        f = pairings.pair_features(graph, nid, e1, e2)
        if f is None:
            return -1.0
        p = float(model.predict_proba(f.reshape(1, -1))[0, 1])
        return p if p > threshold else -1.0
    return score


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=600)
    ap.add_argument("--size", type=int, nargs=2, default=(960, 720))
    ap.add_argument("--seed-base", type=int, default=SEED_BASE)
    ap.add_argument("--val-fraction", type=float, default=0.2)
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--eval-scenes", type=int, default=40)
    ap.add_argument("--out", default=str(MODEL_PATH))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    size = tuple(args.size)
    print(f"harvesting {args.count} scenes from seed {args.seed_base}")
    X, y, g = harvest_many(args.count, args.seed_base, size)
    if len(X) < 200:
        print("not enough pairs harvested")
        return 1
    print(f"  {len(X)} candidate pairs, {int(y.sum())} of them true "
          f"({100 * y.mean():.1f}%)")

    # split by SCENE, never by pair: two pairs at the same node are not
    # independent and a pair-level split leaks the answer
    rng = np.random.default_rng(args.seed)
    scenes = np.unique(g)
    rng.shuffle(scenes)
    n_val = max(1, int(len(scenes) * args.val_fraction))
    val_scenes = set(scenes[:n_val].tolist())
    is_val = np.array([s in val_scenes for s in g])
    print(f"  train {int((~is_val).sum())} pairs / "
          f"{len(scenes) - n_val} scenes, held out {int(is_val.sum())} pairs "
          f"/ {n_val} scenes")

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    clf = HistGradientBoostingClassifier(
        max_iter=args.iters, learning_rate=0.08, max_leaf_nodes=31,
        min_samples_leaf=20, l2_regularization=1.0,
        early_stopping=True, n_iter_no_change=20, random_state=args.seed)
    t0 = time.time()
    clf.fit(X[~is_val], y[~is_val])
    print(f"  fitted in {time.time() - t0:.0f}s, {clf.n_iter_} rounds")

    for name, m in (("train", ~is_val), ("held out", is_val)):
        if m.sum() and 0 < y[m].sum() < m.sum():
            print(f"  pair AUC, {name:<9} {roc_auc_score(y[m], clf.predict_proba(X[m])[:, 1]):.3f}")

    # the only number that decides
    print(f"\nend to end on {args.eval_scenes} fresh benchmark scenes "
          f"(seed 50000, never harvested)")
    geo, learned, shapes = end_to_end(clf, args.eval_scenes, 50_000, size,
                                      args.eval_scenes)
    wins = int((learned > geo + 0.02).sum())
    losses = int((geo > learned + 0.02).sum())
    print(f"  geometric {100 * geo.mean():.1f}   learned "
          f"{100 * learned.mean():.1f}   "
          f"({wins} wins, {losses} losses, {len(geo) - wins - losses} ties)")
    for sh in sorted(set(shapes)):
        idx = [i for i, s in enumerate(shapes) if s == sh]
        print(f"    {sh:<10} n={len(idx):<3} "
              f"{100 * geo[idx].mean():5.1f} / {100 * learned[idx].mean():5.1f}")

    beats = bool(learned.mean() > geo.mean() + 0.002 and wins >= losses)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        pickle.dump({
            "model": clf,
            "feature_names": pairings.FEATURE_NAMES,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "n_pairs": int(len(X)),
            "n_scenes": int(len(scenes)),
            "f1_geometric": float(geo.mean()),
            "f1_learned": float(learned.mean()),
            "beats_geometric": beats,
        }, fh)
    print(f"\nSaved {out} ({out.stat().st_size / 1e6:.1f} MB), "
          f"beats_geometric={beats}")
    print(json.dumps({"geometric": round(float(geo.mean()), 4),
                      "learned": round(float(learned.mean()), 4)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
