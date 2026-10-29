"""Loader for the learned crossing-pairing model used by `graph_tracer`.

**This one is on by default, and it is the only learned component here that
is.** The two before it, `branch_scorer.py` and `endpoint_model.py`, are
opt-in because they lost end to end: each won its own offline metric and
then produced a worse traced path. This one was measured the same way, on
fresh scenes neither it nor the generator's seeds had touched, and won:
true-path F1 97.1 against the geometric rule's 95.4 over 40 scenes, 1 win,
0 losses, 39 ties, and on knots 98.1 against 90.4.

The reason it works where the branch scorer did not is the question it is
asked. The branch scorer scored one step of a pixel walk, and at a crossing
the two strands are locally identical, so the evidence it needed was not in
its input. Here the unit is a pair of whole branches meeting at a node, and
the features are properties of those branches: the direction each leaves
in, how far it runs, how thick it is. Those do differ between the right
pairing and the wrong one.

The same guard as the other two still applies: a pickle that did not record
``beats_geometric`` is refused, so a bad retrain cannot quietly ship. Set
``LINKU_PAIR_MODEL=0`` to force the geometric rule.
"""
from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "pair_model.pkl"
ENV_FLAG = "LINKU_PAIR_MODEL"

_cache = {"loaded": False, "scorer": None}


class PairScorer:
    def __init__(self, model, feature_names, meta):
        self.model = model
        self.feature_names = list(feature_names)
        self.meta = dict(meta)

    @property
    def summary(self) -> str:
        m = self.meta
        return (f"pair_model {m.get('date', '?')}: true-path F1 "
                f"{100 * m.get('f1_learned', float('nan')):.1f} against the "
                f"geometric rule's {100 * m.get('f1_geometric', float('nan')):.1f}")

    def score_many(self, graph, items):
        """Score many (node, e1, e2) at once.

        One `predict_proba` call per pair costs more in sklearn call
        overhead than in arithmetic: on a 31-edge graph that was 1.9 s
        against 0.6 s for the geometric rule. Batched it is back under a
        tenth of a second, which matters because the tracer is the step
        the operator waits on.
        """
        from synthetic.pairings import pair_features
        feats, keep = [], []
        out = [-1.0] * len(items)
        for i, (nid, e1, e2) in enumerate(items):
            f = pair_features(graph, nid, e1, e2)
            if f is not None:
                feats.append(f)
                keep.append(i)
        if not feats:
            return out
        probs = self.model.predict_proba(np.stack(feats))[:, 1]
        for i, pv in zip(keep, probs):
            out[i] = float(pv)
        return out

    def score(self, graph, nid, e1, e2):
        """A `graph_tracer` score function, higher is more likely a pair."""
        # No cache here on purpose. Keying it by id(graph) looked free and
        # is not: CPython reuses an id once the old object is collected, so
        # a later graph can read a previous graph's scores. score_many is
        # the path that actually runs, and it needs no cache.
        from synthetic.pairings import pair_features
        f = pair_features(graph, nid, e1, e2)
        if f is None:
            return -1.0
        return float(self.model.predict_proba(f.reshape(1, -1))[0, 1])


def get_scorer(path: Path | None = None):
    if _cache["loaded"]:
        return _cache["scorer"]
    _cache["loaded"] = True

    if os.environ.get(ENV_FLAG, "1").strip() not in ("1", "true", "yes"):
        logger.info("pair model disabled by %s", ENV_FLAG)
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

    if not data.get("beats_geometric"):
        logger.info("%s exists but did not beat the geometric pairing rule "
                    "when trained; keeping the rule", p.name)
        return None

    scorer = PairScorer(data["model"], data.get("feature_names", []), data)
    _cache["scorer"] = scorer
    logger.info("pair model active: %s", scorer.summary)
    return scorer


def reset():
    _cache["loaded"] = False
    _cache["scorer"] = None
