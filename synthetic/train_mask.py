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

TARGET_W, TARGET_H = 256, 192
MODEL_PATH = _ROOT / "data" / "models" / "mask_model.pkl"
SYNTH_DIR = _ROOT / "data" / "synthetic" / "mask"
REAL_DIR = _ROOT / "data" / "ai_dataset" / "mask_dataset"


def features(img_bgr: np.ndarray) -> np.ndarray:
    """The nine per-pixel features the application uses.

    Copied deliberately rather than imported: `gui/ai_page.py` needs PyQt to
    import, and training must run headless. If that feature set changes, this
    has to change with it or the model will be served inputs it never saw.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b3 = cv2.GaussianBlur(gray, (3, 3), 0)
    b9 = cv2.GaussianBlur(gray, (9, 9), 0)
    lc = (gray - b9).clip(-127, 127) + 127
    return (np.stack([
        img_bgr[:, :, 0].ravel(), img_bgr[:, :, 1].ravel(), img_bgr[:, :, 2].ravel(),
        hsv[:, :, 0].ravel(), hsv[:, :, 1].ravel(), hsv[:, :, 2].ravel(),
        b3.ravel(), b9.ravel(), lc.ravel(),
    ], axis=1).astype("float32") / 255.0)


def _load_pairs(img_dir: Path, mask_dir: Path, limit=None, img_ext=".jpg"):
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
        img = cv2.resize(img, (TARGET_W, TARGET_H), interpolation=cv2.INTER_AREA)
        msk = cv2.resize(msk, (TARGET_W, TARGET_H), interpolation=cv2.INTER_NEAREST)
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


def _stack(pairs, rng, ratio, augment=True):
    Xs, ys = [], []
    for _, img, msk in pairs:
        variants = _augment(img, msk, rng) if augment else [(img, msk)]
        for vi, vm in variants:
            X = features(vi)
            y = vm.ravel().astype(np.int8)
            X, y = _balance(X, y, ratio, rng)
            Xs.append(X)
            ys.append(y)
    if not Xs:
        return np.zeros((0, 9), np.float32), np.zeros((0,), np.int8)
    return np.concatenate(Xs), np.concatenate(ys)


def _scores(clf, pairs, label):
    """Per-image IoU and pixel F1, evaluated whole-image with no balancing.

    Balanced pixel scores flatter a segmenter badly here: the wire is 1.7% of
    the frame, so a model that predicts background everywhere already scores
    98% accuracy. IoU on the wire class is the number that moves.
    """
    from sklearn.metrics import f1_score, precision_score, recall_score
    ious, f1s, precs, recs = [], [], [], []
    for _, img, msk in pairs:
        pred = clf.predict(features(img)).reshape(msk.shape).astype(np.uint8)
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
    ap.add_argument("--max-depth", type=int, default=14)
    ap.add_argument("--min-leaf", type=int, default=150,
                    help="min samples per leaf. This is what bounds the model "
                         "size: with millions of training pixels and no floor "
                         "the forest grows past 400 MB, which GitHub refuses "
                         "and the CM5 cannot load")
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

    from sklearn.ensemble import RandomForestClassifier

    rng = np.random.default_rng(args.seed)
    t0 = time.time()

    synth = _load_pairs(Path(args.synth_dir) / "images",
                        Path(args.synth_dir) / "masks", args.limit)
    real = _load_pairs(Path(args.real_dir) / "images",
                       Path(args.real_dir) / "masks")
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

    X, y = _stack(train + real_train, rng, args.neg_ratio, augment=True)
    print(f"  {len(X)} pixels after augmentation and 1:{args.neg_ratio:g} balancing "
          f"({100 * y.mean():.1f}% wire)")

    cw = None if args.class_weight == "none" else "balanced_subsample"

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

    print("\nScores, whole-image and unbalanced:")
    s_train = _scores(clf, train[:40], "synthetic (train)")
    s_val = _scores(clf, val, "synthetic (held out)")
    s_real = _scores(clf, real_val, "REAL (never trained on)" if not args.mix_real
                     else "real (held out)")

    names = ["B", "G", "R", "H", "S", "V", "blur3", "blur9", "contrast"]
    order = np.argsort(-clf.feature_importances_)
    print("\n  feature importance: " + ", ".join(
        f"{names[i]} {clf.feature_importances_[i]:.2f}" for i in order[:5]))

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
        "target_size": (TARGET_W, TARGET_H),
        "trained_by": "synthetic.train_mask",
        "scores": {"synthetic_train": s_train, "synthetic_val": s_val, "real": s_real},
        "mixed_real": bool(args.mix_real),
    }
    with open(out, "wb") as fh:
        pickle.dump(model_data, fh)
    print(f"\nSaved {out}")
    print(json.dumps({k: round(v, 4) for k, v in s_real.items() if k != "n"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
