"""
The guided calibration session: continuous capture that keeps only good views.

This is the capture loop described in Chapter 4 of
``Documentation/LINKU_Deliverable_Calibration_Method``. It is the piece that
turns the measures in :mod:`camera.calibration_guidance` into a procedure.

The contract it implements:

  * Frames are submitted continuously. The session, not the operator, decides
    which ones are kept.
  * A rejected frame does **not** consume one of the requested slots. Asking
    for 25 views means ending with 25 views that passed both gates, however
    many frames had to be looked at to get them.
  * Every submission returns a verdict and a plain-language reason, so the
    rejection is visible at the moment it happens.
  * Progress is reported as coverage of the pose space and, once enough views
    exist to fit, as convergence of the parameter uncertainty. It is not a
    count of photographs.

The pose-space requirement is the part that addresses the measured cause of
the previous failures. The retrospective analysis of the archive found a
median board tilt of 4.4 degrees and not one frame above 45 degrees, which
leaves the focal length unrecoverable no matter how many frames are taken.
This session therefore refuses to declare itself complete until the accepted
set spans a range of tilts, following the angular-spread requirement of
Rojtberg and Kuijper (ISMAR 2018).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from camera.calibration_guidance import (
    DISTORTION_PARAMS, FrameVerdict, GateAThresholds, PINHOLE_PARAMS, PoseInfo,
    UncertaintyState, analyze_pose, converged, evaluate_frame,
    intrinsics_covariance, max_ere, max_ere_from_covariance,
    rescale_to_opencv_sigmas,
    pose_novelty, rejection_category, uncertainty_from_std,
)

logger = logging.getLogger(__name__)


#: Tilt bins the accepted set must cover, in degrees.
#:
#: The frontal bin exists because the distortion coefficients need frontal
#: views at the image edges, where the distortion is strongest; the tilted
#: bins exist because the pinhole parameters need angular spread. Rojtberg and
#: Kuijper make exactly this split and generate poses across roughly +-70
#: degrees, which is the range these bins cover.
DEFAULT_TILT_BINS: Tuple[Tuple[float, float, str], ...] = (
    (0.0, 10.0, "frontal, for the distortion terms"),
    (15.0, 30.0, "slightly tilted"),
    (30.0, 45.0, "clearly tilted"),
    (45.0, 70.0, "strongly tilted"),
)

#: Minimum accepted views per bin before the session can complete.
DEFAULT_MIN_PER_BIN = 3


@dataclass
class SubmitResult:
    """Outcome of offering one frame to the session."""

    status: str                 # accepted | rejected_quality | rejected_pose | no_board
    message: str                # what to tell the operator, in one line
    verdict: Optional[FrameVerdict] = None
    pose: Optional[PoseInfo] = None
    accepted_total: int = 0

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


@dataclass
class SessionStatus:
    """Everything the interface needs to draw, in one object."""

    accepted: int
    target: int
    seen: int
    bin_counts: Dict[str, int]
    bins_satisfied: bool
    coverage_progress: float            # 0..1, pose-space coverage
    uncertainty: Optional[UncertaintyState] = None
    converged_flags: Dict[str, bool] = field(default_factory=dict)
    convergence_progress: float = 0.0   # 0..1, parameters converged
    max_ere_px: Optional[float] = None
    complete: bool = False
    hint: str = ""

    def overall_progress(self) -> float:
        """Single 0..1 figure for a progress bar.

        Before there are enough views to fit, this is pose-space coverage.
        After that it is the mean of coverage and parameter convergence, so
        the bar keeps moving for the right reason rather than counting frames.
        """
        if self.uncertainty is None:
            return self.coverage_progress
        return 0.5 * (self.coverage_progress + self.convergence_progress)


class GuidedCalibrationSession:
    """Collects a set of calibration views that is good by construction."""

    def __init__(self,
                 board,
                 image_size: Tuple[int, int],
                 target_views: int = 25,
                 thresholds: Optional[GateAThresholds] = None,
                 tilt_bins: Sequence[Tuple[float, float, str]] = DEFAULT_TILT_BINS,
                 min_per_bin: int = DEFAULT_MIN_PER_BIN,
                 refit_every: int = 1,
                 min_views_to_fit: int = 6,
                 compute_max_ere: bool = False):
        self.board = board
        self.image_size = image_size
        self.target_views = int(target_views)
        self.thresholds = thresholds or GateAThresholds()
        self.tilt_bins = tuple(tilt_bins)
        self.min_per_bin = int(min_per_bin)
        self.refit_every = max(int(refit_every), 1)
        self.min_views_to_fit = int(min_views_to_fit)
        self.compute_max_ere = bool(compute_max_ere)

        self.corners_on_board = len(board.getChessboardCorners())

        self._corners: List[np.ndarray] = []
        self._ids: List[np.ndarray] = []
        self._poses: List[PoseInfo] = []
        self._prev_corners: Optional[np.ndarray] = None

        self.seen = 0
        self.rejections: Dict[str, int] = {}
        self._uncertainty: Optional[UncertaintyState] = None
        self._previous_uncertainty: Optional[UncertaintyState] = None
        self._converged: Dict[str, bool] = {}
        self._max_ere: Optional[float] = None
        self._K: Optional[np.ndarray] = None
        self._d: Optional[np.ndarray] = None
        self._rvecs: List[np.ndarray] = []
        self._tvecs: List[np.ndarray] = []
        self._covariance: Optional[np.ndarray] = None

    # -- internals --------------------------------------------------------

    def _bin_of(self, tilt: float) -> Optional[str]:
        for lo, hi, label in self.tilt_bins:
            if lo <= tilt < hi:
                return label
        return None

    def _bin_counts(self) -> Dict[str, int]:
        counts = {label: 0 for _, _, label in self.tilt_bins}
        for p in self._poses:
            b = self._bin_of(p.tilt_deg)
            if b is not None:
                counts[b] += 1
        return counts

    def _provisional_K(self) -> np.ndarray:
        """Intrinsics used only to recover a board pose for the tilt test.

        Once a real fit exists it is used; before that a rough guess suffices,
        because the tilt angle is insensitive to focal-length error. Varying
        the assumed focal length by 20 percent moves the recovered tilt by
        under one degree, which was verified on the archived sessions.
        """
        if self._K is not None:
            return self._K
        w, h = self.image_size
        return np.array([[w, 0, w / 2.0], [0, w, h / 2.0], [0, 0, 1.0]], float)

    def _estimate_pose(self, corners: np.ndarray, ids: np.ndarray) -> Optional[PoseInfo]:
        if ids is None or len(ids) < 6:
            return None
        obj = self.board.getChessboardCorners()[np.asarray(ids).flatten()]
        d = self._d if self._d is not None else np.zeros(5)
        ok, rvec, tvec = cv2.solvePnP(
            obj.astype(np.float64),
            np.asarray(corners, np.float64).reshape(-1, 1, 2),
            self._provisional_K(), d)
        return analyze_pose(rvec, tvec) if ok else None

    def _refit(self) -> None:
        if len(self._corners) < self.min_views_to_fit:
            return
        try:
            (rms, K, d, rvecs, tvecs, sdI, _,
             _) = cv2.aruco.calibrateCameraCharucoExtended(
                self._corners, self._ids, self.board, self.image_size, None, None)
        except cv2.error as exc:
            logger.warning("refit failed: %s", exc)
            return
        self._K, self._d = K, d
        self._rvecs, self._tvecs = list(rvecs), list(tvecs)
        self._previous_uncertainty = self._uncertainty
        self._uncertainty = uncertainty_from_std(K, d, sdI, rms, len(self._corners))
        if self._previous_uncertainty is not None:
            self._converged = converged(self._previous_uncertainty, self._uncertainty)

        if self.compute_max_ere:
            # Full covariance when it can be built, which is the published
            # metric. The diagonal-only fallback overstates the error badly,
            # because it throws away the focal-length/distance and principal-
            # point/translation correlations.
            objs = [self.board.getChessboardCorners()[np.asarray(i).flatten()]
                    for i in self._ids]
            cov = intrinsics_covariance(objs, self._corners, rvecs, tvecs,
                                        K, d, rms)
            if cov is not None:
                cov = rescale_to_opencv_sigmas(cov, sdI)
            self._covariance = cov
            if cov is not None:
                self._max_ere = max_ere_from_covariance(
                    K, d, cov, self.image_size, n_samples=80)
            else:
                self._max_ere = max_ere(K, d, sdI, self.image_size, n_samples=60)

    # -- public API -------------------------------------------------------

    def submit(self,
               gray: np.ndarray,
               corners: Optional[np.ndarray],
               ids: Optional[np.ndarray]) -> SubmitResult:
        """Offer one frame. The session decides whether to keep it."""
        self.seen += 1

        verdict = evaluate_frame(gray, corners, self.corners_on_board,
                                 previous_corners=self._prev_corners,
                                 thresholds=self.thresholds)
        self._prev_corners = (np.asarray(corners).reshape(-1, 2)
                              if corners is not None and len(corners) else None)

        if corners is None or len(corners) == 0:
            self._count("no board")
            return SubmitResult("no_board", "board not found", verdict,
                                accepted_total=len(self._corners))

        if not verdict.accepted:
            self._count(verdict.reasons[0] if verdict.reasons else "quality")
            return SubmitResult("rejected_quality", verdict.reason_text(), verdict,
                                accepted_total=len(self._corners))

        pose = self._estimate_pose(corners, ids)
        if pose is None:
            self._count("pose not recoverable")
            return SubmitResult("rejected_pose", "pose could not be estimated",
                                verdict, accepted_total=len(self._corners))

        # Gate B. A frame in an under-filled tilt bin is wanted even if it
        # resembles an existing pose, because bin coverage is the binding
        # constraint; elsewhere, duplicates are refused.
        bin_label = self._bin_of(pose.tilt_deg)
        if bin_label is None:
            self._count("tilt outside the useful range")
            return SubmitResult("rejected_pose",
                                f"tilt {pose.tilt_deg:.0f} deg is outside the "
                                f"useful range", verdict, pose,
                                len(self._corners))

        counts = self._bin_counts()
        if counts[bin_label] >= self.min_per_bin:
            novel, why = pose_novelty(pose, self._poses)
            if not novel:
                self._count("duplicate pose")
                return SubmitResult("rejected_pose", why, verdict, pose,
                                    len(self._corners))

        self._corners.append(np.asarray(corners, np.float32).reshape(-1, 1, 2))
        self._ids.append(np.asarray(ids, np.int32).reshape(-1, 1))
        self._poses.append(pose)

        if len(self._corners) % self.refit_every == 0:
            self._refit()

        return SubmitResult("accepted",
                            f"kept ({bin_label}, tilt {pose.tilt_deg:.0f} deg)",
                            verdict, pose, len(self._corners))

    def _count(self, reason: str) -> None:
        key = rejection_category(reason)
        self.rejections[key] = self.rejections.get(key, 0) + 1

    def status(self) -> SessionStatus:
        counts = self._bin_counts()
        satisfied = all(c >= self.min_per_bin for c in counts.values())
        needed = self.min_per_bin * len(self.tilt_bins)
        have = sum(min(c, self.min_per_bin) for c in counts.values())
        coverage = have / float(needed) if needed else 1.0

        conv = (sum(self._converged.values()) / float(len(self._converged))
                if self._converged else 0.0)
        complete = satisfied and len(self._corners) >= self.target_views

        return SessionStatus(
            accepted=len(self._corners), target=self.target_views, seen=self.seen,
            bin_counts=counts, bins_satisfied=satisfied,
            coverage_progress=coverage, uncertainty=self._uncertainty,
            converged_flags=dict(self._converged), convergence_progress=conv,
            max_ere_px=self._max_ere, complete=complete, hint=self.hint())

    def hint(self) -> str:
        """One line telling the operator what to do next."""
        counts = self._bin_counts()
        missing = [(label, self.min_per_bin - c)
                   for (_, _, label), c in
                   ((b, counts[b[2]]) for b in self.tilt_bins)
                   if c < self.min_per_bin]
        if missing:
            label, n = missing[0]
            lo, hi = next((lo, hi) for lo, hi, l in self.tilt_bins if l == label)
            return (f"need {n} more view(s) at {lo:.0f} to {hi:.0f} degrees "
                    f"of tilt ({label})")

        if len(self._corners) < self.target_views:
            left = self.target_views - len(self._corners)
            if self._uncertainty is not None:
                worst, _ = self._uncertainty.max_iod()
                group = ("tilt the board further and move it off centre"
                         if worst in PINHOLE_PARAMS else
                         "bring the board to the edges and corners of the frame")
                return (f"{left} more view(s). Least determined: {worst}; "
                        f"{group}")
            return f"{left} more view(s)"

        return "complete: pose space covered and target reached"

    def result(self) -> Dict:
        """Final calibration and the evidence behind it."""
        if self._uncertainty is None:
            self._refit()
        st = self.status()
        return {
            "camera_matrix": None if self._K is None else self._K.tolist(),
            "dist_coeffs": None if self._d is None else self._d.tolist(),
            "n_views": len(self._corners),
            "frames_seen": self.seen,
            "rejections": dict(self.rejections),
            "tilt_deg": [p.tilt_deg for p in self._poses],
            "tilt_spread_deg": (max(p.tilt_deg for p in self._poses)
                                - min(p.tilt_deg for p in self._poses)
                                if len(self._poses) > 1 else 0.0),
            "bin_counts": st.bin_counts,
            "rms_reprojection": (None if self._uncertainty is None
                                 else self._uncertainty.rms_reprojection),
            "sigmas": (None if self._uncertainty is None
                       else dict(self._uncertainty.sigmas)),
            "index_of_dispersion": (None if self._uncertainty is None
                                    else dict(self._uncertainty.iod)),
            "max_ere_px": self._max_ere,
            "complete": st.complete,
        }
