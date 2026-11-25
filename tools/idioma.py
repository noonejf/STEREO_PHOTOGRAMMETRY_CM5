#!/usr/bin/env python3
"""Un diccionario para que las figuras salgan en los dos idiomas.

Las figuras se piensan y se discuten en espanol, que es como se trabaja aqui,
y acaban dentro de entregables escritos en ingles. Tenerlas en un solo idioma
obliga a elegir entre un repositorio incomodo y un entregable con los ejes en
otra lengua, asi que el texto vive una sola vez, en espanol, y este modulo lo
traduce al vuelo:

    import idioma
    idioma.usar("en")
    ax.set_title(idioma.t("Inclinar cuesta contraste, y no es poco"))

La clave **es la frase en espanol**, no un identificador. Es a proposito: una
figura sin traducir sigue saliendo entera, en espanol, en vez de mostrar
``titulo_panel_3``. Lo que no se puede permitir es que una frase cambie en el
codigo y nadie note que su traduccion se quedo con la version vieja, y por eso
``faltantes()`` devuelve lo que se pidio y no estaba, y los scripts lo
imprimen al terminar.

``sufijo()`` da lo que se le pega al nombre del archivo, vacio en espanol y
``_en`` en ingles, para que las dos versiones convivan en la misma carpeta.
"""
from __future__ import annotations

_IDIOMA = "es"
_FALTAN: set = set()

EN = {
    # ------------------------------------------------ fig_cuarto.py, arriba
    "5 luminarias a 6.0 m, haz vertical":
        "5 fixtures at 6.0 m, vertical beam",
    "5 a 6.0 m, haz inclinado 40 grados":
        "5 at 6.0 m, beam tilted 40 degrees",
    "6 a 6.25 m, 20 m de cable":
        "6 at 6.25 m, 20 m of tether",
    "5 a solo 0.5 m sobre el cable":
        "5 at only 0.5 m above the tether",
    "{etq}   |   peor punto {v} lx":
        "{etq}   |   worst point {v} lx",
    "piso propio del IMX477: 2320 lx":
        "IMX477 own floor: 2320 lx",
    "posicion a lo largo del cable (m desde la pared de las camaras)":
        "position along the tether (m from the camera wall)",
    "iluminancia en el cable,\ncara a la luz (lx)":
        "illuminance at the tether,\nfacing the light (lx)",
    "Lo que decide la fila no es la potencia, es si las huellas de los conos "
    "se tocan":
        "What decides the row is not the power, it is whether the cone "
        "footprints touch",
    "Los triangulos son las cinco luminarias de la fila recomendada. Modelo "
    "de fuente puntual con perfil cos^n, sin rebotes de pared ni perdidas "
    "por suciedad:\nel render de Cycles entrega un 30 % mas, medido "
    "recuperando los lux del piso de molton. La cuarta curva no es una "
    "propuesta, es el control que muestra el hueco.":
        "The triangles are the five fixtures of the recommended row. Point "
        "source model with a cos^n profile, with no wall bounce and no "
        "losses to dirt:\nthe Cycles render delivers 30 % more, recovered "
        "from the lux of the molton floor. The fourth curve is not a "
        "proposal, it is the control that shows the gap.",
    # --------------------------------------- fig_cuarto.py, abajo izquierda
    "barrido de inclinacion": "tilt sweep",
    "test de tres vias, cable corrido": "three-way test, tether shifted",
    "inclinacion del haz (grados desde la vertical)":
        "beam tilt (degrees from vertical)",
    "contraste del cordon (niveles)": "cord contrast (levels)",
    "Inclinar cuesta contraste, y no es poco":
        "Tilting costs contrast, and not a little",
    "De un cilindro visto casi de punta la camara ve\nel limbo, cuyas "
    "normales apuntan en x y en z.\nEl haz vertical ilumina justamente una "
    "de ellas.":
        "Of a cylinder seen nearly end on the camera sees\nthe limb, whose "
        "normals point along x and z.\nThe vertical beam lights exactly one "
        "of them.",
    # ----------------------------------------- fig_cuarto.py, abajo derecha
    "molton negro\nsobre la madera": "black molton\nover the wood",
    "madera desnuda": "bare wood",
    "fondo medio del cuadro (niveles)": "mean frame background (levels)",
    "cuadro sobre 10 niveles (%)": "frame above 10 levels (%)",
    "La tela no es una mejora, es una condicion del montaje":
        "The cloth is not an improvement, it is a condition of the setup",
    "Albedos ASUMIDOS, 0.04 el molton y 0.30 la madera barnizada: hay que "
    "medirlos con el fotometro el dia de la sesion. Y la madera barnizada no "
    "es lambertiana: manda un reflejo \nespecular que este modelo no "
    "reproduce, asi que 0.30 difuso es la version optimista del problema.":
        "ASSUMED albedos, 0.04 for the molton and 0.30 for varnished wood: "
        "both have to be measured with the photometer on session day. And "
        "varnished wood is not Lambertian: it sends a specular \nreflection "
        "this model does not reproduce, so 0.30 diffuse is the optimistic "
        "version of the problem.",
    "vertical": "vertical",
    "inclinado 40 grados": "tilted 40 degrees",
    "{etq}, cordon {c} y fondo medio {f} con {p} % del cuadro encendido":
        "{etq}, cord {c} and mean background {f} with {p} % of the frame lit",
    "En la vista de COSTADO el cordon empata y lo que cambia es el fondo: "
    "{pares}. El haz vertical gana en las dos vistas.":
        "In the SIDE view the cord ties and what changes is the background: "
        "{pares}. The vertical beam wins in both views.",
    "El TV2 con las luminarias que el estudio tiene: 4 STORM 1200x y 1 LS "
    "1200d Pro":
        "TV2 with the fixtures the studio actually has: 4 STORM 1200x and 1 "
        "LS 1200d Pro",
    # ------------------------------------------------------- fig_esfera.py
    "Contraste del cordon": "Cord contrast",
    "niveles de 8 bits": "8-bit levels",
    "Cable que la mascara no puede segmentar":
        "Tether the mask cannot segment",
    "% del cable": "% of the tether",
    "inclinacion del sol (grados)": "sun inclination (degrees)",
    "azimut del sol alrededor del eje del cable (grados)":
        "sun azimuth around the tether axis (degrees)",
    "Convenio de build_sun: a 0 y 0 el sol viene de arriba, perpendicular al "
    "cable. Inclinacion positiva, el sol esta del lado del extremo lejano.":
        "build_sun convention: at 0 and 0 the sun comes from above, "
        "perpendicular to the tether. Positive inclination, the sun is on "
        "the far end side.",
    "Los polos quedan fuera del mapa porque alli el azimut no significa "
    "nada: ":
        "The poles are left off the map because there the azimuth means "
        "nothing: ",
    "inclinacion {inc} da contraste {c} y {z} % ciego":
        "inclination {inc} gives contrast {c} and {z} % blind",
    "La esfera del sol: 16 azimutes por 7 inclinaciones, IMX477 con el 8 mm":
        "The sphere of the sun: 16 azimuths by 7 inclinations, IMX477 with "
        "the 8 mm",
    "cable ciego (%)": "blind tether (%)",
    "azimut (grados)": "azimuth (degrees)",
    "{inc} grados": "{inc} degrees",
    " (el anillo ya medido)": " (the ring already measured)",
    "inclinacion del sol": "sun inclination",
    "El azimut dibuja la forma, la inclinacion la desplaza":
        "The azimuth draws the shape, the inclination shifts it",
    # ------------------------------------------------------ fig_renders.py
    "Camara izquierda, realzada con gamma {g} para poder verse impresa. Las "
    "cifras salen del render crudo, no de estas copias.":
        "Left camera, enhanced with gamma {g} so it can be seen in print. "
        "The figures come from the raw render, not from these copies.",
    "Haz vertical, molton": "Vertical beam, molton",
    "la recomendada, contraste 92.4": "the recommended one, contrast 92.4",
    "Haz inclinado 40°, molton": "Beam tilted 40°, molton",
    "contraste 77.3, luz en una cara que no se ve":
        "contrast 77.3, light on a face that is not seen",
    "Haz inclinado 40°, piso de madera":
        "Beam tilted 40°, wooden floor",
    "fondo medio 50.2 contra 17.5": "mean background 50.2 against 17.5",
    "Doce paneles de 1x1 m": "Twelve 1x1 m panels",
    "contraste 59.5 con 9.62 kW": "contrast 59.5 with 9.62 kW",
    "IMX296 con el 6 mm": "IMX296 with the 6 mm",
    "contraste 38.4, cordon de 0.58 px a 3 m":
        "contrast 38.4, cord of 0.58 px at 3 m",
    "Vista de costado, haz vertical": "Side view, vertical beam",
    "fondo medio 9.8 niveles": "mean background 9.8 levels",
    "Vertical": "Vertical",
    "contraste 110.6": "contrast 110.6",
    "Inclinado 40° hacia las camaras":
        "Tilted 40° towards the cameras",
    "contraste 89.5": "contrast 89.5",
    "Inclinado 40° hacia el extremo lejano":
        "Tilted 40° towards the far end",
    "contraste 86.0": "contrast 86.0",
    "Cable corrido a y = 5.0 m para que las tres quepan en la misma sala. ":
        "Tether shifted to y = 5.0 m so the three fit in the same room. ",
    "Sol detras de las camaras": "Sun behind the cameras",
    "inclinacion -89°. Contraste 26.0, cable ciego 11.7 %":
        "inclination -89°. Contrast 26.0, blind tether 11.7 %",
    "Sol perpendicular al cable": "Sun perpendicular to the tether",
    "inclinacion 0°. Contraste 36.1, cable ciego 16.4 %":
        "inclination 0°. Contrast 36.1, blind tether 16.4 %",
    "Sol al final del cable": "Sun at the far end of the tether",
    "inclinacion +89°. Contraste 0.6, cable ciego 82.1 %":
        "inclination +89°. Contrast 0.6, blind tether 82.1 %",
    # ------------------------------- render_escenario.py, los diagramas
    "5 luminarias reales a 6.0 m: 4 STORM 1200x + 1 LS 1200d Pro":
        "5 real fixtures at 6.0 m: 4 STORM 1200x + 1 LS 1200d Pro",
    "haz vertical, medido": "vertical beam, measured",
    "cono de 45 grados: tiro 4.50 m, huella 3.73 m":
        "45 degree cone: 4.50 m throw, 3.73 m footprint",
    "cable 1 mm (dibujado x150), 18 m, a 1.5 m del piso":
        "1 mm tether (drawn x150), 18 m, 1.5 m above the floor",
    "par estereo, base 100 mm": "stereo pair, 100 mm baseline",
    "molton negro sobre el piso de madera":
        "black molton over the wooden floor",
    "techo del estudio a 10 m, no dibujado":
        "studio ceiling at 10 m, not drawn",
    "18 m de cable": "18 m of tether",
    "5 luminarias, una cada 4.5 m": "5 fixtures, one every 4.5 m",
    "par estereo": "stereo pair",
    "molton negro, 20 x 3 m": "black molton, 20 x 3 m",
    "15 m de ancho": "15 m wide",
    # ------------------------------------------------------ fig_renders.py
    "Azimut 0 en las tres. Camara izquierda, realzada con gamma {g}, mas "
    "fuerte que la del cuarto porque el sol deja el cable mas oscuro. Las "
    "cifras salen del render crudo.":
        "Azimuth 0 in all three. Left camera, enhanced with gamma {g}, "
        "stronger than the room's because the sun leaves the tether darker. "
        "The figures come from the raw render.",
}


def usar(idioma_nuevo: str) -> None:
    global _IDIOMA
    if idioma_nuevo not in ("es", "en"):
        raise ValueError(idioma_nuevo)
    _IDIOMA = idioma_nuevo


def actual() -> str:
    return _IDIOMA


def sufijo() -> str:
    return "" if _IDIOMA == "es" else "_en"


def t(s: str) -> str:
    if _IDIOMA == "es":
        return s
    v = EN.get(s)
    if v is None:
        _FALTAN.add(s)
        return s
    return v


def faltantes():
    return sorted(_FALTAN)


def avisar() -> int:
    """Imprime lo que se pidio traducir y no estaba. Devuelve cuantas son."""
    f = faltantes()
    for s in f:
        print("SIN TRADUCIR:", repr(s[:90]))
    return len(f)
