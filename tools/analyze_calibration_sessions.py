"""
Stage S0: retrospective diagnosis of the archived calibration sessions.

Runs the Gate A and Gate B measures of ``camera/calibration_guidance.py`` over
every session in ``data/calibration/`` and reports, per session:

  * how many pairs were captured and how many the board was detected in,
  * the distribution of board-region sharpness,
  * the spread of board tilt angles, which is what determines whether the
    focal length is recoverable at all,
  * how many poses are degenerate by the Rojtberg and Kuijper rules,
  * the capture resolution actually used.

This answers the question the work plan asks, namely what the 23 previous
attempts have in common, before any new capture code is written.

Usage:
    python tools/analyze_calibration_sessions.py
    python tools/analyze_calibration_sessions.py --session calibration_20260216_161309
    python tools/analyze_calibration_sessions.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from camera.calibration_guidance import (  # noqa: E402
    analyze_pose, evaluate_frame, tenengrad, GateAThresholds, PoseInfo,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
log = logging.getLogger("s0")

# Board definition, from config/camera_config.py StereoConfig.
SQUARES_X, SQUARES_Y = 5, 7
SQUARE_MM, MARKER_MM = 37.0, 29.6
DICT_NAME = "DICT_6X6_250"
CORNERS_ON_BOARD = (SQUARES_X - 1) * (SQUARES_Y - 1)


def build_board():
    adict = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_NAME))
    if hasattr(cv2.aruco, "CharucoBoard"):
        board = cv2.aruco.CharucoBoard(
            (SQUARES_X, SQUARES_Y), SQUARE_MM / 1000.0, MARKER_MM / 1000.0, adict)
        detector = cv2.aruco.CharucoDetector(board)
        return board, detector, adict
    board = cv2.aruco.CharucoBoard_create(
        SQUARES_X, SQUARES_Y, SQUARE_MM / 1000.0, MARKER_MM / 1000.0, adict)
    return board, None, adict


def detect(gray, board, detector, adict):
    """Return (charuco_corners, charuco_ids) or (None, None)."""
    if detector is not None:
        corners, ids, _, _ = detector.detectBoard(gray)
        if corners is None or len(corners) == 0:
            return None, None
        return corners, ids
    params = cv2.aruco.DetectorParameters_create()
    mc, mids, _ = cv2.aruco.detectMarkers(gray, adict, parameters=params)
    if mids is None or len(mids) == 0:
        return None, None
    _, cc, ci = cv2.aruco.interpolateCornersCharuco(mc, mids, gray, board)
    if cc is None or len(cc) == 0:
        return None, None
    return cc, ci


def guess_intrinsics(w: int, h: int) -> np.ndarray:
    """A rough pinhole guess, used only to recover a board pose for the tilt
    statistics. The IMX477 has a 1.55 um pitch; the images here are scaled, so
    the focal length in pixels is scaled with them. An approximate K is enough
    for an angle, which is what this tool reports."""
    f_mm, pitch_mm, full_w = 8.0, 1.55e-3, 4056.0
    fx = (f_mm / pitch_mm) * (w / full_w)
    return np.array([[fx, 0, w / 2.0], [0, fx, h / 2.0], [0, 0, 1.0]], dtype=np.float64)


def analyze_session(session: Path, thresholds: GateAThresholds) -> Optional[Dict]:
    pairs = sorted(p for p in session.glob("calib_pair_*") if p.is_dir())
    if not pairs:
        return None
    board, detector, adict = build_board()

    rows: List[Dict] = []
    resolutions = set()
    for pair in pairs:
        meta_path = pair / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                res = meta.get("camera_config", {}).get("capture_resolution_used")
                if res:
                    resolutions.add(tuple(res))
            except Exception:
                pass

        for side in ("left", "right"):
            img_path = pair / f"{side}.jpg"
            if not img_path.exists():
                continue
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            h, w = img.shape[:2]
            corners, ids = detect(img, board, detector, adict)
            verdict = evaluate_frame(img, corners, CORNERS_ON_BOARD,
                                     thresholds=thresholds)
            row = {
                "pair": pair.name, "side": side, "w": w, "h": h,
                "detected": corners is not None,
                "n_corners": verdict.metrics.n_corners,
                "sharp_board": verdict.metrics.sharpness,
                "sharp_global": verdict.metrics.sharpness_global,
                "coverage": verdict.metrics.coverage,
                "clipped": verdict.metrics.clipped_fraction,
                "tilt_deg": None, "inplane_deg": None,
                "distance_mm": None, "degenerate": None,
            }
            if corners is not None and ids is not None and len(corners) >= 6:
                K = guess_intrinsics(w, h)
                obj = board.getChessboardCorners()[ids.flatten()]
                ok, rvec, tvec = cv2.solvePnP(
                    obj.astype(np.float64),
                    np.asarray(corners, np.float64).reshape(-1, 1, 2),
                    K, np.zeros(5))
                if ok:
                    pi = analyze_pose(rvec, tvec)
                    row.update(tilt_deg=pi.tilt_deg, inplane_deg=pi.inplane_deg,
                               distance_mm=pi.distance_mm * 1000.0,
                               degenerate=pi.degenerate)
            rows.append(row)

    det = [r for r in rows if r["detected"]]
    tilts = [r["tilt_deg"] for r in det if r["tilt_deg"] is not None]
    sharp = [r["sharp_board"] for r in det]
    return {
        "session": session.name,
        "n_pairs": len(pairs),
        "n_images": len(rows),
        "n_detected": len(det),
        "detect_rate": len(det) / len(rows) if rows else 0.0,
        "resolutions": sorted(resolutions),
        "tilt_min": min(tilts) if tilts else None,
        "tilt_max": max(tilts) if tilts else None,
        "tilt_spread": (max(tilts) - min(tilts)) if len(tilts) > 1 else None,
        "tilt_median": float(np.median(tilts)) if tilts else None,
        "n_degenerate": sum(1 for r in det if r["degenerate"]),
        "sharp_median": float(np.median(sharp)) if sharp else None,
        "sharp_min": float(np.min(sharp)) if sharp else None,
        "sharp_max": float(np.max(sharp)) if sharp else None,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "data" / "calibration"))
    ap.add_argument("--session", default=None, help="analyse only this session")
    ap.add_argument("--json", default=None, help="write the full per-image table here")
    ap.add_argument("--min-sharpness", type=float, default=0.0)
    args = ap.parse_args()

    root = Path(args.data)
    sessions = sorted(d for d in root.glob("calibration_*") if d.is_dir())
    if args.session:
        sessions = [d for d in sessions if d.name == args.session]
    if not sessions:
        print(f"no sessions found in {root}")
        return 1

    th = GateAThresholds(min_sharpness=args.min_sharpness)
    results = []
    print(f"{'session':34s} {'img':>4s} {'det':>5s} {'tilt min-max':>14s} "
          f"{'spread':>7s} {'degen':>6s} {'sharpness med':>14s} {'res':>11s}")
    print("-" * 104)
    for s in sessions:
        r = analyze_session(s, th)
        if r is None:
            continue
        results.append(r)
        tilt = (f"{r['tilt_min']:.0f}-{r['tilt_max']:.0f}"
                if r["tilt_min"] is not None else "n/a")
        spread = f"{r['tilt_spread']:.0f}" if r["tilt_spread"] is not None else "n/a"
        sharpm = f"{r['sharp_median']:.0f}" if r["sharp_median"] is not None else "n/a"
        res = (f"{r['resolutions'][0][0]}x{r['resolutions'][0][1]}"
               if r["resolutions"] else "?")
        print(f"{r['session']:34s} {r['n_images']:4d} "
              f"{100 * r['detect_rate']:4.0f}% {tilt:>14s} {spread:>7s} "
              f"{r['n_degenerate']:6d} {sharpm:>14s} {res:>11s}")

    print("\n" + "=" * 104)
    all_tilts = [t for r in results for t in
                 [x["tilt_deg"] for x in r["rows"] if x["tilt_deg"] is not None]]
    all_sharp = [x["sharp_board"] for r in results for x in r["rows"] if x["detected"]]
    all_glob = [x["sharp_global"] for r in results for x in r["rows"] if x["detected"]]
    n_img = sum(r["n_images"] for r in results)
    n_det = sum(r["n_detected"] for r in results)
    n_deg = sum(r["n_degenerate"] for r in results)

    print(f"sessions analysed          : {len(results)}")
    print(f"images                     : {n_img}, board detected in {n_det} "
          f"({100 * n_det / max(n_img, 1):.0f}%)")
    if all_tilts:
        q = np.percentile(all_tilts, [5, 25, 50, 75, 95])
        print(f"board tilt, all images     : p5 {q[0]:.0f}  p25 {q[1]:.0f}  "
              f"median {q[2]:.0f}  p75 {q[3]:.0f}  p95 {q[4]:.0f} deg")
        print(f"poses flagged degenerate   : {n_deg} of {n_det} "
              f"({100 * n_deg / max(n_det, 1):.0f}%)")
    if all_sharp:
        qs = np.percentile(all_sharp, [5, 50, 95])
        qg = np.percentile(all_glob, [5, 50, 95])
        print(f"sharpness over board       : p5 {qs[0]:.0f}  median {qs[1]:.0f}  "
              f"p95 {qs[2]:.0f}")
        print(f"sharpness over whole frame : p5 {qg[0]:.0f}  median {qg[1]:.0f}  "
              f"p95 {qg[2]:.0f}   <- what the old check measured")
    resolutions = sorted({tuple(x) for r in results for x in r["resolutions"]})
    print(f"capture resolutions used   : {resolutions}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nfull table written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
