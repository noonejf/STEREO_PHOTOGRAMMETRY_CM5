"""Train the segmenter (Model 1) on synthetic data, validated on real data.

Differences from the in-app trainer in `gui/ai_page.py`, both deliberate:

1. **There is a held-out split.** The app reports F1, precision and recall
   from `predict` on the same array it just passed to `fit`, so its numbers
   are training-set scores and optimistic by construction. Here the synthetic
   set is split by *sample*, never by pixel, because pixels from one image are
   not independent and a pixel-level split leaks almost perfectly.

2. **Real samples are never trained on, only evaluated.** The question that
   matters is not whether synthetic data can be fitted, which it obviously
   can, but whether a model fitted on it works on photographs from the
   camera. That number is printed separately and is the one to believe. Pass
   `--mix-real` to train on both once the transfer number is understood.

The output pickle is the same shape the application loads, so a model trained
here drops straight into `data/models/mask_model.pkl` and the AI page picks it
up with no code change.
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

import synthetic  # noqa: F401,E402  (console encoding fix)
from synthetic.checkpoint import train_forest  # noqa: E402
from processing import mask_features  # noqa: E402

TARGET_W, TARGET_H = 256, 192
MODEL_PATH = _ROOT / "data" / "models" / "mask_model.pkl"
SYNTH_DIR = _ROOT / "data" / "synthetic" / "mask"
REAL_DIR = _ROOT / "data" / "ai_dataset" / "mask_dataset"


def features(img_bgr: np.ndarray, version: int = 1) -> np.ndarray:
    """Per-pixel features, from `processing/mask_features.py`.

    The feature set is not defined here any more. It had been copied into
    this file, into the app trainer and into the inference path, with
    nothing checking that the three stayed equal.
    """
    return mask_features.features(img_bgr, version)


def _load_pairs(img_dir: Path, mask_dir: Path, limit=None, img_ext=".jpg",
                size=(TARGET_W, TARGET_H)):
    out = []
    files = sorted(img_dir.glob(f"*{img_ext}"))
    if limit:
        files = files[:limit]
    for ip in files:
        mp = mask_dir / (ip.stem + ".png")
        if not mp.exists():
            continue
        img = cv2.imread(str(ip))
        msk = cv2.imread(str(mp), cv2.IMREAD_GRAYSCALE)
        if img is None or msk is None:
            continue
        img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
        msk = cv2.resize(msk, size, interpolation=cv2.INTER_NEAREST)
        out.append((ip.stem, img, (msk > 127).astype(np.uint8)))
    return out


def _balance(X, y, ratio, rng):
    """Keep every wire pixel and `ratio` times as many background pixels."""
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    if len(pos) == 0:
        return X, y
    k = min(len(neg), int(len(pos) * ratio))
    keep = np.concatenate([pos, rng.choice(neg, k, replace=False)])
    rng.shuffle(keep)
    return X[keep], y[keep]


def _augment(img, msk, rng):
    """Flips and a brightness shift, matching what the app does."""
    out = [(img, msk)]
    if rng.random() < 0.5:
        out.append((cv2.flip(img, 1), cv2.flip(msk, 1)))
    if rng.random() < 0.3:
        out.append((cv2.flip(img, 0), cv2.flip(msk, 0)))
    if rng.random() < 0.5:
        d = int(rng.integers(-35, 36))
        out.append((np.clip(img.astype(np.int16) + d, 0, 255).astype(np.uint8), msk))
    return out


def _stack(pairs, rng, ratio, augment=True, version=1):
    Xs, ys = [], []
    for _, img, msk in pairs:
        variants = _augment(img, msk, rng) if augment else [(img, msk)]
        for vi, vm in variants:
            X = features(vi, version)
            y = vm.ravel().astype(np.int8)
            X, y = _balance(X, y, ratio, rng)
            Xs.append(X)
            ys.append(y)
    if not Xs:
        nf = mask_features.n_features(version)
        return np.zeros((0, nf), np.float32), np.zeros((0,), np.int8)
    return np.concatenate(Xs), np.concatenate(ys)


def _tune_postproc(clf, pairs, version, thresholds=None, closes=(0, 3, 5)):
    """Pick the decision threshold and closing size on held-out data.

    Two reasons not to leave these at 0.5 and off.

    The threshold: the sampler keeps one cable pixel for every `--neg-ratio`
    background ones, so the model is fitted on a class balance that is
    nothing like a real frame, where the cable is under 2% of the pixels.
    The probability that separates best is therefore not 0.5, and which one
    it is depends on the mix, so it has to be measured per run.

    The closing: a sharper mask is not automatically better here. The
    tracker stops at a break, so a one-pixel gap through the cable costs the
    rest of the trace while a one-pixel bulge along its edge costs nothing.
    `whole` is reported next to IoU precisely so a run that wins on overlap
    while cutting the cable in two is visible instead of looking like
    progress.

    The objective is the mean of IoU and clDice, not IoU alone. IoU alone
    is what chose a closing of zero in the first runs, and it would: IoU
    cannot see that the mask it prefers is in three pieces. clDice
    (`processing/mask_features.py`, after Shit et al., CVPR 2021) measures
    the overlap of each mask with the other's skeleton, which is precisely
    what changes when the cable breaks. Combining the two rather than
    replacing one with the other is what the paper does, and for the same
    reason: clDice on its own does not care how wide the cable is, and the
    width is one of the measurements this payload exists to produce.

    Chosen on the synthetic held-out split, never on the real pairs: the
    real numbers have to stay a verdict, not another thing that was fitted.
    """
    if not pairs or not hasattr(clf, "predict_proba"):
        return 0.5, 0
    if thresholds is None:
        thresholds = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70,
                      0.75, 0.80, 0.85]

    probs = []
    for _, img, msk in pairs[:30]:
        pr = clf.predict_proba(features(img, version))[:, 1].reshape(msk.shape)
        probs.append((pr, msk))

    best, best_obj, best_parts = (0.5, 0), -1.0, (0.0, 0.0)
    for t in thresholds:
        for ck in closes:
            ious, clds = [], []
            for pr, msk in probs:
                pred = (pr >= t).astype(np.uint8)
                if ck > 1:
                    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ck, ck))
                    pred = cv2.morphologyEx(pred, cv2.MORPH_CLOSE, k)
                inter = int(np.logical_and(pred, msk).sum())
                union = int(np.logical_or(pred, msk).sum())
                ious.append(inter / union if union else 1.0)
                clds.append(mask_features.cldice(pred, msk))
            iou, cld = float(np.mean(ious)), float(np.mean(clds))
            obj = 0.5 * iou + 0.5 * cld
            if obj > best_obj:
                best_obj, best, best_parts = obj, (t, ck), (iou, cld)
    print(f"  post-processing tuned on {len(probs)} held-out synthetic: "
          f"threshold {best[0]:.2f}, closing {best[1]} "
          f"(IoU {best_parts[0]:.3f}, clDice {best_parts[1]:.3f} there)")
    return best


def _scores(clf, pairs, label, version=1, threshold=0.5, close_ksize=0):
    """Per-image IoU and pixel F1, evaluated whole-image with no balancing.

    Balanced pixel scores flatter a segmenter badly here: the wire is 1.7% of
    the frame, so a model that predicts background everywhere already scores
    98% accuracy. IoU on the wire class is the number that moves.
    """
    from sklearn.metrics import f1_score, precision_score, recall_score
    ious, f1s, precs, recs = [], [], [], []
    for _, img, msk in pairs:
        pred = mask_features.predict_mask(
            clf, img, version=version, threshold=threshold,
            close_ksize=close_ksize)
        inter = int(np.logical_and(pred, msk).sum())
        union = int(np.logical_or(pred, msk).sum())
        ious.append(inter / union if union else 1.0)
        yt, yp = msk.ravel(), pred.ravel()
        f1s.append(f1_score(yt, yp, zero_division=0))
        precs.append(precision_score(yt, yp, zero_division=0))
        recs.append(recall_score(yt, yp, zero_division=0))
    r = {"n": len(pairs), "iou": float(np.mean(ious)) if ious else 0.0,
         "f1": float(np.mean(f1s)) if f1s else 0.0,
         "precision": float(np.mean(precs)) if precs else 0.0,
         "recall": float(np.mean(recs)) if recs else 0.0}
    print(f"  {label:<26} n={r['n']:<4} IoU {r['iou']:.3f}  F1 {r['f1']:.3f}  "
          f"P {r['precision']:.3f}  R {r['recall']:.3f}")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synth-dir", default=str(SYNTH_DIR))
    ap.add_argument("--real-dir", default=str(REAL_DIR))
    ap.add_argument("--limit", type=int, default=None, help="cap synthetic samples")
    ap.add_argument("--val-fraction", type=float, default=0.2)
    ap.add_argument("--trees", type=int, default=120)
    ap.add_argument("--batch", type=int, default=20,
                    help="trees per checkpoint; the run resumes from the last one")
    ap.add_argument("--fresh", action="store_true", help="ignore any checkpoint")
    ap.add_argument("--max-depth", type=int, default=None,
                    help="forest only; None lets the trees grow out")
    ap.add_argument("--min-leaf", type=int, default=4,
                    help="forest only. This is what bounds the file size: with "
                         "millions of training pixels and no floor a forest "
                         "passes 400 MB. The segmenter runs on the ground, not "
                         "on the flight computer, so a large file is allowed; "
                         "anything over 100 MB simply cannot live in git and "
                         "has to be regenerated from this script")
    ap.add_argument("--model", default="hgb", choices=["hgb", "rf"],
                    help="hgb: histogram gradient boosting, a few MB and the "
                         "better model here. rf: the random forest the app "
                         "trains, kept for comparison and for resumability")
    ap.add_argument("--features", type=int, default=2, choices=[1, 2],
                    help="1 is the original nine colour features, 2 adds the "
                         "ridge, gradient and morphology channels that "
                         "describe a thin line rather than a dark pixel")
    ap.add_argument("--target", default="256x192",
                    help="working resolution, WxH. Inference resizes the "
                         "camera frame to this and the mask back up, so a "
                         "coarse value quantises the cable width")
    ap.add_argument("--iters", type=int, default=400,
                    help="hgb only: boosting rounds, with early stopping")
    ap.add_argument("--neg-ratio", type=float, default=8.0,
                    help="background pixels kept per wire pixel")
    ap.add_argument("--class-weight", default="none", choices=["none", "balanced"],
                    help="leave at none: the sampler above already balances, and "
                         "applying both corrections at once biases the model "
                         "toward predicting wire and costs precision")
    ap.add_argument("--mix-real", action="store_true",
                    help="also train on the real samples instead of only testing on them")
    ap.add_argument("--out", default=str(MODEL_PATH))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    rng = np.random.default_rng(args.seed)
    t0 = time.time()

    tw, th = (int(v) for v in args.target.lower().split("x"))
    size = (tw, th)
    ver = args.features
    print(f"features v{ver} ({mask_features.n_features(ver)} columns), "
          f"{args.model} at {tw}x{th}")

    synth = _load_pairs(Path(args.synth_dir) / "images",
                        Path(args.synth_dir) / "masks", args.limit, size=size)
    real = _load_pairs(Path(args.real_dir) / "images",
                       Path(args.real_dir) / "masks", size=size)
    print(f"Loaded {len(synth)} synthetic and {len(real)} real image/mask pairs")
    if not synth and not real:
        print("Nothing to train on. Run: python -m synthetic.generate mask --count 2000")
        return 1

    # split by sample, never by pixel
    idx = rng.permutation(len(synth))
    n_val = max(1, int(len(synth) * args.val_fraction)) if synth else 0
    val = [synth[i] for i in idx[:n_val]]
    train = [synth[i] for i in idx[n_val:]]
    real_train, real_val = [], real
    if args.mix_real and real:
        ridx = rng.permutation(len(real))
        nrv = max(1, int(len(real) * args.val_fraction))
        real_val = [real[i] for i in ridx[:nrv]]
        real_train = [real[i] for i in ridx[nrv:]]

    print(f"  train {len(train)} synthetic + {len(real_train)} real | "
          f"held out {len(val)} synthetic + {len(real_val)} real")

    X, y = _stack(train + real_train, rng, args.neg_ratio, augment=True,
                  version=ver)
    print(f"  {len(X)} pixels after augmentation and 1:{args.neg_ratio:g} balancing "
          f"({100 * y.mean():.1f}% wire)")

    cw = None if args.class_weight == "none" else "balanced_subsample"

    if args.model == "hgb":
        # Boosting fits residuals, so it keeps a compact model of the pixels
        # that are actually hard instead of memorising every leaf. There is
        # no warm_start here, but it converges in minutes rather than the
        # hour a forest of this size takes, so there is nothing to resume.
        from sklearn.ensemble import HistGradientBoostingClassifier
        clf = HistGradientBoostingClassifier(
            max_iter=args.iters, learning_rate=0.1, max_leaf_nodes=63,
            min_samples_leaf=max(args.min_leaf, 20), l2_regularization=1.0,
            early_stopping=True, n_iter_no_change=20, validation_fraction=0.1,
            random_state=args.seed,
            class_weight=None if cw is None else "balanced")
        clf.fit(X, y)
        print(f"  fitted in {time.time() - t0:.0f}s, "
              f"{clf.n_iter_} of {args.iters} boosting rounds")
    else:
        from sklearn.ensemble import RandomForestClassifier

        def make():
            return RandomForestClassifier(
                n_estimators=0, warm_start=True, max_depth=args.max_depth,
                min_samples_leaf=args.min_leaf,
                n_jobs=-1, random_state=args.seed, class_weight=cw)

        ckpt = Path(args.out).with_suffix(".ckpt")
        clf, state = train_forest(make, X, y, args.trees, args.batch, ckpt,
                                  resume=not args.fresh, label="mask")
        print(f"  fitted in {time.time() - t0:.0f}s"
              + (f", resumed from {state['resumed_from']} trees"
                 if state["resumed_from"] else ""))

    thr, close_k = _tune_postproc(clf, val, ver)

    print("\nScores, whole-image and unbalanced:")
    s_train = _scores(clf, train[:40], "synthetic (train)", ver, thr, close_k)
    s_val = _scores(clf, val, "synthetic (held out)", ver, thr, close_k)
    s_real = _scores(clf, real_val, "REAL (never trained on)" if not args.mix_real
                     else "real (held out)", ver, thr, close_k)

    names = mask_features.feature_names(ver)
    if hasattr(clf, "feature_importances_"):
        order = np.argsort(-clf.feature_importances_)
        print("\n  feature importance: " + ", ".join(
            f"{names[i]} {clf.feature_importances_[i]:.2f}" for i in order[:6]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    model_data = {
        "model": clf,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_pairs": len(train) + len(real_train),
        "n_augmented": len(X),
        # the app reads these three for its status line; give it the held-out
        # numbers, not the training ones, so the display is not a lie
        "f1_train": s_val["f1"],
        "precision": s_val["precision"],
        "recall": s_val["recall"],
        "target_size": (tw, th),
        "feature_version": ver,
        "model_kind": args.model,
        "decision_threshold": float(thr),
        "close_ksize": int(close_k),
        "trained_by": "synthetic.train_mask",
        "scores": {"synthetic_train": s_train, "synthetic_val": s_val, "real": s_real},
        "mixed_real": bool(args.mix_real),
        # written down rather than left implicit in the rng: a later
        # comparison has to know which real pairs this model never saw,
        # and reconstructing the permutation from the seed is fragile
        "real_val_stems": [t[0] for t in real_val],
        "real_train_stems": [t[0] for t in real_train],
    }
    with open(out, "wb") as fh:
        pickle.dump(model_data, fh)
    size_mb = out.stat().st_size / 1e6
    print(f"\nSaved {out} ({size_mb:.0f} MB)")
    print(json.dumps({k: round(v, 4) for k, v in s_real.items() if k != "n"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
