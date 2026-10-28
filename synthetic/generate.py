"""Mass generation of synthetic training data.

Two datasets, because the two models need different things:

``mask``
    photograph plus ground-truth mask, for the per-pixel segmenter. Only this
    model sees pixels, so this is the dataset whose *appearance* has to match
    the archive. Shapes are weighted toward the simple ones, which keeps the
    cord thick enough to survive the downscale to the 256x192 training grid.

``path``
    mask plus ground-truth ordered path plus harvested branch decisions, for
    the branch scorer. This model never sees a pixel of photograph, so there
    is no appearance to match and no domain gap to worry about. Shapes are
    weighted toward crossings, which is the whole point of the model.

Usage::

    python -m synthetic.generate mask --count 4000
    python -m synthetic.generate path --count 2000
    python -m synthetic.generate both --count 2000 --workers 8

Output goes to ``data/synthetic/`` which is git-ignored: at the default sizes
a few thousand samples run to hundreds of megabytes, and the repository
already carries more image data than it should.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from synthetic import appearance, branches, config, geometry, rasterize  # noqa: E402

DEFAULT_OUT = _ROOT / "data" / "synthetic"

#: Shapes for the segmenter. Simple shapes dominate, so the cord stays thick
#: enough to still exist after the downscale to 256x192 that Model 1 trains at.
MASK_SHAPE_WEIGHTS = {
    "straight": 0.16, "catenary": 0.20, "smooth": 0.26,
    "loop": 0.20, "coil": 0.06, "knot": 0.06, "tangle": 0.06,
}

#: Shapes for the branch scorer. Crossings dominate, deliberately and far
#: beyond their share of real captures: a set that mirrored reality would be
#: almost entirely easy examples and would teach the model nothing about the
#: case it exists for.
PATH_SHAPE_WEIGHTS = {
    "straight": 0.04, "catenary": 0.06, "smooth": 0.10,
    "loop": 0.26, "coil": 0.14, "knot": 0.24, "tangle": 0.16,
}

#: Base radius for path samples, in output pixels. Set explicitly rather than
#: solved from a foreground target, so the mask lands in the regime the
#: tracker's internal rescaling expects. Foreground fraction does not matter
#: for this model; topology and relative thickness do.
PATH_RADIUS_PX = (8.0, 24.0)

SHARD_SIZE = 250


def _weighted_pick(weights, rng):
    kinds = list(weights)
    w = np.array([weights[k] for k in kinds], dtype=float)
    return kinds[int(rng.choice(len(kinds), p=w / w.sum()))]


# --------------------------------------------------------------- mask set

def make_mask_sample(seed: int, size, jpeg_quality: int):
    rng = np.random.default_rng(seed)
    kind = _weighted_pick(MASK_SHAPE_WEIGHTS, rng)
    oof = rng.random() < config.OUT_OF_FRAME_RATE
    xy, depth = geometry.make_centreline(kind, size, rng, allow_out_of_frame=oof)
    mask, buffers, info = rasterize.rasterize(xy, depth, size, rng)
    family = "lab" if rng.random() < config.LAB_PROBABILITY else "orbital"
    img, anotes = appearance.render(buffers, size, family, rng,
                                    radius=info["base_radius_px"],
                                    jpeg_quality=jpeg_quality)
    meta = {"seed": seed, "shape": kind, "out_of_frame": bool(oof),
            "size": list(size), **info, **anotes}
    return img, mask, meta


# --------------------------------------------------------------- path set

def make_path_sample(seed: int, size, stride: int, min_options: int):
    rng = np.random.default_rng(seed)
    kind = _weighted_pick(PATH_SHAPE_WEIGHTS, rng)
    oof = rng.random() < config.OUT_OF_FRAME_RATE * 0.5
    xy, depth = geometry.make_centreline(kind, size, rng, allow_out_of_frame=oof)
    radius = rng.uniform(*PATH_RADIUS_PX)
    # Gentler degradation than the segmenter set: a break severs the path, and
    # a severed path has no traversable ground truth to label against.
    mask, _, info = rasterize.rasterize(xy, depth, size, rng,
                                        base_radius=radius, degrade_strength=0.45)
    visible = rasterize.visible_path(xy, size)
    harvest = branches.harvest(mask, xy, min_options=min_options, stride=stride, rng=rng)
    meta = {"seed": seed, "shape": kind, "out_of_frame": bool(oof),
            "size": list(size), "crossings": len(geometry.crossings(xy)),
            "visible_fraction": round(float(visible.mean()), 4),
            **info,
            "n_decisions": harvest["n_decisions"],
            "n_branch_points": harvest["n_branch_points"],
            "n_unlabelled": harvest["n_unlabelled"],
            "internal_scale": harvest["internal_scale"]}
    return mask, xy, harvest, meta


# --------------------------------------------------------------- workers

def _mask_worker(args):
    idx, seed, size, q, out = args
    img, mask, meta = make_mask_sample(seed, size, q)
    name = f"{idx:06d}"
    cv2.imwrite(str(Path(out) / "images" / f"{name}.jpg"), img,
                [cv2.IMWRITE_JPEG_QUALITY, q])
    cv2.imwrite(str(Path(out) / "masks" / f"{name}.png"), mask,
                [cv2.IMWRITE_PNG_COMPRESSION, 9])
    meta["id"] = name
    return meta


def _path_worker(args):
    idx, seed, size, stride, min_options, out = args
    mask, xy, harvest, meta = make_path_sample(seed, size, stride, min_options)
    name = f"{idx:06d}"
    cv2.imwrite(str(Path(out) / "masks" / f"{name}.png"), mask,
                [cv2.IMWRITE_PNG_COMPRESSION, 9])
    with open(Path(out) / "paths" / f"{name}.json", "w", encoding="utf-8") as fh:
        json.dump({"path": np.round(xy, 2).tolist()}, fh)
    meta["id"] = name
    return meta, harvest["X"], harvest["y"], harvest["group"]


# --------------------------------------------------------------- drivers

def _prepare(out: Path, subdirs):
    for d in subdirs:
        (out / d).mkdir(parents=True, exist_ok=True)
    return out


def run_mask(count, out, size, workers, jpeg_quality, seed0, verbose=True):
    out = _prepare(Path(out), ["images", "masks"])
    jobs = [(i, seed0 + i, size, jpeg_quality, str(out)) for i in range(count)]
    metas = _run(jobs, _mask_worker, workers, verbose, "mask")
    _write_index(out, metas)
    return metas


def run_path(count, out, size, workers, stride, min_options, seed0, verbose=True):
    out = _prepare(Path(out), ["masks", "paths", "features"])
    jobs = [(i, seed0 + i, size, stride, min_options, str(out)) for i in range(count)]
    results = _run(jobs, _path_worker, workers, verbose, "path")

    metas = []
    shard, shard_i, rows = {"X": [], "y": [], "g": [], "sid": []}, 0, 0
    gbase = 0
    for meta, X, y, g in results:
        metas.append(meta)
        if len(X):
            shard["X"].append(X)
            shard["y"].append(y)
            shard["g"].append(g + gbase)
            shard["sid"].append(np.full(len(X), int(meta["id"]), dtype=np.int32))
            gbase += int(g.max()) + 1 if len(g) else 0
            rows += len(X)
        if len(metas) % SHARD_SIZE == 0:
            shard_i = _flush(out, shard, shard_i)
    _flush(out, shard, shard_i)
    _write_index(out, metas)
    if verbose:
        print(f"  harvested {rows} candidate rows across "
              f"{sum(m['n_decisions'] for m in metas)} decisions")
    return metas


def _flush(out, shard, shard_i):
    if not shard["X"]:
        return shard_i
    np.savez_compressed(Path(out) / "features" / f"shard_{shard_i:03d}.npz",
                        X=np.concatenate(shard["X"]),
                        y=np.concatenate(shard["y"]),
                        group=np.concatenate(shard["g"]),
                        sample_id=np.concatenate(shard["sid"]),
                        feature_names=np.array(branches.FEATURE_NAMES))
    for k in shard:
        shard[k].clear()
    return shard_i + 1


def _run(jobs, fn, workers, verbose, label):
    t0 = time.time()
    out = []
    if workers and workers > 1:
        import multiprocessing as mp
        with mp.Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(fn, jobs, chunksize=4), 1):
                out.append(r)
                if verbose and (i % 50 == 0 or i == len(jobs)):
                    _tick(label, i, len(jobs), t0)
    else:
        for i, j in enumerate(jobs, 1):
            out.append(fn(j))
            if verbose and (i % 50 == 0 or i == len(jobs)):
                _tick(label, i, len(jobs), t0)
    return out


def _tick(label, i, n, t0):
    el = time.time() - t0
    rate = i / max(el, 1e-6)
    eta = (n - i) / max(rate, 1e-6)
    print(f"  [{label}] {i}/{n}  {rate:.1f}/s  eta {eta/60:.1f} min", flush=True)


def _write_index(out: Path, metas):
    with open(out / "index.jsonl", "w", encoding="utf-8") as fh:
        for m in metas:
            fh.write(json.dumps(m) + "\n")


def summarise(metas, label):
    if not metas:
        print(f"  {label}: nothing generated")
        return
    fg = [m["foreground_fraction"] * 100 for m in metas]
    cc = [m["components"] for m in metas]
    print(f"  {label}: {len(metas)} samples | fg% median {np.median(fg):.2f} "
          f"p95 {np.percentile(fg, 95):.2f} | single-component "
          f"{100 * np.mean([c == 1 for c in cc]):.0f}%")
    shapes = {}
    for m in metas:
        shapes[m["shape"]] = shapes.get(m["shape"], 0) + 1
    print("    shapes: " + ", ".join(f"{k} {v}" for k, v in sorted(shapes.items())))
    if "n_decisions" in metas[0]:
        print(f"    decisions/sample median "
              f"{np.median([m['n_decisions'] for m in metas]):.0f}, "
              f"crossings median {np.median([m['crossings'] for m in metas]):.0f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["mask", "path", "both"])
    ap.add_argument("--count", type=int, default=500,
                    help="samples to generate (per dataset for 'both')")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--size", default=None,
                    help="preview (1920x1440), full, half, or WxH. "
                         "Default: preview for mask, half for path")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--jpeg-quality", type=int, default=88)
    ap.add_argument("--stride", type=int, default=3,
                    help="harvest every Nth step along the path")
    ap.add_argument("--min-options", type=int, default=2,
                    help="only harvest points offering at least this many options")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    def pick_size(default_key):
        if args.size is None:
            return config.RESOLUTIONS[default_key]
        if args.size in config.RESOLUTIONS:
            return config.RESOLUTIONS[args.size]
        w, h = args.size.lower().split("x")
        return (int(w), int(h))

    out = Path(args.out)
    print(f"Synthetic generation -> {out}")

    if args.what in ("mask", "both"):
        size = pick_size("preview")
        print(f"\nmask dataset: {args.count} samples at {size[0]}x{size[1]}, "
              f"{args.workers} workers")
        metas = run_mask(args.count, out / "mask", size, args.workers,
                         args.jpeg_quality, args.seed)
        summarise(metas, "mask")

    if args.what in ("path", "both"):
        size = pick_size("half")
        print(f"\npath dataset: {args.count} samples at {size[0]}x{size[1]}, "
              f"{args.workers} workers, stride {args.stride}")
        metas = run_path(args.count, out / "path", size, args.workers,
                         args.stride, args.min_options, args.seed + 500000)
        summarise(metas, "path")

    print("\nDone.")


if __name__ == "__main__":
    main()
