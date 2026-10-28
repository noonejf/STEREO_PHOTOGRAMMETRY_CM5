#!/usr/bin/env python3
"""Measure the real image and mask archive, and compare the generator to it.

Every constant in `synthetic/config.py` is supposed to come from this script
rather than from somebody's impression of what the captures look like. Run it
after adding real samples, and update the config if the statistics have moved.

    python3 tools/measure_real_samples.py
    python3 tools/measure_real_samples.py --compare      # also sample the generator

Reads only; writes nothing.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASETS = [ROOT / "data" / "ai_dataset" / "mask_dataset",
            ROOT / "data" / "ai_dataset" / "path_dataset"]


def measure_pair(img_path: Path, mask_path: Path):
    img = cv2.imread(str(img_path))
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if img is None or mask is None:
        return None
    fg = mask > 127
    if not fg.any():
        return None
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(float)
    dt = cv2.distanceTransform(fg.astype(np.uint8), cv2.DIST_L2, 5)
    n_lab, _ = cv2.connectedComponents(fg.astype(np.uint8))
    return {
        "name": img_path.stem,
        "size": mask.shape,
        "fg_pct": 100.0 * fg.mean(),
        "dt_max": float(dt.max()),
        "components": int(n_lab - 1),
        "wire_grey": float(grey[fg].mean()),
        "bg_grey": float(grey[~fg].mean()),
        "bg_std": float(grey[~fg].std()),
        "contrast": float(grey[fg].mean() - grey[~fg].mean()),
    }


def collect(dirs):
    rows = []
    for d in dirs:
        img_dir, mask_dir = d / "images", d / "masks"
        if not img_dir.is_dir():
            continue
        for ip in sorted(img_dir.glob("*.jpg")):
            mp = mask_dir / (ip.stem + ".png")
            if mp.exists():
                r = measure_pair(ip, mp)
                if r:
                    r["dataset"] = d.name
                    rows.append(r)
    return rows


def summarise(rows, label):
    if not rows:
        print(f"{label}: no samples found")
        return {}
    out = {}
    print(f"\n{label}: {len(rows)} image/mask pairs")
    print(f"  {'quantity':<22}{'median':>9}{'p05':>9}{'p95':>9}{'min':>9}{'max':>9}")
    for key in ("fg_pct", "dt_max", "wire_grey", "bg_grey", "bg_std", "contrast"):
        v = [r[key] for r in rows]
        out[key] = (st.median(v), float(np.percentile(v, 5)), float(np.percentile(v, 95)),
                    min(v), max(v))
        print(f"  {key:<22}{out[key][0]:>9.2f}{out[key][1]:>9.2f}{out[key][2]:>9.2f}"
              f"{out[key][3]:>9.2f}{out[key][4]:>9.2f}")
    single = sum(1 for r in rows if r["components"] == 1)
    out["single_component_pct"] = 100.0 * single / len(rows)
    print(f"  {'single component':<22}{single}/{len(rows)} = {out['single_component_pct']:.0f}%")
    sizes = {}
    for r in rows:
        sizes[r["size"]] = sizes.get(r["size"], 0) + 1
    print("  resolutions: " + ", ".join(f"{w}x{h} n={n}" for (h, w), n in sorted(sizes.items())))
    return out


def sample_generator(n, size):
    from synthetic import appearance, config, geometry, rasterize
    rows = []
    for seed in range(n):
        rng = np.random.default_rng(10_000 + seed)
        kind = geometry.pick_shape(rng)
        xy, depth = geometry.make_centreline(kind, size, rng)
        mask, buffers, info = rasterize.rasterize(xy, depth, size, rng)
        family = "lab" if rng.random() < config.LAB_PROBABILITY else "orbital"
        img, _ = appearance.render(buffers, size, family, rng,
                                   radius=info["base_radius_px"], jpeg_quality=88)
        fg = mask > 127
        if not fg.any():
            continue
        grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(float)
        dt = cv2.distanceTransform(fg.astype(np.uint8), cv2.DIST_L2, 5)
        rows.append({"name": f"synth{seed}", "size": mask.shape,
                     "fg_pct": 100.0 * fg.mean(), "dt_max": float(dt.max()),
                     "components": info["components"],
                     "wire_grey": float(grey[fg].mean()),
                     "bg_grey": float(grey[~fg].mean()),
                     "bg_std": float(grey[~fg].std()),
                     "contrast": float(grey[fg].mean() - grey[~fg].mean()),
                     "dataset": "synthetic"})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compare", action="store_true",
                    help="also sample the generator and print both side by side")
    ap.add_argument("--n", type=int, default=120, help="generator samples for --compare")
    args = ap.parse_args(argv)

    real = collect(DATASETS)
    r = summarise(real, "REAL archive")

    if args.compare:
        s = summarise(sample_generator(args.n, (1920, 1440)), "GENERATOR")
        if r and s:
            print("\nSide by side, medians:")
            print(f"  {'quantity':<22}{'real':>10}{'synthetic':>12}{'ratio':>9}")
            for key in ("fg_pct", "dt_max", "wire_grey", "bg_grey", "contrast"):
                a, b = r[key][0], s[key][0]
                print(f"  {key:<22}{a:>10.2f}{b:>12.2f}{(b / a if a else 0):>9.2f}")
            print(f"  {'single component %':<22}{r['single_component_pct']:>10.0f}"
                  f"{s['single_component_pct']:>12.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
