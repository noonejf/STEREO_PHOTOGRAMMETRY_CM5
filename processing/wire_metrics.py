"""
Wire Metrics - Cuantificación 3D del cable a partir del tracking estéreo.

Dado el output del SmartWireTracker (izquierdo y derecho) y la calibración,
computa métricas reales del cable en metros:

  - Longitud total del cable en 3D
  - Perfil de profundidad Z a lo largo del cable
  - Perfil de diámetro estimado (desde Distance Transform + Z)
  - Curvatura local (suavizada)
  - Índice de rectitud
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

import numpy as np


@dataclass
class WireMetrics:
    """Resultado completo de la cuantificación 3D del cable."""

    points_3d: np.ndarray          # N×3, metros
    total_length_m: float
    straightness: float            # 1.0 = recto, <1 = curvado
    depth_profile: np.ndarray      # Z en metros por punto
    diameter_profile_m: np.ndarray # diámetro estimado en metros
    curvature_profile: np.ndarray  # curvatura suavizada en rad/m
    start_3d: np.ndarray
    end_3d: np.ndarray
    min_depth_m: float = 0.0
    max_depth_m: float = 0.0

    def summary(self) -> Dict[str, Any]:
        kappa = self.curvature_profile
        mean_kappa = float(np.mean(kappa)) if len(kappa) else 0.0
        p95_kappa  = float(np.percentile(kappa, 95)) if len(kappa) else 0.0
        return {
            'total_length_m':      round(self.total_length_m, 4),
            'straightness':        round(self.straightness, 3),
            'min_depth_m':         round(self.min_depth_m, 3),
            'max_depth_m':         round(self.max_depth_m, 3),
            'mean_depth_m':        round(float(np.mean(self.depth_profile)), 3),
            'mean_diameter_mm':    round(float(np.mean(self.diameter_profile_m)) * 1000, 2),
            'mean_curvature_rad_m': round(mean_kappa, 3),
            'p95_curvature_rad_m':  round(p95_kappa, 3),
            'start_3d_m':          self.start_3d.tolist(),
            'end_3d_m':            self.end_3d.tolist(),
            'num_points':          len(self.points_3d),
        }


def compute_wire_metrics(
    matches: List[Tuple[float, float, float, float]],
    disparities: List[float],
    calibration_data: Dict[str, Any],
    dt_profile_left: Optional[List[float]] = None,
    _decision_points_2d: Optional[List[Tuple[int, int]]] = None,  # reservado para uso futuro
) -> Optional[WireMetrics]:
    """
    Calcula métricas 3D del cable a partir del matching estéreo paramétrico.

    Args:
        matches:          Lista de (x_left, y_left, x_right, y_right).
        disparities:      Disparidades correspondientes (pixels).
        calibration_data: Dict con 'disparity_to_depth_matrix' (Q 4×4).
        dt_profile_left:  Valores de DT a lo largo del path izquierdo (radio en px).
        decision_points_2d: No usado actualmente (reservado para uso futuro).
    """
    if len(matches) < 2 or len(disparities) < 2:
        return None

    # --- Parámetros de calibración ---
    Q = calibration_data.get('disparity_to_depth_matrix')
    if Q is not None:
        Q = np.array(Q)
        focal    = float(Q[2, 3])
        baseline = float(abs(1.0 / Q[3, 2])) if Q[3, 2] != 0 else 0.1
        cx       = float(-Q[0, 3])
        cy       = float(-Q[1, 3])
    else:
        focal    = float(calibration_data.get('focal_length', 2600.0))
        baseline = float(calibration_data.get('baseline', 0.1))
        cx       = float(calibration_data.get('cx', 960.0))
        cy       = float(calibration_data.get('cy', 720.0))

    # --- Triangulación ---
    points_3d = []
    for (x_l, y_l, _x_r, _y_r), disp in zip(matches, disparities):
        if disp <= 0:
            continue
        Z = (baseline * focal) / disp
        if not (0.05 < Z < 50.0):
            continue
        X = (x_l - cx) * Z / focal
        Y = (y_l - cy) * Z / focal
        points_3d.append([X, Y, Z])

    if len(points_3d) < 2:
        return None

    pts = np.array(points_3d)  # N×3

    # --- Longitud del arco 3D ---
    seg_lengths  = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    total_length = float(np.sum(seg_lengths))

    # --- Índice de rectitud ---
    chord       = float(np.linalg.norm(pts[-1] - pts[0]))
    straightness = float(np.clip(chord / total_length, 0.0, 1.0)) if total_length > 0 else 1.0

    # --- Perfil de profundidad ---
    depth_profile = pts[:, 2]

    # --- Perfil de diámetro (DT + Z) ---
    if dt_profile_left is not None and len(dt_profile_left) >= 2:
        t_orig  = np.linspace(0.0, 1.0, len(dt_profile_left))
        t_pts   = np.linspace(0.0, 1.0, len(pts))
        dt_vals = np.interp(t_pts, t_orig, dt_profile_left)
        diameter_profile_m = (2.0 * dt_vals * depth_profile) / focal
    else:
        diameter_profile_m = np.zeros(len(pts))

    # --- Curvatura suavizada (Menger sobre path decimado) ---
    # Decimar a máx 500 pts para reducir ruido de profundidad antes de calcular
    curvature = _compute_curvature_smooth(pts, max_pts=500)

    return WireMetrics(
        points_3d          = pts,
        total_length_m     = total_length,
        straightness       = straightness,
        depth_profile      = depth_profile,
        diameter_profile_m = diameter_profile_m,
        curvature_profile  = curvature,
        start_3d           = pts[0],
        end_3d             = pts[-1],
        min_depth_m        = float(np.min(depth_profile)),
        max_depth_m        = float(np.max(depth_profile)),
    )


def _compute_curvature_smooth(pts: np.ndarray, max_pts: int = 500) -> np.ndarray:
    """
    Curvatura de Menger sobre una versión decimada del path.
    Decimar reduce el impacto del ruido de profundidad en puntos consecutivos.
    """
    n = len(pts)
    if n < 3:
        return np.zeros(n)

    # Decimar uniformemente a max_pts puntos
    if n > max_pts:
        idx  = np.round(np.linspace(0, n - 1, max_pts)).astype(int)
        work = pts[idx]
    else:
        work = pts
        idx  = np.arange(n)

    nw = len(work)
    kappa_work = np.zeros(nw)
    for i in range(1, nw - 1):
        a, b, c = work[i-1], work[i], work[i+1]
        cross = np.cross(b - a, c - b)
        denom = np.linalg.norm(b-a) * np.linalg.norm(c-b) * np.linalg.norm(c-a)
        kappa_work[i] = 2.0 * np.linalg.norm(cross) / denom if denom > 1e-12 else 0.0
    kappa_work[0]  = kappa_work[1]
    kappa_work[-1] = kappa_work[-2]

    # Interpolar de vuelta a N puntos
    t_work = np.linspace(0.0, 1.0, nw)
    t_full = np.linspace(0.0, 1.0, n)
    return np.interp(t_full, t_work, kappa_work)
