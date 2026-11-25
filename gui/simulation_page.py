#!/usr/bin/env python3
"""
Simulation page: look at what the simulation rendered, and at where it was
rendered from.

This page replaces a published HTML artifact. The artifact worked, but it
lived in a claude.ai account and the project cannot depend on one: the
measurements belong to the repository and the deliverables, and the thing
that lets an operator walk through them belongs to the application the
operator already opens. Nothing here computes anything new. Every number
comes from a CSV that a measuring script wrote and that is versioned beside
the experiment:

    SIMULATION/experimentos/sol_esfera/medidas.csv
    SIMULATION/experimentos/estudio_luminarias_reales/medidas_familia.csv

So the page is a reader, never a second implementation of the measurement.
If a figure here disagrees with the deliverable, the CSV is wrong or stale,
and the fix is to re-run ``tools/medir_esfera.py`` and not to patch this
file.

**Why the orbit diagram is drawn and not just the sphere of dots.** The
first version of this viewer showed a flat disc of markers, and the honest
report from the first person to use it was that it was disorienting: a dot
on a disc does not say where the sun is, because it does not say where
anything else is. A direction only means something next to the cord it
lights and the cameras that look at it. So the diagram draws the scene:
the cord with the shape it actually has in the render, the stereo pair at
the near end with its image frame, the world axes, and the sphere of
directions around all of it. Dragging turns the **view**, never the sun.
The sun is chosen by clicking a marker or by the grid below, and both say
so on screen, because a control that silently does two things is the
reason the first one was confusing.

**The images are a display copy.** Gamma ``0.42`` is applied before any
resize, the same curve and the same order as ``tools/armar_esfera_web.py``
and ``tools/fig_renders.py``. The render is correctly exposed and the cord
still sits a few tens of levels above a near-black background, which is
plenty for the sensor and nothing for a screen. The curve is monotone so
it invents no pixel and swaps no two, but the copy stops being
proportional to light: no measurement comes out of what is displayed here.
"""

from __future__ import annotations

import csv
import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from PyQt5.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF,
)
from PyQt5.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from utils.logger import get_logger

logger = get_logger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BG_DEEP = "#0F172A"
BG_PANEL = "#1E293B"
BG_CARD = "#273548"
ACCENT_CYAN = "#22D3EE"
ACCENT_AMBER = "#F59E0B"
TEXT_PRIMARY = "#E2E8F0"
TEXT_SECONDARY = "#94A3B8"
TEXT_DIM = "#64748B"
BORDER_SUBTLE = "#334155"

#: La misma curva de realce que usan las figuras y el visor web, y por la
#: misma razon. Se aplica ANTES de encoger, nunca al reves: encoger primero
#: reparte un cordon de 1.7 px entre tres vecinos y lo borra.
GAMMA = 0.42

#: Arrastrar y hacer clic son dos cosas. Por debajo de este umbral, en
#: pixeles, el gesto fue un clic y selecciona; por encima giro la vista.
UMBRAL_ARRASTRE = 4

#: La vista no puede pasar por detras del par estereo, y esto es lo que lo
#: impide. El vector "derecha de la pantalla" del visor es
#: ``(f_y, -f_x, 0)`` normalizado, asi que su componente en X vale
#: ``sin(yaw)``: positiva entre 0 y 180 grados, negativa fuera. Con el yaw
#: fuera de ese rango el mundo se dibuja **espejado respecto de la foto**:
#: Cam_R sale a la izquierda, Cam_L a la derecha, y el sol de un azimut
#: dado aparece del lado contrario al que ilumina en la imagen. Se llega
#: ahi con dos arrastres y desde ahi el diagrama entero miente, asi que el
#: yaw se recorta y el usuario nunca cruza. Quedan 172 grados de giro libre
#: mas la inclinacion entera, de sobra para situar una direccion.
YAW_MIN, YAW_MAX = 4.0, 176.0

#: Cuanto tiene que separar la vista a las dos camaras, en fraccion de la
#: base, para que valga la pena decir cual es cual. Es ``sin(yaw)``, asi que
#: 0.5 son las vistas entre 30 y 150 grados de yaw. Fuera de ahi se dibuja
#: una sola caja ``L+R``.
SEPARACION_MINIMA = 0.5


# ─────────────────────────────────────────────────────── la escena medida

#: Geometria de la variante SOL, copiada de ``SIMULATION/build_tv2_studio.py``
#: y de la entrada ``"SOL"`` de ``render_studio_iterations.VARIANTES``. Esta
#: duplicada a proposito y en un solo lugar: el diagrama tiene que poder
#: dibujarse en la CM5, donde no hay Blender y por tanto no se puede importar
#: el modulo que construye la escena. Si cambia la variante, cambia esto.
ESCENA = dict(
    cord_y0=2.0, cord_y1=26.5, cord_x=0.0, cord_z=5.0,
    cam_y=2.0, baseline_mm=100.0, focal_mm=8.0,
    wave_x=(0.0, 0.35), wave_z=(-0.55, 0.30, 0.20),
)


def _suma_modos(t: float, amplitudes) -> float:
    """``sum(a_k sin(k pi t))``, igual que ``build_tv2_studio._mode_sum``."""
    return sum(a * math.sin((k + 1) * math.pi * t)
               for k, a in enumerate(amplitudes) if a)


def puntos_del_cable(segmentos: int = 80) -> List[Tuple[float, float, float]]:
    """El cordon tal como se renderizo, con origen en el par estereo.

    En coordenadas del diagrama: X a la derecha de la imagen, Y a lo largo
    del cable alejandose de las camaras, Z arriba. El origen es el punto
    medio de la base estereo, que es donde esta el extremo cercano del
    cable.
    """
    largo = ESCENA["cord_y1"] - ESCENA["cord_y0"]
    pts = []
    for i in range(segmentos):
        t = i / (segmentos - 1)
        pts.append((_suma_modos(t, ESCENA["wave_x"]),
                    t * largo,
                    _suma_modos(t, ESCENA["wave_z"])))
    return pts


def direccion_del_sol(azimut_deg: float, inclinacion_deg: float):
    """Hacia donde VIAJA la luz, con el convenio de ``build_sun``.

    ``(cos t sin o, -sin t, -cos t cos o)``. A 0 y 0 el haz baja desde
    arriba, perpendicular al cable; a 90 de azimut llega del lado -x; a 180
    de abajo. La inclinacion lo tumba a lo largo del propio cable:
    positiva, el sol esta del lado del extremo lejano.
    """
    o = math.radians(azimut_deg)
    t = math.radians(inclinacion_deg)
    return (math.cos(t) * math.sin(o), -math.sin(t), -math.cos(t) * math.cos(o))


# ───────────────────────────────────────────────────────── lectura de datos

class Direccion:
    """Una direccion del sol, con lo que se midio en ella."""

    __slots__ = ("azimut", "inclinacion", "carpeta", "contraste",
                 "contraste_lejos", "ciego_pct", "ciego_desde", "ciego_hasta")

    def __init__(self, fila: dict):
        self.azimut = float(fila["azimut_deg"])
        self.inclinacion = float(fila["inclinacion_deg"])
        self.carpeta = fila["carpeta"]
        self.contraste = float(fila["contraste"])
        self.contraste_lejos = float(fila["contraste_lejos"])
        self.ciego_pct = float(fila["ciego_pct"])
        self.ciego_desde = float(fila["ciego_desde_m"])
        self.ciego_hasta = float(fila["ciego_hasta_m"])

    @property
    def clave(self):
        return (self.azimut, self.inclinacion)


def leer_esfera() -> List[Direccion]:
    """Las direcciones medidas, de la CSV que escribe ``medir_esfera.py``."""
    ruta = os.path.join(ROOT, "SIMULATION", "experimentos", "sol_esfera",
                        "medidas.csv")
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as f:
        return [Direccion(fila) for fila in csv.DictReader(f)]


def leer_familia() -> List[dict]:
    """Las variantes del estudio, de ``medidas_familia.csv``."""
    ruta = os.path.join(ROOT, "SIMULATION", "experimentos",
                        "estudio_luminarias_reales", "medidas_familia.csv")
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Par:
    """De donde salen las dos imagenes de un caso, y si ya vienen realzadas.

    Hay dos sitios y el orden importa. ``data/captures`` tiene el render
    crudo a resolucion completa, que es lo mejor que se puede mirar, y
    **no esta versionado**: en un clon limpio, o en la Raspberry, no
    existe. Al lado de cada experimento hay una copia chica que si se
    versiona, la que escribe ``tools/armar_vistas_simulacion.py``.

    ``ya_realzada`` existe para no aplicar la gamma dos veces. La copia
    chica se graba ya realzada, porque es para mirar; el render crudo no.
    Realzar lo ya realzado da un cordon que parece el doble de brillante
    de lo que es, y eso en una pagina que existe para juzgar contraste no
    es un detalle cosmetico.
    """

    __slots__ = ("izquierda", "derecha", "ya_realzada")

    def __init__(self, izquierda, derecha, ya_realzada):
        self.izquierda = izquierda
        self.derecha = derecha
        self.ya_realzada = ya_realzada


def _si_esta(ruta):
    return ruta if ruta and os.path.exists(ruta) else None


def par_crudo(carpeta: str) -> Optional[Par]:
    base = os.path.join(ROOT, "data", "captures", carpeta)
    izq = _si_esta(os.path.join(base, "left.jpg"))
    if not izq:
        return None
    return Par(izq, _si_esta(os.path.join(base, "right.jpg")), False)


def par_esfera(d: "Direccion") -> Par:
    crudo = par_crudo(d.carpeta)
    if crudo:
        return crudo
    nombre = f"az{d.azimut:05.1f}_inc{d.inclinacion:+06.1f}.jpg"
    return Par(_si_esta(os.path.join(ROOT, "SIMULATION", "experimentos",
                                     "sol_esfera", "vistas", nombre)),
               None, True)


def par_estudio(variante: str, carpeta: str) -> Par:
    crudo = par_crudo(carpeta)
    if crudo:
        return crudo
    base = os.path.join(ROOT, "SIMULATION", "experimentos",
                        "estudio_luminarias_reales", "vistas")
    return Par(_si_esta(os.path.join(base, f"{variante}_left.jpg")),
               _si_esta(os.path.join(base, f"{variante}_right.jpg")), True)


def cargar(ruta: str, realzar: bool, ancho_max: int = 1400) -> Optional[QPixmap]:
    """Lee, realza con gamma y RECIEN DESPUES encoge. Ese orden importa."""
    import cv2
    img = cv2.imread(ruta, cv2.IMREAD_COLOR)
    if img is None:
        return None
    if realzar:
        tabla = np.clip(((np.arange(256) / 255.0) ** GAMMA) * 255.0,
                        0, 255).astype(np.uint8)
        img = cv2.LUT(img, tabla)
    if img.shape[1] > ancho_max:
        alto = int(round(img.shape[0] * ancho_max / img.shape[1]))
        img = cv2.resize(img, (ancho_max, alto), interpolation=cv2.INTER_AREA)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, _ = img.shape
    qim = QImage(img.data, w, h, 3 * w, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qim)


# ───────────────────────────────────────────────────────────── color escalas

def _mezcla(c1, c2, t):
    return QColor(int(c1[0] + (c2[0] - c1[0]) * t),
                  int(c1[1] + (c2[1] - c1[1]) * t),
                  int(c1[2] + (c2[2] - c1[2]) * t))


def color_metrica(valor: float, lo: float, hi: float, invertir: bool) -> QColor:
    """Azul frio para lo malo, ambar para lo bueno. Invertido si procede.

    Dos escalas y no una sola de arcoiris: el ojo ordena bien claro contra
    oscuro y mal rojo contra verde, y ademas una parte de los operadores no
    distingue esos dos.
    """
    if hi <= lo:
        t = 0.5
    else:
        t = (valor - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    if invertir:
        t = 1.0 - t
    return _mezcla((30, 58, 95), (251, 191, 36), t)


# ───────────────────────────────────────────────────────── el diagrama 3D

class VistaOrbital(QWidget):
    """La escena en 3D: cable, par estereo, ejes y la esfera de direcciones.

    Proyeccion en perspectiva debil, que es lo que hace un visor de CAD: con
    la camara lejos y el foco largo las paralelas siguen pareciendo
    paralelas y la figura no se deforma al girarla, que es justamente lo que
    marea en una perspectiva corta.
    """

    seleccionada = pyqtSignal(float, float)
    #: Se emite en cuanto el usuario gira a mano, para que el boton de la
    #: vista con nombre deje de decir que seguimos en ella.
    vista_libre = pyqtSignal()

    #: Las vistas con nombre, ``(yaw, pitch)`` en grados.
    #:
    #: Las cuatro estan elegidas con dos reglas, y las dos se escogieron
    #: despues de mirar las alternativas dibujadas. El cable se aleja hacia
    #: la **derecha** de la pantalla en las tres vistas donde se ve de
    #: lado, porque leerlo al reves obliga a invertir mentalmente cada
    #: medida que habla de "el extremo lejano". Y el ojo esta **encima** de
    #: la escena salvo cuando mira de frente: con ``pitch`` positivo el ojo
    #: queda debajo del cable y la planta sale vista desde el suelo, que es
    #: correcto y nadie lo espera.
    #:
    #: ``yaw`` 90 con ``pitch`` 0 es exactamente el encuadre de las
    #: camaras: la derecha de la pantalla es +X y arriba es +Z, los mismos
    #: dos ejes del render.
    VISTAS = {
        "3/4": (122.0, -24.0),
        "Desde las camaras": (90.0, 0.0),
        "Planta": (90.0, -86.0),
        "Costado": (176.0, 0.0),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

        self.direcciones: List[Direccion] = []
        self.metrica = "contraste"
        self.sel: Optional[Tuple[float, float]] = None
        self._hover: Optional[Tuple[float, float]] = None

        self.yaw, self.pitch = self.VISTAS["3/4"]
        self.zoom = 1.0
        self._arrastrando = False
        self._movido = False
        self._p0 = QPoint()
        self._proyectados: List[Tuple[float, float, float, Direccion]] = []

        largo = ESCENA["cord_y1"] - ESCENA["cord_y0"]
        self._centro = (0.0, largo / 2.0, 0.0)
        self._radio = largo * 0.62
        self._cable = puntos_del_cable()

    # ── datos ────────────────────────────────────────────────────────────

    def set_datos(self, direcciones, metrica, seleccion):
        self.direcciones = direcciones
        self.metrica = metrica
        self.sel = seleccion
        self.update()

    def vista(self, nombre):
        if nombre in self.VISTAS:
            self.yaw, self.pitch = self.VISTAS[nombre]
            self.zoom = 1.0
            self.update()

    # ── proyeccion ───────────────────────────────────────────────────────

    def _camara(self):
        y = math.radians(self.yaw)
        p = math.radians(max(-86.0, min(86.0, self.pitch)))
        f = (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p))
        rx, ry = f[1], -f[0]
        n = math.hypot(rx, ry) or 1.0
        r = (rx / n, ry / n, 0.0)
        u = (r[1] * f[2] - r[2] * f[1],
             r[2] * f[0] - r[0] * f[2],
             r[0] * f[1] - r[1] * f[0])
        dist = self._radio * 3.4
        ojo = tuple(self._centro[i] - f[i] * dist for i in range(3))
        foco = 1.25 * min(self.width(), self.height()) * self.zoom
        return f, r, u, ojo, foco

    def _proyectar(self, p, cam):
        f, r, u, ojo, foco = cam
        v = (p[0] - ojo[0], p[1] - ojo[1], p[2] - ojo[2])
        dz = v[0] * f[0] + v[1] * f[1] + v[2] * f[2]
        if dz < 0.2:
            return None
        k = foco / dz
        return (self.width() / 2.0 + k * (v[0] * r[0] + v[1] * r[1] + v[2] * r[2]),
                self.height() / 2.0 - k * (v[0] * u[0] + v[1] * u[1] + v[2] * u[2]),
                dz)

    def _linea(self, pintor, a, b, cam):
        pa, pb = self._proyectar(a, cam), self._proyectar(b, cam)
        if pa and pb:
            pintor.drawLine(int(pa[0]), int(pa[1]), int(pb[0]), int(pb[1]))

    # ── dibujo ───────────────────────────────────────────────────────────

    def paintEvent(self, _ev):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, True)
        pintor.fillRect(self.rect(), QColor("#0B1120"))
        cam = self._camara()

        self._esfera(pintor, cam)
        self._ejes(pintor, cam)
        self._cordon(pintor, cam)
        self._camaras(pintor, cam)
        self._marcadores(pintor, cam)
        self._rayo(pintor, cam)
        self._gizmo(pintor, cam)
        self._pie(pintor)
        pintor.end()

    def _esfera(self, pintor, cam):
        """Paralelos y meridianos. Los de atras, mas tenues."""
        f, _, _, ojo, _ = cam
        cx, cy, cz = self._centro
        dc = sum((self._centro[i] - ojo[i]) * f[i] for i in range(3))

        def pto(az, inc):
            d = direccion_del_sol(az, inc)
            return (cx - self._radio * d[0], cy - self._radio * d[1],
                    cz - self._radio * d[2])

        def traza(puntos):
            for a, b in zip(puntos, puntos[1:]):
                pa, pb = self._proyectar(a, cam), self._proyectar(b, cam)
                if not (pa and pb):
                    continue
                atras = (pa[2] + pb[2]) / 2.0 > dc
                pintor.setPen(QPen(QColor(51, 65, 85, 70 if atras else 150),
                                   1.0))
                pintor.drawLine(int(pa[0]), int(pa[1]), int(pb[0]), int(pb[1]))

        for inc in (-60.0, -30.0, 0.0, 30.0, 60.0):
            traza([pto(a, inc) for a in range(0, 361, 6)])
        for az in (0.0, 45.0, 90.0, 135.0):
            traza([pto(az, t) for t in range(-90, 91, 4)]
                  + [pto(az + 180.0, t) for t in range(90, -91, -4)])

    #: Los tres ejes del mundo, con lo que significan **en la imagen**. Es la
    #: unica traduccion que hace falta para leer un render: +Z sale arriba,
    #: +X a la derecha, +Y se aleja por el cable.
    EJES = (((1.0, 0.0, 0.0), "+X  derecha", "#F87171"),
            ((0.0, 1.0, 0.0), "+Y  cable", "#4ADE80"),
            ((0.0, 0.0, 1.0), "+Z  arriba", "#60A5FA"))

    def _ejes(self, pintor, cam):
        """Una triada corta en el origen, sin rotulos.

        Los rotulos van en el gizmo de la esquina y no aqui. Estuvieron
        aqui primero y se pisaban entre ellos y con las camaras, que estan
        en el mismo punto: tres textos de 20 caracteres saliendo del mismo
        pixel no se leen en ninguna orientacion de la vista.
        """
        largo = self._radio * 0.22
        o = self._proyectar((0, 0, 0), cam)
        if not o:
            return
        for u, _rotulo, color in self.EJES:
            q = self._proyectar(tuple(c * largo for c in u), cam)
            if not q:
                continue
            pintor.setPen(QPen(QColor(color), 1.5))
            pintor.drawLine(int(o[0]), int(o[1]), int(q[0]), int(q[1]))

    def _gizmo(self, pintor, cam):
        """La brujula del visor, en la esquina y a tamano fijo.

        Gira con la vista pero no se aleja ni se encoge con el zoom, que es
        lo que hace util a la de un CAD: siempre esta, siempre se lee, y
        contesta de un vistazo la pregunta por la que esta pagina existe,
        cual lado de la imagen es arriba.
        """
        f, r, u, _ojo, _foco = cam
        cx, cy, largo = self.width() - 44, self.height() - 46, 17.0
        fuente = QFont()
        fuente.setPointSize(7)
        pintor.setFont(fuente)
        pintor.setPen(QPen(QColor(51, 65, 85, 140), 1.0))
        pintor.setBrush(QBrush(QColor(11, 17, 32, 225)))
        pintor.drawEllipse(QRectF(cx - 28, cy - 28, 56, 56))
        pintor.setBrush(Qt.NoBrush)
        for v, rotulo, color in self.EJES:
            sx = largo * (v[0] * r[0] + v[1] * r[1] + v[2] * r[2])
            sy = -largo * (v[0] * u[0] + v[1] * u[1] + v[2] * u[2])
            delante = (v[0] * f[0] + v[1] * f[1] + v[2] * f[2]) < 0.0
            c = QColor(color)
            c.setAlpha(255 if delante else 110)
            pintor.setPen(QPen(c, 1.6))
            pintor.drawLine(int(cx), int(cy), int(cx + sx), int(cy + sy))
            tx = min(int(cx + sx * 1.45) - 14, self.width() - 62)
            pintor.drawText(tx, int(cy + sy * 1.5) + 3, rotulo)

    def _cordon(self, pintor, cam):
        """El cable con la forma que tiene en el render, no una recta."""
        camino = QPainterPath()
        primero = True
        for p in self._cable:
            q = self._proyectar(p, cam)
            if not q:
                continue
            if primero:
                camino.moveTo(q[0], q[1])
                primero = False
            else:
                camino.lineTo(q[0], q[1])
        pintor.setPen(QPen(QColor("#E2E8F0"), 2.2))
        pintor.drawPath(camino)
        lejos = self._proyectar(self._cable[-1], cam)
        if lejos:
            fuente = QFont()
            fuente.setPointSize(7)
            pintor.setFont(fuente)
            pintor.setPen(QPen(QColor(TEXT_SECONDARY)))
            largo = ESCENA["cord_y1"] - ESCENA["cord_y0"]
            texto = f"extremo lejano, {largo:.1f} m"
            x = min(int(lejos[0]) + 5, self.width() - 7 * len(texto) - 4)
            pintor.drawText(x, int(lejos[1]), texto)

    def _camaras(self, pintor, cam):
        """El par estereo, con la base exagerada para que se vea.

        La base real son 100 mm sobre un cable de 24.5 m: a escala es medio
        pixel. Se dibuja 60 veces mas grande y el rotulo lo dice, porque la
        pregunta que la figura tiene que contestar es cual camara esta a
        que lado, no cuanto miden.

        Las dos cajas miran siempre al ojo: se arman con los vectores de
        pantalla de la camara del visor y no con los ejes del mundo. Hechas
        en el plano x-z salian de canto en la planta, como dos rayas, y la
        letra encima no se leia.
        """
        f, r, u = cam[0], cam[1], cam[2]
        escala = 60.0
        media = (ESCENA["baseline_mm"] / 1000.0) / 2.0 * escala
        cuerpo = 1.30

        # La base estereo corre a lo largo de X, asi que lo que separa a las
        # dos camaras en pantalla es ``r[0]``, que vale exactamente
        # ``sin(yaw)``. Por debajo de SEPARACION_MINIMA las dos cajas caen a
        # pocos pixeles una de otra y cual sale a la izquierda ya no lo
        # decide la geometria estereo sino la perspectiva, porque la mas
        # cercana al ojo se proyecta un poco mas afuera. Dibujar una L y una
        # R ahi es afirmar un orden que no existe, y es lo que hace pensar
        # que las etiquetas estan cambiadas. Cuando no se puede afirmar, se
        # dibuja una sola caja.
        #
        # El criterio anterior miraba ``f[0]``, que mezcla la inclinacion:
        # con la vista bajada 35 grados y el cable casi de perfil no
        # saltaba, y ahi es justamente donde el orden no significa nada.
        if abs(r[0]) < SEPARACION_MINIMA:
            caras = ((0.0, "L+R"),)
        else:
            caras = ((-1.0, "L"), (+1.0, "R"))
        for signo, nombre in caras:
            centro = (signo * media, -cuerpo, 0.0)
            h = cuerpo / 2
            caja = [tuple(centro[k] + a * h * r[k] + b * h * u[k]
                          for k in range(3))
                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            poli = QPolygonF()
            ok = True
            for v in caja:
                q = self._proyectar(v, cam)
                if not q:
                    ok = False
                    break
                poli.append(QPoint(int(q[0]), int(q[1])))
            if not ok:
                continue
            pintor.setPen(QPen(QColor(ACCENT_CYAN), 1.4))
            pintor.setBrush(QBrush(QColor(34, 211, 238, 55)))
            pintor.drawPolygon(poli)
            pintor.setBrush(Qt.NoBrush)
            c = self._proyectar(centro, cam)
            if c:
                fuente = QFont()
                fuente.setPointSize(7)
                fuente.setBold(True)
                pintor.setFont(fuente)
                pintor.setPen(QPen(QColor(ACCENT_CYAN)))
                pintor.drawText(int(c[0]) - 4 * len(nombre), int(c[1]) + 3,
                                nombre)

        # El cuadro de la imagen, un metro delante del par. Es la pieza que
        # ata el diagrama al render: lo que cae dentro de este rectangulo
        # es lo que sale en la foto, y su borde de arriba es el de arriba.
        d = 6.0
        ancho = d * (6.287 / 2.0) / ESCENA["focal_mm"]
        alto = d * (4.712 / 2.0) / ESCENA["focal_mm"]
        marco = [(-ancho, d, -alto), (ancho, d, -alto),
                 (ancho, d, alto), (-ancho, d, alto)]
        poli = QPolygonF()
        for v in marco:
            q = self._proyectar(v, cam)
            if not q:
                return
            poli.append(QPoint(int(q[0]), int(q[1])))
        pintor.setPen(QPen(QColor(100, 116, 139, 190), 1.0, Qt.DashLine))
        pintor.drawPolygon(poli)
        arriba = self._proyectar((0, d, alto), cam)
        if arriba:
            fuente = QFont()
            fuente.setPointSize(7)
            pintor.setFont(fuente)
            pintor.setPen(QPen(QColor(TEXT_DIM)))
            pintor.drawText(int(arriba[0]) - 46, int(arriba[1]) - 4,
                            "arriba del cuadro")

    def _marcadores(self, pintor, cam):
        """Las direcciones medidas. De atras hacia adelante."""
        if not self.direcciones:
            return
        vals = [self._valor(d) for d in self.direcciones]
        lo, hi = min(vals), max(vals)
        invertir = self.metrica == "ciego_pct"
        cx, cy, cz = self._centro

        self._proyectados = []
        for d in self.direcciones:
            u = direccion_del_sol(d.azimut, d.inclinacion)
            p = (cx - self._radio * u[0], cy - self._radio * u[1],
                 cz - self._radio * u[2])
            q = self._proyectar(p, cam)
            if q:
                self._proyectados.append((q[0], q[1], q[2], d))
        self._proyectados.sort(key=lambda t: -t[2])

        for sx, sy, _dz, d in self._proyectados:
            es_sel = self.sel == d.clave
            es_hover = self._hover == d.clave
            r = 7.0 if es_sel else (5.5 if es_hover else 4.0)
            pintor.setBrush(QBrush(color_metrica(
                self._valor(d), lo, hi, invertir)))
            pintor.setPen(QPen(QColor("#F8FAFC" if es_sel else "#0B1120"),
                               2.0 if es_sel else 1.0))
            pintor.drawEllipse(QRectF(sx - r, sy - r, 2 * r, 2 * r))

    def _rayo(self, pintor, cam):
        """La flecha del sol elegido hasta el centro del cable."""
        if not self.sel:
            return
        u = direccion_del_sol(*self.sel)
        cx, cy, cz = self._centro
        origen = (cx - self._radio * 1.18 * u[0],
                  cy - self._radio * 1.18 * u[1],
                  cz - self._radio * 1.18 * u[2])
        a = self._proyectar(origen, cam)
        b = self._proyectar(self._centro, cam)
        if not (a and b):
            return
        pintor.setPen(QPen(QColor(245, 158, 11, 210), 1.6, Qt.DashLine))
        pintor.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
        pintor.setPen(QPen(QColor(ACCENT_AMBER), 1.4))
        pintor.setBrush(QBrush(QColor(251, 191, 36)))
        pintor.drawEllipse(QRectF(a[0] - 7, a[1] - 7, 14, 14))
        pintor.setBrush(Qt.NoBrush)
        fuente = QFont()
        fuente.setPointSize(7)
        fuente.setBold(True)
        pintor.setFont(fuente)
        pintor.setPen(QPen(QColor(ACCENT_AMBER)))
        pintor.drawText(int(a[0]) + 10, int(a[1]) + 3, "sol")

    def _pie(self, pintor):
        fuente = QFont()
        fuente.setPointSize(7)
        pintor.setFont(fuente)
        pintor.setPen(QPen(QColor(TEXT_DIM)))
        pintor.drawText(
            8, self.height() - 20,
            "Arrastra para girar LA VISTA. El sol se elige con un clic en un "
            "punto o con la rejilla.")
        pintor.drawText(
            8, self.height() - 8,
            "La vista no cruza por detras del par: la L siempre a la "
            "izquierda.")

    def _valor(self, d: Direccion) -> float:
        return getattr(d, self.metrica)

    # ── interaccion ──────────────────────────────────────────────────────

    def _cercano(self, pos) -> Optional[Direccion]:
        mejor, mejor_d2 = None, 15.0 ** 2
        for sx, sy, _dz, d in reversed(self._proyectados):
            d2 = (sx - pos.x()) ** 2 + (sy - pos.y()) ** 2
            if d2 < mejor_d2:
                mejor, mejor_d2 = d, d2
        return mejor

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._arrastrando = True
            self._movido = False
            self._p0 = ev.pos()

    def mouseMoveEvent(self, ev):
        if not self._arrastrando:
            prev = self._hover
            cerca = self._cercano(ev.pos())
            self._hover = cerca.clave if cerca else None
            if cerca:
                self.setToolTip(
                    f"azimut {cerca.azimut:.1f}, inclinacion "
                    f"{cerca.inclinacion:+.1f}\ncontraste {cerca.contraste:.1f}"
                    f"   ciego {cerca.ciego_pct:.1f} %")
            else:
                self.setToolTip("")
            if prev != self._hover:
                self.update()
            return
        if not self._movido:
            if (abs(ev.x() - self._p0.x()) + abs(ev.y() - self._p0.y())
                    < UMBRAL_ARRASTRE):
                return
            self._movido = True
            self.setCursor(Qt.ClosedHandCursor)
            self.vista_libre.emit()
        self.yaw = max(YAW_MIN, min(YAW_MAX,
                                   self.yaw + (ev.x() - self._p0.x()) * 0.45))
        self.pitch = max(-86.0, min(86.0,
                                    self.pitch + (ev.y() - self._p0.y()) * 0.35))
        self._p0 = ev.pos()
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        self.setCursor(Qt.OpenHandCursor)
        if self._arrastrando and not self._movido:
            cerca = self._cercano(ev.pos())
            if cerca:
                self.seleccionada.emit(cerca.azimut, cerca.inclinacion)
        self._arrastrando = False
        self._movido = False

    def wheelEvent(self, ev):
        self.zoom *= 1.0015 ** ev.angleDelta().y()
        self.zoom = max(0.45, min(3.0, self.zoom))
        self.update()


# ───────────────────────────────────────────────────────────── la rejilla

class RejillaEsfera(QWidget):
    """Azimut por inclinacion, como mapa de calor y como selector.

    El diagrama sirve para entender donde esta el sol; para elegir una
    direccion exacta sirve mal, porque un punto de 4 px sobre una esfera que
    gira no es un boton. Esta rejilla es el boton: cada celda es una
    direccion, el color es la misma metrica y las flechas del teclado se
    mueven por ella.
    """

    seleccionada = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.direcciones: List[Direccion] = []
        self.metrica = "contraste"
        self.sel: Optional[Tuple[float, float]] = None
        self._azimutes: List[float] = []
        self._inclinaciones: List[float] = []
        self._mapa: Dict[Tuple[float, float], Direccion] = {}

    def set_datos(self, direcciones, metrica, seleccion):
        self.direcciones = direcciones
        self.metrica = metrica
        self.sel = seleccion
        self._azimutes = sorted({d.azimut for d in direcciones})
        self._inclinaciones = sorted({d.inclinacion for d in direcciones},
                                     reverse=True)
        self._mapa = {d.clave: d for d in direcciones}
        self.update()

    def _celdas(self):
        if not self._azimutes or not self._inclinaciones:
            return None
        izq, arriba, abajo = 46, 16, 20
        w = (self.width() - izq - 8) / len(self._azimutes)
        h = (self.height() - arriba - abajo) / len(self._inclinaciones)
        return izq, arriba, w, h

    def paintEvent(self, _ev):
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, False)
        pintor.fillRect(self.rect(), QColor(BG_PANEL))
        geo = self._celdas()
        if not geo:
            return
        izq, arriba, w, h = geo
        vals = [getattr(d, self.metrica) for d in self.direcciones]
        lo, hi = min(vals), max(vals)
        invertir = self.metrica == "ciego_pct"
        fuente = QFont()
        fuente.setPointSize(7)
        pintor.setFont(fuente)

        for fila, inc in enumerate(self._inclinaciones):
            y = arriba + fila * h
            pintor.setPen(QPen(QColor(TEXT_SECONDARY)))
            pintor.drawText(2, int(y + h / 2 + 3), f"{inc:+.0f}")
            for col, az in enumerate(self._azimutes):
                d = self._mapa.get((az, inc))
                x = izq + col * w
                celda = QRectF(x, y, w - 1, h - 1)
                if d is None:
                    pintor.fillRect(celda, QColor(15, 23, 42))
                    continue
                pintor.fillRect(celda, color_metrica(
                    getattr(d, self.metrica), lo, hi, invertir))
                if self.sel == d.clave:
                    pintor.setPen(QPen(QColor("#F8FAFC"), 2.0))
                    pintor.drawRect(celda)

        pintor.setPen(QPen(QColor(TEXT_SECONDARY)))
        for col, az in enumerate(self._azimutes):
            if az % 45.0 == 0.0:
                pintor.drawText(int(izq + col * w), self.height() - 6,
                                f"{az:.0f}")
        pintor.setPen(QPen(QColor(TEXT_DIM)))
        pintor.drawText(2, 10, "inclinacion / azimut, grados")
        pintor.end()

    def mousePressEvent(self, ev):
        geo = self._celdas()
        if not geo:
            return
        izq, arriba, w, h = geo
        col = int((ev.x() - izq) // w)
        fila = int((ev.y() - arriba) // h)
        if 0 <= col < len(self._azimutes) and 0 <= fila < len(self._inclinaciones):
            clave = (self._azimutes[col], self._inclinaciones[fila])
            if clave in self._mapa:
                self.setFocus()
                self.seleccionada.emit(*clave)

    def keyPressEvent(self, ev):
        if not self.sel or not self._azimutes:
            return super().keyPressEvent(ev)
        az, inc = self.sel
        try:
            col = self._azimutes.index(az)
            fila = self._inclinaciones.index(inc)
        except ValueError:
            return super().keyPressEvent(ev)
        if ev.key() == Qt.Key_Left:
            col = (col - 1) % len(self._azimutes)
        elif ev.key() == Qt.Key_Right:
            col = (col + 1) % len(self._azimutes)
        elif ev.key() == Qt.Key_Up:
            fila = max(0, fila - 1)
        elif ev.key() == Qt.Key_Down:
            fila = min(len(self._inclinaciones) - 1, fila + 1)
        else:
            return super().keyPressEvent(ev)
        clave = (self._azimutes[col], self._inclinaciones[fila])
        if clave in self._mapa:
            self.seleccionada.emit(*clave)


class Leyenda(QWidget):
    """La barra de color con sus dos extremos rotulados.

    Sin ella el mapa de calor es decorativo: un ambar mas claro que otro no
    dice nada hasta que se sabe entre que dos numeros va la escala, y esos
    dos numeros cambian con la metrica elegida.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self._lo, self._hi, self._unidad = 0.0, 1.0, ""
        self._invertir = False

    def set_rango(self, lo, hi, unidad, invertir):
        self._lo, self._hi, self._unidad = lo, hi, unidad
        self._invertir = invertir
        self.update()

    def paintEvent(self, _ev):
        pintor = QPainter(self)
        barra = QRectF(0, 0, self.width(), 10)
        for i in range(int(barra.width())):
            t = i / max(1.0, barra.width() - 1)
            pintor.setPen(QPen(color_metrica(
                self._lo + t * (self._hi - self._lo),
                self._lo, self._hi, self._invertir), 1))
            pintor.drawLine(i, 0, i, 9)
        fuente = QFont()
        fuente.setPointSize(7)
        pintor.setFont(fuente)
        pintor.setPen(QPen(QColor(TEXT_SECONDARY)))
        pintor.drawText(0, 23, f"{self._lo:.1f} {self._unidad}")
        texto = f"{self._hi:.1f} {self._unidad}"
        pintor.drawText(self.width() - 7 * len(texto) - 2, 23, texto)
        pintor.end()


# ──────────────────────────────────────────────────────── panel de imagen

class PanelRender(QWidget):
    """Una o dos imagenes, escaladas a la caja, con su pie.

    Dos y no una cuando el render tiene las dos camaras: la izquierda y la
    derecha lado a lado son la unica forma de ver que la base estereo cruza
    el cable en vez de correr a lo largo de el. **La mayoria de las
    direcciones de la esfera se renderizaron solo con la izquierda**, para
    que el barrido de 82 cupiera en una noche, asi que el panel dice cual
    es el caso en vez de dejar un hueco.
    """

    #: Que camara es cada panel. **El panel de la izquierda es SIEMPRE
    #: ``left.jpg``**, que es Cam_L, la que esta en x = -50 mm. No depende de
    #: como este girado el diagrama, y hace falta decirlo porque el diagrama
    #: se puede girar hasta poner la R a la izquierda.
    ROTULOS = ("Izquierda   ·   Cam_L, x = -50 mm",
               "Derecha   ·   Cam_R, x = +50 mm")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.lbl_izq = QLabel()
        self.lbl_der = QLabel()
        self.cab_izq = QLabel(self.ROTULOS[0])
        self.cab_der = QLabel(self.ROTULOS[1])
        self.col_izq = QWidget()
        self.col_der = QWidget()
        for col, cab, lbl in ((self.col_izq, self.cab_izq, self.lbl_izq),
                              (self.col_der, self.cab_der, self.lbl_der)):
            cab.setAlignment(Qt.AlignCenter)
            cab.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
                f"letter-spacing: 0.4px; background-color: {BG_PANEL};"
                f"border: 1px solid {BORDER_SUBTLE}; padding: 3px;")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"background-color: #000; border: 1px solid "
                              f"{BORDER_SUBTLE};")
            # Sin esto el QLabel pide del layout el tamano de su pixmap, el
            # primero en recibir imagen se queda con el ancho y el otro sale
            # como una tira. El pixmap no debe mandar en el reparto.
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            lbl.setMinimumSize(1, 1)
            cv = QVBoxLayout(col)
            cv.setContentsMargins(0, 0, 0, 0)
            cv.setSpacing(3)
            cv.addWidget(cab)
            cv.addWidget(lbl, 1)
            fila.addWidget(col, 1)
        v.addLayout(fila, 1)
        self.pie = QLabel()
        self.pie.setWordWrap(True)
        self.pie.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
        v.addWidget(self.pie)
        self._pix = (None, None)
        self._cache: Dict[tuple, QPixmap] = {}

    def _leer(self, ruta, realzar):
        clave = (ruta, realzar)
        if clave not in self._cache:
            if len(self._cache) > 12:
                self._cache.clear()
            self._cache[clave] = cargar(ruta, realzar)
        return self._cache[clave]

    def mostrar(self, par: Par, pie_extra: str = ""):
        realzar = not par.ya_realzada
        self._pix = (self._leer(par.izquierda, realzar) if par.izquierda
                     else None,
                     self._leer(par.derecha, realzar) if par.derecha else None)
        fuente = ("copia chica versionada" if par.ya_realzada
                  else "render crudo de data/captures")
        if par.derecha:
            nota = f"Camara izquierda y derecha, {fuente}, gamma 0.42."
        elif par.izquierda:
            nota = (f"Solo camara izquierda: este caso se renderizo con una "
                    f"sola camara. {fuente.capitalize()}, gamma 0.42.")
        else:
            nota = ("No hay imagen de este caso, ni el render crudo ni la "
                    "copia chica. Vuelve a generarla con: python "
                    "tools/armar_vistas_simulacion.py")
        self.pie.setText(nota + ("  " + pie_extra if pie_extra else ""))
        self.col_der.setVisible(bool(par.derecha))
        self._reescalar()

    def _reescalar(self):
        for lbl, pix in ((self.lbl_izq, self._pix[0]),
                         (self.lbl_der, self._pix[1])):
            if pix is None:
                lbl.setText("sin imagen")
                lbl.setStyleSheet(
                    f"background-color: #000; border: 1px solid "
                    f"{BORDER_SUBTLE}; color: {TEXT_DIM}; font-size: 11px;")
                lbl.setPixmap(QPixmap())
                continue
            lbl.setText("")
            lbl.setPixmap(pix.scaled(max(1, lbl.width() - 2),
                                     max(1, lbl.height() - 2),
                                     Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._reescalar()


def _cifra(texto: str, decimales: int = 1) -> str:
    """El numero, o ``---`` si no lo hay.

    ``medidas_familia.csv`` trae un ``nan`` legitimo: en la vista de
    costado el cordon no tiene fondo oscuro detras, porque lo que hay
    detras es la pared del cuarto, asi que el contraste sobre fondo oscuro
    no esta definido. Imprimir ``nan`` hace pensar en un error de calculo.
    """
    try:
        v = float(texto)
    except (TypeError, ValueError):
        return "---"
    return "---" if v != v else f"{v:.{decimales}f}"


def _tarjeta(titulo: str) -> Tuple[QFrame, QLabel]:
    """Una cifra grande con su rotulo. Devuelve el marco y el QLabel del dato."""
    marco = QFrame()
    marco.setStyleSheet(
        f"QFrame {{ background-color: {BG_CARD}; border: 1px solid "
        f"{BORDER_SUBTLE}; border-radius: 6px; }}")
    v = QVBoxLayout(marco)
    v.setContentsMargins(10, 7, 10, 7)
    v.setSpacing(1)
    valor = QLabel("--")
    valor.setStyleSheet(
        f"color: {TEXT_PRIMARY}; font-size: 19px; font-weight: bold;"
        f"background: transparent; border: none;")
    rotulo = QLabel(titulo)
    rotulo.setStyleSheet(
        f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 0.5px;"
        f"background: transparent; border: none;")
    v.addWidget(valor)
    v.addWidget(rotulo)
    return marco, valor


# ───────────────────────────────────────────────────── pestana de la esfera

class PaginaEsfera(QWidget):
    """Las 82 direcciones del sol: el diagrama, la rejilla y el render."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        self.direcciones = leer_esfera()
        self.metrica = "contraste"
        self.sel: Optional[Tuple[float, float]] = None

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(12)

        izquierda = QWidget()
        izquierda.setMaximumWidth(430)
        col = QVBoxLayout(izquierda)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        self.vista = VistaOrbital()
        self.vista.seleccionada.connect(self.seleccionar)
        self.vista.vista_libre.connect(self._vista_libre)
        col.addWidget(self.vista, 3)

        botones = QHBoxLayout()
        botones.setSpacing(4)
        self._grupo = QButtonGroup(self)
        for i, nombre in enumerate(VistaOrbital.VISTAS):
            b = QPushButton(nombre)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setStyleSheet(self._qss_boton())
            b.clicked.connect(lambda _c, n=nombre: self.vista.vista(n))
            self._grupo.addButton(b)
            botones.addWidget(b)
        col.addLayout(botones)

        sel_fila = QHBoxLayout()
        lbl = QLabel("Colorear por")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        self.combo = QComboBox()
        self.combo.addItem("Contraste del cordon", "contraste")
        self.combo.addItem("Cable ciego (%)", "ciego_pct")
        self.combo.addItem("Contraste mas alla de 18 m", "contraste_lejos")
        self.combo.setStyleSheet(
            f"QComboBox {{ background-color: {BG_CARD}; color: {TEXT_PRIMARY};"
            f"border: 1px solid {BORDER_SUBTLE}; border-radius: 4px;"
            f"padding: 4px 8px; font-size: 12px; }}")
        self.combo.currentIndexChanged.connect(self._cambio_metrica)
        sel_fila.addWidget(lbl)
        sel_fila.addWidget(self.combo, 1)
        col.addLayout(sel_fila)

        self.leyenda = Leyenda()
        col.addWidget(self.leyenda)

        self.rejilla = RejillaEsfera()
        self.rejilla.seleccionada.connect(self.seleccionar)
        col.addWidget(self.rejilla, 2)

        self.nota = QLabel(
            "82 direcciones renderizadas de las 112 de la rejilla completa. "
            "El contraste se promedia desde 5 m; cable ciego es la fraccion "
            "bajo 5 niveles sobre el fondo local, que es donde la mascara ya "
            "no tiene nada que segmentar. Medidas de "
            "SIMULATION/experimentos/sol_esfera/medidas.csv.")
        self.nota.setWordWrap(True)
        self.nota.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")
        col.addWidget(self.nota)
        raiz.addWidget(izquierda, 0)

        derecha = QWidget()
        dv = QVBoxLayout(derecha)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(8)
        self.titulo = QLabel("Elige una direccion")
        self.titulo.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-size: 16px; font-weight: bold;")
        dv.addWidget(self.titulo)

        tarjetas = QHBoxLayout()
        tarjetas.setSpacing(8)
        self._valores = {}
        for clave, rotulo in (("contraste", "CONTRASTE"),
                              ("ciego_pct", "CABLE CIEGO"),
                              ("contraste_lejos", "MAS DE 18 M"),
                              ("tramo", "TRAMO CIEGO")):
            marco, valor = _tarjeta(rotulo)
            self._valores[clave] = valor
            tarjetas.addWidget(marco)
        dv.addLayout(tarjetas)

        self.panel = PanelRender()
        dv.addWidget(self.panel, 1)

        # La pregunta que esta pantalla provoca la primera vez que se mira, y
        # que no se contesta sola. Va escrita y no en un tooltip.
        self.aviso = QLabel(
            "Por que las dos no se parecen cerca del borde, y por que eso no "
            "es el sol: el cable arranca EN el punto medio de la base "
            "estereo, y su primer metro pasa a 11 cm de cada lente, donde un "
            "cordon de 1 mm mide 50 px y satura. A 11 cm, 10 cm de base son "
            "media paralaje, asi que cada camara ve ese tramo en otro sitio "
            "del cuadro. Del centro hacia afuera, que es el cable a mas de "
            "5 m, las dos coinciden: 70.5 contra 80.9 niveles de media en el "
            "recorte central de 600 px. El contraste se promedia desde 5 m, "
            "asi que ninguna cifra de arriba usa ese primer metro.")
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; background: transparent;"
            f"border-top: 1px solid {BORDER_SUBTLE}; padding-top: 5px;")
        dv.addWidget(self.aviso)
        raiz.addWidget(derecha, 1)

        if self.direcciones:
            inicial = min(self.direcciones,
                          key=lambda d: (abs(d.inclinacion), abs(d.azimut)))
            self.seleccionar(inicial.azimut, inicial.inclinacion)
        else:
            self.titulo.setText("No hay medidas de la esfera")
            self.nota.setText(
                "Falta SIMULATION/experimentos/sol_esfera/medidas.csv. Se "
                "genera con: python tools/medir_esfera.py --csv "
                "SIMULATION/experimentos/sol_esfera/medidas.csv")

    def _vista_libre(self):
        """Girar a mano apaga el boton de la vista con nombre.

        No es cosmetico. Un boton que sigue diciendo "3/4" sobre una vista
        que ya no lo es hace que la L y la R del diagrama parezcan
        intercambiadas respecto de los dos paneles, y eso manda a buscar un
        error en el nombre de los archivos que no existe.
        """
        if self._grupo.checkedButton() is None:
            return
        self._grupo.setExclusive(False)
        for b in self._grupo.buttons():
            b.setChecked(False)
        self._grupo.setExclusive(True)

    @staticmethod
    def _qss_boton():
        return (f"QPushButton {{ background-color: {BG_CARD};"
                f"color: {TEXT_SECONDARY}; border: 1px solid {BORDER_SUBTLE};"
                f"border-radius: 4px; padding: 4px 6px; font-size: 11px; }}"
                f"QPushButton:checked {{ border-color: {ACCENT_CYAN};"
                f"color: {ACCENT_CYAN}; }}")

    def _cambio_metrica(self, _i):
        self.metrica = self.combo.currentData()
        self._refrescar()

    def seleccionar(self, azimut: float, inclinacion: float):
        self.sel = (azimut, inclinacion)
        self._refrescar()
        d = next((x for x in self.direcciones if x.clave == self.sel), None)
        if d is None:
            return
        self.titulo.setText(
            f"Azimut {d.azimut:.1f}, inclinacion {d.inclinacion:+.1f} grados")
        self._valores["contraste"].setText(f"{d.contraste:.1f}")
        self._valores["ciego_pct"].setText(f"{d.ciego_pct:.1f} %")
        self._valores["contraste_lejos"].setText(f"{d.contraste_lejos:.1f}")
        if d.ciego_pct > 0.0:
            self._valores["tramo"].setText(
                f"{d.ciego_desde:.1f} a {d.ciego_hasta:.1f} m")
        else:
            self._valores["tramo"].setText("---")
        self.panel.mostrar(par_esfera(d), f"Captura {d.carpeta}.")

    #: Como se rotula cada metrica en la leyenda, y si mas es peor.
    UNIDAD = {"contraste": ("niveles", False),
              "ciego_pct": ("% ciego", True),
              "contraste_lejos": ("niveles", False)}

    def _refrescar(self):
        self.vista.set_datos(self.direcciones, self.metrica, self.sel)
        self.rejilla.set_datos(self.direcciones, self.metrica, self.sel)
        if self.direcciones:
            vals = [getattr(d, self.metrica) for d in self.direcciones]
            unidad, invertir = self.UNIDAD[self.metrica]
            self.leyenda.set_rango(min(vals), max(vals), unidad, invertir)


# ──────────────────────────────────────────────────── pestana del estudio

class PaginaEstudio(QWidget):
    """La familia de variantes del TV2, con su render y sus cifras."""

    COLUMNAS = (("variante", "Variante"), ("luminarias", "Luminarias"),
                ("kw", "kW"), ("contraste_fondo_oscuro", "Contraste"),
                ("fondo_medio", "Fondo medio"), ("piso", "Piso"),
                ("inclinacion_deg", "Inclinacion"), ("sensor", "Sensor"),
                ("focal_mm", "Focal mm"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        self.filas = leer_familia()
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(12, 12, 12, 12)
        raiz.setSpacing(12)

        izq = QWidget()
        izq.setMaximumWidth(430)
        col = QVBoxLayout(izq)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        tit = QLabel("Las variantes renderizadas")
        tit.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-size: 14px; font-weight: bold;")
        col.addWidget(tit)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setStyleSheet(f"background-color: {BG_DEEP}; border: none;")
        interior = QWidget()
        lista = QVBoxLayout(interior)
        lista.setContentsMargins(0, 0, 0, 0)
        lista.setSpacing(4)
        self._botones = []
        for fila in self.filas:
            b = QPushButton(f"{fila['variante']}   ·   contraste "
                            f"{_cifra(fila['contraste_fondo_oscuro'])}")
            b.setCheckable(True)
            b.setStyleSheet(PaginaEsfera._qss_boton())
            b.clicked.connect(lambda _c, f=fila: self.elegir(f))
            lista.addWidget(b)
            self._botones.append((b, fila))
        lista.addStretch()
        area.setWidget(interior)
        col.addWidget(area, 1)

        self.nota = QLabel(
            "Medidas de SIMULATION/experimentos/estudio_luminarias_reales/"
            "medidas_familia.csv, la misma tabla que el capitulo 5 del "
            "informe de la sesion. Contraste sobre fondo oscuro, en niveles "
            "de 8 bits.")
        self.nota.setWordWrap(True)
        self.nota.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")
        col.addWidget(self.nota)
        raiz.addWidget(izq, 0)

        der = QWidget()
        dv = QVBoxLayout(der)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(8)
        self.titulo = QLabel("Elige una variante")
        self.titulo.setStyleSheet(
            f"color: {ACCENT_CYAN}; font-size: 16px; font-weight: bold;")
        dv.addWidget(self.titulo)
        self.detalle = QLabel()
        self.detalle.setWordWrap(True)
        self.detalle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;")
        dv.addWidget(self.detalle)
        self.panel = PanelRender()
        dv.addWidget(self.panel, 1)
        raiz.addWidget(der, 1)

        if self.filas:
            self._botones[0][0].setChecked(True)
            self.elegir(self.filas[0])
        else:
            self.titulo.setText("No hay medidas del estudio")

    def elegir(self, fila):
        for b, f in self._botones:
            b.setChecked(f is fila)
        self.titulo.setText(fila["variante"])
        partes = [f"{rotulo}: {fila.get(clave, '---')}"
                  for clave, rotulo in self.COLUMNAS[1:]]
        self.detalle.setText("   ·   ".join(partes))
        self.panel.mostrar(par_estudio(fila["variante"], fila["captura"]),
                           f"Captura {fila['captura']}.")


# ───────────────────────────────────────────────────────────── la pagina

class SimulationPage(QWidget):
    """Lo que la simulacion midio, leido desde el repositorio.

    Dos pestanas porque son dos preguntas distintas. La esfera acota la
    condicion orbital: donde puede estar el sol y que le pasa a la medida
    en cada sitio. El estudio es el sustituto que se puede montar en el
    TV2, y lo que se compara es si la condicion del sustituto cae dentro
    de la envolvente de la otra.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_DEEP};")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        cabecera = QLabel(
            "  Simulacion: lo medido sobre los renders de Cycles. Las cifras "
            "salen de las CSV versionadas, no se recalculan aqui.")
        cabecera.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 8px 12px;"
            f"background-color: {BG_PANEL}; border-bottom: 1px solid "
            f"{BORDER_SUBTLE};")
        v.addWidget(cabecera)

        pestanas = QTabWidget()
        pestanas.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {BG_DEEP}; }}"
            f"QTabBar::tab {{ background: {BG_PANEL}; color: {TEXT_SECONDARY};"
            f"padding: 7px 18px; min-width: 130px;"
            f"border: 1px solid {BORDER_SUBTLE};"
            f"border-bottom: none; font-size: 12px; }}"
            f"QTabBar::tab:selected {{ background: {BG_DEEP};"
            f"color: {ACCENT_CYAN}; }}")
        try:
            pestanas.addTab(PaginaEsfera(self), "Sol: la esfera")
            pestanas.addTab(PaginaEstudio(self), "Estudio TV2")
            logger.info("Simulation page loaded")
        except Exception as exc:                              # noqa: BLE001
            logger.warning("Simulation page unavailable: %s", exc)
            aviso = QLabel(f"La pagina de simulacion no pudo cargarse.\n\n{exc}")
            aviso.setWordWrap(True)
            aviso.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 40px;")
            pestanas.addTab(aviso, "Simulacion")
        v.addWidget(pestanas, 1)
