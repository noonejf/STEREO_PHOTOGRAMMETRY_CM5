"""Optional learned scorer for the tracker's branch decisions (Model 2).

`SmartWireTracker` ranks the candidate continuations at each step with a fixed
hand-tuned formula:

    direction continuity x1200 + thickness continuity x600
        + centeredness x300 - parallel-line penalty

This module lets a trained classifier replace that ranking. It is **off
unless explicitly switched on** with ``LINKU_BRANCH_SCORER=1``, and even
then it refuses to load a model that did not beat the hand-tuned formula on
held-out decisions.

The explicit opt-in is there because of a measurement, not caution. The
first trained scorer beat the formula by a wide margin on the offline
metric, 0.692 against 0.456 top-1 over 25317 held-out decisions, and then
did **not** improve the tracker end to end: over four synthetic masks it won
one, lost one badly (32.9% coverage against 67.3%) and tied two, while
running two to five times slower. Per-step accuracy and final path coverage
are different things, because the tracker is a sequential search with
backtracking: one confident wrong turn early can cost more than the several
hesitant ones the backtracking was tuned around.

So the offline number is necessary and not sufficient. Before switching this
on for real work, run ``tools/benchmark_branch_scorer.py`` over enough masks
to see coverage, and switch it on only if coverage improves.

Train one with::

    python -m synthetic.generate path --count 2000
    python -m synthetic.train_path

The features are computed by `synthetic.branches`, the same module that
harvested the training rows, so the model is always served exactly the
inputs it was fitted on. If that file's FEATURE_NAMES changes, the stored
list will no longer match and the scorer refuses to load rather than
silently feeding the model the wrong columns.
"""
from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "path_model.pkl"

#: Set LINKU_BRANCH_SCORER=1 to switch the learned scorer on. Anything else,
#: including unset, keeps the hand-tuned formula. Opt-in rather than opt-out
#: because a model that wins the offline metric has already been observed to
#: lose on end-to-end coverage.
ENV_FLAG = "LINKU_BRANCH_SCORER"

_cache = {"loaded": False, "scorer": None}


class BranchScorer:
    """Wraps a trained model and the feature extractor it was fitted with."""

    def __init__(self, model, feature_names, meta):
        self.model = model
        self.feature_names = list(feature_names)
        self.meta = dict(meta)

    @property
    def summary(self) -> str:
        m = self.meta
        return (f"path_model {m.get('date', '?')}: top-1 {m.get('top1_val', 0):.3f} "
                f"vs hand-tuned {m.get('top1_val_heuristic', 0):.3f} "
                f"on {m.get('n_decisions', 0)} decisions")

    def rank(self, tracker, current, options, momentum):
        """Return ``options`` ordered best first, or None if scoring failed.

        Returning None rather than raising is deliberate: a scorer that
        cannot run must fall back to the shipped formula, not abort a
        reconstruction the operator is waiting on.
        """
        try:
            from synthetic.branches import FEATURE_NAMES, _features_for
            feats = _features_for(tracker, current, options, momentum)
            if feats.shape[1] != len(FEATURE_NAMES):
                return None
            keep = [FEATURE_NAMES.index(n) for n in self.feature_names]
            proba = self.model.predict_proba(feats[:, keep])[:, 1]
            order = sorted(range(len(options)), key=lambda i: -proba[i])
            return [options[i] for i in order]
        except Exception as exc:  # noqa: BLE001
            logger.warning("branch scorer failed, falling back to the formula: %s", exc)
            return None


def get_scorer(path: Path | None = None):
    """Load the scorer once, or return None if it should not be used."""
    if _cache["loaded"]:
        return _cache["scorer"]
    _cache["loaded"] = True

    if os.environ.get(ENV_FLAG, "0") != "1":
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

    if not data.get("beats_heuristic"):
        logger.info("%s exists but did not beat the hand-tuned formula "
                    "(top-1 %.3f vs %.3f); keeping the formula",
                    p.name, data.get("top1_val", 0.0),
                    data.get("top1_val_heuristic", 0.0))
        return None

    try:
        from synthetic.branches import FEATURE_NAMES
    except Exception:  # noqa: BLE001
        logger.warning("synthetic.branches is not importable; branch scorer off")
        return None

    names = list(data.get("feature_names", []))
    if not names or any(n not in FEATURE_NAMES for n in names):
        logger.warning("%s was trained on a feature set this code no longer "
                       "produces; retrain it. Branch scorer off", p.name)
        return None

    scorer = BranchScorer(data["model"], names, data)
    _cache["scorer"] = scorer
    logger.info("branch scorer active: %s", scorer.summary)
    return scorer


def reset():
    """Forget the cached scorer. For tests and for A/B runs in one process."""
    _cache["loaded"] = False
    _cache["scorer"] = None
