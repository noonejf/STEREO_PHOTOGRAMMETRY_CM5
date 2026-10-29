"""Re-tune a segmenter's threshold and closing without retraining it.

The two post-processing values live in the pickle, not in the fitted trees,
so changing the objective they were chosen under costs a few minutes
instead of the half hour a retrain takes. That matters because the
objective did change: the first runs maximised IoU, which cannot see that
the mask it prefers is in three pieces, and so chose no closing at all.
The objective here is the mean of IoU and clDice, the same combination the
clDice paper uses as a loss, for the same reason.

Tuned on held-out synthetic samples only. The real pairs stay a verdict.

    python3 tools/retune_mask_postproc.py data/models/mask_model_r960.pkl
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
from synthetic.train_mask import SYNTH_DIR, _load_pairs  # noqa: E402

THRESHOLDS = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
CLOSES = [0, 3, 5, 7]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--write", action="store_true",
                    help="store the result in the pickle; without it the "
                         "table is printed and nothing is changed")
    args = ap.parse_args(argv)

    path = Path(args.model)
    with open(path, "rb") as fh:
        meta = pickle.load(fh)
    clf = meta["model"]
    ver = mask_features.version_of(meta)
    tw, th = meta.get("target_size", (256, 192))
    mask_features.check_columns(clf, ver)
    print(f"{path.name}: features v{ver}, {tw}x{th}, "
          f"currently threshold {meta.get('decision_threshold', 0.5):.2f} "
          f"closing {meta.get('close_ksize', 0)}")

    # the same held-out synthetic split the trainer used
    pairs = _load_pairs(SYNTH_DIR / "images", SYNTH_DIR / "masks",
                        size=(tw, th))
    if not pairs:
        raise SystemExit("no synthetic samples; run synthetic.generate mask")
    rng = np.random.default_rng(args.seed)
    idx = rng.permutation(len(pairs))[:args.samples]
    use = [pairs[i] for i in idx]
    print(f"  {len(use)} held-out synthetic samples")

    probs = [(clf.predict_proba(mask_features.features(img, ver))[:, 1]
              .reshape(msk.shape), msk) for _, img, msk in use]

    print(f"\n  {'thr':>6}{'close':>7}{'IoU':>8}{'clDice':>9}{'objective':>11}")
    best, best_obj = None, -1.0
    for t in THRESHOLDS:
        for ck in CLOSES:
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
                best_obj, best = obj, (t, ck, iou, cld)
    for t, ck, iou, cld, obj in [(best[0], best[1], best[2], best[3], best_obj)]:
        print(f"  {t:>6.2f}{ck:>7}{iou:>8.3f}{cld:>9.3f}{obj:>11.3f}  <- best")

    if args.write:
        meta["decision_threshold"] = float(best[0])
        meta["close_ksize"] = int(best[1])
        meta["postproc_objective"] = "mean(IoU, clDice) on held-out synthetic"
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(meta, fh)
        tmp.replace(path)
        print(f"\n  written: threshold {best[0]:.2f}, closing {best[1]}")
    else:
        print("\n  nothing written; pass --write to store it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
