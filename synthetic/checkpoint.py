"""Resumable CPU training for the forests, shared by all three trainers.

There is no GPU on this project and there will not be one on the flight
computer either, so training is CPU-bound and long. A run that has to start
over because the machine was needed for something else is the main practical
obstacle to using a large dataset, and that is what this removes.

`RandomForestClassifier` supports `warm_start`, which lets trees be added to
an existing forest. Training therefore proceeds in batches: fit a few trees,
write the whole estimator to disk with the batch index, repeat. A resumed
run loads the checkpoint and continues from the tree count it reached.

The checkpoint is written to a temporary file and then moved into place, so
an interrupt during the write cannot leave a half-written model that a later
run would load and trust.
"""
from __future__ import annotations

import os
import pickle
import time
from pathlib import Path


def _atomic_dump(obj, path: Path):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "wb") as fh:
        pickle.dump(obj, fh)
    os.replace(tmp, path)


def load_checkpoint(path: Path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as fh:
            return pickle.load(fh)
    except Exception:
        return None


def train_forest(make_estimator, X, y, total_trees: int, batch: int,
                 ckpt_path, resume: bool = True, extra: dict | None = None,
                 label: str = "forest"):
    """Fit a forest to `total_trees`, checkpointing every `batch` trees.

    `make_estimator` is called with no arguments and must return an
    unfitted estimator with `warm_start=True` and `n_estimators=0`; the
    caller owns every other hyper-parameter.

    Returns ``(estimator, state)`` where state records how the run went,
    including whether it resumed and how long it took.
    """
    ckpt_path = Path(ckpt_path)
    state = {"resumed_from": 0, "batches": 0, "seconds": 0.0}

    clf = None
    if resume:
        saved = load_checkpoint(ckpt_path)
        if saved and saved.get("label") == label:
            clf = saved.get("model")
            done = int(saved.get("trees", 0))
            if clf is not None and done > 0:
                state["resumed_from"] = done
                print(f"  resuming {label} from {done} trees "
                      f"({ckpt_path.name})")
    if clf is None:
        clf = make_estimator()

    t0 = time.time()
    done = state["resumed_from"]
    while done < total_trees:
        step = min(batch, total_trees - done)
        clf.n_estimators = done + step
        clf.fit(X, y)
        done = clf.n_estimators
        state["batches"] += 1
        payload = {"model": clf, "trees": done, "label": label,
                   "total_trees": total_trees, "extra": extra or {}}
        _atomic_dump(payload, ckpt_path)
        el = time.time() - t0
        rate = (done - state["resumed_from"]) / max(el, 1e-6)
        eta = (total_trees - done) / max(rate, 1e-9)
        print(f"  {label}: {done}/{total_trees} trees, {el:.0f}s elapsed, "
              f"eta {eta/60:.1f} min", flush=True)

    state["seconds"] = time.time() - t0
    return clf, state


def clear_checkpoint(path):
    p = Path(path)
    if p.exists():
        p.unlink()
