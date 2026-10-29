"""Optional learned endpoint finder, used by `detect_wire_endpoints`.

The shipped detector skeletonises the mask, keeps the pixels with a single
skeleton neighbour, and picks the geodesically farthest pair. That cannot
find an end which leaves no tip, and ends frequently leave no tip: when the
free end of the cord lies across another part of the cord, the skeleton
merges straight through it. Measured over 80 synthetic masks, 47 of 138 true
endpoints had no skeleton tip within two wire radii, 44 of them sitting
squarely on the mask, concentrated in 83% of loop ends and 71% of knot ends.

The learned finder scores **every** skeleton pixel rather than only the
tips, which lifts the ceiling on those same masks from 66% to 100%, and then
takes the best pixel plus the best one geodesically far from it.

Like the branch scorer this is **opt-in**, with ``LINKU_ENDPOINT_MODEL=1``,
and refuses to load a model that did not beat the classical detector when it
was trained. Endpoint detection is stage 2 of the measurement pipeline and
every later stage depends on it, so it does not get switched on by the mere
presence of a file.
"""
from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

#: Width the model works at. It was trained on 960 px masks, and several of
#: its features (local windows, densities, neighbour counts) are defined in
#: pixels of that regime, so a capture-resolution mask is resized down before
#: scoring and the answer is scaled back up. This is also what keeps the
#: graph walk affordable on a 4056x3040 mask.
WORK_WIDTH = 960

#: How much better than the classical pair of farthest tips the learned pair
#: has to score before it is used at all. The learned finder is better only
#: on the masks where an end leaves no skeleton tip, so it answers only when
#: the evidence says this is one of those; otherwise it abstains and the
#: shipped detector runs. Overridable for sweeps, not for production.
DEFAULT_MARGIN = 1.5
MARGIN_ENV = "LINKU_ENDPOINT_MARGIN"

#: Weight on the geodesic span when the model reranks the classical
#: candidates. The shipped detector takes the pair that spans the most
#: cable; this keeps that as one term of the ranking instead of throwing it
#: away, because on the masks that are hard the true ends often leave no
#: skeleton tip and no candidate is an end at all. A large weight
#: reproduces the classical choice, zero is the model on its own.
DEFAULT_GEO_WEIGHT = 1.0
GEO_WEIGHT_ENV = "LINKU_ENDPOINT_GEO_W"

#: ``LINKU_ENDPOINT_MODEL`` takes three values rather than a boolean.
#:
#: ``0``      off, the shipped detector alone.
#: ``1``      rerank. The shipped detector runs, and the model picks the
#:            pair out of the candidates it proposed. Every answer is one
#:            of those candidates, so this can only trade one skeleton tip
#:            for another, which is the cheap kind of mistake.
#: ``full``   the model scores the whole skeleton and answers on its own.
#:            This is the arrangement that was measured and lost: better
#:            endpoints, worse traces, because its mistakes land mid-cord.
#:            Kept so the comparison stays reproducible.
MODE_OFF, MODE_RERANK, MODE_FULL = "0", "1", "full"


def mode() -> str:
    v = os.environ.get(ENV_FLAG, MODE_OFF).strip().lower()
    return v if v in (MODE_RERANK, MODE_FULL) else MODE_OFF

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "endpoint_model.pkl"
ENV_FLAG = "LINKU_ENDPOINT_MODEL"

_cache = {"loaded": False, "finder": None}


class EndpointFinder:
    def __init__(self, model, feature_names, meta):
        self.model = model
        self.feature_names = list(feature_names)
        self.meta = dict(meta)

    @property
    def summary(self) -> str:
        m = self.meta
        cl = m.get("median_error_px_classical")
        return (f"endpoint_model {m.get('date', '?')}: median error "
                f"{m.get('median_error_px', float('nan')):.1f} px"
                + (f" against the classical detector's {cl:.1f} px" if cl else ""))

    def choose_among(self, mask, candidates):
        """Pick the pair from a shortlist the classical detector proposed.

        Returns ``(start, end)`` in the coordinates of ``mask``, or None to
        leave the caller's own answer alone.
        """
        try:
            from synthetic.endpoints import score_candidates
            h, w = mask.shape[:2]
            scale = 1.0
            work = mask
            cand = [(float(x), float(y)) for x, y in candidates]
            if w > WORK_WIDTH:
                scale = WORK_WIDTH / float(w)
                work = cv2.resize(mask, (WORK_WIDTH, max(1, int(round(h * scale)))),
                                  interpolation=cv2.INTER_NEAREST)
                cand = [(x * scale, y * scale) for x, y in cand]
            gw = float(os.environ.get(GEO_WEIGHT_ENV, DEFAULT_GEO_WEIGHT))
            p1, p2, info = score_candidates(self.model, self.feature_names,
                                            work, cand, geodesic_weight=gw)
            self.last_info = info
            if p1 is None or p2 is None:
                return None
            if scale != 1.0:
                inv = 1.0 / scale
                p1 = _snap_to_mask(mask, p1[0] * inv, p1[1] * inv, int(inv * 3))
                p2 = _snap_to_mask(mask, p2[0] * inv, p2[1] * inv, int(inv * 3))
                if p1 is None or p2 is None:
                    return None
            return p1, p2
        except Exception as exc:  # noqa: BLE001
            logger.warning("endpoint rerank failed, keeping the classical "
                           "pair: %s", exc)
            return None

    def find(self, mask):
        """Return ``(start, end)`` as (x, y) tuples, or None to fall back."""
        try:
            from synthetic.endpoints import predict_pair
            h, w = mask.shape[:2]
            scale = 1.0
            work = mask
            if w > WORK_WIDTH:
                scale = WORK_WIDTH / float(w)
                work = cv2.resize(mask, (WORK_WIDTH, max(1, int(round(h * scale)))),
                                  interpolation=cv2.INTER_NEAREST)
            margin = float(os.environ.get(MARGIN_ENV, DEFAULT_MARGIN))
            p1, p2, info = predict_pair(self.model, self.feature_names, work,
                                        classical_margin=margin)
            self.calls = getattr(self, "calls", 0) + 1
            self.last_info = info
            if p1 is None or p2 is None:
                if info.get("deferred_to_classical"):
                    self.deferred = getattr(self, "deferred", 0) + 1
                else:
                    self.abstained = getattr(self, "abstained", 0) + 1
                return None
            self.answered = getattr(self, "answered", 0) + 1
            if scale != 1.0:
                inv = 1.0 / scale
                p1 = _snap_to_mask(mask, p1[0] * inv, p1[1] * inv, int(inv * 3))
                p2 = _snap_to_mask(mask, p2[0] * inv, p2[1] * inv, int(inv * 3))
                if p1 is None or p2 is None:
                    return None
            return p1, p2
        except Exception as exc:  # noqa: BLE001
            logger.warning("endpoint model failed, falling back to the "
                           "classical detector: %s", exc)
            return None


def _snap_to_mask(mask, x, y, radius):
    """Nearest mask pixel to (x, y), searched in a local window.

    A point scored at WORK_WIDTH and scaled back up can land a few pixels off
    the full-resolution mask, and the tracker needs its seed ON the cable.
    """
    h, w = mask.shape[:2]
    xi = int(np.clip(round(x), 0, w - 1))
    yi = int(np.clip(round(y), 0, h - 1))
    if mask[yi, xi] > 0:
        return (xi, yi)
    r = max(2, radius)
    x0, x1 = max(0, xi - r), min(w, xi + r + 1)
    y0, y1 = max(0, yi - r), min(h, yi + r + 1)
    win = mask[y0:y1, x0:x1]
    ys, xs = np.nonzero(win)
    if len(ys) == 0:
        return None
    d = (ys - (yi - y0)) ** 2 + (xs - (xi - x0)) ** 2
    k = int(np.argmin(d))
    return (int(x0 + xs[k]), int(y0 + ys[k]))


def get_finder(path: Path | None = None):
    if _cache["loaded"]:
        return _cache["finder"]
    _cache["loaded"] = True

    if mode() == MODE_OFF:
        return None

    p = Path(path) if path else MODEL_PATH
    if not p.exists():
        return None
    try:
        with open(p, "rb") as fh:
            data = pickle.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read %s: %s", p, exc)
        return None

    if not data.get("beats_classical"):
        logger.info("%s exists but did not beat the classical detector when "
                    "trained; keeping the classical one", p.name)
        return None

    finder = EndpointFinder(data["model"], data.get("feature_names", []), data)
    _cache["finder"] = finder
    logger.info("endpoint model active: %s", finder.summary)
    return finder


def reset():
    _cache["loaded"] = False
    _cache["finder"] = None
