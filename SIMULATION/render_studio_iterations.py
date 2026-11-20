"""Render the TV2 studio scene in several configurations, for comparison.

    blender --background --python SIMULATION/render_studio_iterations.py -- \
            --variant A --samples 32 --scale 100

Each variant is a different answer to the same question: how much of a 30 m
cord can this room actually show. They are rendered from one Blender process
so the scene is rebuilt rather than reloaded, and each writes a capture
folder the Processing page can open.

**Render at full resolution even for a quick look.** The subject is 0.135 px
wide when the whole cord is framed, so dropping ``--scale`` does not make a
cheaper version of the same image, it removes the thing being looked at.
Spend the budget on resolution and take the noise: ``--samples 32`` with
denoising keeps a cord that is still measurable against a 0.02 albedo room.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

import build_tv2_studio as S  # noqa: E402


# Each variant says where the cord goes, where the lamps go and how the
# cameras look at it. The intensity is never written here: it is solved for
# the configuration, so a variant cannot quietly carry another one's lamps.
VARIANTS = {
    "A": dict(
        note="Axis view, full 29 m cord, 12 lamps 2 m over it. The best "
             "uniformity the room allows over its whole length, about 10%.",
        cord=(0.0, 0.5, 29.5), lamps=(12, 2.0, 0.5, 29.5),
        view="axis", cam_offset=0.2, focal=8.0),
    "B": dict(
        note="Axis view, 24 m cord centred, 10 lamps 3 m over it. Trades "
             "5 m of cord for uniformity inside R4.",
        cord=(0.0, 3.0, 27.0), lamps=(10, 3.0, 0.5, 29.5),
        view="axis", cam_offset=0.2, focal=8.0),
    "C": dict(
        note="Axis view, 26.5 m cord, 21 lamps only 1.5 m over it. The "
             "cheapest in watts and the most uniform, at the cost of "
             "twenty-one fixtures.",
        cord=(0.0, 1.75, 28.25), lamps=(21, 1.5, 0.5, 29.5),
        view="axis", cam_offset=0.2, focal=8.0),
    "D": dict(
        note="Side view across the width, 8 mm. The cord runs 2.5 m off the "
             "far wall and the camera sits against the near one, 12 m away. "
             "About 9.4 m of cord is in frame, and every metre of it gets "
             "430 px instead of piling up at the vanishing point.",
        cord=(5.0, 0.5, 29.5), lamps=(12, 2.0, 0.5, 29.5),
        view="side", cam_offset=-7.0, focal=8.0,
        tilt=(40.0, "+x")),
    "E": dict(
        note="Side view, 2.6 mm. Wide enough to frame the whole 29 m from "
             "12 m away, which puts the cord back at 0.135 px. This is the "
             "variant that tests whether sub-pixel detection survives when "
             "the cord is NOT helped by piling up along the axis.",
        cord=(5.0, 0.5, 29.5), lamps=(12, 2.0, 0.5, 29.5),
        view="side", cam_offset=-7.0, focal=2.6,
        tilt=(40.0, "+x")),
    "F": dict(
        note="Variant A with the beams leaned 40 degrees down-range, away "
             "from the cameras. Forced to A's exact lamp intensity so the "
             "only difference is the tilt.",
        cord=(0.0, 0.5, 29.5), lamps=(12, 2.0, 2.2, 29.5),
        view="axis", cam_offset=0.2, focal=8.0,
        tilt=(40.0, "+y"), candela=7168.1),
    "G": dict(
        note="Variant A with the beams leaned 40 degrees back towards the "
             "cameras. Same intensity as A and F, so A, F and G are a clean "
             "three-way test of beam direction alone.",
        cord=(0.0, 0.5, 29.5), lamps=(12, 2.0, 0.5, 27.8),
        view="axis", cam_offset=0.2, focal=8.0,
        tilt=(40.0, "-y"), candela=7168.1),
    # H and I follow the convention of the orbital simulation the project
    # already has, Simulation camera_64MP.blend: the cord is born between the
    # two cameras and runs away from them to the back of the scene, instead of
    # crossing in front of them. There the cord goes from (0, 0, 3.0), the
    # exact midpoint of the 100 mm baseline, out to 100 m, and the cameras sit
    # 0.5 m behind that anchor looking straight down it.
    "H": dict(
        note="Axis view with the cord anchored at the baseline midpoint, "
             "0.5 m ahead of the cameras, running the full 29 m to the back "
             "wall. The literal reading of the orbital scene, and it shows "
             "why that scene curves its cord: a straight cord on the optical "
             "axis projects into 516 px however long it is.",
        cord=(0.0, 0.8, 29.8), lamps=(12, 2.0, 0.5, 28.0),
        view="axis", cam_offset=0.3, focal=8.0, tilt=(40.0, "-y")),
    "I": dict(
        note="Same cord and same lamps, but anchored 0.25 m to the side of "
             "the rig instead of between the lenses. The near end then falls "
             "outside the frame and the cord enters at the edge and recedes "
             "to the vanishing point, which is what the orbital render looks "
             "like. Nothing else changes: still taut, still parallel to the "
             "optical axis, still 29 m.",
        cord=(0.25, 0.8, 29.8), lamps=(12, 2.0, 0.5, 28.0),
        view="axis", cam_offset=0.3, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0),
    "J": dict(
        note="I with the anchor moved from beside the lenses to below them, "
             "and the cord pulled inside the lamp row. Offsetting the anchor "
             "sideways puts the cord ALONG the epipolar lines, which is the "
             "degenerate case; offsetting it vertically puts the cord across "
             "them. Same rig, same room, same lamps.",
        cord=(0.0, 2.5, 28.5), lamps=(12, 2.0, 0.5, 28.0),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_dz=0.25),
    "K": dict(
        note="J with the lamp row pulled back from the far wall and the cord "
             "ended short of it. In J the last lamps sat 0.3 m off the back "
             "wall and lit the very patch the cord's far end projects onto, "
             "which took the tip's contrast from about 100 down to 2.3. The "
             "cord's far end and the wall behind it are the same pixels, so "
             "the only fix is to stop lighting that wall.",
        cord=(0.0, 2.5, 26.5), lamps=(12, 2.0, 0.5, 25.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_dz=0.25),
    # L, M and N are the first variants whose cord is not a straight line.
    # Everything else about L is K, so the pair is a clean test of the shape
    # alone, and M and N are the same cord seen from the side.
    "L": dict(
        note="K with the cord waved instead of taut: the first three pinned "
             "modes of a string, 0.82 m of excursion over 24 m. A tether in "
             "flight is never straight, and the straight cord was also the "
             "case that hid how much of the measurement depends on the cord "
             "lying exactly where the geometry says.",
        cord=(0.0, 2.5, 26.5), lamps=(12, 2.0, 0.5, 25.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_dz=0.25, wave=S.WAVE),
    "M": dict(
        note="The same waved cord from the side with the 8 mm that is "
             "actually mounted, cameras stacked vertically. Only about 9.5 m "
             "of the cord is in frame from 12 m away, but every metre of it "
             "is in its own place instead of piling up at the vanishing "
             "point, so this is the view that measures arc length.",
        cord=(5.0, 2.5, 26.5), lamps=(12, 2.0, 0.5, 25.5),
        view="side", cam_offset=-7.0, focal=8.0, tilt=(40.0, "+x"),
        wave=S.WAVE,
        blend_name="estudio_vista_de_costado"),
    "N": dict(
        note="M with the 2.6 mm the project does not own, which is the only "
             "way to get the whole 24 m of the waved cord into one frame. "
             "Rendered to show the shape, not as a proposal.",
        cord=(5.0, 2.5, 26.5), lamps=(12, 2.0, 0.5, 25.5),
        view="side", cam_offset=-7.0, focal=2.6, tilt=(40.0, "+x"),
        wave=S.WAVE),
    "O": dict(
        note="L with the anchor moved from below the lenses to beside them, "
             "which is the framing of the orbital reference: the near end "
             "falls outside the frame, the cord enters at the edge and "
             "recedes to the vanishing point. Same cord, same wave, same "
             "lamps, same 0.25 m of offset; only its direction changes.",
        cord=(0.25, 2.5, 26.5), lamps=(12, 2.0, 0.5, 25.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE),
    "P": dict(
        note="The cord born at the EXACT midpoint of the baseline, zero "
             "offset in either direction, which is what the orbital scene "
             "does and what O and L both got wrong by 25 cm. The test is "
             "that the near end falls on OPPOSITE sides of the centre in "
             "the two frames, +516 px and -516 px, because at 0.5 m the "
             "only thing separating the two views is the baseline itself.",
        cord=(0.0, 2.5, 26.5), lamps=(12, 2.0, 0.5, 25.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE),
    "Q": dict(
        note="The cord born AT the lens plane, not half a metre in front of "
             "it, which is where a tether attached to the satellite that "
             "carries the cameras actually starts. Then its first centimetre "
             "is inside the lens and cannot be seen: the near end is not a "
             "visible tip, it is the cord sweeping in from the edge of the "
             "frame, from the RIGHT edge in the left camera and the LEFT "
             "edge in the right one, thick where it passes close and "
             "converging on the principal point 24 m away. That mirror is "
             "the whole signature of a cord born between the two lenses, "
             "and every earlier variant lost it by anchoring 0.5 m ahead.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 0.5, 25.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE),
    "R": dict(
        note="Q with the lamp row aimed at the cord instead of at a stretch "
             "that no longer exists. The nominal row was left at 0.5 to 25.5 "
             "from an older cord, and because a 40 degree tilt lands each "
             "beam 1.68 m downstream of its lamp, the first beam landed at "
             "y = 0.5, which is 1.5 m BEHIND the cameras: one lamp of twelve "
             "lighting nothing. Aiming the row at 2.0 to 26.5 is the only "
             "change.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE),
    # S, T and U are R at the three illuminance levels that matter. Nothing
    # else changes, and that is the point: the exposure is solved from the
    # same target as the lamps, so the three renders look alike and the
    # difference lives in the power bill and in the shutter the real cameras
    # would get to use.
    "S": dict(
        note="R raised to requirement R5 at 1 deg/s, 3600 lx, which is the "
             "level sized for the Hawk-eye and therefore for all three "
             "sensors. R was running at 2320 lx, the IMX477-only floor, "
             "mislabelled R5 in the code.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE,
        e_target=S.E_R5_SLOW_LX, e_basis="R5, 3 sensores, 1 deg/s",
        blend_name="estudio_12lamparas"),
    "T": dict(
        note="The same at R5's fast case, 10000 lx at 2.76 deg/s. This is "
             "the level the requirement asks for if the session is to "
             "exercise the rotation rate as well as the geometry.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE,
        e_target=S.E_R5_FAST_LX, e_basis="R5, 3 sensores, 2.76 deg/s"),
    "U": dict(
        note="The Sun itself, AM0 at 132800 lx. Not buildable: 180 kW of "
             "lamps in a television studio. Rendered once so the page can "
             "say what the other two are a fraction of, and because its "
             "exposure, -8.76 stops, is the one the orbital scene already "
             "uses, which is a check that both scenes are on one scale.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE,
        e_target=S.E_AM0_LX, e_basis="AM0, el Sol, solo como escala"),
    "V": dict(
        note="The orbital twin of S: the same cord, the same wave, the same "
             "two cameras and the same 8 mm lens, with the room and the lamp "
             "row replaced by one Sun at AM0. Every difference between S and "
             "V is the lighting, which is the comparison the whole pair of "
             "scenes exists for.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE, env="orbit",
        e_target=S.E_AM0_LX, e_basis="AM0, 1361 W/m2, el Sol de verdad"),
    "W": dict(
        note="V with a starfield behind it. Rendered as a pair with V so the "
             "light the stars add to the cord can be measured instead of "
             "assumed: everything else about the two scenes is identical.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE, env="orbit", stars=True,
        e_target=S.E_AM0_LX, e_basis="AM0, 1361 W/m2, con estrellas",
        blend_name="orbita_sol_AM0_estrellas"),
    "X": dict(
        note="S with the lamps visible to the camera, which is what the real "
             "session will actually photograph. Nine of the twelve fall "
             "inside the field of view: the vertical half-field of the 8 mm "
             "is 16.4 degrees and anything past 6.8 m from the camera is "
             "inside it. Hiding them was requirement R7, lamp out of frame, "
             "but with the row directly over the cord this geometry does not "
             "satisfy R7 at all, so the render was concealing something the "
             "session will have. Rendered to find out how much it matters.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE, lamps_visible=True,
        e_target=S.E_R5_SLOW_LX, e_basis="R5, 3 sensores, 1 deg/s",
        blend_name="estudio_lamparas_visibles"),

    # --- Los cuatro casos que faltaban de CASOS_COMPARACION.md -------------
    # Se nombran por el numero de caso y no por letra: las letras A a X son
    # el registro de como se llego hasta aqui, y estos cuatro existen para
    # una matriz concreta.
    "C5": dict(
        note="Caso 5: la orbita vista de costado. Par del caso 4, que es la "
             "misma vista en el estudio. De costado el cable no se comprime "
             "contra el punto de fuga, asi que es la vista con la que el "
             "largo de arco significa algo.",
        cord=(5.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="side", cam_offset=-7.0, focal=8.0, tilt=(40.0, "+x"),
        wave=S.WAVE, env="orbit",
        e_target=S.E_AM0_LX, e_basis="AM0, 1361 W/m2",
        blend_name="orbita_vista_de_costado"),
    "C6": dict(
        note="Caso 6: el cable TENSO en el estudio. Es el unico caso en el "
             "que el criterio A3.6 se puede evaluar: la rectitud es la "
             "cuerda entre extremos dividida por el arco, asi que sobre un "
             "cable ondulado a proposito devuelve un numero bajo que no "
             "significa nada.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=None,
        e_target=S.E_R5_SLOW_LX, e_basis="R5, 3 sensores, 1 deg/s",
        blend_name="estudio_cable_tenso"),
    "C7": dict(
        note="Caso 7: el mismo cable tenso en orbita. Par del caso 6.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=None, env="orbit",
        e_target=S.E_AM0_LX, e_basis="AM0, 1361 W/m2",
        blend_name="orbita_cable_tenso"),
    "C8": dict(
        note="Caso 8: la onda al doble, 1.65 m de excursion sobre 24.5 m, "
             "que es el 6.7 por ciento del largo y 18.3 grados de pendiente "
             "maxima contra los 9.4 del caso base. Existe para estresar al "
             "trazador y para ver cuanto crece el tramo que queda paralelo "
             "a las epipolares, que es donde la profundidad no se puede "
             "determinar.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=dict(x=(0.0, 0.70), z=(-1.10, 0.60, 0.40)),
        e_target=S.E_R5_SLOW_LX, e_basis="R5, 3 sensores, 1 deg/s",
        blend_name="estudio_onda_fuerte"),

    # --- Barrido de roll: la luz orbitando alrededor del cable -------------
    # R0 es la variante X, que ya esta renderizada con las lamparas visibles
    # y roll cero.
    "R22": dict(
        note="El rig rodado 22.5 grados alrededor del eje del cable. Ni el "
             "cable ni las lamparas se mueven: rodar el par alrededor de "
             "ellos es lo mismo que orbitar la fila alrededor del cable, y "
             "es mas barato que mover doce lamparas. Lo que cambia es de "
             "donde parece llegar la luz y que parte de la circunferencia "
             "del cilindro queda vuelta hacia las camaras. Las lamparas van "
             "visibles para que el giro se vea; ya esta medido que estando "
             "en cuadro no cambian la mascara.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE, roll_deg=22.5, lamps_visible=True,
        e_target=S.E_R5_SLOW_LX, e_basis="R5, 3 sensores, 1 deg/s",
        blend_name="estudio_roll_22"),
    "R45": dict(
        note="El rig rodado 45.0 grados alrededor del eje del cable. Ni el "
             "cable ni las lamparas se mueven: rodar el par alrededor de "
             "ellos es lo mismo que orbitar la fila alrededor del cable, y "
             "es mas barato que mover doce lamparas. Lo que cambia es de "
             "donde parece llegar la luz y que parte de la circunferencia "
             "del cilindro queda vuelta hacia las camaras. Las lamparas van "
             "visibles para que el giro se vea; ya esta medido que estando "
             "en cuadro no cambian la mascara.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE, roll_deg=45.0, lamps_visible=True,
        e_target=S.E_R5_SLOW_LX, e_basis="R5, 3 sensores, 1 deg/s",
        blend_name="estudio_roll_45"),
    "R90": dict(
        note="El rig rodado 90.0 grados alrededor del eje del cable. Ni el "
             "cable ni las lamparas se mueven: rodar el par alrededor de "
             "ellos es lo mismo que orbitar la fila alrededor del cable, y "
             "es mas barato que mover doce lamparas. Lo que cambia es de "
             "donde parece llegar la luz y que parte de la circunferencia "
             "del cilindro queda vuelta hacia las camaras. Las lamparas van "
             "visibles para que el giro se vea; ya esta medido que estando "
             "en cuadro no cambian la mascara.",
        cord=(0.0, 2.0, 26.5), lamps=(12, 2.0, 2.0, 26.5),
        view="axis", cam_offset=2.0, focal=8.0, tilt=(40.0, "-y"),
        cam_x=0.0, wave=S.WAVE, roll_deg=90.0, lamps_visible=True,
        e_target=S.E_R5_SLOW_LX, e_basis="R5, 3 sensores, 1 deg/s",
        blend_name="estudio_roll_90"),
}


def required_candela(lamp_ys, lamp_x, lamp_z, points,
                     e_target=S.E_TARGET_LX):
    """Intensity each lamp needs so the dimmest point of the cord meets R5.

    Point-source Lambertian model, the same one the layout was chosen with.
    It is an estimate of the lamp setting, not a prediction of the render:
    it ignores the rectangle's extent and every bounce off the walls, both
    of which add light. The render is what decides.

    ``points`` is the cord itself, from ``S.cord_points``, not a start and an
    end, because the cord is no longer a straight line between them.

    Measured, it changes nothing on the variants here, and the reason is
    worth knowing before trusting that: the wave is pinned at both ends, and
    on this layout the dimmest point of the cord **is** an end, because the
    lamp row stops short of the far one. So the minimum is taken at the one
    place the wave cannot move. The answer would change if the row ever
    overhangs both ends, which is the arrangement the uniformity sweep keeps
    asking for, and then a straight-line model would set every lamp from a
    geometry that is not in the frame.
    """
    worst = None
    for xp, yp, zp in points:
        e = 0.0
        for yl in lamp_ys:
            dx, dy, dz = xp - lamp_x, yp - yl, zp - lamp_z
            r2 = dx * dx + dy * dy + dz * dz
            e += ((lamp_z - zp) / math.sqrt(r2)) / r2
        if worst is None or e < worst:
            worst = e
    return e_target / worst


def render(variant, samples, scale, both_cameras, linear=False,
           blend_only=False, roll_override=None):
    """``linear`` writes OpenEXR with the view transform off.

    AgX is a tone map, so a JPEG pixel is not proportional to the light that
    reached it: over the 17x range of irradiance along a 26 m cord it
    compresses the bright end hard. Measuring lamp ripple off the JPEG read
    73% where the photometric model says 16%, and the model was right. Any
    measurement of how evenly the row lights the cord has to come from this
    path, not from the picture.
    """
    v = VARIANTS[variant]
    # ``--rolls`` barre el mismo caso a varios angulos sin tener que escribir
    # una entrada de VARIANTS por angulo. El angulo entra en el nombre de la
    # carpeta para que el barrido se ordene solo al listarlo.
    etiqueta_var = variant
    if roll_override is not None:
        v = dict(v, roll_deg=roll_override)
        etiqueta_var = f"{variant}_roll{roll_override:05.1f}"
    cord_x, y0, y1 = v["cord"]
    n_lamps, lamp_h, ly0, ly1 = v["lamps"]
    cord_z = S.TETHER["z_m"]
    lamp_z = cord_z + lamp_h

    lamp_ys = [ly0] if n_lamps == 1 else \
        [ly0 + (ly1 - ly0) * i / (n_lamps - 1) for i in range(n_lamps)]
    # A variant may pin the intensity instead of solving for it, which is the
    # only way to compare two lighting geometries without the comparison
    # being decided by one of them quietly drawing more power.
    far_x, far_z = v.get("cord_far", (cord_x, cord_z))
    wave = v.get("wave")
    points = S.cord_points(cord_x, cord_z, y0, y1, 512, far_x, far_z,
                           wave=wave)
    # El objetivo de iluminancia decide dos cosas a la vez y tienen que ser
    # la misma: cuanta potencia necesita la fila, y a que exposicion se revela
    # el render. Subir una sin la otra no simula mas luz, satura el cuadro.
    e_target = v.get("e_target", S.E_TARGET_LX)
    cd = v.get("candela") or required_candela(lamp_ys, cord_x, lamp_z, points,
                                              e_target)

    tilt_deg, tilt_dir = v.get("tilt", (0.0, "+y"))

    S._clear()
    # "orbit" is the same cord and the same rig with the room and the lamp
    # row taken away and one Sun put in their place. It exists so the two
    # cases differ in the lighting model and in nothing else: comparing the
    # studio against the orbital .blend instead would also change the sensor
    # and the lens, and then a difference in the result could not be pinned
    # on the light.
    orbit = v.get("env") == "orbit"
    if not orbit:
        S.build_room(S.ROOM["depth_m"], S.ROOM["width_m"], S.ROOM["height_m"])
    S.build_tether(cord_x, cord_z, y0, y1, S.TETHER["diameter_mm"],
                   x_far=far_x, z_far=far_z, wave=wave)
    if orbit:
        sun = S.build_sun(tilt_deg=tilt_deg, tilt_dir=tilt_dir,
                          stars=v.get("stars", False))
    else:
        S.build_lamp_row(cord_x, lamp_z, ly0, ly1, n_lamps, cd,
                         tilt_deg=tilt_deg, tilt_dir=tilt_dir, over=lamp_h,
                         visible_to_camera=v.get("lamps_visible", False))
    mid = (y0 + y1) / 2.0
    # The cameras are not always centred on the cord: anchoring the cord to
    # the side of the rig is the whole point of variant I.
    S.build_stereo_pair(v["focal"], S.OPTICS["baseline_mm"],
                        cord_z + v.get("cam_dz", 0.0),
                        v["view"], v.get("cam_x", cord_x), mid,
                        v["cam_offset"], roll_deg=v.get("roll_deg", 0.0))

    exposure = S.exposure_for(e_target)
    scene = S.configure_render(samples, exposure, scale)
    if linear:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.exposure = 0.0
        scene.render.image_settings.file_format = "OPEN_EXR"
        scene.render.image_settings.color_depth = "32"
    else:
        scene.render.image_settings.file_format = "JPEG"
        scene.render.image_settings.quality = 95

    # ``--blend-only`` builds the variant and saves it instead of rendering
    # it, which is the only way to actually LOOK at the scene: the lamps are
    # ``visible_camera = False``, so they light the cord and never appear in
    # the frame, and asking why they cannot be seen in a render is a fair
    # question with a confusing answer. Open the .blend and they are twelve
    # rectangles hanging over the cord.
    if blend_only:
        # El nombre lleva la letra Y lo que es. La letra enlaza con VARIANTS
        # y con el metadata de los renders; el resto es para quien abre la
        # carpeta sin haber leido este archivo.
        etiqueta = v.get("blend_name", v["view"])
        out = os.path.join(ROOT, "SIMULATION", "escenas",
                           f"TV2_{variant}_{etiqueta}.blend")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[blend] {variant} -> {out}", flush=True)
        return out

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "data", "captures",
                           f"stereo_sim_studio{etiqueta_var}_{stamp}")
    os.makedirs(out_dir, exist_ok=True)

    meta = {
        "capture_name": os.path.basename(out_dir),
        "source": "blender_simulation",
        "variant": variant,
        "note": v["note"],
        "room_m": dict(S.ROOM),
        "cord": dict(x_m=cord_x, z_m=cord_z, y0_m=y0, y1_m=y1,
                     x_far_m=far_x, z_far_m=far_z,
                     camera_x_m=v.get("cam_x", cord_x),
                     camera_dz_m=v.get("cam_dz", 0.0),
                     anchor_ahead_of_cameras_m=round(y0 - v["cam_offset"], 3),
                     length_m=round(y1 - y0, 3),
                     diameter_mm=S.TETHER["diameter_mm"],
                     albedo=S.TETHER["albedo"],
                     wave_modes_m=wave,
                     wave_excursion_m=round(max(
                         max(abs(p[0] - cord_x) for p in points),
                         max(abs(p[2] - cord_z) for p in points)), 4)),
        "environment": "orbit" if orbit else "studio",
        "sun": (dict(irradiance_w_m2=1361.0, temperature_k=5772.0,
                     angular_diameter_deg=0.526, tilt_deg=tilt_deg,
                     tilt_dir=tilt_dir, parallel=True, falloff=False,
                     starfield=v.get("stars", False))
                if orbit else None),
        "lamps": None if orbit else dict(count=n_lamps, height_over_cord_m=lamp_h, z_m=lamp_z,
                      y0_m=ly0, y1_m=ly1,
                      spacing_m=round((ly1 - ly0) / max(1, n_lamps - 1), 3),
                      candela=round(cd, 1), tilt_deg=tilt_deg,
                      tilt_dir=tilt_dir,
                      watts_each=round(S.candela_to_watts(cd), 1),
                      kw_electrical_total=round(
                          math.pi * cd / 90.0 * n_lamps / 1000.0, 2),
                      colour_k=5600.0,
                      visible_to_camera=v.get("lamps_visible", False)),
        "optics": dict(focal_mm=v["focal"], baseline_mm=S.OPTICS["baseline_mm"],
                       hfov_deg=round(S.hfov_deg(v["focal"]), 2)),
        "illuminance_target_lx": round(e_target, 1),
        "illuminance_target_basis": v.get("e_basis", "default"),
        "view": v["view"],
        "roll_deg": v.get("roll_deg", 0.0),
        "samples": samples,
        "resolution_percentage": scale,
        "view_transform": "Standard" if linear else "AgX",
        "exposure_stops": round(exposure, 4),
    }

    ext = "exr" if linear else "jpg"
    sides = ("left", "right") if both_cameras else ("left",)
    for side in sides:
        cam = bpy.data.objects["Cam_L" if side == "left" else "Cam_R"]
        scene.camera = cam
        path = os.path.join(out_dir, f"{side}.{ext}")
        scene.render.filepath = path
        print(f"[render] {variant} {side} -> {path}", flush=True)
        bpy.ops.render.render(write_still=True)
        meta[f"{side}_camera"] = dict(
            location_m=[round(c, 4) for c in cam.location],
            focal_mm=cam.data.lens,
            resolution=[scene.render.resolution_y, scene.render.resolution_x])

    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=4)
    print(f"[render] wrote {out_dir}", flush=True)
    return out_dir


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="A")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--scale", type=int, default=100)
    ap.add_argument("--both", action="store_true")
    ap.add_argument("--linear", action="store_true")
    ap.add_argument("--blend-only", action="store_true",
                    help="guarda la escena en vez de renderizarla")
    ap.add_argument("--rolls", default="",
                    help="lista de angulos de roll, en grados, separados por "
                         "comas: renderiza la variante una vez por angulo")
    args = ap.parse_args(argv)

    rolls = [float(r) for r in args.rolls.split(",") if r.strip()]
    for v in args.variant.split(","):
        if rolls:
            for r in rolls:
                render(v.strip(), args.samples, args.scale, args.both,
                       args.linear, args.blend_only, roll_override=r)
        else:
            render(v.strip(), args.samples, args.scale, args.both,
                   args.linear, args.blend_only)


main()
