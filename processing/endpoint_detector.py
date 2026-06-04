#!/usr/bin/env python3
"""
Detector automático de endpoints (extremos) en máscaras de cables.
Identifica los puntos de inicio y final para el wire tracker.
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional
from scipy import ndimage


class EndpointDetector:
    """Detecta endpoints automáticamente en máscaras de cables."""

    def __init__(self, mask: np.ndarray, side: str = ""):
        """
        Args:
            mask: Máscara binaria del cable (255=cable, 0=fondo)
            side: "left" o "right" (para carpeta de debug separada)
        """
        self.mask = mask.astype(np.uint8)
        self.mask_binary = (self.mask > 127).astype(np.uint8)
        self._debug_side = side

    def detect_endpoints(self, method: str = "skeleton", save_debug: bool = False) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta los dos endpoints principales del cable.

        Normalización canónica: start siempre tiene Y menor (más arriba en la imagen).
        Si Y es igual, start tiene X menor (más a la izquierda).

        Args:
            method: Método de detección ("skeleton", "contour", or "distance_transform")

        Returns:
            Tupla con (start_point, end_point) en formato (x, y),
            donde start es el punto superior (menor Y).
        """
        if method == "skeleton":
            start, end = self._detect_endpoints_skeleton(save_debug=save_debug)
        elif method == "contour":
            start, end = self._detect_endpoints_contour()
        elif method == "distance_transform":
            start, end = self._detect_endpoints_distance_transform()
        else:
            raise ValueError(f"Método desconocido: {method}")

        # --- NORMALIZACIÓN CANÓNICA: start = punto superior (menor Y) ---
        # Esto garantiza dirección consistente top-to-bottom entre imágenes
        start_y = start[1]
        end_y = end[1]
        swapped = False
        if start_y > end_y or (start_y == end_y and start[0] > end[0]):
            print(f"DEBUG: Normalizando dirección endpoints (swap): "
                  f"({start}) <-> ({end})")
            start, end = end, start
            swapped = True

        if save_debug:
            self._save_debug_final(start, end, swapped)

        return start, end

    def _detect_endpoints_skeleton(self, save_debug: bool = False) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta endpoints usando skeleton y DISTANCIA GEODÉSICA.
        Los endpoints reales son los que tienen el camino MÁS LARGO entre ellos
        a lo largo del skeleton (no distancia euclidiana).
        """
        # Crear skeleton (sin dilatar — la dilatación creaba falsos endpoints en bordes DT=1)
        skeleton = self._create_skeleton()
        skeleton_raw    = (skeleton > 0).astype(np.uint8)
        skeleton_binary = skeleton_raw   # alias para el resto del código

        if save_debug:
            self._save_debug_skeleton_pair(skeleton_raw, skeleton_binary)

        # Contar vecinos de cada píxel del skeleton (raw = binary, son lo mismo)
        kernel = np.ones((3, 3), np.float32)
        kernel[1, 1] = 0
        neighbors     = cv2.filter2D(skeleton_binary.astype(np.float32), -1, kernel) * skeleton_binary
        neighbors_raw = neighbors   # mismo array, para compatibilidad con debug

        # Endpoints: exactamente 1 vecino en el skeleton
        endpoints_mask = ((neighbors >= 0.9) & (neighbors <= 1.1)).astype(np.uint8)
        endpoint_coords = np.column_stack(np.where(endpoints_mask > 0))

        if len(endpoint_coords) < 2:
            print("⚠️ No se encontraron endpoints con skeleton, usando método de contornos...")
            return self._detect_endpoints_contour()

        # Filtrar endpoints muy cerca del borde de la imagen: son ramas espurias
        # creadas por artefactos en los bordes de la máscara, no extremos reales.
        h_sk, w_sk = skeleton_binary.shape
        border_margin = 50
        in_bounds = (
            (endpoint_coords[:, 0] >= border_margin) &
            (endpoint_coords[:, 0] < h_sk - border_margin) &
            (endpoint_coords[:, 1] >= border_margin) &
            (endpoint_coords[:, 1] < w_sk - border_margin)
        )
        if in_bounds.sum() >= 2:
            n_removed = int((~in_bounds).sum())
            if n_removed > 0:
                print(f"DEBUG: Filtrados {n_removed} endpoint(s) en borde (<{border_margin}px) "
                      f"→ quedan {int(in_bounds.sum())} candidatos")
            endpoint_coords = endpoint_coords[in_bounds]

        # Filtrar endpoints donde la cuerda continúa en ambos lados (crossings >= 4):
        # son falsos endpoints creados por la dilatación+re-thinning en zonas de DT bajo.
        dt_map = cv2.distanceTransform(self.mask_binary, cv2.DIST_L2, 5)
        # Filtro conservador: eliminar SOLO endpoints en el borde fino del cable
        # (DT<=2) donde la cuerda claramente continúa en ambos lados (crossings>=4).
        # Con el skeleton raw (sin dilatación) este filtro casi nunca aplica,
        # pero atrapa los raros casos de endpoints espurios en bordes de máscara.
        valid_eps = []
        for ep in endpoint_coords:
            cy, cx = int(ep[0]), int(ep[1])
            dt_val = float(dt_map[cy, cx])
            # Endpoints con DT>2 (dentro del cuerpo del cable) → siempre válidos
            if dt_val > 2.0:
                valid_eps.append(ep)
                continue
            # Endpoints en el borde fino (DT<=2): verificar si la cuerda continúa
            radius = max(15, int(dt_val) + 8)
            crossings = self._count_circle_crossings(cx, cy, radius)
            if crossings < 4:
                valid_eps.append(ep)
        if len(valid_eps) >= 2:
            n_removed = len(endpoint_coords) - len(valid_eps)
            if n_removed > 0:
                print(f"DEBUG: Filtrados {n_removed} endpoint(s) thin-edge "
                      f"(DT≤2 + crossings≥4) → quedan {len(valid_eps)}")
            endpoint_coords = np.array(valid_eps)

        print(f"DEBUG: {len(endpoint_coords)} endpoints tras todos los filtros")

        if save_debug:
            self._save_debug_candidates_detailed(
                skeleton_raw, skeleton_binary, neighbors_raw, neighbors, endpoint_coords)

        # Buscar el par con MAYOR DISTANCIA GEODÉSICA a lo largo del skeleton.
        # Para cuerdas enredadas el skeleton puede fragmentarse en los cruces,
        # haciendo que los extremos reales queden en componentes desconectadas
        # (geodésica = 0). En ese caso se reintenta con skeleton ligeramente
        # dilatado para puentear las brechas en los cruces.
        skeleton_for_geodesic = skeleton_binary
        best_pair, max_geodesic_dist, all_pair_scores = self._find_best_geodesic_pair(
            skeleton_for_geodesic, endpoint_coords
        )

        if max_geodesic_dist == 0:
            # Skeleton fragmentado: puentear brechas con dilatación mínima
            print("DEBUG: Skeleton fragmentado (geodésica=0). Reintentando con skeleton dilatado...")
            bridge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            skeleton_bridged = cv2.dilate(skeleton_binary, bridge_kernel, iterations=1)
            skeleton_bridged = (skeleton_bridged > 0).astype(np.uint8)
            best_pair2, max_geodesic_dist2, all_pair_scores2 = self._find_best_geodesic_pair(
                skeleton_bridged, endpoint_coords
            )
            if max_geodesic_dist2 > 0:
                best_pair = best_pair2
                max_geodesic_dist = max_geodesic_dist2
                all_pair_scores = all_pair_scores2
                print(f"DEBUG: Skeleton dilatado encontró geodésica={max_geodesic_dist:.0f}px")
            else:
                # Último recurso: usar distancia euclidiana
                print("DEBUG: Aún fragmentado, usando distancia euclidiana como fallback...")
                best_pair, max_geodesic_dist, all_pair_scores = self._find_best_geodesic_pair(
                    skeleton_binary, endpoint_coords, use_euclidean_fallback=True
                )

        if best_pair is None:
            print("⚠️ No se encontró par válido, usando contornos...")
            return self._detect_endpoints_contour()

        if save_debug:
            self._save_debug_scores(skeleton_binary, endpoint_coords, all_pair_scores, best_pair)

        # Convertir de (y, x) a (x, y)
        start = (int(best_pair[0][1]), int(best_pair[0][0]))
        end = (int(best_pair[1][1]), int(best_pair[1][0]))

        print(f"DEBUG: Endpoints finales - geodesic_dist={max_geodesic_dist:.0f}px")
        print(f"DEBUG: Start: {start}, End: {end}")

        return start, end

    def _prune_short_branches(self, skeleton: np.ndarray, min_length: int = 40) -> np.ndarray:
        """
        Elimina ramas del skeleton más cortas que min_length píxeles.
        Itera quitando pixels-hoja (1 vecino) hasta min_length veces;
        se detiene automáticamente al llegar a un punto de bifurcación (3+ vecinos).
        Esto elimina artefactos de ruido sin afectar los extremos reales del cable.
        """
        pruned = skeleton.copy().astype(np.uint8)
        kernel = np.ones((3, 3), np.float32)
        kernel[1, 1] = 0

        for _ in range(min_length):
            neighbors = cv2.filter2D(pruned.astype(np.float32), -1, kernel) * pruned
            # Puntos de bifurcación (3+ vecinos): NO eliminar
            branch_pts = neighbors >= 2.9
            # Endpoints actuales (exactamente 1 vecino)
            leaf_pts = (neighbors >= 0.9) & (neighbors <= 1.1) & (pruned > 0)
            to_remove = leaf_pts & ~branch_pts
            if not to_remove.any():
                break
            pruned[to_remove] = 0

        return pruned

    def _find_best_geodesic_pair(self, skeleton: np.ndarray,
                                  endpoint_coords: np.ndarray,
                                  use_euclidean_fallback: bool = False):
        """
        Evalúa todos los pares de endpoints y devuelve el que tiene mayor
        distancia geodésica (o euclidiana si use_euclidean_fallback=True).

        Returns:
            (best_pair, max_dist, all_scores)
        """
        best_pair = None
        max_dist = 0
        all_scores = []

        for i in range(len(endpoint_coords)):
            for j in range(i + 1, len(endpoint_coords)):
                ep1 = endpoint_coords[i]
                ep2 = endpoint_coords[j]
                euclid_dist = float(np.linalg.norm(ep1 - ep2))

                if use_euclidean_fallback:
                    dist = euclid_dist
                else:
                    dist = self._compute_geodesic_distance(skeleton, ep1, ep2)

                all_scores.append((i, j, dist, euclid_dist,
                                   (int(ep1[1]), int(ep1[0])),
                                   (int(ep2[1]), int(ep2[0]))))

                if dist > max_dist:
                    max_dist = dist
                    best_pair = (ep1, ep2)
                    print(f"DEBUG: Nuevo mejor par - dist={dist:.0f}, "
                          f"({ep1[1]},{ep1[0]}) <-> ({ep2[1]},{ep2[0]})")

        return best_pair, max_dist, all_scores

    # ------------------------------------------------------------------ #
    #  DEBUG HELPERS                                                       #
    # ------------------------------------------------------------------ #

    def _save_debug_skeleton_pair(self, skeleton_raw: np.ndarray, skeleton_bridged: np.ndarray):
        """Guarda el skeleton ANTES y DESPUÉS de la dilatación para ver si se cierran las brechas."""
        d = self._get_debug_dir()
        h, w = self.mask.shape[:2]

        cv2.imwrite(str(d / "00_input_mask.png"), self.mask)
        mask_px = int(np.sum(self.mask_binary > 0))
        print(f"DEBUG máscara recibida: {w}x{h} | {mask_px} px activos "
              f"({100*mask_px/(h*w):.3f}%)")

        def _render_skel(skel, label):
            vis = np.zeros((h, w, 3), dtype=np.uint8)
            vis[self.mask_binary > 0] = [120, 120, 120]
            num_labels, labels = cv2.connectedComponents(skel)
            colors = [(255,80,80),(80,255,80),(80,80,255),
                      (255,255,80),(255,80,255),(80,255,255)]
            for lbl in range(1, num_labels):
                vis[labels == lbl] = colors[(lbl-1) % len(colors)]
            n_comp = num_labels - 1
            cv2.putText(vis, f"{label} | {np.sum(skel>0)}px | {n_comp} componentes",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0,220,255), 2)
            return vis, n_comp

        vis_raw,  n_raw  = _render_skel(skeleton_raw,      "RAW (antes dil)")
        vis_brid, n_brid = _render_skel(skeleton_bridged,  "BRIDGED (tras dil)")

        cv2.imwrite(str(d / "01a_skeleton_raw.png"),      vis_raw)
        cv2.imwrite(str(d / "01b_skeleton_bridged.png"),  vis_brid)
        # También mantenemos el nombre original para compatibilidad con el resto del código
        cv2.imwrite(str(d / "01_skeleton.png"), vis_brid)
        print(f"DEBUG skeletons: RAW={n_raw} comp, BRIDGED={n_brid} comp → "
              f"{'REDUJO' if n_brid < n_raw else 'SIN CAMBIO'}")

    def _save_debug_candidates_detailed(self,
                                         skeleton_raw: np.ndarray,
                                         skeleton_bridged: np.ndarray,
                                         neighbors_raw: np.ndarray,
                                         neighbors_bridged: np.ndarray,
                                         endpoint_coords: np.ndarray):
        """
        Debug detallado de cada candidato:
        - Coordenadas y valor DT
        - Nº de vecinos en skeleton RAW y BRIDGED
        - Circle crossings (2 = extremo real, 4+ = falso/brecha)
        - Imagen zoom 8× alrededor de cada candidato
        """
        d = self._get_debug_dir()
        h, w = self.mask.shape[:2]

        # Calcular DT sobre la máscara
        dt = cv2.distanceTransform(self.mask_binary, cv2.DIST_L2, 5)

        # Vista general con todos los candidatos
        vis = np.zeros((h, w, 3), dtype=np.uint8)
        vis[self.mask_binary > 0] = [60, 60, 60]
        vis[skeleton_bridged > 0] = [200, 200, 200]

        zoom_dir = d / "candidate_zooms"
        zoom_dir.mkdir(exist_ok=True)

        print(f"\n{'='*70}")
        print(f"DIAGNÓSTICO DE CANDIDATOS  ({len(endpoint_coords)} total)")
        print(f"{'ID':>3}  {'(x,y)':>12}  {'DT':>5}  "
              f"{'vecRAW':>7}  {'vecBRID':>8}  {'crossings':>10}  TIPO")
        print(f"{'-'*70}")

        for idx, (cy, cx) in enumerate(endpoint_coords):
            # DT en ese pixel
            dt_val = float(dt[cy, cx])

            # Vecinos en skeleton raw y bridged
            vec_raw  = float(neighbors_raw[cy, cx])
            vec_brid = float(neighbors_bridged[cy, cx])

            # Circle crossings (radio = DT + 8px margen)
            radius = max(15, int(dt_val) + 8)
            crossings = self._count_circle_crossings(cx, cy, radius)

            # Diagnóstico automático
            if crossings >= 4:
                tipo = "FALSO (rope continúa)"
            elif crossings == 2:
                tipo = "REAL (extremo rope)"
            else:
                tipo = f"DUDOSO (cross={crossings})"

            print(f"{idx:>3}  ({cx:>5},{cy:>4})  {dt_val:>5.1f}  "
                  f"{vec_raw:>7.0f}  {vec_brid:>8.0f}  {crossings:>10}  {tipo}")

            # Dibujar en la vista general
            color = (0,255,0) if crossings == 2 else (0,0,255) if crossings >= 4 else (0,200,200)
            cv2.circle(vis, (cx, cy), 8, color, -1)
            cv2.putText(vis, f"{idx}:{crossings}x", (cx+10, cy+5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

            # Zoom 8× alrededor del candidato (parche de 60px)
            pad = 60
            y0, y1 = max(0, cy-pad), min(h, cy+pad)
            x0, x1 = max(0, cx-pad), min(w, cx+pad)

            patch_mask  = self.mask_binary[y0:y1, x0:x1]
            patch_raw   = skeleton_raw[y0:y1, x0:x1]
            patch_brid  = skeleton_bridged[y0:y1, x0:x1]

            zoom = np.zeros((y1-y0, x1-x0, 3), dtype=np.uint8)
            zoom[patch_mask > 0] = [80, 80, 80]
            zoom[patch_raw  > 0] = [255, 100, 0]    # naranja = raw skeleton
            zoom[patch_brid > 0] = [255, 255, 255]  # blanco  = bridged skeleton

            # Punto candidato en el zoom
            lcx, lcy = cx - x0, cy - y0
            cv2.circle(zoom, (lcx, lcy), 4, (0, 255, 0), -1)

            # Ampliar 4×
            zoom_big = cv2.resize(zoom, (zoom.shape[1]*4, zoom.shape[0]*4),
                                  interpolation=cv2.INTER_NEAREST)
            # Añadir etiqueta
            cv2.putText(zoom_big, f"#{idx} ({cx},{cy}) DT={dt_val:.1f} "
                        f"vRaw={vec_raw:.0f} vBrid={vec_brid:.0f} cross={crossings}",
                        (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,255), 1)
            cv2.imwrite(str(zoom_dir / f"cand_{idx:02d}.png"), zoom_big)

        print(f"{'='*70}\n")

        cv2.putText(vis, f"{len(endpoint_coords)} candidatos | verde=real rojo=falso cian=dudoso",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200,200,200), 2)
        cv2.imwrite(str(d / "02_candidates.png"), vis)
        print(f"DEBUG guardado: {d}/02_candidates.png + zooms en candidate_zooms/")

    def _get_debug_dir(self):
        from pathlib import Path
        suffix = f"_{self._debug_side}" if self._debug_side else ""
        d = Path(f"data/results/debug/endpoints{suffix}")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _save_debug_skeleton(self, skeleton_binary: np.ndarray):
        """Guarda el skeleton sobre la máscara original."""
        d = self._get_debug_dir()
        h, w = self.mask.shape[:2]

        # Guardar la máscara de entrada tal cual para diagnóstico
        cv2.imwrite(str(d / "00_input_mask.png"), self.mask)
        mask_px = int(np.sum(self.mask_binary > 0))
        total_px = h * w
        print(f"DEBUG máscara recibida: {w}x{h} | {mask_px} px activos ({100*mask_px/total_px:.3f}% del total)")

        vis = np.zeros((h, w, 3), dtype=np.uint8)
        # Máscara en gris visible (no oscuro)
        vis[self.mask_binary > 0] = [120, 120, 120]
        # Skeleton en blanco brillante
        vis[skeleton_binary > 0] = [255, 255, 255]

        # Contar componentes del skeleton para diagnóstico
        num_labels, labels = cv2.connectedComponents(skeleton_binary)
        num_components = num_labels - 1
        cv2.putText(vis, f"Skeleton: {np.sum(skeleton_binary > 0)} px | {num_components} componentes",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)

        # Colorear cada componente diferente para ver fragmentos
        colors = [(255, 80, 80), (80, 255, 80), (80, 80, 255),
                  (255, 255, 80), (255, 80, 255), (80, 255, 255)]
        for lbl in range(1, num_labels):
            color = colors[(lbl - 1) % len(colors)]
            vis[labels == lbl] = color

        cv2.imwrite(str(d / "01_skeleton.png"), vis)
        print(f"DEBUG guardado: {d}/01_skeleton.png  ({num_components} componentes en skeleton)")

    def _save_debug_candidates(self, skeleton_binary: np.ndarray,
                               endpoint_coords: np.ndarray):
        """Guarda todos los candidatos a endpoint numerados."""
        d = self._get_debug_dir()
        h, w = self.mask.shape[:2]

        vis = np.zeros((h, w, 3), dtype=np.uint8)
        vis[self.mask_binary > 0] = [60, 60, 60]
        vis[skeleton_binary > 0] = [200, 200, 200]

        for idx, (cy, cx) in enumerate(endpoint_coords):
            cv2.circle(vis, (cx, cy), 8, (0, 255, 255), -1)
            cv2.putText(vis, str(idx), (cx + 10, cy + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        cv2.putText(vis, f"{len(endpoint_coords)} candidatos (amarillo)",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.imwrite(str(d / "02_candidates.png"), vis)
        print(f"DEBUG guardado: {d}/02_candidates.png  ({len(endpoint_coords)} candidatos)")

    def _save_debug_scores(self, skeleton_binary: np.ndarray,
                           endpoint_coords: np.ndarray,
                           all_pair_scores: list,
                           best_pair: tuple):
        """Guarda el par ganador y una tabla de scores."""
        d = self._get_debug_dir()
        h, w = self.mask.shape[:2]

        vis = np.zeros((h, w, 3), dtype=np.uint8)
        vis[self.mask_binary > 0] = [60, 60, 60]
        vis[skeleton_binary > 0] = [200, 200, 200]

        # Ordenar por distancia geodésica descendente
        sorted_scores = sorted(all_pair_scores, key=lambda x: x[2], reverse=True)

        # Top-5 pares en azul tenue
        for rank, (i, j, geo, euc, p1, p2) in enumerate(sorted_scores[:5]):
            alpha = max(40, 180 - rank * 30)
            cv2.line(vis, p1, p2, (alpha, alpha // 2, 0), 1)

        # Par ganador en verde brillante
        best_p1 = (int(best_pair[0][1]), int(best_pair[0][0]))
        best_p2 = (int(best_pair[1][1]), int(best_pair[1][0]))
        cv2.line(vis, best_p1, best_p2, (0, 255, 0), 2)
        cv2.circle(vis, best_p1, 10, (0, 255, 0), -1)
        cv2.circle(vis, best_p2, 10, (0, 0, 255), -1)
        cv2.putText(vis, "A", (best_p1[0] + 12, best_p1[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(vis, "B", (best_p2[0] + 12, best_p2[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Tabla de top-5 en la imagen
        best_geo = sorted_scores[0][2] if sorted_scores else 0
        y_txt = 30
        cv2.putText(vis, "Top 5 pares (geodesic desc):",
                    (10, y_txt), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        for rank, (i, j, geo, euc, p1, p2) in enumerate(sorted_scores[:5]):
            y_txt += 22
            marker = "<<< GANADOR" if rank == 0 else ""
            cv2.putText(vis,
                        f"#{rank+1} [{i}-{j}] geo={geo:.0f} euc={euc:.0f} {marker}",
                        (10, y_txt), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 0) if rank == 0 else (160, 160, 160), 1)

        cv2.imwrite(str(d / "03_winner_pair.png"), vis)
        print(f"DEBUG guardado: {d}/03_winner_pair.png  (ganador: geo={best_geo:.0f}px)")

        # También guardar tabla de texto
        with open(str(d / "scores.txt"), "w") as f:
            f.write(f"Total candidatos: {len(endpoint_coords)}\n")
            f.write(f"Total pares evaluados: {len(all_pair_scores)}\n\n")
            f.write(f"{'Rank':<5} {'i-j':<8} {'Geodesic':>10} {'Euclidean':>10}  p1(x,y)        p2(x,y)\n")
            f.write("-" * 65 + "\n")
            for rank, (i, j, geo, euc, p1, p2) in enumerate(sorted_scores):
                f.write(f"{rank+1:<5} {i}-{j:<6} {geo:>10.1f} {euc:>10.1f}  {str(p1):<15} {str(p2)}\n")
        print(f"DEBUG guardado: {d}/scores.txt")

    def _save_debug_final(self, start: Tuple[int, int], end: Tuple[int, int], swapped: bool):
        """Guarda el resultado final con START/END sobre la máscara."""
        d = self._get_debug_dir()
        h, w = self.mask.shape[:2]

        vis = np.zeros((h, w, 3), dtype=np.uint8)
        vis[self.mask_binary > 0] = [100, 100, 100]

        cv2.circle(vis, start, 14, (0, 255, 0), -1)
        cv2.circle(vis, end, 14, (0, 0, 255), -1)
        cv2.line(vis, start, end, (180, 180, 0), 1)
        cv2.putText(vis, "START", (start[0] + 16, start[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(vis, "END", (end[0] + 16, end[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        swap_txt = "  (swap canonico aplicado)" if swapped else ""
        cv2.putText(vis, f"START menor Y={start[1]}{swap_txt}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        cv2.imwrite(str(d / "04_final_result.png"), vis)
        print(f"DEBUG guardado: {d}/04_final_result.png  START={start} END={end}")

    def _compute_geodesic_distance(self, skeleton: np.ndarray,
                                    start: np.ndarray, end: np.ndarray) -> float:
        """
        Calcula la distancia geodésica (camino más corto a lo largo del skeleton)
        entre dos puntos usando BFS.

        Returns:
            Distancia en píxeles, o 0 si no hay camino conectado.
        """
        from collections import deque

        h, w = skeleton.shape
        start_y, start_x = int(start[0]), int(start[1])
        end_y, end_x = int(end[0]), int(end[1])

        # BFS para encontrar camino más corto
        visited = np.zeros((h, w), dtype=bool)
        queue = deque([(start_y, start_x, 0)])  # (y, x, distance)
        visited[start_y, start_x] = True

        # 8-conectividad
        neighbors_dy = [-1, -1, -1, 0, 0, 1, 1, 1]
        neighbors_dx = [-1, 0, 1, -1, 1, -1, 0, 1]

        while queue:
            y, x, dist = queue.popleft()

            # Llegamos al destino?
            if y == end_y and x == end_x:
                return dist

            # Explorar vecinos
            for dy, dx in zip(neighbors_dy, neighbors_dx):
                ny, nx = y + dy, x + dx

                if 0 <= ny < h and 0 <= nx < w:
                    if skeleton[ny, nx] > 0 and not visited[ny, nx]:
                        visited[ny, nx] = True
                        # Distancia diagonal = sqrt(2), recta = 1
                        step_dist = 1.414 if (dy != 0 and dx != 0) else 1.0
                        queue.append((ny, nx, dist + step_dist))

        # No hay camino conectado
        return 0

    def _count_circle_crossings(self, cx: int, cy: int, radius: int = 20) -> int:
        """
        Cuenta cuántas veces una circunferencia cruza la máscara.
        - 2 cruces = endpoint real (cable entra y sale por el grosor)
        - 4+ cruces = punto en medio del cable (cable pasa por ambos lados)
        """
        # Generar puntos de la circunferencia
        num_points = 360
        crossings = 0
        prev_inside = None

        for i in range(num_points + 1):
            angle = 2 * np.pi * i / num_points
            x = int(cx + radius * np.cos(angle))
            y = int(cy + radius * np.sin(angle))

            # Verificar si el punto está dentro de la imagen
            if 0 <= y < self.mask_binary.shape[0] and 0 <= x < self.mask_binary.shape[1]:
                inside = self.mask_binary[y, x] > 0
            else:
                inside = False

            # Contar transiciones (cruces)
            if prev_inside is not None and inside != prev_inside:
                crossings += 1

            prev_inside = inside

        return crossings

    def _detect_endpoints_contour(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta endpoints usando análisis de contornos.
        Los endpoints son los puntos extremos del contorno principal.
        """
        # Encontrar contornos
        contours, _ = cv2.findContours(self.mask_binary * 255,
                                       cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)

        if not contours:
            raise ValueError("No se encontraron contornos en la máscara")

        # Tomar el contorno más grande
        main_contour = max(contours, key=cv2.contourArea)

        # Simplificar contorno para obtener puntos clave
        epsilon = 0.001 * cv2.arcLength(main_contour, True)
        approx = cv2.approxPolyDP(main_contour, epsilon, True)

        # Aplanar puntos
        points = approx.reshape(-1, 2)

        # Encontrar los dos puntos más alejados (endpoints)
        max_dist = 0
        best_pair = (points[0], points[1])

        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                dist = np.linalg.norm(points[i] - points[j])
                if dist > max_dist:
                    max_dist = dist
                    best_pair = (points[i], points[j])

        start = (int(best_pair[0][0]), int(best_pair[0][1]))
        end = (int(best_pair[1][0]), int(best_pair[1][1]))

        return start, end

    def _detect_endpoints_distance_transform(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Detecta endpoints usando distance transform.
        Los endpoints están en regiones de alta distancia al borde.
        """
        # Calcular distance transform
        dist_transform = cv2.distanceTransform(self.mask_binary, cv2.DIST_L2, 5)

        # Crear centerline (píxeles de alta distancia)
        dt_max = np.max(dist_transform)
        threshold = dt_max * 0.5
        centerline = (dist_transform >= threshold).astype(np.uint8)

        # Adelgazar centerline
        skeleton = self._thin_image(centerline * 255)

        # Usar método de skeleton sobre este centerline
        temp_detector = EndpointDetector(skeleton)
        return temp_detector._detect_endpoints_skeleton()

    def _create_skeleton(self) -> np.ndarray:
        """Crea skeleton de la máscara."""
        return self._thin_image(self.mask_binary * 255)

    def _thin_image(self, img: np.ndarray) -> np.ndarray:
        """
        Adelgaza imagen binaria usando morfología.
        Alternativa a cv2.ximgproc.thinning que puede no estar disponible.
        """
        # Método 1: Usar cv2.ximgproc si está disponible
        try:
            skeleton = cv2.ximgproc.thinning(img, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
            return skeleton
        except (AttributeError, cv2.error):
            pass

        # Método 2: Morfología iterativa
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        skeleton = np.zeros_like(img)
        temp = img.copy()

        while True:
            eroded = cv2.erode(temp, kernel)
            temp_opened = cv2.dilate(eroded, kernel)
            temp_skeleton = cv2.subtract(temp, temp_opened)
            skeleton = cv2.bitwise_or(skeleton, temp_skeleton)
            temp = eroded.copy()

            if cv2.countNonZero(temp) == 0:
                break

        return skeleton

    def visualize_endpoints(self, start: Tuple[int, int], end: Tuple[int, int],
                           output_path: Optional[str] = None) -> np.ndarray:
        """
        Visualiza los endpoints detectados sobre la máscara.

        Args:
            start: Punto de inicio (x, y)
            end: Punto final (x, y)
            output_path: Ruta para guardar imagen (opcional)

        Returns:
            Imagen visualizada
        """
        # Crear imagen RGB
        vis = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2BGR)

        # Dibujar endpoints
        cv2.circle(vis, start, 10, (0, 255, 0), -1)  # Verde para start
        cv2.circle(vis, end, 10, (0, 0, 255), -1)    # Rojo para end

        # Añadir etiquetas
        cv2.putText(vis, "START", (start[0] + 15, start[1]),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(vis, "END", (end[0] + 15, end[1]),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        if output_path:
            cv2.imwrite(output_path, vis)
            print(f"Visualización guardada en: {output_path}")

        return vis


def detect_wire_endpoints(mask: np.ndarray,
                         method: str = "skeleton",
                         visualize: bool = False,
                         vis_output_path: Optional[str] = None,
                         side: str = "") -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Función de utilidad para detectar endpoints de un cable.

    Args:
        mask: Máscara binaria del cable
        method: Método de detección ("skeleton", "contour", "distance_transform")
        visualize: Si True, crea visualización básica
        vis_output_path: Ruta para guardar visualización básica
        side: "left" o "right" — activa debug completo en data/results/debug/endpoints_{side}/

    Returns:
        (start_point, end_point) en formato (x, y)
    """
    detector = EndpointDetector(mask, side=side)
    # debug siempre activo — las imágenes van a data/results/debug/endpoints_{side}/
    start, end = detector.detect_endpoints(method=method, save_debug=True)

    if visualize:
        detector.visualize_endpoints(start, end, vis_output_path)

    return start, end


if __name__ == "__main__":
    # Test del detector
    import sys

    if len(sys.argv) < 2:
        print("Uso: python endpoint_detector.py <ruta_mascara>")
        sys.exit(1)

    mask_path = sys.argv[1]
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        print(f"Error: No se pudo cargar {mask_path}")
        sys.exit(1)

    print(f"Detectando endpoints en {mask_path}...")
    start, end = detect_wire_endpoints(mask, method="skeleton", visualize=True,
                                      vis_output_path="endpoint_detection_result.png")

    print(f"✓ Start: {start}")
    print(f"✓ End: {end}")
    print(f"✓ Distancia: {np.linalg.norm(np.array(start) - np.array(end)):.1f} px")
