#!/usr/bin/env python3
"""Dibuja la escena en vez de fotografiarla: el montaje visto desde afuera.

    blender --background --python SIMULATION/render_escenario.py -- --samples 96

Las salidas van a ``SIMULATION/experimentos/escenario/``.

**Esto no es un render del experimento, es un diagrama del montaje.** Los
renders de ``render_studio_iterations.py`` son lo que ve el par estereo: el
cable de 1 mm sub-pixel sobre fondo negro, que es justamente lo que hay que
medir y lo que no explica nada a quien no lo monto. Aqui la escena se mira
desde fuera, con el cuarto, la fila de lamparas, el par estereo y el cable en
su sitio, para poder senalarla en una reunion.

Tres cosas estan **deliberadamente falseadas**, y hay que decirlo cada vez que
se muestre una de estas imagenes:

* **El cable se dibuja 150 veces mas gordo.** El real mide 1 mm, que a 24 m de
  distancia y 1920 px de ancho de imagen es una centesima de pixel. Un
  diagrama en el que no se ve el objeto medido no sirve.
* **El cuarto se aclara.** El estudio tiene albedo 0.02, negro mate, y la
  iluminacion de la escena apunta al cable, no a las paredes: una vista
  exterior fiel sale negra. Aqui hay luz ambiente de diagrama y las paredes
  estan en 0.22.
* **Los mastiles son esquematicos.** Que los dos extremos del cable tengan que
  quedar a 5 m de altura y 24.5 m de separacion es real y es lo que hay que
  acordar con el estudio; como se sujetan, no. Esos cilindros son un dibujo,
  no una propuesta de montaje.

Lo que **no** esta falseado es la geometria: posiciones, alturas, distancias,
numero de lamparas, su separacion, su tamano, la base estereo y el campo de
los lentes salen de ``build_tv2_studio.py``, que es el mismo archivo con el
que se renderiza el experimento.
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Euler

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import build_tv2_studio as S  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
import calculadora_luz as CL  # noqa: E402

SALIDA = os.path.join(HERE, "experimentos", "escenario")

#: El cable de verdad mide 1 mm. A esta escala no se ve, asi que el diagrama
#: lo engorda. El factor va en el nombre del archivo y en el docstring para
#: que nadie lo lea como una medida.
CORDON_FACTOR = 150.0

COLORES = dict(
    cordon=(1.0, 0.45, 0.08),
    camara=(0.18, 0.52, 1.0),
    lampara=(1.0, 0.95, 0.80),
    mastil=(0.45, 0.47, 0.50),
    marca=(0.95, 0.80, 0.25),
    madera=(0.42, 0.30, 0.19),
    molton=(0.035, 0.035, 0.042),
    haz=(1.0, 0.86, 0.55),
    direccion=(0.35, 0.80, 1.0),
)


# ------------------------------------------------------------- materiales

def _mat_color(nombre, rgb, emision=0.0):
    mat = bpy.data.materials.new(nombre)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    if emision > 0.0:
        for clave in ("Emission Color", "Emission"):
            if clave in bsdf.inputs:
                bsdf.inputs[clave].default_value = (*rgb, 1.0)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emision
    return mat


def _pintar(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def _texto(cadena, loc, euler, tam, mat, centrado=False):
    """Un rotulo dentro de la escena, no encima de la imagen.

    Se le da el **mismo euler que a la camara** que lo va a ver: asi su +z
    local, que es por donde mira el texto, apunta a la camara, y su +x local,
    que es la direccion de lectura, cae sobre el derecho de la imagen. Vale
    igual para la elevacion y para la planta sin tocar nada mas.
    """
    bpy.ops.object.text_add()
    obj = bpy.context.active_object
    obj.name = f"Txt_{cadena[:18]}"
    obj.data.body = cadena
    obj.data.size = tam
    obj.data.extrude = 0.0
    if centrado:
        obj.data.align_x = "CENTER"
    obj.location = loc
    obj.rotation_euler = Euler(euler, "XYZ")
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


# ------------------------------------------------------------- geometria

def _cilindro(nombre, p0, p1, radio, mat):
    """Un cilindro entre dos puntos. Para cables, mastiles y flechas."""
    import mathutils
    v = mathutils.Vector(p1) - mathutils.Vector(p0)
    largo = v.length
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radio,
                                        depth=largo)
    obj = bpy.context.active_object
    obj.name = nombre
    obj.location = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0,
                    (p0[2] + p1[2]) / 2.0)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = v.to_track_quat("Z", "Y")
    return _pintar(obj, mat)


def cordon_grueso(pts, mat):
    """El cable como una tira de cilindros, engordado para que se vea."""
    radio = S.TETHER["diameter_mm"] / 1000.0 / 2.0 * CORDON_FACTOR
    paso = max(1, len(pts) // 90)
    trozos = []
    for i in range(0, len(pts) - paso, paso):
        trozos.append(_cilindro(f"Cordon_{i}", pts[i], pts[i + paso],
                                radio, mat))
    return trozos


def camaras_proxy(z, baseline_mm, cam_y, mat):
    """Dos cajas azules donde van las camaras, y la base entre ellas."""
    half = baseline_mm / 1000.0 / 2.0
    cuerpos = []
    for s in (-1.0, 1.0):
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        obj = bpy.context.active_object
        obj.name = "Camara_L" if s < 0 else "Camara_R"
        # 38 x 38 mm de placa, dibujadas a 0.30 m para que se vean.
        obj.scale = (0.30, 0.42, 0.30)
        obj.location = (s * half, cam_y, z)
        bpy.ops.object.transform_apply(scale=True)
        cuerpos.append(_pintar(obj, mat))
    return cuerpos


def lamparas_proxy(x, z, y0, y1, count, mat, tilt_deg=40.0, over=2.0):
    """Los doce rectangulos de 1 x 1 m, como paneles que se ven.

    **Inclinados, como en el experimento.** La primera version los dibujaba
    planos y eso contradecia el render sin que nada lo avisara: en
    ``build_lamp_row`` el haz se inclina ``tilt_deg`` hacia la camara, lo que
    gira cada panel ``-tilt`` sobre X y ademas lo corre ``over * tan(tilt)``
    rio arriba, 1.68 m a 40 grados sobre una fila 2 m encima del cable. Esas
    dos cosas se repiten aqui con la misma formula para que el diagrama no
    pueda volver a separarse de la escena.
    """
    t = math.radians(tilt_deg)
    corrimiento = over * math.tan(t)
    ys = [y0] if count == 1 else \
        [y0 + (y1 - y0) * i / (count - 1) for i in range(count)]
    paneles = []
    for i, y in enumerate(ys):
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        obj = bpy.context.active_object
        obj.name = f"Lampara_{i:02d}"
        obj.scale = (1.0, 1.0, 0.08)
        bpy.ops.object.transform_apply(scale=True)
        obj.location = (x, y + corrimiento, z)
        obj.rotation_euler = Euler((-t, 0.0, 0.0), "XYZ")
        paneles.append(_pintar(obj, mat))
    return paneles, ys


def _mat_translucido(nombre, rgb, fuerza=1.1, opacidad=0.14):
    """Emision mezclada con transparente: un volumen de diagrama.

    Los conos de haz tienen que dejar ver el cable que hay dentro, asi que no
    pueden ser solidos. En Cycles la transparencia de un diagrama se hace con
    un Mix Shader contra un Transparent BSDF, no con ``blend_method``, que es
    de EEVEE y aqui no hace nada.
    """
    mat = bpy.data.materials.new(nombre)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    salida = nt.nodes["Material Output"]
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = (*rgb, 1.0)
    emi.inputs["Strength"].default_value = fuerza
    tra = nt.nodes.new("ShaderNodeBsdfTransparent")
    mez = nt.nodes.new("ShaderNodeMixShader")
    mez.inputs["Fac"].default_value = opacidad
    nt.links.new(tra.outputs[0], mez.inputs[1])
    nt.links.new(emi.outputs[0], mez.inputs[2])
    nt.links.new(mez.outputs[0], salida.inputs["Surface"])
    return mat


def cono_de_haz(nombre, apex, tilt_deg, largo, haz_deg, mat, tilt_dir="-y"):
    """El cono que una luminaria realmente ilumina, dibujado.

    Es la pieza que hace que el diagrama se explique solo. Doce paneles de
    1 x 1 m banan el cable entero y no hay nada que mirar; cinco conos de 45
    grados se tocan apenas, y en el dibujo se ve donde no llegan.

    El cono de Blender nace con el vertice en +Z local, asi que para que el
    vertice quede en la luminaria y la boca mire por donde viaja el haz, su
    +Z tiene que apuntar al reves del haz: con el haz en ``(0, -sin t,
    -cos t)``, eso es una rotacion de ``-t`` sobre X, la misma que lleva el
    cuerpo de la luminaria. El centro va medio largo por delante del vertice
    en la direccion del haz.
    """
    t = math.radians(tilt_deg)
    if tilt_dir == "-y":
        beam = (0.0, -math.sin(t), -math.cos(t))
        rot = (-t, 0.0, 0.0)
    elif tilt_dir == "+y":
        beam = (0.0, math.sin(t), -math.cos(t))
        rot = (t, 0.0, 0.0)
    elif tilt_dir == "+x":
        beam = (math.sin(t), 0.0, -math.cos(t))
        rot = (0.0, -t, 0.0)
    else:
        beam = (-math.sin(t), 0.0, -math.cos(t))
        rot = (0.0, t, 0.0)
    radio = largo * math.tan(math.radians(haz_deg / 2.0))
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=radio, radius2=0.0,
                                    depth=largo)
    obj = bpy.context.active_object
    obj.name = nombre
    obj.location = (apex[0] + beam[0] * largo / 2.0,
                    apex[1] + beam[1] * largo / 2.0,
                    apex[2] + beam[2] * largo / 2.0)
    obj.rotation_euler = Euler(rot, "XYZ")
    _pintar(obj, mat)
    # Un cono de diagrama no tiene que hacer sombra ni recibirla: si la hace,
    # oscurece el piso justo donde se quiere ver que la luz llega.
    obj.visible_shadow = False
    return obj


def proyectores_proxy(x, z, y0, y1, unidades, mat_cuerpo, mat_cono,
                      tilt_deg=40.0, over=4.5, tilt_dir="-y"):
    """Las luminarias REALES del estudio, con su cono y su rotulo.

    ``unidades`` son ``(candela, haz_deg, etiqueta)`` de
    ``tools/calculadora_luz.py``, en el orden en que esa calculadora las
    reparte por la fila. El cuerpo es un cilindro corto, que es la forma de
    un proyector con reflector conico, y no un panel plano: la diferencia
    entre los doce paneles supuestos y estas cinco es exactamente eso.

    El corrimiento rio arriba repite la formula de ``build_projector_row``,
    ``over * tan(tilt)``, para que el diagrama no pueda separarse de la
    escena que se renderiza. A 40 grados con la fila 4.5 m sobre el cable son
    3.78 m, que es mucho: una luminaria dibujada sobre el punto que ilumina
    seria una mentira de casi cuatro metros.
    """
    t = math.radians(tilt_deg)
    corrimiento = over * math.tan(t)
    tiro = over / math.cos(t)
    n = len(unidades)
    ys = [y0] if n == 1 else [y0 + (y1 - y0) * i / (n - 1) for i in range(n)]
    cuerpos = []
    for i, ((cd, haz, etiqueta), ya) in enumerate(zip(unidades, ys)):
        if tilt_dir in ("-y", "+y"):
            loc = (x, ya + (corrimiento if tilt_dir == "-y" else -corrimiento),
                   z)
        else:
            loc = (x + (corrimiento if tilt_dir == "-x" else -corrimiento),
                   ya, z)
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.26,
                                            depth=0.62)
        obj = bpy.context.active_object
        obj.name = f"Proyector_{i:02d}_{etiqueta}"
        obj.location = loc
        obj.rotation_euler = Euler(
            (-t, 0.0, 0.0) if tilt_dir == "-y" else
            (t, 0.0, 0.0) if tilt_dir == "+y" else
            (0.0, -t, 0.0) if tilt_dir == "+x" else (0.0, t, 0.0), "XYZ")
        cuerpos.append(_pintar(obj, mat_cuerpo))
        # El cono se dibuja un 15 % mas largo que el tiro para que se vea
        # que pasa de largo del cable y termina en el piso.
        cono_de_haz(f"Haz_{i:02d}", loc, tilt_deg, tiro * 1.15, haz,
                    mat_cono, tilt_dir=tilt_dir)
    return cuerpos, ys, corrimiento, tiro


def marcas_de_piso(y0, y1, paso, mat):
    """Una marca cada cinco metros, para que la escala no haya que creerla."""
    marcas = []
    y = y0
    while y <= y1 + 1e-6:
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        obj = bpy.context.active_object
        obj.name = f"Marca_{int(y):02d}m"
        obj.scale = (2.2, 0.12, 0.03)
        obj.location = (0.0, y, 0.02)
        bpy.ops.object.transform_apply(scale=True)
        marcas.append(_pintar(obj, mat))
        y += paso
    return marcas


# ------------------------------------------------------------- iluminacion

def ambiente(fuerza=1.1, color=(0.42, 0.46, 0.52)):
    """Luz de diagrama. No es la del experimento y no pretende serlo.

    El estudio es negro mate y su fila de lamparas apunta al cable, asi que
    una vista exterior fiel sale negra. Esto existe para que la geometria se
    lea en una reunion, y por eso toda imagen de este archivo lleva el aviso.
    """
    world = bpy.data.worlds.new("Diagrama")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = fuerza
    return world


def rasante(energia=4.0):
    """Un sol flojo y rasante, solo para que las cajas tengan volumen."""
    data = bpy.data.lights.new("SolDiagrama", type="SUN")
    data.energy = energia
    data.angle = math.radians(8.0)
    obj = bpy.data.objects.new("SolDiagrama", data)
    obj.rotation_euler = Euler((math.radians(-55.0), math.radians(25.0),
                                math.radians(30.0)), "XYZ")
    bpy.context.collection.objects.link(obj)
    return obj


# ------------------------------------------------------------- camaras

def camara_vista(nombre, loc, mirando_a=None, lente=24.0, orto=None,
                 euler=None):
    import mathutils
    data = bpy.data.cameras.new(nombre)
    if orto:
        data.type = "ORTHO"
        data.ortho_scale = orto
    else:
        data.lens = lente
        data.sensor_width = 36.0
    data.clip_start = 0.05
    data.clip_end = 400.0
    obj = bpy.data.objects.new(nombre, data)
    obj.location = loc
    if euler is not None:
        obj.rotation_euler = Euler(euler, "XYZ")
    else:
        v = mathutils.Vector(mirando_a) - mathutils.Vector(loc)
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = (-v).to_track_quat("Z", "Y")
    bpy.context.collection.objects.link(obj)
    return obj


# ------------------------------------------------------------- escenas

def escena_estudio():
    """El cuarto TV2 con la fila de doce y el par estereo al pie."""
    S._clear()
    ambiente()
    rasante()

    cord_x, y0, y1 = 0.0, 2.0, 26.5
    cord_z = S.TETHER["z_m"]
    lamp_z = cord_z + 2.0

    # El cuarto, gris y **abierto**: piso, pared del fondo y pared lateral,
    # sin techo ni pared cercana. Dos razones. Con el albedo real, 0.02, el
    # diagrama sale negro; y una caja cerrada no deja entrar la luz ambiente
    # del diagrama, asi que el primer intento salio negro por dentro aunque
    # las paredes ya estaban en 0.22. Un diagrama no tiene que ser estanco,
    # el render del experimento si, y ese usa ``S.build_room``.
    gris = _mat_color("CuartoDiagrama", (0.26, 0.26, 0.27))
    W, D, H = S.ROOM["width_m"], S.ROOM["depth_m"], S.ROOM["height_m"]
    for nombre, loc, escala, rot in (
            ("Piso",        (0.0, D / 2.0, 0.0),  (W, D, 1.0), (0, 0, 0)),
            ("ParedFondo",  (0.0, D, H / 2.0),    (W, H, 1.0),
             (math.radians(90.0), 0, 0)),
            ("ParedLateral", (-W / 2.0, D / 2.0, H / 2.0), (D, H, 1.0),
             (0, math.radians(90.0), math.radians(90.0)))):
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        obj = bpy.context.active_object
        obj.name = nombre
        obj.scale = escala
        obj.rotation_euler = Euler(rot, "XYZ")
        obj.location = loc
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _pintar(obj, gris)

    pts = S.cord_points(cord_x, cord_z, y0, y1, 512, wave=S.WAVE)
    cordon_grueso(pts, _mat_color("CordonDiagrama", COLORES["cordon"], 1.2))
    _, lamp_ys = lamparas_proxy(cord_x, lamp_z, y0, y1, 12,
                                _mat_color("LamparaDiagrama",
                                           COLORES["lampara"], 6.0))
    camaras_proxy(cord_z, S.OPTICS["baseline_mm"], y0,
                  _mat_color("CamaraDiagrama", COLORES["camara"], 0.4))
    marcas_de_piso(5.0, 25.0, 5.0,
                   _mat_color("MarcaDiagrama", COLORES["marca"], 0.6))

    mast = _mat_color("MastilDiagrama", COLORES["mastil"])
    _cilindro("Mastil_cerca", (0.0, y0, 0.0), (0.0, y0, cord_z - 0.35),
              0.09, mast)
    _cilindro("Mastil_lejos", (pts[-1][0], y1, 0.0),
              (pts[-1][0], y1, pts[-1][2]), 0.09, mast)
    return dict(cord_x=cord_x, y0=y0, y1=y1, cord_z=cord_z, lamp_z=lamp_z,
                lamp_ys=lamp_ys, pts=pts)


def escena_estudio_real(spec="storm1200x:45:4,ls1200d_pro:45:1",
                        cord_z=1.5, lamp_z=6.0, y0=2.0, y1=20.0,
                        tilt_deg=0.0, molton=True):
    """El TV2 como se va a montar el viernes 11, con las luminarias que hay.

    Sustituye a ``escena_estudio``, que dibuja los doce paneles de 1 x 1 m
    que suponiamos. Ese dibujo no esta mal, es de otro montaje: el estudio
    tiene cuatro STORM 1200x y dos LS 1200d Pro, que son proyectores de cono.

    Tres cosas de este dibujo no son decoracion y conviene leerlas:

    * **el cable baja a 1.5 m**, porque un cono de 45 grados necesita de 4.5
      a 6 m de tiro para cubrir su tramo y con techo de 10 m eso no deja el
      cable a 5. A 1.5 m se tiende a mano, sin andamio.
    * **el piso es de madera y lleva molton negro encima.** El cable que se
      mide tiene 1 mm, asi que cualquier fondo claro lo tapa, y al bajar el
      cable el piso entra en cuadro a 5.1 m en vez de a 17. El rectangulo
      oscuro del dibujo es la tela, 20 x 3 m.
    * **el haz va vertical**, y eso esta medido, no supuesto. Inclinarlo 40
      grados cuesta el 20 % del contraste del cordon en la vista que mira a
      lo largo del cable, porque de un cilindro visto casi de punta la camara
      ve el limbo y un haz inclinado reparte su luz hacia una cara que no
      esta ahi. Con el haz vertical cada luminaria va justo encima del tramo
      que ilumina; con ``tilt_deg`` distinto de cero se corre
      ``over * tan(tilt)`` rio arriba, 3.78 m a 40 grados, que es lo que
      dibujaba la primera version de esta escena.
    """
    S._clear()
    ambiente()
    rasante()

    cord_x = 0.0
    over = lamp_z - cord_z
    W, D, H = S.ROOM["width_m"], S.ROOM["depth_m"], S.ROOM["height_m"]

    # El cuarto abierto, como en ``escena_estudio``: piso, fondo y un lateral.
    # El piso va de color madera, que es lo que Jose confirmo que hay, para
    # que la tela se lea como lo que es y no como una sombra.
    madera = _mat_color("PisoMadera", COLORES["madera"])
    pared = _mat_color("ParedDiagrama", (0.24, 0.24, 0.26))
    for nombre, loc, escala, rot, mat in (
            ("Piso", (0.0, D / 2.0, 0.0), (W, D, 1.0), (0, 0, 0), madera),
            ("ParedFondo", (0.0, D, H / 2.0), (W, H, 1.0),
             (math.radians(90.0), 0, 0), pared),
            ("ParedLateral", (-W / 2.0, D / 2.0, H / 2.0), (D, H, 1.0),
             (0, math.radians(90.0), math.radians(90.0)), pared)):
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        obj = bpy.context.active_object
        obj.name = nombre
        obj.scale = escala
        obj.rotation_euler = Euler(rot, "XYZ")
        obj.location = loc
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _pintar(obj, mat)

    if molton:
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        tela = bpy.context.active_object
        tela.name = "MoltonNegro"
        tela.scale = (3.0, (y1 - y0) + 2.0, 1.0)
        tela.location = (0.0, (y0 + y1) / 2.0, 0.015)
        bpy.ops.object.transform_apply(scale=True, location=True)
        _pintar(tela, _mat_color("MoltonDiagrama", COLORES["molton"]))

    pts = S.cord_points(cord_x, cord_z, y0, y1, 512, wave=S.WAVE)
    cordon_grueso(pts, _mat_color("CordonDiagrama", COLORES["cordon"], 1.2))

    unidades = []
    for modelo, ref in CL.unidades_de(spec):
        cd, _ = CL.intensidad_cd(modelo, ref)
        unidades.append((cd, CL.LUMINARIAS[modelo]["haz"][ref],
                         "STORM" if modelo.startswith("storm") else "LS"))
    _, lamp_ys, corrimiento, tiro = proyectores_proxy(
        cord_x, lamp_z, y0, y1, unidades,
        _mat_color("CuerpoProyector", (0.82, 0.82, 0.84), 0.2),
        _mat_translucido("HazDiagrama", COLORES["haz"]),
        tilt_deg=tilt_deg, over=over)

    camaras_proxy(cord_z, S.OPTICS["baseline_mm"], y0,
                  _mat_color("CamaraDiagrama", COLORES["camara"], 0.4))
    marcas_de_piso(5.0, 20.0, 5.0,
                   _mat_color("MarcaDiagrama", COLORES["marca"], 0.6))

    mast = _mat_color("MastilDiagrama", COLORES["mastil"])
    _cilindro("Mastil_cerca", (0.0, y0, 0.0), (0.0, y0, cord_z - 0.12),
              0.07, mast)
    _cilindro("Mastil_lejos", (pts[-1][0], y1, 0.0),
              (pts[-1][0], y1, pts[-1][2]), 0.07, mast)
    return dict(cord_x=cord_x, y0=y0, y1=y1, cord_z=cord_z, lamp_z=lamp_z,
                lamp_ys=lamp_ys, pts=pts, corrimiento=corrimiento, tiro=tiro,
                unidades=unidades)


def escena_esfera(azimutes=16, inclinaciones=(-60.0, -30.0, 0.0, 30.0, 60.0),
                  destacada=(45.0, 30.0)):
    """El cable y la ESFERA de direcciones desde las que puede llegar el sol.

    El anillo que dibuja ``escena_orbita`` es un corte de esto: un azimut que
    gira alrededor del eje del cable, a inclinacion cero. La esfera es el
    experimento completo, porque no se sabe en que direccion va a estar el
    sol y el azimut solo recorre un circulo maximo.

    Cada bolita es una direccion renderizada, puesta en el radio del
    diagrama. Hay ``azimutes * len(inclinaciones)`` mas los dos polos, y la
    destacada lleva un sol de verdad, una esfera y no un circulo, con una
    linea hasta el cable para que se vea que el haz apunta ahi.
    """
    S._clear()
    S._build_world(stars=True)
    rasante(energia=2.0)

    cord_x, y0, y1 = 0.0, 2.0, 20.0
    cord_z = 5.0
    pts = S.cord_points(cord_x, cord_z, y0, y1, 512, wave=S.WAVE)
    cordon_grueso(pts, _mat_color("CordonDiagrama", COLORES["cordon"], 1.4))
    camaras_proxy(cord_z, S.OPTICS["baseline_mm"], y0,
                  _mat_color("CamaraDiagrama", COLORES["camara"], 0.5))

    centro = (cord_x, (y0 + y1) / 2.0, cord_z)
    radio = 7.5
    mat_dir = _mat_color("DireccionDiagrama", COLORES["direccion"], 2.2)
    mat_sol = _mat_color("SolDiagrama", (1.0, 0.93, 0.70), 9.0)

    def punto(az_deg, inc_deg):
        """La direccion de la que viene el haz, en el radio del diagrama.

        Es la inversa de ``build_sun``: alli el haz viaja en
        ``(cos t sin o, -sin t, -cos t cos o)``, asi que el sol esta en menos
        eso. Se reconstruye aqui con la misma formula y no con otra, que es
        la unica forma de que el dibujo y el render hablen del mismo angulo.
        """
        t, o = math.radians(inc_deg), math.radians(az_deg)
        haz = (math.cos(t) * math.sin(o), -math.sin(t),
               -math.cos(t) * math.cos(o))
        return (centro[0] - haz[0] * radio, centro[1] - haz[1] * radio,
                centro[2] - haz[2] * radio)

    direcciones = []
    for i in range(azimutes):
        az = 360.0 * i / azimutes
        for inc in inclinaciones:
            direcciones.append((az, inc))
    direcciones += [(0.0, -89.0), (0.0, 89.0)]

    for k, (az, inc) in enumerate(direcciones):
        pp = punto(az, inc)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, segments=16,
                                             ring_count=8, location=pp)
        obj = bpy.context.active_object
        obj.name = f"Dir_{k:03d}_az{az:05.1f}_inc{inc:+05.1f}"
        _pintar(obj, mat_dir)
        obj.visible_shadow = False

    # El sol destacado: una ESFERA, con su tamano exagerado para que se vea,
    # y la linea del haz hasta el cable.
    ps = punto(*destacada)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.95, segments=32,
                                         ring_count=16, location=ps)
    sol = bpy.context.active_object
    sol.name = "Sol_destacado"
    _pintar(sol, mat_sol)
    sol.visible_shadow = False
    _cilindro("Haz_destacado", ps, centro, 0.045,
              _mat_color("HazLinea", COLORES["haz"], 2.0))
    return dict(centro=centro, radio=radio, direcciones=direcciones,
                destacada=destacada, pts=pts)


def escena_orbita(orbit_deg=45.0, marcas=16):
    """El mismo cable en orbita, y el anillo por el que gira el haz."""
    S._clear()
    # Las estrellas se quedan: ``ambiente()`` reemplaza el mundo entero, asi
    # que aqui no se llama y el volumen de las cajas lo dan dos soles flojos.
    S._build_world(stars=True)
    rasante(energia=2.5)
    relleno = bpy.data.lights.new("SolRelleno", type="SUN")
    relleno.energy = 1.6
    relleno.angle = math.radians(12.0)
    obj_relleno = bpy.data.objects.new("SolRelleno", relleno)
    obj_relleno.rotation_euler = Euler((math.radians(-110.0), 0.0,
                                        math.radians(-40.0)), "XYZ")
    bpy.context.collection.objects.link(obj_relleno)

    cord_x, y0, y1 = 0.0, 2.0, 26.5
    cord_z = S.TETHER["z_m"]
    pts = S.cord_points(cord_x, cord_z, y0, y1, 512, wave=S.WAVE)
    cordon_grueso(pts, _mat_color("CordonOrbita", COLORES["cordon"], 1.4))
    camaras_proxy(cord_z, S.OPTICS["baseline_mm"], y0,
                  _mat_color("CamaraOrbita", COLORES["camara"], 0.5))

    # El anillo de azimutes: dieciseis posiciones del haz alrededor del eje
    # del cable. El eje es Y, asi que el anillo vive en el plano X-Z.
    # El anillo se centra en el cable mismo y no en el eje recto: el cable se
    # aparta hasta 0.82 m del eje, y un anillo centrado en el eje deja la
    # flecha del haz apuntando al aire.
    medio = pts[len(pts) // 2]
    centro = (medio[0], medio[1], medio[2])
    radio = 6.0
    mat_sol = _mat_color("SolMarca", (1.0, 0.86, 0.45), 3.0)
    mat_act = _mat_color("SolActivo", (1.0, 0.72, 0.15), 14.0)
    for k in range(marcas):
        ang = 360.0 / marcas * k
        t = math.radians(ang)
        # Misma convencion que build_sun: a 0 grados el haz viene de arriba,
        # a 90 del lado -x.
        p = (centro[0] - math.sin(t) * radio, centro[1],
             centro[2] + math.cos(t) * radio)
        activo = abs(ang - orbit_deg) < 1e-6
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.55 if activo else 0.22, segments=16, ring_count=8)
        obj = bpy.context.active_object
        obj.name = f"Sol_{ang:05.1f}"
        obj.location = p
        _pintar(obj, mat_act if activo else mat_sol)
        if activo:
            # La flecha del haz, desde la marca hasta el cable.
            _cilindro("Haz", p, centro, 0.10, mat_act)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=radio, minor_radius=0.025,
        location=centro, rotation=(math.radians(90.0), 0.0, 0.0),
        major_segments=96, minor_segments=8)
    anillo = bpy.context.active_object
    anillo.name = "Anillo"
    _pintar(anillo, _mat_color("AnilloDiagrama", (0.55, 0.60, 0.70), 0.8))
    return dict(centro=centro, pts=pts, cord_z=cord_z, y0=y0, y1=y1)


# ------------------------------------------------------------- driver

def _render(nombre, cam, samples, ancho=1920, alto=1080):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = ancho
    scene.render.resolution_y = alto
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = 0.0
    scene.render.image_settings.file_format = "PNG"
    try:
        scene.cycles.device = "CPU"
    except Exception:
        pass
    os.makedirs(SALIDA, exist_ok=True)
    scene.camera = cam
    path = os.path.join(SALIDA, f"{nombre}.png")
    scene.render.filepath = path
    print(f"[escenario] {nombre} -> {path}", flush=True)
    bpy.ops.render.render(write_still=True)
    return path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    pedidas = {s.strip() for s in args.only.split(",") if s.strip()}

    def quiere(n):
        return not pedidas or n in pedidas

    hechos = []

    if quiere("estudio_tres_cuartos") or quiere("estudio_elevacion") \
            or quiere("estudio_planta"):
        g = escena_estudio()
        tinta = _mat_color("Rotulo", (0.97, 0.97, 0.98), 1.6)
        # Las dos vistas ortograficas se rotulan dentro de la escena. El
        # ``euler`` de cada rotulo es el de su camara, asi el texto la mira
        # de frente y se lee de izquierda a derecha.
        E_ELEV = (math.radians(90.0), 0.0, math.radians(90.0))
        E_PLAN = (0.0, 0.0, math.radians(90.0))
        if quiere("estudio_tres_cuartos"):
            cam = camara_vista("VistaTresCuartos", (13.5, -7.0, 9.5),
                               mirando_a=(0.0, 12.0, 5.0), lente=24.0)
            hechos.append(_render("estudio_tres_cuartos", cam, args.samples))
        if quiere("estudio_elevacion"):
            # Perfil: el eje largo del cuarto en horizontal y las alturas en
            # vertical. Ortografica, para que se puedan medir las alturas.
            for txt, loc, tam in (
                    ("12 lamparas de 1 x 1 m, a 7.0 m",
                     (2.0, 3.6, 7.55), 0.72),
                    ("cable 1 mm (dibujado x150), 24.5 m, a 5.0 m",
                     (2.0, 6.5, 3.35), 0.72),
                    ("par estereo, base 100 mm", (2.0, 0.0, 6.3), 0.72),
                    ("piso del estudio", (2.0, 20.0, 0.45), 0.60),
                    ("techo a 10 m", (2.0, 20.0, 9.3), 0.60)):
                _texto(txt, loc, E_ELEV, tam, tinta)
            cam = camara_vista("VistaElevacion", (14.0, 15.0, 5.0),
                               orto=32.0, euler=E_ELEV)
            hechos.append(_render("estudio_elevacion", cam, args.samples))
            for o in [o for o in bpy.data.objects if o.name.startswith("Txt_")]:
                bpy.data.objects.remove(o, do_unlink=True)
        if quiere("estudio_planta"):
            for txt, loc, tam in (
                    ("24.5 m de cable", (-4.6, 8.0, 0.06), 0.80),
                    ("fila de 12 lamparas, una cada 2.23 m",
                     (1.4, 4.0, 0.06), 0.72),
                    ("par estereo", (-2.2, 0.4, 0.06), 0.72),
                    ("15 m de ancho", (5.6, 20.0, 0.06), 0.72)):
                _texto(txt, loc, E_PLAN, tam, tinta)
            cam = camara_vista("VistaPlanta", (0.0, 15.0, 9.7), orto=32.0,
                               euler=E_PLAN)
            hechos.append(_render("estudio_planta", cam, args.samples))

    # --- El cuarto con las luminarias que el estudio tiene ----------------
    if quiere("tv2_tres_cuartos") or quiere("tv2_elevacion") \
            or quiere("tv2_planta"):
        g = escena_estudio_real()
        tinta = _mat_color("RotuloTV2", (0.97, 0.97, 0.98), 1.6)
        E_ELEV = (math.radians(90.0), 0.0, math.radians(90.0))
        E_PLAN = (0.0, 0.0, math.radians(90.0))
        if quiere("tv2_tres_cuartos"):
            cam = camara_vista("TV2TresCuartos", (10.5, -5.5, 7.0),
                               mirando_a=(0.0, 10.0, 2.6), lente=24.0)
            hechos.append(_render("tv2_tres_cuartos", cam, args.samples))
        if quiere("tv2_elevacion"):
            for txt, loc, tam in (
                    ("5 luminarias reales a 6.0 m: 4 STORM 1200x + 1 LS 1200d Pro",
                     (2.0, 2.2, 6.55), 0.62),
                    ("haz vertical: medido, inclinarlo cuesta hasta el 42 % "
                     "del contraste del cordon", (2.0, 2.2, 5.95), 0.52),
                    ("cono de 45 grados: tiro 4.50 m, huella 3.73 m",
                     (2.0, 6.2, 4.35), 0.55),
                    ("cable 1 mm (dibujado x150), 18 m, a 1.5 m del piso",
                     (2.0, 4.0, 2.25), 0.62),
                    ("par estereo, base 100 mm", (2.0, -1.2, 1.15), 0.55),
                    ("molton negro sobre el piso de madera",
                     (2.0, 3.0, 0.22), 0.55),
                    ("techo del estudio a 10 m, no dibujado",
                     (2.0, 13.0, 9.3), 0.55)):
                _texto(txt, loc, E_ELEV, tam, tinta)
            cam = camara_vista("TV2Elevacion", (14.0, 10.5, 4.2),
                               orto=26.0, euler=E_ELEV)
            hechos.append(_render("tv2_elevacion", cam, args.samples))
            for o in [o for o in bpy.data.objects
                      if o.name.startswith("Txt_")]:
                bpy.data.objects.remove(o, do_unlink=True)
        if quiere("tv2_planta"):
            for txt, loc, tam in (
                    ("18 m de cable", (-4.2, 7.0, 0.06), 0.72),
                    ("5 luminarias, una cada 4.5 m", (1.6, 5.0, 0.06), 0.62),
                    ("par estereo", (-2.0, 0.6, 0.06), 0.62),
                    ("molton negro, 20 x 3 m", (3.4, 14.0, 0.06), 0.62),
                    ("15 m de ancho", (5.8, 19.0, 0.06), 0.62)):
                _texto(txt, loc, E_PLAN, tam, tinta)
            cam = camara_vista("TV2Planta", (0.0, 10.5, 9.7), orto=26.0,
                               euler=E_PLAN)
            hechos.append(_render("tv2_planta", cam, args.samples))
            for o in [o for o in bpy.data.objects
                      if o.name.startswith("Txt_")]:
                bpy.data.objects.remove(o, do_unlink=True)

    # --- La esfera de direcciones del sol ---------------------------------
    if quiere("orbita_esfera"):
        escena_esfera()
        cam = camara_vista("VistaEsfera", (-13.0, -7.0, 12.5),
                           mirando_a=(0.0, 11.0, 5.0), lente=26.0)
        hechos.append(_render("orbita_esfera", cam, args.samples))

    if quiere("orbita_anillo"):
        escena_orbita(orbit_deg=45.0)
        cam = camara_vista("VistaOrbita", (-11.0, -6.0, 11.0),
                           mirando_a=(0.0, 13.0, 5.0), lente=28.0)
        hechos.append(_render("orbita_anillo", cam, args.samples))

    print(f"[escenario] {len(hechos)} imagenes en {SALIDA}", flush=True)
    for h in hechos:
        print("   ", h, flush=True)


main()
