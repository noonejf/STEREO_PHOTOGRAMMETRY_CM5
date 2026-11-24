#!/usr/bin/env python3
"""Copia las figuras de los experimentos a Images/ del informe de la sesion.

    python tools/fig_al_informe.py

Las figuras viven donde se generan, en ``SIMULATION/experimentos/``, y el
LaTeX necesita las suyas dentro de su propia carpeta. Esto las copia con el
nombre que usa el documento, y **los diagramas de 1920x1080 los pasa a JPEG**:
en PNG pesan 2 MB cada uno y son renders de Cycles, no graficos de lineas,
asi que el PNG no compra nada y el PDF se iba a 20 MB. Las figuras de
matplotlib se copian tal cual, porque ahi el PNG si gana.

**Las figuras de matplotlib se toman en su version ``_en``**, que es la que
sacan esos scripts con ``--idioma en``: el documento esta escrito en ingles y
una figura con los ejes en espanol dentro de un entregable en ingles es un
defecto que se ve a la primera. Los diagramas de Blender no llevan texto, asi
que sirven los dos idiomas.

Si una figura falta, se dice y se sigue: lo que falta es un render que no se
ha hecho, o una figura que no se ha generado en ingles, y el resto del
documento no depende de ella.
"""
from __future__ import annotations

import os
import shutil

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, "SIMULATION", "experimentos")
DEST = os.path.join(ROOT, "Documentation", "LINKU_Experiment_TV2", "Images")

#: origen -> nombre en el documento. Un ``.jpg`` de destino recomprime.
FIGURAS = {
    "escenario/tv2_tres_cuartos_en.png": "sim_montage_threequarter.jpg",
    "escenario/tv2_elevacion_en.png": "sim_montage_elevation.jpg",
    "escenario/tv2_planta_en.png": "sim_montage_plan.jpg",
    "escenario/orbita_esfera.png": "sun_sphere_scene.jpg",
    "estudio_luminarias_reales/fig_cuarto_lux_en.png":
        "sim_lux_profile.png",
    "estudio_luminarias_reales/fig_renders_cuarto_en.png":
        "sim_room_renders.png",
    "estudio_luminarias_reales/fig_renders_haz_en.png":
        "sim_beam_renders.png",
    "sol_esfera/fig_esfera_mapa_en.png": "sun_sphere_map.png",
    "sol_esfera/fig_esfera_perfiles_en.png": "sun_sphere_profiles.png",
    "sol_esfera/fig_renders_polos_en.png": "sun_pole_renders.png",
}
CALIDAD = 92


def main():
    os.makedirs(DEST, exist_ok=True)
    total = 0
    for origen, nombre in FIGURAS.items():
        src = os.path.join(EXP, origen.replace("/", os.sep))
        dst = os.path.join(DEST, nombre)
        if not os.path.exists(src):
            print(f"FALTA  {origen}")
            continue
        if nombre.endswith(".jpg"):
            img = cv2.imread(src, cv2.IMREAD_COLOR)
            cv2.imwrite(dst, img, [int(cv2.IMWRITE_JPEG_QUALITY), CALIDAD])
        else:
            shutil.copy(src, dst)
        total += os.path.getsize(dst)
        print(f"{os.path.getsize(dst) // 1024:5d} kB  {nombre}")
    print(f"{total / 1e6:.1f} MB en {DEST}")


if __name__ == "__main__":
    main()
