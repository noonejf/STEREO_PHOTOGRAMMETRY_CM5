"""
Replay an archived calibration session through the guided session loop.

Feeds the stored frames to :class:`camera.guided_session.GuidedCalibrationSession`
one at a time, exactly as a live preview would, and prints the verdict for each
one plus the running progress. Nothing is written and no camera is needed, so
this is the way to exercise and tune the loop before putting it behind the GUI.

Usage:
    python tools/replay_guided_session.py calibration_20260216_160735
    python tools/replay_guided_session.py <session> --target 25 --quiet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from camera.calibration_guidance import GateAThresholds  # noqa: E402
from camera.guided_session import GuidedCalibrationSession  # noqa: E402
from tools.analyze_calibration_sessions import build_board, detect  # noqa: E402

SYMBOL = {"accepted": "[+]", "rejected_quality": "[-]",
          "rejected_pose": "[~]", "no_board": "[ ]"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--data", default=str(ROOT / "data" / "calibration"))
    ap.add_argument("--target", type=int, default=25)
    ap.add_argument("--min-per-bin", type=int, default=3)
    ap.add_argument("--min-sharpness", type=float, default=0.0)
    ap.add_argument("--side", default="left", choices=["left", "right"])
    ap.add_argument("--quiet", action="store_true", help="only the summary")
    args = ap.parse_args()

    sess_dir = Path(args.data) / args.session
    pairs = sorted(p for p in sess_dir.glob("calib_pair_*") if p.is_dir())
    if not pairs:
        print(f"no pairs in {sess_dir}")
        return 1

    board, detector, adict = build_board()
    first = cv2.imread(str(pairs[0] / f"{args.side}.jpg"), cv2.IMREAD_GRAYSCALE)
    if first is None:
        print("could not read the first frame")
        return 1
    size = (first.shape[1], first.shape[0])

    session = GuidedCalibrationSession(
        board, size, target_views=args.target,
        thresholds=GateAThresholds(min_sharpness=args.min_sharpness,
                                   enable_stability=False),
        min_per_bin=args.min_per_bin)

    print(f"session {args.session}, {len(pairs)} frames, {size[0]}x{size[1]}, "
          f"asking for {args.target} good views\n")

    for pair in pairs:
        img = cv2.imread(str(pair / f"{args.side}.jpg"), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        corners, ids = detect(img, board, detector, adict)
        r = session.submit(img, corners, ids)
        if not args.quiet:
            st = session.status()
            print(f"  {SYMBOL[r.status]} {pair.name:16s} {r.message[:52]:54s} "
                  f"{st.accepted:2d}/{args.target}  {100 * st.overall_progress():3.0f}%")

    st = session.status()
    res = session.result()

    print("\n" + "=" * 78)
    print(f"frames offered            : {st.seen}")
    print(f"views kept                : {st.accepted} of {args.target} requested")
    print(f"tilt spread of kept views : {res['tilt_spread_deg']:.1f} deg")
    print("\npose-space coverage (needs "
          f"{args.min_per_bin} per bin):")
    for (lo, hi, label) in session.tilt_bins:
        n = st.bin_counts[label]
        mark = "ok " if n >= args.min_per_bin else "   "
        print(f"  {mark} {lo:4.0f}-{hi:4.0f} deg  {n:2d}  {label}")

    if session.rejections:
        print("\nwhy frames were refused:")
        for reason, n in sorted(session.rejections.items(),
                                key=lambda kv: -kv[1]):
            print(f"  {n:3d}  {reason}")

    if res["sigmas"]:
        print(f"\nRMS reprojection : {res['rms_reprojection']:.4f} px")
        fx = res["camera_matrix"][0][0]
        sfx = res["sigmas"]["fx"]
        print(f"fx               : {fx:.1f} +- {sfx:.1f} px "
              f"({100 * sfx / fx:.2f} % relative)")
        worst = max(res["index_of_dispersion"],
                    key=lambda k: res["index_of_dispersion"][k])
        print(f"least determined : {worst} "
              f"(IOD {res['index_of_dispersion'][worst]:.3f})")

    print(f"\ncomplete         : {st.complete}")
    print(f"next             : {st.hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
