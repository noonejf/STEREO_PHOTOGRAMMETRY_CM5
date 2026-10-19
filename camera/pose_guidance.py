#!/usr/bin/env python3
"""
Target pose generation and on-screen guidance for stereo calibration.

This is the part of Rojtberg and Kuijper (ISMAR 2018) that the first
implementation left out. Telling the operator "I need a view between 45 and
70 degrees of tilt" asks them to translate an angle into a hand position;
drawing the pose they should match asks them only to line two shapes up. In
the authors' user study that difference took novices to a precise
calibration in about two minutes.

What this module provides:

  * :func:`next_target_pose`, which picks the next board pose from the rules
    in the paper: tilt to break the focal-length degeneracy, in-plane
    rotation so the board is parallel to neither image axis, an off-centre
    shift when the principal point is the parameter that needs work, and a
    frontal pose pushed into the corners when the distortion terms do.
  * :func:`project_board_outline`, which turns that pose into the polygon to
    draw.
  * :func:`stereo_counterpart`, which expresses the same physical pose in the
    right camera, so the operator sees where the board has to go in both
    views at once. A pose that only satisfies one camera is of no use to a
    stereo calibration.
  * :func:`pose_match`, which scores how close the board currently is, so the
    overlay can turn green and the capture can fire on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

#: In-plane rotation applied to every generated pose.
#:
#: Rojtberg and Kuijper rotate by this much so the pattern is parallel to
#: neither image axis: a board aligned with an axis leaves the principal
#: point along that axis unobservable.
INPLANE_DEG = 22.5

#: Fraction of the image width the board should span. Large enough that the
#: corners localise well, small enough that the whole board stays in frame
#: once it is tilted.
TARGET_FILL = 0.55

#: Offset applied when the principal point is the parameter being targeted,
#: as a fraction of the image size. The authors found this speeds convergence.
PRINCIPAL_SHIFT = 0.05


@dataclass
class TargetPose:
    """A board pose for the operator to match, and why it was chosen."""

    rvec: np.ndarray
    tvec: np.ndarray
    tilt_deg: float
    reason: str                 # one line, shown on screen
    targets_distortion: bool = False


def _board_extent(board) -> Tuple[float, float]:
    """Board width and height in metres, from its own corner coordinates."""
    pts = np.asarray(board.getChessboardCorners(), np.float64).reshape(-1, 3)
    return float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1]))


def board_outline_3d(board) -> np.ndarray:
    """The board's outer rectangle plus its diagonals, in board coordinates.

    The diagonals matter: an outline alone is ambiguous about which way the
    board is tilted, and the operator has to reproduce the tilt, not just the
    silhouette.
    """
    bw, bh = _board_extent(board)
    pts = np.asarray(board.getChessboardCorners(), np.float64).reshape(-1, 3)
    x0, y0 = float(pts[:, 0].min()), float(pts[:, 1].min())
    c = [(x0, y0), (x0 + bw, y0), (x0 + bw, y0 + bh), (x0, y0 + bh)]
    return np.array([[x, y, 0.0] for x, y in c], np.float64)


def _fit_distance(board, K, dist, rvec, image_size,
                  fill: float = TARGET_FILL) -> float:
    """
    Distance at which the whole board lands inside the frame at this tilt.

    Solving this from the board width alone is not enough and was the first
    version's mistake: this board is 111 by 185 mm, taller than it is wide,
    and the 22.5 degree in-plane rotation widens its bounding box further, so
    sizing on width put every generated pose off the bottom of the image.

    Projecting at a trial distance and scaling by the measured overflow
    converges in a couple of passes and needs no closed form, so it stays
    correct for any tilt, any board shape and any lens distortion.
    """
    w, h = image_size
    obj = board_outline_3d(board)
    R, _ = cv2.Rodrigues(np.asarray(rvec, np.float64))
    centre_local = obj.mean(axis=0)

    Z = 0.8
    for _ in range(6):
        tvec = np.array([0.0, 0.0, Z]) - R @ centre_local
        pts, _ = cv2.projectPoints(obj, rvec, tvec, K,
                                   np.asarray(dist, np.float64).reshape(-1))
        pts = pts.reshape(-1, 2)
        span_x = float(np.ptp(pts[:, 0]))
        span_y = float(np.ptp(pts[:, 1]))
        over = max(span_x / (fill * w), span_y / (fill * h))
        if 0.97 < over < 1.03:
            break
        Z *= over
        Z = float(np.clip(Z, 0.12, 20.0))
    return Z


def _rvec_from_tilt(tilt_deg: float, axis: str, inplane_deg: float) -> np.ndarray:
    """Rotation vector for a board tilted about one axis, then spun in plane."""
    t = np.deg2rad(tilt_deg)
    if axis == "x":
        R_tilt, _ = cv2.Rodrigues(np.array([t, 0.0, 0.0]))
    else:
        R_tilt, _ = cv2.Rodrigues(np.array([0.0, t, 0.0]))
    R_spin, _ = cv2.Rodrigues(np.array([0.0, 0.0, np.deg2rad(inplane_deg)]))
    rvec, _ = cv2.Rodrigues(R_spin @ R_tilt)
    return rvec.reshape(3)


def next_target_pose(board,
                     K: np.ndarray,
                     image_size: Tuple[int, int],
                     missing_bin: Optional[Tuple[float, float, str]] = None,
                     worst_param: Optional[str] = None,
                     taken_tilts: Sequence[float] = (),
                     ) -> TargetPose:
    """
    Choose the next pose to ask for.

    ``missing_bin`` is the under-filled tilt range, which takes priority
    because bin coverage is what the session blocks on. ``worst_param`` is the
    parameter with the largest index of dispersion, used once the bins are
    satisfied. ``taken_tilts`` lets the angle be spread inside a bin instead
    of repeating its midpoint.
    """
    w, h = image_size
    cx, cy = float(K[0, 2]), float(K[1, 2])
    dist = np.zeros(5)

    axis = "y"
    shift_u = shift_v = 0.0
    tilt = 45.0
    targets_distortion = False

    if missing_bin is not None:
        lo, hi, label = missing_bin
        # Spread angles inside the bin by binary subdivision of the range, as
        # the paper does, rather than always asking for the midpoint.
        inside = sorted(t for t in taken_tilts if lo <= t < hi)
        fracs = (0.5, 0.25, 0.75, 0.375, 0.625)
        frac = fracs[min(len(inside), len(fracs) - 1)]
        tilt = lo + frac * (hi - lo)

        # Tilt about the axis that foreshortens the board's LONGER side.
        # This board is 111 by 185 mm, so tilting about the vertical axis
        # squeezes the side that is already short and the target comes out a
        # thin slanted sliver: hard to match by hand and poorly conditioned
        # for corner localisation across the narrow direction. Foreshortening
        # the long side instead keeps the projected shape near square.
        bw0, bh0 = _board_extent(board)
        axis = "x" if bh0 >= bw0 else "y"
        # Alternate inside the bin so both focal lengths get constrained:
        # tilt about x informs fy, tilt about y informs fx.
        if len(inside) % 2 == 1:
            axis = "y" if axis == "x" else "x"

        reason = (f"tilt {tilt:.0f} deg about the "
                  f"{'horizontal' if axis == 'x' else 'vertical'} axis")
        if lo < 10.0:
            # The frontal bin exists for the distortion terms, which need the
            # board at the edges where the distortion is strongest.
            targets_distortion = True
            shift_u = PRINCIPAL_SHIFT * 4 * w * (1 if len(inside) % 2 == 0 else -1)
            shift_v = PRINCIPAL_SHIFT * 3 * h * (1 if (len(inside) // 2) % 2 == 0 else -1)
            reason = "near frontal, board out to the edge, for the distortion terms"
    else:
        p = (worst_param or "fx").lower()
        if p in ("fy", "cy"):
            axis = "x"
        if p == "cx":
            shift_u = PRINCIPAL_SHIFT * w
        elif p == "cy":
            shift_v = PRINCIPAL_SHIFT * h
        if p.startswith("k") or p.startswith("p"):
            targets_distortion = True
            tilt = 5.0
            shift_u = PRINCIPAL_SHIFT * 4 * w
        reason = f"targets {worst_param or 'fx'}"

    rvec = _rvec_from_tilt(tilt, axis, INPLANE_DEG)

    # Distance comes after the rotation, because how much room the board needs
    # depends on how it is turned.
    Z = _fit_distance(board, K, dist, rvec, image_size)

    # Place the board so its centre lands at the chosen image point, working
    # back through the pinhole: X = (u - cx) * Z / fx. The shift is clamped so
    # the board stays on screen: an off-centre target the operator cannot fit
    # in frame is worse than a centred one.
    margin_u = 0.5 * TARGET_FILL * w
    margin_v = 0.5 * TARGET_FILL * h
    u = float(np.clip(cx + shift_u, margin_u, w - margin_u))
    v = float(np.clip(cy + shift_v, margin_v, h - margin_v))
    X = (u - cx) * Z / float(K[0, 0])
    Y = (v - cy) * Z / float(K[1, 1])

    # The board's origin is a corner, so offset by its centre to put the
    # centre where it was asked for.
    R, _ = cv2.Rodrigues(rvec)
    centre_local = board_outline_3d(board).mean(axis=0)
    tvec = np.array([X, Y, Z]) - R @ centre_local

    return TargetPose(rvec=rvec, tvec=tvec, tilt_deg=float(tilt),
                      reason=reason, targets_distortion=targets_distortion)


def project_board_outline(board, rvec, tvec, K, dist) -> np.ndarray:
    """Project the outline to pixels. Returns a 4x2 array."""
    obj = board_outline_3d(board)
    pts, _ = cv2.projectPoints(obj, np.asarray(rvec, np.float64),
                               np.asarray(tvec, np.float64),
                               np.asarray(K, np.float64),
                               np.asarray(dist, np.float64).reshape(-1))
    return pts.reshape(-1, 2)


def stereo_counterpart(rvec, tvec,
                       R: Optional[np.ndarray] = None,
                       T: Optional[np.ndarray] = None,
                       baseline_m: float = 0.1) -> Tuple[np.ndarray, np.ndarray]:
    """
    Express a board pose given in the left camera in the right camera's frame.

    With a stereo calibration available the exact transform is used. Without
    one, the rig is treated as two parallel cameras separated by the baseline,
    which is what the support is built to be. The approximation only has to be
    good enough to aim at: the operator matches the shape, and the real pose
    is whatever they end up holding.
    """
    rvec = np.asarray(rvec, np.float64).reshape(3)
    tvec = np.asarray(tvec, np.float64).reshape(3)

    if R is not None and T is not None:
        R = np.asarray(R, np.float64).reshape(3, 3)
        T = np.asarray(T, np.float64).reshape(3)
        R_board, _ = cv2.Rodrigues(rvec)
        R_right = R @ R_board
        t_right = R @ tvec + T
        rv, _ = cv2.Rodrigues(R_right)
        return rv.reshape(3), t_right

    return rvec, tvec - np.array([float(baseline_m), 0.0, 0.0])


def pose_match(current_corners: np.ndarray,
               target_polygon: np.ndarray,
               image_size: Tuple[int, int]) -> Tuple[float, str]:
    """
    How close the board is to the target, as 0..1 and a short instruction.

    Compared in image space rather than in pose space on purpose: image space
    is what the operator can see and correct, and it sidesteps the question of
    how to weigh an angle against a distance.
    """
    w, h = image_size
    pts = np.asarray(current_corners, np.float64).reshape(-1, 2)
    tgt = np.asarray(target_polygon, np.float64).reshape(-1, 2)
    if len(pts) < 4:
        return 0.0, "show the board"

    cur_c = pts.mean(axis=0)
    tgt_c = tgt.mean(axis=0)
    diag = float(np.hypot(w, h))

    offset = float(np.linalg.norm(cur_c - tgt_c)) / diag
    cur_size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    tgt_size = float(np.linalg.norm(tgt.max(axis=0) - tgt.min(axis=0)))
    size_err = abs(cur_size - tgt_size) / max(tgt_size, 1.0)

    score = max(0.0, 1.0 - (offset * 3.0) - (size_err * 1.2))

    dx, dy = cur_c - tgt_c
    if offset > 0.06:
        if abs(dx) > abs(dy):
            hint = "move it left" if dx > 0 else "move it right"
        else:
            hint = "move it up" if dy > 0 else "move it down"
    elif size_err > 0.15:
        hint = "move it back" if cur_size > tgt_size else "bring it closer"
    else:
        hint = "match the tilt"
    return float(np.clip(score, 0.0, 1.0)), hint


def draw_target(frame: np.ndarray,
                polygon: np.ndarray,
                matched: bool = False,
                label: str = "") -> np.ndarray:
    """
    Draw the target outline on an RGB frame, in place.

    Line weight scales with the image so the overlay stays visible from the
    distance the board is actually held at, which is well back from the
    screen.
    """
    if polygon is None or len(polygon) < 4:
        return frame
    h, w = frame.shape[:2]
    thick = max(2, int(round(w / 320.0)))
    colour = (90, 230, 120) if matched else (60, 210, 240)   # RGB

    pts = np.asarray(polygon, np.int32).reshape(-1, 1, 2)
    cv2.polylines(frame, [pts], True, colour, thick, cv2.LINE_AA)

    # Diagonals give the tilt away; the outline alone does not.
    p = polygon.astype(np.int32)
    cv2.line(frame, tuple(p[0]), tuple(p[2]), colour, max(1, thick // 2), cv2.LINE_AA)
    cv2.line(frame, tuple(p[1]), tuple(p[3]), colour, max(1, thick // 2), cv2.LINE_AA)

    # One marked corner, so the operator can tell which way round it goes.
    cv2.circle(frame, tuple(p[0]), thick * 3, colour, -1, cv2.LINE_AA)

    if label:
        scale = max(0.5, w / 900.0)
        org = (int(polygon[:, 0].min()), max(24, int(polygon[:, 1].min()) - 10))
        cv2.putText(frame, label, org, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (0, 0, 0), int(thick * 2.5), cv2.LINE_AA)
        cv2.putText(frame, label, org, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    colour, max(1, thick), cv2.LINE_AA)
    return frame
