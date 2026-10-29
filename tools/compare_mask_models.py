"""Compare segmenter pickles on the real pairs, the way the pipeline uses them.

Run with no arguments to score every `*.pkl` in `data/models` that looks like
a segmenter, incumbent first.

Two things this does that the trainer's own report does not.

**It scores the mask at the resolution the tracker will see.** Inference
resizes the camera frame down to the model's `target_size`, predicts, and
resizes the mask back up. A model working at 256x192 therefore quantises the
cable to about three pixels of width and then multiplies every error by
seven and a half. Scoring each model at its own working size hides that
completely, and makes a coarse model look equal to a fine one. Here every
model does its own round trip and is then scored at a common 960x720, which
is the width `SmartWireTracker` actually runs at.

**It counts whether the cable survives in one piece.** IoU is indifferent to
where the wrong pixels are: losing 10% of the cable from its middle, which
cuts the trace in two, scores the same as losing 10% from along its edges,
which costs nothing. The tracker cares enormously about the difference,
because a break is where it stops. `pieces` is the number of predicted
components that overlap the cable, and `whole` is the fraction of the cable
covered by the single largest one, which is the most the tracker can reach
from one seed without bridging a gap. Read `whole` first; it is the closest
thing here to the end-to-end number.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import synthetic  # noqa: F401,E402  (console encoding fix)
from processing import mask_features  # noqa: E402

REAL_DIR = _ROOT / "data" / "ai_dataset" / "mask_dataset"
MODELS_DIR = _ROOT / "data" / "models"
EVAL_W, EVAL_H = 960, 720


def load_real(size=(EVAL_W, EVAL_H)):
    out = []
    for ip in sorted((REAL_DIR / "images").glob("*.jpg")):
        mp = REAL_DIR / "masks" / (ip.stem + ".png")
        if not mp.exists():
            continue
        img = cv2.imread(str(ip))
        msk = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
        if img is None or msk is None:
            continue
        out.append((ip.stem,
                    cv2.resize(img, size, interpolation=cv2.INTER_AREA),
                    (cv2.resize(msk, size, interpolation=cv2.INTER_NEAREST) > 127
                     ).astype(np.uint8)))
    return out


def predict_full(clf, img_eval, target_size, meta):
    """One model's full round trip: down to its size, predict, back up."""
    tw, th = target_size
    small = cv2.resize(img_eval, (tw, th), interpolation=cv2.INTER_AREA)
    pred = mask_features.predict_mask(clf, small, meta)
    return cv2.resize(pred, (img_eval.shape[1], img_eval.shape[0]),
                      interpolation=cv2.INTER_NEAREST)


def score_one(pred, gt):
    inter = int(np.logical_and(pred, gt).sum())
    union = int(np.logical_or(pred, gt).sum())
    tp = inter
    fp = int(pred.sum()) - tp
    fn = int(gt.sum()) - tp
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    n, lab = cv2.connectedComponents(pred.astype(np.uint8), connectivity=8)
    pieces, best = 0, 0
    for i in range(1, n):
        hit = int(np.logical_and(lab == i, gt).sum())
        if hit > 0:
            pieces += 1
            best = max(best, hit)
    total_gt = int(gt.sum())
    return {"iou": inter / union if union else 1.0, "f1": f1,
            "precision": prec, "recall": rec,
            "pieces": pieces,
            "cldice": mask_features.cldice(pred, gt),
            "whole": best / total_gt if total_gt else 1.0}


def evaluate(path: Path, pairs, only=None):
    with open(path, "rb") as fh:
        meta = pickle.load(fh)
    clf = meta["model"] if isinstance(meta, dict) else meta
    ver = mask_features.version_of(meta)
    tsz = tuple(meta.get("target_size", (256, 192))) if isinstance(meta, dict) \
        else (256, 192)

    try:
        mask_features.check_columns(clf, ver)
    except ValueError as exc:
        raise SystemExit(f"{path.name}: {exc}. Refusing to score it on "
                         f"columns it never saw.")

    use = [p for p in pairs if only is None or p[0] in only]
    rows = [score_one(predict_full(clf, img, tsz, meta), gt) for _, img, gt in use]
    agg = {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}
    agg["n"] = len(rows)
    agg["mb"] = path.stat().st_size / 1e6
    agg["version"] = ver
    agg["target"] = f"{tsz[0]}x{tsz[1]}"
    agg["kind"] = meta.get("model_kind", "rf") if isinstance(meta, dict) else "rf"
    agg["thr"] = float(meta.get("decision_threshold", 0.5)) if isinstance(meta, dict) else 0.5
    agg["close"] = int(meta.get("close_ksize", 0)) if isinstance(meta, dict) else 0
    agg["holdout"] = set(meta.get("real_val_stems", [])) if isinstance(meta, dict) else set()
    return agg


def _row(name, r):
    return (f"  {name:<30}{r['mb']:>6.0f}{('v%d' % r['version']):>4}"
            f"{r['target']:>10}{r['thr']:>6.2f}{r['close']:>4}"
            f"{r['iou']:>7.3f}{r['f1']:>7.3f}{r['cldice']:>8.3f}"
            f"{r['whole']:>7.3f}{r['pieces']:>7.1f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", help="pickles to compare; default is "
                                              "every segmenter in data/models")
    ap.add_argument("--holdout-of", default=None,
                    help="also print a table restricted to the real pairs this "
                         "model was not trained on, which is the only subset "
                         "that is fair to a model trained with --mix-real")
    args = ap.parse_args(argv)

    paths = [Path(m) for m in args.models]
    if not paths:
        paths = [MODELS_DIR / "mask_model.pkl"]
        paths += sorted(p for p in MODELS_DIR.glob("mask_model_*.pkl"))
    paths = [p for p in paths if p.exists()]
    if not paths:
        raise SystemExit("no segmenter pickles found")

    pairs = load_real()
    print(f"{len(pairs)} real pairs, scored at {EVAL_W}x{EVAL_H} after each "
          f"model's own resize round trip\n")

    hdr = (f"  {'model':<30}{'MB':>6}{'ft':>4}{'size':>10}{'thr':>6}{'cl':>4}"
           f"{'IoU':>7}{'F1':>7}{'clDice':>8}{'whole':>7}{'pieces':>7}")
    results = {}
    print("all 20 real pairs (the incumbent trained on every one of them, so "
          "this table favours it)")
    print(hdr)
    for p in paths:
        r = evaluate(p, pairs)
        results[p] = r
        print(_row(p.name, r))

    ref = Path(args.holdout_of) if args.holdout_of else None
    if ref is None:
        for p, r in results.items():
            if r["holdout"]:
                ref = p
                break
    if ref is not None and results.get(ref, {}).get("holdout"):
        only = results[ref]["holdout"]
        print(f"\nthe {len(only)} pairs {ref.name} never trained on")
        print(hdr)
        for p in paths:
            r = evaluate(p, pairs, only=only)
            print(_row(p.name, r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
