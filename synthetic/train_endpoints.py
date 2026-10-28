"""Train the endpoint finder, and measure it against the shipped detector.

This is the half of the path capability that the branch scorer does not
cover. Walking the mask is useless without knowing where to start and where
to stop, and the shipped detector cannot find a third of the endpoints at
all: it looks for skeleton tips, and an end that happens to lie across
another part of the cord leaves no tip. Measured over 80 synthetic masks,
47 of 138 true endpoints had no tip within two wire radii, concentrated in
the shapes that matter, 83% of loop ends and 71% of knot ends.

Scoring every skeleton pixel instead of only the tips raises the ceiling
from 66% to 100% on the same masks. See `synthetic/endpoints.py`.

Harvesting and training are separate phases and both resume, because this
runs on CPU and takes a while:

    python -m synthetic.train_endpoints --harvest          # writes shards
    python -m synthetic.train_endpoints                    # trains, resumable
    python -m synthetic.train_endpoints --resume           # continue after Ctrl-C

The number that decides is median endpoint error in pixels against the
classical detector on held-out masks, printed side by side.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402
from synthetic import endpoints as EP  # noqa: E402
from synthetic.checkpoint import train_forest  # noqa: E402

DATA = _ROOT / "data" / "synthetic" / "path"
SHARD_DIR = DATA / "endpoint_features"
MODEL_PATH = _ROOT / "data" / "models" / "endpoint_model.pkl"
CKPT_PATH = _ROOT / "data" / "models" / "endpoint_model.ckpt"
SHARD_SIZE = 150

#: Background skeleton pixels kept per positive. A mask has about 1800
#: skeleton pixels and exactly two endpoints, so without this the positive
#: class is 0.1% and the forest learns to answer "no" everywhere.
NEG_PER_POS = 400


def harvest_all(data: Path, shard_dir: Path, limit=None, resume=True):
    masks = sorted((data / "masks").glob("*.png"))
    if limit:
        masks = masks[:limit]
    shard_dir.mkdir(parents=True, exist_ok=True)

    done = set()
    if resume:
        for s in shard_dir.glob("shard_*.npz"):
            z = np.load(s, allow_pickle=True)
            done.update(str(v) for v in z["sample_id"])
        if done:
            print(f"  resuming harvest, {len(done)} samples already done")

    todo = [m for m in masks if m.stem not in done]
    if not todo:
        print("  harvest already complete")
        return

    rng = np.random.default_rng(0)
    buf = {"X": [], "y": [], "sid": []}
    shard_i = len(list(shard_dir.glob("shard_*.npz")))
    t0 = time.time()
    stats = {"reachable": 0, "ends": 0}

    for i, mp in enumerate(todo, 1):
        pj = data / "paths" / (mp.stem + ".json")
        if not pj.exists():
            continue
        mask = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
        gt = np.array(json.load(open(pj, encoding="utf-8"))["path"])
        if mask is None or len(gt) < 2:
            continue
        h = EP.harvest(mask, gt)
        if len(h["X"]) == 0:
            continue
        stats["ends"] += 2
        stats["reachable"] += sum(h["reachable"])

        pos = np.flatnonzero(h["y"] == 1)
        # everything inside the tolerance but not the chosen pixel is neither
        # a clean positive nor a clean negative, so it is dropped
        neg_pool = np.flatnonzero((h["y"] == 0) & (~h["ambiguous"]))
        if len(pos) == 0 or len(neg_pool) == 0:
            continue
        k = min(len(neg_pool), NEG_PER_POS * len(pos))
        neg = rng.choice(neg_pool, k, replace=False)
        take = np.concatenate([pos, neg])
        buf["X"].append(h["X"][take])
        buf["y"].append(h["y"][take])
        buf["sid"].append(np.array([mp.stem] * len(take)))

        if len(buf["sid"]) >= SHARD_SIZE:
            shard_i = _flush(shard_dir, buf, shard_i)
        if i % 50 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  harvest {i}/{len(todo)}  {i/max(el,1e-6):.1f}/s  "
                  f"eta {(len(todo)-i)/max(i/max(el,1e-6),1e-9)/60:.1f} min", flush=True)
    _flush(shard_dir, buf, shard_i)
    if stats["ends"]:
        print(f"  endpoints with a skeleton pixel in range: "
              f"{stats['reachable']}/{stats['ends']} = "
              f"{100*stats['reachable']/stats['ends']:.0f}%")


def _flush(shard_dir, buf, shard_i):
    if not buf["X"]:
        return shard_i
    np.savez_compressed(shard_dir / f"shard_{shard_i:03d}.npz",
                        X=np.concatenate(buf["X"]),
                        y=np.concatenate(buf["y"]),
                        sample_id=np.concatenate(buf["sid"]),
                        feature_names=np.array(EP.FEATURE_NAMES))
    for k in buf:
        buf[k].clear()
    return shard_i + 1


def load_shards(shard_dir: Path):
    shards = sorted(Path(shard_dir).glob("shard_*.npz"))
    if not shards:
        return None
    X, y, sid = [], [], []
    for s in shards:
        z = np.load(s, allow_pickle=True)
        names = [str(v) for v in z["feature_names"]]
        if names != EP.FEATURE_NAMES:
            raise SystemExit(
                f"{s.name} was harvested with a different feature set.\n"
                f"  file: {names}\n  code: {EP.FEATURE_NAMES}\n"
                "Delete the shards and harvest again.")
        X.append(z["X"])
        y.append(z["y"])
        sid.append(z["sample_id"])
    return np.concatenate(X), np.concatenate(y).astype(np.int8), np.concatenate(sid)


def evaluate(model, feature_names, data: Path, sample_ids, limit=40):
    """Median endpoint error, learned against the shipped detector."""
    from processing.endpoint_detector import EndpointDetector

    def pair_error(pred, truth):
        if pred[0] is None or pred[1] is None:
            return None
        a = np.linalg.norm(np.array(pred[0]) - truth[0]) + np.linalg.norm(np.array(pred[1]) - truth[1])
        b = np.linalg.norm(np.array(pred[0]) - truth[1]) + np.linalg.norm(np.array(pred[1]) - truth[0])
        return min(a, b) / 2.0

    # Shape is read back from the index so the report can be split by it.
    # The aggregate alone misleads: the path dataset is 40% knot and tangle
    # by design, which is right for the branch scorer and badly
    # unrepresentative of the real tether, a near-straight cable.
    shapes = {}
    idx_path = data / "index.jsonl"
    if idx_path.exists():
        for line in open(idx_path, encoding="utf-8"):
            rec = json.loads(line)
            shapes[rec["id"]] = rec.get("shape", "?")

    learned, classical, times = [], [], []
    per_shape = {}
    for sid in list(sample_ids)[:limit]:
        mp = data / "masks" / f"{sid}.png"
        pj = data / "paths" / f"{sid}.json"
        if not mp.exists() or not pj.exists():
            continue
        mask = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
        gt = np.array(json.load(open(pj, encoding="utf-8"))["path"])
        truth = (gt[0], gt[-1])

        t0 = time.time()
        p1, p2, _ = EP.predict_pair(model, feature_names, mask)
        times.append(time.time() - t0)
        e = pair_error((p1, p2), truth)
        if e is not None:
            learned.append(e)
            per_shape.setdefault(shapes.get(str(sid), "?"), []).append(e)

        try:
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                det = EndpointDetector(mask)
                s, t = det.detect_endpoints(method="skeleton", save_debug=False)
            e2 = pair_error((s, t), truth)
            if e2 is not None:
                classical.append(e2)
        except Exception:
            pass

    return {"learned": learned, "classical": classical, "per_shape": per_shape,
            "seconds": float(np.mean(times)) if times else 0.0}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--shards", default=str(SHARD_DIR))
    ap.add_argument("--harvest", action="store_true", help="harvest only, then stop")
    ap.add_argument("--limit", type=int, default=None, help="cap masks harvested")
    ap.add_argument("--trees", type=int, default=160)
    ap.add_argument("--batch", type=int, default=20, help="trees per checkpoint")
    ap.add_argument("--max-depth", type=int, default=16)
    ap.add_argument("--min-leaf", type=int, default=4)
    ap.add_argument("--val-fraction", type=float, default=0.2)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--fresh", action="store_true", help="ignore any checkpoint")
    ap.add_argument("--eval-limit", type=int, default=40)
    ap.add_argument("--out", default=str(MODEL_PATH))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    data = Path(args.data)
    shard_dir = Path(args.shards)

    print("Harvest phase")
    harvest_all(data, shard_dir, args.limit, resume=not args.fresh)
    if args.harvest:
        return 0

    loaded = load_shards(shard_dir)
    if loaded is None:
        print(f"No shards in {shard_dir}. Run with --harvest first.")
        return 1
    X, y, sid = loaded
    print(f"\nLoaded {len(X)} rows, {int(y.sum())} positives, "
          f"{len(np.unique(sid))} samples, {X.shape[1]} features")

    rng = np.random.default_rng(args.seed)
    samples = np.unique(sid)
    rng.shuffle(samples)
    n_val = max(1, int(len(samples) * args.val_fraction))
    val_s = set(samples[:n_val].tolist())
    is_val = np.array([s in val_s for s in sid])
    print(f"  train {len(samples)-n_val} samples / {int((~is_val).sum())} rows | "
          f"held out {n_val} samples / {int(is_val.sum())} rows")

    from sklearn.ensemble import RandomForestClassifier

    # Class weights are computed once from the whole training set and passed
    # as an explicit dict. The "balanced_subsample" preset recomputes them
    # per fit, and sklearn warns that this is wrong under warm_start because
    # each batch would weight the classes slightly differently.
    from sklearn.utils.class_weight import compute_class_weight
    classes = np.unique(y[~is_val])
    w = compute_class_weight("balanced", classes=classes, y=y[~is_val])
    cw = {int(c): float(v) for c, v in zip(classes, w)}
    print(f"  class weights {cw}")

    def make():
        return RandomForestClassifier(
            n_estimators=0, warm_start=True, max_depth=args.max_depth,
            min_samples_leaf=args.min_leaf, n_jobs=-1,
            random_state=args.seed, class_weight=cw)

    print("\nTraining, checkpointed")
    clf, state = train_forest(make, X[~is_val], y[~is_val], args.trees, args.batch,
                              CKPT_PATH, resume=not args.fresh,
                              label="endpoint", extra={"features": EP.FEATURE_NAMES})
    print(f"  done in {state['seconds']:.0f}s"
          + (f", resumed from {state['resumed_from']} trees" if state["resumed_from"] else ""))

    print("\nEndpoint error on held-out masks, in pixels (lower is better)")
    res = evaluate(clf, EP.FEATURE_NAMES, data, samples[:n_val], args.eval_limit)
    le, ce = res["learned"], res["classical"]
    if le:
        print(f"  {'learned':<12} n={len(le):<4} median {np.median(le):7.1f}  "
              f"p75 {np.percentile(le,75):7.1f}  mean {np.mean(le):7.1f}  "
              f"within 25px {100*np.mean(np.array(le)<25):.0f}%")
    if ce:
        print(f"  {'shipped':<12} n={len(ce):<4} median {np.median(ce):7.1f}  "
              f"p75 {np.percentile(ce,75):7.1f}  mean {np.mean(ce):7.1f}  "
              f"within 25px {100*np.mean(np.array(ce)<25):.0f}%")
    print(f"  learned inference: {res['seconds']*1000:.0f} ms per mask")

    SIMPLE = {"straight", "catenary", "smooth"}
    ps = res.get("per_shape", {})
    if ps:
        print("")
        print("  by shape, learned median error:")
        for shp in sorted(ps):
            v = np.array(ps[shp])
            print(f"    {shp:<10} n={len(v):<4} median {np.median(v):6.0f} px   "
                  f"within 25px {100*np.mean(v < 25):3.0f}%")
        simple = np.array([e for k, v in ps.items() if k in SIMPLE for e in v])
        hard = np.array([e for k, v in ps.items() if k not in SIMPLE for e in v])
        if len(simple):
            print("")
            print(f"    simple shapes, which is what the real tether is: "
                  f"median {np.median(simple):.0f} px, "
                  f"within 25px {100*np.mean(simple < 25):.0f}%")
        if len(hard):
            print(f"    tangled shapes: median {np.median(hard):.0f} px, "
                  f"within 25px {100*np.mean(hard < 25):.0f}%")

    better = bool(le and ce and np.median(le) < np.median(ce))
    print("\nVerdict: " + ("the learned finder beats the shipped detector"
                           if better else
                           "the learned finder does NOT beat the shipped detector"))

    imp = sorted(zip(EP.FEATURE_NAMES, clf.feature_importances_), key=lambda t: -t[1])
    print("  feature importance: " + ", ".join(f"{n} {v:.2f}" for n, v in imp[:6]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        pickle.dump({
            "model": clf,
            "feature_names": EP.FEATURE_NAMES,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "n_rows": int(len(X)),
            "n_samples": int(len(samples)),
            "median_error_px": float(np.median(le)) if le else None,
            "median_error_px_classical": float(np.median(ce)) if ce else None,
            "within_25px": float(np.mean(np.array(le) < 25)) if le else None,
            "beats_classical": better,
            "trained_by": "synthetic.train_endpoints",
        }, fh)
    mb = out.stat().st_size / 1e6
    print(f"\nSaved {out} ({mb:.0f} MB)")
    if mb > 25:
        print("  WARNING: too large for the CM5 and for GitHub. Retrain with "
              "--trees 60 --max-depth 12 --min-leaf 20")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
