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

logger = logging.getLogger(__name__)

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

    def find(self, mask):
        """Return ``(start, end)`` as (x, y) tuples, or None to fall back."""
        try:
            from synthetic.endpoints import predict_pair
            p1, p2, _ = predict_pair(self.model, self.feature_names, mask)
            if p1 is None or p2 is None:
                return None
            return p1, p2
        except Exception as exc:  # noqa: BLE001
            logger.warning("endpoint model failed, falling back to the "
                           "classical detector: %s", exc)
            return None


def get_finder(path: Path | None = None):
    if _cache["loaded"]:
        return _cache["finder"]
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
