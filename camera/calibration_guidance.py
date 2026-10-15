"""
Guided, self-evaluating calibration support for the LINKU stereo pair.

This module implements the methods reviewed in
``Documentation/LINKU_Deliverable_Calibration_Method``. It is deliberately free
of any camera or GUI dependency so that it can be run offline against the
archived sessions in ``data/calibration/``.

What is implemented, and where it comes from:

Gate A, per-frame quality
    Sharpness, completeness, clipping and stability. The sharpness measure is
    evaluated over the detected board region only, not the whole frame, which
    matters in a dark room where most of the image is empty background.

Gate B, pose admissibility
    The degeneracy rules of Rojtberg and Kuijper (ISMAR 2018), themselves
    derived from Sturm and Maybank: a board parallel to the image plane leaves
    the focal length unrecoverable, and a board parallel to an image axis
    leaves the corresponding principal point coordinate unrecoverable.

Parameter uncertainty
    The index of dispersion sigma_i^2 / C_i and the per-parameter convergence
    ratio test of Rojtberg and Kuijper. OpenCV's ``calibrateCameraExtended``
    already returns the standard deviations of the intrinsics, which it derives
    from the same Jacobian the Levenberg-Marquardt step computes, so no
    separate covariance propagation is needed.

Max ERE
    The sampling-based expected reprojection error of Richardson, Strom and
    Olson (IROS 2013), used as a stopping criterion expressed in pixels.

    Caveat, stated here because it affects interpretation: OpenCV exposes only
    the standard deviations, that is the diagonal of the parameter covariance,
    not the full matrix. The Max ERE computed here therefore ignores
    correlations between parameters and is an approximation of the published
    metric. It remains monotone in the right direction and is useful for
    monitoring convergence, but it should not be quoted as the published
    quantity without computing the full covariance.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Gate A: is this frame usable at all?
# --------------------------------------------------------------------------

#: Order in which OpenCV returns ``stdDeviationsIntrinsics``.
INTRINSIC_NAMES: Tuple[str, ...] = (
    "fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2", "k3",
)

#: Parameter grouping of Rojtberg and Kuijper: the pinhole group needs angular
#: spread, the distortion group needs coverage of the image edges.
PINHOLE_PARAMS = ("fx", "fy", "cx", "cy")
DISTORTION_PARAMS = ("k1", "k2", "p1", "p2", "k3")


@dataclass
class FrameMetrics:
    """Measured properties of one captured frame."""

    n_corners: int = 0
    completeness: float = 0.0       # detected corners / corners on the board
    sharpness: float = 0.0          # Tenengrad over the board region
    sharpness_global: float = 0.0   # same measure over the whole frame
    coverage: float = 0.0           # board bounding box / image area
    clipped_fraction: float = 0.0   # saturated pixels inside the board region
    motion_px: Optional[float] = None  # median corner shift vs previous frame


@dataclass
class FrameVerdict:
    """Gate A outcome for one frame."""

    accepted: bool
    reasons: List[str] = field(default_factory=list)
    metrics: FrameMetrics = field(default_factory=FrameMetrics)

    def reason_text(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "ok"


@dataclass
class GateAThresholds:
    """Acceptance thresholds for Gate A.

    The defaults are starting points, not validated numbers. ``min_sharpness``
    in particular must be fixed empirically against real sessions; see
    ``tools/analyze_calibration_sessions.py``, which reports the distribution
    actually observed. The value shipped in the previous implementation, a
    Laplacian variance of 3.0 over the whole frame, accepted essentially every
    image and is the reason this threshold is called out here.
    """

    min_corners: int = 8
    min_completeness: float = 0.30
    min_sharpness: float = 0.0        # 0 disables; set from measured data
    min_coverage: float = 0.02
    max_coverage: float = 0.90
    max_clipped_fraction: float = 0.02
    max_motion_px: float = 2.0

    #: Whether to require the board to be momentarily still.
    #:
    #: This test compares a frame against the one before it, so it is only
    #: meaningful on a continuous stream where consecutive frames are
    #: milliseconds apart. Replaying archived stills, which were taken seconds
    #: apart with the board deliberately moved in between, must disable it:
    #: otherwise every frame is rejected for motion that was intentional.
    enable_stability: bool = True


def tenengrad(gray: np.ndarray) -> float:
    """Mean squared Sobel gradient magnitude.

    Preferred over the variance of the Laplacian because it is less dominated
    by isolated noise pixels, which matters when the region analysed is small.
    """
    if gray.size == 0:
        return 0.0
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return float(np.mean(gx * gx + gy * gy))


def _board_roi(gray: np.ndarray, corners: np.ndarray, pad: int = 8
               ) -> Tuple[np.ndarray, Tuple[int, int, int, int], float]:
    """Crop the frame to the bounding box of the detected corners."""
    pts = corners.reshape(-1, 2)
    x0 = max(int(np.floor(pts[:, 0].min())) - pad, 0)
    y0 = max(int(np.floor(pts[:, 1].min())) - pad, 0)
    x1 = min(int(np.ceil(pts[:, 0].max())) + pad, gray.shape[1])
    y1 = min(int(np.ceil(pts[:, 1].max())) + pad, gray.shape[0])
    if x1 <= x0 or y1 <= y0:
        return np.empty((0, 0), gray.dtype), (x0, y0, x1, y1), 0.0
    roi = gray[y0:y1, x0:x1]
    coverage = float((x1 - x0) * (y1 - y0)) / float(gray.shape[0] * gray.shape[1])
    return roi, (x0, y0, x1, y1), coverage


def evaluate_frame(gray: np.ndarray,
                   corners: Optional[np.ndarray],
                   corners_on_board: int,
                   previous_corners: Optional[np.ndarray] = None,
                   thresholds: Optional[GateAThresholds] = None,
                   ) -> FrameVerdict:
    """Gate A. Decide whether a frame is worth measuring at all.

    Args:
        gray: single channel image.
        corners: detected ChArUco corners, shape (N, 1, 2) or (N, 2), or None.
        corners_on_board: how many corners the board has in total, used for the
            completeness ratio.
        previous_corners: corners from the preceding frame, for the stability
            test. Pass None on the first frame.
        thresholds: acceptance thresholds; defaults are used when omitted.
    """
    th = thresholds or GateAThresholds()
    m = FrameMetrics()

    if corners is None or len(corners) == 0:
        return FrameVerdict(False, ["board not detected"], m)

    pts = np.asarray(corners, dtype=np.float64).reshape(-1, 2)
    m.n_corners = int(len(pts))
    m.completeness = m.n_corners / float(max(corners_on_board, 1))

    roi, _, m.coverage = _board_roi(gray, pts)
    m.sharpness = tenengrad(roi)
    m.sharpness_global = tenengrad(gray)
    if roi.size:
        hi = 250 if gray.dtype == np.uint8 else 0.98 * float(gray.max() or 1)
        m.clipped_fraction = float(np.mean(roi >= hi))

    if previous_corners is not None and len(previous_corners) == len(pts):
        prev = np.asarray(previous_corners, dtype=np.float64).reshape(-1, 2)
        m.motion_px = float(np.median(np.linalg.norm(pts - prev, axis=1)))

    reasons: List[str] = []
    if m.n_corners < th.min_corners:
        reasons.append(f"only {m.n_corners} corners")
    if m.completeness < th.min_completeness:
        reasons.append(f"board {100 * m.completeness:.0f}% detected")
    if th.min_sharpness > 0 and m.sharpness < th.min_sharpness:
        reasons.append(f"blurred (sharpness {m.sharpness:.0f})")
    if m.coverage < th.min_coverage:
        reasons.append("board too small in frame")
    if m.coverage > th.max_coverage:
        reasons.append("board too large in frame")
    if m.clipped_fraction > th.max_clipped_fraction:
        reasons.append(f"{100 * m.clipped_fraction:.0f}% of the board clipped")
    if (th.enable_stability and m.motion_px is not None
            and m.motion_px > th.max_motion_px):
        reasons.append(f"moving ({m.motion_px:.1f} px between frames)")

    return FrameVerdict(not reasons, reasons, m)


#: Coarse categories used when tallying why frames were refused, so that the
#: summary groups "moving (72 px)" and "moving (120 px)" together.
def rejection_category(reason: str) -> str:
    """Map a detailed rejection reason to a category for counting."""
    r = reason.lower()
    for key, label in (("moving", "board moving"),
                       ("blurred", "out of focus"),
                       ("clipped", "clipped highlights"),
                       ("corners", "too few corners"),
                       ("% detected", "board partly detected"),
                       ("too small", "board too small in frame"),
                       ("too large", "board too large in frame"),
                       ("duplicat", "duplicate pose"),
                       ("outside the useful range", "tilt outside useful range"),
                       ("not found", "board not found"),
                       ("pose", "pose not recoverable")):
        if key in r:
            return label
    return reason


# --------------------------------------------------------------------------
# Gate B: does this pose carry information the solution still needs?
# --------------------------------------------------------------------------

@dataclass
class PoseInfo:
    """Geometry of one board pose relative to the camera."""

    tilt_deg: float          # angle between the board normal and the optical axis
    inplane_deg: float       # rotation of the board about the optical axis
    distance_mm: float
    degenerate: bool
    notes: List[str] = field(default_factory=list)


def analyze_pose(rvec: np.ndarray,
                 tvec: np.ndarray,
                 min_tilt_deg: float = 5.0,
                 axis_align_tol_deg: float = 10.0,
                 ) -> PoseInfo:
    """Gate B, first half: is this pose admissible for the pinhole parameters?

    The two rules come from Rojtberg and Kuijper, after Sturm and Maybank:

    * A board parallel to the image plane makes the focal length unrecoverable,
      because a larger focal length at a greater distance gives an identical
      image. ``min_tilt_deg`` defaults to 5 degrees, the spread Triggs found
      necessary.
    * A board parallel to an image axis prevents estimating the principal point
      along that axis. Their fix is to rotate the view by 22.5 degrees, so we
      flag in-plane angles that sit near a multiple of 90 degrees.

    Note that these rules constrain poses used for the *pinhole* group. The
    distortion group deliberately wants frontal views at the image edges, so a
    pose flagged here is not useless, it is simply not useful for ``C_K``.
    """
    R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3))
    # Board normal in camera coordinates is the third column of R.
    normal = R[:, 2]
    axis = np.array([0.0, 0.0, 1.0])
    cos_t = abs(float(np.dot(normal, axis)) / (np.linalg.norm(normal) + 1e-12))
    tilt = math.degrees(math.acos(min(cos_t, 1.0)))

    # In-plane rotation: direction of the board x axis projected on the sensor.
    inplane = math.degrees(math.atan2(float(R[1, 0]), float(R[0, 0]))) % 180.0

    t = np.asarray(tvec, dtype=np.float64).reshape(3)
    distance = float(np.linalg.norm(t))

    notes: List[str] = []
    if tilt < min_tilt_deg:
        notes.append(f"nearly parallel to the sensor (tilt {tilt:.1f} deg): "
                     "does not constrain the focal length")
    near_axis = min(inplane, abs(inplane - 90.0), abs(inplane - 180.0))
    if near_axis < axis_align_tol_deg:
        notes.append(f"aligned with an image axis (in-plane {inplane:.1f} deg): "
                     "does not constrain that principal point coordinate")

    return PoseInfo(tilt, inplane, distance, bool(notes), notes)


def pose_novelty(pose: PoseInfo,
                 accepted: Sequence[PoseInfo],
                 min_tilt_separation_deg: float = 8.0,
                 min_inplane_separation_deg: float = 15.0,
                 ) -> Tuple[bool, str]:
    """Gate B, second half: is this pose meaningfully different from the set?

    A cheap stand-in for the full information-gain test. The strict version
    predicts the covariance that adding this frame would produce; this one
    rejects poses that duplicate the angular configuration of a frame already
    held, which is what the duplicate would mostly fail to improve anyway.
    """
    for prev in accepted:
        d_tilt = abs(pose.tilt_deg - prev.tilt_deg)
        d_inplane = abs(pose.inplane_deg - prev.inplane_deg)
        d_inplane = min(d_inplane, 180.0 - d_inplane)
        if d_tilt < min_tilt_separation_deg and d_inplane < min_inplane_separation_deg:
            return False, (f"duplicates an existing pose "
                           f"(tilt {prev.tilt_deg:.0f} deg, "
                           f"in-plane {prev.inplane_deg:.0f} deg)")
    return True, "new pose"


# --------------------------------------------------------------------------
# Parameter uncertainty and convergence
# --------------------------------------------------------------------------

@dataclass
class UncertaintyState:
    """Uncertainty of one calibration solution."""

    values: Dict[str, float]
    sigmas: Dict[str, float]
    iod: Dict[str, float]            # index of dispersion, sigma^2 / value
    rms_reprojection: float
    n_views: int

    def max_iod(self) -> Tuple[str, float]:
        """The parameter currently least well determined."""
        name = max(self.iod, key=lambda k: self.iod[k])
        return name, self.iod[name]

    def worst_pinhole(self) -> Tuple[str, float]:
        sub = {k: v for k, v in self.iod.items() if k in PINHOLE_PARAMS}
        name = max(sub, key=lambda k: sub[k])
        return name, sub[name]


def uncertainty_from_std(camera_matrix: np.ndarray,
                         dist_coeffs: np.ndarray,
                         std_intrinsics: np.ndarray,
                         rms: float,
                         n_views: int) -> UncertaintyState:
    """Package OpenCV's ``stdDeviationsIntrinsics`` into an UncertaintyState.

    The index of dispersion is sigma^2 / value, following Rojtberg and
    Kuijper, who use it so that parameters with different units and magnitudes
    can be compared against each other. Parameters whose value is near zero,
    which the distortion terms often are, fall back to sigma^2 alone, as the
    authors specify.
    """
    K = np.asarray(camera_matrix, dtype=np.float64)
    d = np.asarray(dist_coeffs, dtype=np.float64).reshape(-1)
    std = np.asarray(std_intrinsics, dtype=np.float64).reshape(-1)

    values = {
        "fx": float(K[0, 0]), "fy": float(K[1, 1]),
        "cx": float(K[0, 2]), "cy": float(K[1, 2]),
    }
    for i, name in enumerate(("k1", "k2", "p1", "p2", "k3")):
        values[name] = float(d[i]) if i < len(d) else 0.0

    sigmas, iod = {}, {}
    for i, name in enumerate(INTRINSIC_NAMES):
        s = float(std[i]) if i < len(std) else float("nan")
        sigmas[name] = s
        v = values[name]
        iod[name] = (s * s / abs(v)) if abs(v) > 1e-9 else (s * s)

    return UncertaintyState(values, sigmas, iod, float(rms), int(n_views))


def converged(previous: UncertaintyState,
              current: UncertaintyState,
              min_reduction: float = 0.05,
              ) -> Dict[str, bool]:
    """Per-parameter convergence by the ratio test of Rojtberg and Kuijper.

    A parameter is declared converged when the reduction ``1 - r`` of its
    variance between successive solutions falls below ``min_reduction``.
    """
    out: Dict[str, bool] = {}
    for name in INTRINSIC_NAMES:
        s0, s1 = previous.sigmas.get(name), current.sigmas.get(name)
        if s0 is None or s1 is None or not np.isfinite(s0) or not np.isfinite(s1) or s0 <= 0:
            out[name] = False
            continue
        r = (s1 * s1) / (s0 * s0)
        out[name] = (1.0 - r) < min_reduction
    return out


# --------------------------------------------------------------------------
# Max ERE
# --------------------------------------------------------------------------

def max_ere(camera_matrix: np.ndarray,
            dist_coeffs: np.ndarray,
            std_intrinsics: np.ndarray,
            image_size: Tuple[int, int],
            n_samples: int = 100,
            grid: int = 5,
            depth_mm: float = 2000.0,
            rng: Optional[np.random.Generator] = None,
            ) -> float:
    """Approximate Max ERE of Richardson, Strom and Olson.

    A grid of 3D test points is placed so that its projection covers the image
    uniformly. Calibrations are sampled from the parameter posterior, each test
    point is projected under every sample, and the metric is the maximum over
    the grid of the mean displacement from the projection under the mean
    calibration. Taking the maximum rather than the mean is deliberate: it
    checks that the calibration is constrained everywhere, not on average.

    Approximation, as noted in the module docstring: only the diagonal of the
    parameter covariance is available from OpenCV, so correlations between
    parameters are ignored and the result is a lower bound on the published
    metric rather than the metric itself.

    Returns the Max ERE in pixels.
    """
    rng = rng or np.random.default_rng(0)
    K = np.asarray(camera_matrix, dtype=np.float64)
    d = np.asarray(dist_coeffs, dtype=np.float64).reshape(-1)
    std = np.asarray(std_intrinsics, dtype=np.float64).reshape(-1)
    w, h = image_size

    # Test points: a grid spanning the image, unprojected to a plane at depth.
    us = np.linspace(0.1 * w, 0.9 * w, grid)
    vs = np.linspace(0.1 * h, 0.9 * h, grid)
    uu, vv = np.meshgrid(us, vs)
    uv = np.stack([uu.ravel(), vv.ravel()], axis=1).astype(np.float64)
    normalized = cv2.undistortPoints(uv.reshape(-1, 1, 2), K, d).reshape(-1, 2)
    pts3d = np.concatenate(
        [normalized * depth_mm, np.full((len(normalized), 1), depth_mm)], axis=1)

    zero = np.zeros(3)
    base, _ = cv2.projectPoints(pts3d, zero, zero, K, d)
    base = base.reshape(-1, 2)

    acc = np.zeros(len(pts3d))
    n_par = min(len(std), 9)
    for _ in range(n_samples):
        Ks = K.copy()
        ds = d.copy()
        perturbed = [std[i] * rng.standard_normal() if np.isfinite(std[i]) else 0.0
                     for i in range(n_par)]
        Ks[0, 0] += perturbed[0]
        Ks[1, 1] += perturbed[1]
        Ks[0, 2] += perturbed[2]
        Ks[1, 2] += perturbed[3]
        for i in range(4, n_par):
            j = i - 4
            if j < len(ds):
                ds[j] += perturbed[i]
        proj, _ = cv2.projectPoints(pts3d, zero, zero, Ks, ds)
        acc += np.linalg.norm(proj.reshape(-1, 2) - base, axis=1)

    return float(np.max(acc / n_samples))


# --------------------------------------------------------------------------
# Session orchestration
# --------------------------------------------------------------------------

@dataclass
class SessionReport:
    """Everything a finished or in-progress session can report."""

    n_frames_seen: int = 0
    n_accepted: int = 0
    rejections: Dict[str, int] = field(default_factory=dict)
    poses: List[PoseInfo] = field(default_factory=list)
    uncertainty: Optional[UncertaintyState] = None
    max_ere_px: Optional[float] = None
    converged_flags: Dict[str, bool] = field(default_factory=dict)

    def tilt_spread_deg(self) -> float:
        """Angular spread of the accepted poses.

        Triggs found a spread above roughly 5 degrees necessary for the focal
        length to be determined; this is the number to check that against.
        """
        if len(self.poses) < 2:
            return 0.0
        tilts = [p.tilt_deg for p in self.poses]
        return float(max(tilts) - min(tilts))

    def progress(self) -> float:
        """Fraction of intrinsic parameters that have converged, in [0, 1]."""
        if not self.converged_flags:
            return 0.0
        return sum(self.converged_flags.values()) / float(len(self.converged_flags))
