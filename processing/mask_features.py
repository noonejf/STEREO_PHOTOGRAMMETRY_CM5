"""Per-pixel features for the cable segmenter (Model 1), in one place.

This used to be copy-pasted into three files that had to stay byte-identical
or the model would be served inputs it never saw: `gui/ai_page.py` (training
in the app), `synthetic/train_mask.py` (training offline) and
`edge_detection_tuner.py` (inference, the only path that reaches the
pipeline). Nothing enforced the agreement. Now they all call in here and the
pickle records which version it was fitted on, so a mismatch is caught at
load time instead of producing a quietly wrong mask.

Two versions ship:

- **v1** is the original nine: B, G, R, H, S, V, a 3x3 blur, a 9x9 blur and
  local contrast. Every one of them describes the *colour* of a pixel. None
  of them describes the *shape* of its neighbourhood, so the model can only
  learn "the cable is darker than the wall", which fails wherever the
  background is also dark. Kept so old pickles keep working.

- **v2** adds the shape. A cable is a ridge: a locally linear structure a few
  pixels wide, darker or brighter than both of its sides. That is exactly
  what the Hessian eigenvalues measure, which is why ridge filters are the
  classical tool for vessels in angiograms and for cracks in concrete. Three
  scales cover the width the cable can appear at between 1 m and 40 m. The
  difference-of-Gaussians, gradient magnitude, local deviation and the
  morphological hat transforms are cheaper descriptions of the same
  neighbourhood and are kept because trees pick whichever separates best.

Trees are invariant to any monotone rescaling of a feature, so the divisors
below exist to keep the numbers readable, not to condition the model. What
matters is only that training and inference compute them identically, which
is the whole reason this file exists.
"""
from __future__ import annotations

import cv2
import numpy as np

CURRENT_VERSION = 2

FEATURE_NAMES_V1 = ["B", "G", "R", "H", "S", "V", "blur3", "blur9", "contrast"]

FEATURE_NAMES_V2 = FEATURE_NAMES_V1 + [
    "gray",
    "dog_1_3", "dog_3_9", "dog_9_21",
    "ridge_s1", "ridge_s2", "ridge_s4",
    "grad_s1", "grad_s3",
    "std5", "std15",
    "blackhat9", "tophat9",
]


def feature_names(version: int = CURRENT_VERSION):
    return FEATURE_NAMES_V1 if int(version) == 1 else FEATURE_NAMES_V2


def n_features(version: int = CURRENT_VERSION) -> int:
    return len(feature_names(version))


def _ridge(gray: np.ndarray, sigma: float) -> np.ndarray:
    """Signed principal curvature, the eigenvalue of largest magnitude.

    Positive where the pixel sits on a dark line against a lighter ground,
    negative on a bright line. The sigma squared factor is the usual
    normalisation that makes responses comparable across scales, so one
    threshold learned by the tree means the same thing at every width.
    """
    k = int(2 * round(3 * sigma) + 1)
    g = cv2.GaussianBlur(gray, (k, k), sigma)
    lxx = cv2.Sobel(g, cv2.CV_32F, 2, 0, ksize=3)
    lyy = cv2.Sobel(g, cv2.CV_32F, 0, 2, ksize=3)
    lxy = cv2.Sobel(g, cv2.CV_32F, 1, 1, ksize=3)
    tmp = np.sqrt((lxx - lyy) ** 2 + 4.0 * lxy * lxy)
    tr = lxx + lyy
    e1 = 0.5 * (tr + tmp)
    e2 = 0.5 * (tr - tmp)
    big = np.where(np.abs(e1) >= np.abs(e2), e1, e2)
    return (sigma * sigma) * big


def _grad(gray: np.ndarray, sigma: float) -> np.ndarray:
    k = int(2 * round(3 * sigma) + 1)
    g = cv2.GaussianBlur(gray, (k, k), sigma)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def _local_std(gray: np.ndarray, k: int) -> np.ndarray:
    mu = cv2.blur(gray, (k, k))
    mu2 = cv2.blur(gray * gray, (k, k))
    return np.sqrt(np.maximum(mu2 - mu * mu, 0.0))


def features_v1(img_bgr: np.ndarray) -> np.ndarray:
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


def features_v2(img_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b1 = cv2.GaussianBlur(gray, (3, 3), 1.0)
    b3 = cv2.GaussianBlur(gray, (3, 3), 0)
    b9 = cv2.GaussianBlur(gray, (9, 9), 0)
    b21 = cv2.GaussianBlur(gray, (21, 21), 0)
    lc = (gray - b9).clip(-127, 127) + 127
    se9 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    cols = [
        img_bgr[:, :, 0], img_bgr[:, :, 1], img_bgr[:, :, 2],
        hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2],
        b3, b9, lc,
        gray,
        b1 - b3, b3 - b9, b9 - b21,
        _ridge(gray, 1.0), _ridge(gray, 2.0), _ridge(gray, 4.0),
        _grad(gray, 1.0), _grad(gray, 3.0),
        _local_std(gray, 5), _local_std(gray, 15),
        cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, se9),
        cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, se9),
    ]
    return (np.stack([c.ravel() for c in cols], axis=1)
            .astype("float32") / 255.0)


def features(img_bgr: np.ndarray, version: int = CURRENT_VERSION) -> np.ndarray:
    """Per-pixel features in row-major order, one row per pixel."""
    return features_v1(img_bgr) if int(version) == 1 else features_v2(img_bgr)


def cldice(pred, gt) -> float:
    """Centerline Dice, from Shit et al., CVPR 2021 (arXiv:2003.07311).

    IoU and Dice are blind to topology: a mask cut in half scores the same
    as one that lost the same number of pixels from along its edges, and
    for a tracer those two are nothing alike. clDice measures the overlap
    between each mask and the *skeleton* of the other, which is exactly
    the quantity that changes when a cable breaks.

    Topological precision is the fraction of the predicted skeleton that
    lies inside the true mask, so it falls when the prediction invents a
    branch. Topological sensitivity is the fraction of the true skeleton
    inside the predicted mask, so it falls when the prediction drops part
    of the cable. clDice is their harmonic mean.

    The paper's loss combines soft-clDice with Dice rather than replacing
    it, because clDice on its own does not care how wide the cable is, and
    here the width is a measurement output.
    """
    from skimage.morphology import skeletonize
    pred = (np.asarray(pred) > 0)
    gt = (np.asarray(gt) > 0)
    if not pred.any() or not gt.any():
        return 0.0 if pred.any() != gt.any() else 1.0
    sp = skeletonize(pred)
    sg = skeletonize(gt)
    tprec = float((sp & gt).sum()) / max(float(sp.sum()), 1.0)
    tsens = float((sg & pred).sum()) / max(float(sg.sum()), 1.0)
    if tprec + tsens <= 0:
        return 0.0
    return 2.0 * tprec * tsens / (tprec + tsens)


def predict_mask(clf, img_bgr, meta=None, version=None, threshold=None,
                 close_ksize=None):
    """Run a segmenter over one image and return a uint8 0/1 mask.

    Three call sites need this to be identical: the inference path in
    `edge_detection_tuner.py`, the trainer's own scoring, and
    `tools/compare_mask_models.py`. The two post-processing choices live in
    the pickle rather than in the code:

    ``threshold`` is not fixed at 0.5 because 0.5 is only optimal when the
    training mix matches the real class balance, and it does not: the
    sampler keeps one cable pixel for every eight background ones while the
    cable is under 2% of a real frame. Tuning it on held-out data is free
    accuracy that costs nothing at run time.

    ``close_ksize`` is a morphological closing applied after thresholding.
    A sharper mask is not automatically a better one here: the tracker stops
    at a break, so a one-pixel gap in the middle of the cable costs far more
    than a one-pixel bulge along its edge. Closing buys connectivity at a
    small, measured cost in precision. Zero disables it.
    """
    meta = meta if isinstance(meta, dict) else {}
    if version is None:
        version = version_of(meta)
    if threshold is None:
        threshold = float(meta.get("decision_threshold", 0.5))
    if close_ksize is None:
        close_ksize = int(meta.get("close_ksize", 0))

    h, w = img_bgr.shape[:2]
    feats = features(img_bgr, version)
    if threshold == 0.5 or not hasattr(clf, "predict_proba"):
        out = clf.predict(feats).reshape(h, w).astype(np.uint8)
    else:
        prob = clf.predict_proba(feats)[:, 1].reshape(h, w)
        out = (prob >= threshold).astype(np.uint8)
    if close_ksize and close_ksize > 1:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (close_ksize, close_ksize))
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, k)
    return out


def check_columns(clf, version: int):
    """Raise if a model's column count disagrees with its declared version.

    A mismatch does not crash on its own. It produces a plausible, wrong
    mask, which is the worst available outcome, so every loader checks.
    """
    want = getattr(clf, "n_features_in_", None)
    if want is not None and want != n_features(version):
        raise ValueError(
            f"model declares feature v{version} ({n_features(version)} "
            f"columns) but was fitted on {want}")


def version_of(meta) -> int:
    """Which feature set a loaded pickle was fitted on.

    Models written before this module existed carry no marker and are v1 by
    definition. A model whose column count disagrees with its declared
    version is refused by the caller rather than silently fed wrong columns.
    """
    if isinstance(meta, dict):
        return int(meta.get("feature_version", 1))
    return 1
