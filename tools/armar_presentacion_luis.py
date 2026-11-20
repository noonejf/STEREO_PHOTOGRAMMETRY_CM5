#!/usr/bin/env python3
"""Arma la presentacion para la reunion con el estudio TV2.

    python tools/armar_presentacion_luis.py

Escribe ``Documentation/presentacion_luis_tv2.pptx``, 16:9.

**Para quien es.** Luis Domingues, que administra el estudio de la Facultad de
Comunicaciones, no es del equipo y no tiene por que saber de fotogrametria. La
presentacion existe para que en media hora entienda que vamos a montar, cuanto
espacio y cuanta luz hace falta, y que decisiones necesitamos de su lado. Por
eso casi no hay texto y casi todo son imagenes del montaje simulado.

Las imagenes salen de ``SIMULATION/experimentos/``, que se regeneran con
``render_escenario.py`` y con el barrido del sol. Si una falta, el guion lo
dice y sigue con el resto en vez de reventar.
"""
from __future__ import annotations

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESC = os.path.join(ROOT, "SIMULATION", "experimentos", "escenario")
SOL = os.path.join(ROOT, "SIMULATION", "experimentos", "sol_orbita")
ROLL = os.path.join(ROOT, "SIMULATION", "experimentos", "roll_360_estudio")
SALIDA = os.path.join(ROOT, "Documentation", "presentacion_luis_tv2.pptx")

FONDO = RGBColor(0x12, 0x14, 0x18)
TINTA = RGBColor(0xEC, 0xEF, 0xF4)
GRIS = RGBColor(0x92, 0x9C, 0xAB)
NARANJA = RGBColor(0xFF, 0x9A, 0x3C)
AZUL = RGBColor(0x4F, 0xA8, 0xFF)

W, H = Inches(13.333), Inches(7.5)


def nueva(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    fondo = s.background.fill
    fondo.solid()
    fondo.fore_color.rgb = FONDO
    return s


def texto(slide, x, y, w, h, cadena, tam=18, color=TINTA, negrita=False,
          alineado=PP_ALIGN.LEFT, interlineado=1.18):
    caja = slide.shapes.add_textbox(x, y, w, h)
    tf = caja.text_frame
    tf.word_wrap = True
    for i, linea in enumerate(cadena.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = alineado
        p.line_spacing = interlineado
        r = p.add_run()
        r.text = linea
        r.font.size = Pt(tam)
        r.font.color.rgb = color
        r.font.bold = negrita
        r.font.name = "Segoe UI"
    return caja


def vinetas(slide, x, y, w, items, tam=17, color=TINTA, salto=Pt(10)):
    caja = slide.shapes.add_textbox(x, y, w, Inches(0.5))
    tf = caja.text_frame
    tf.word_wrap = True
    for i, (fuerte, resto) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = salto
        p.line_spacing = 1.15
        r = p.add_run()
        r.text = fuerte
        r.font.size = Pt(tam)
        r.font.bold = True
        r.font.color.rgb = NARANJA
        r.font.name = "Segoe UI"
        if resto:
            r2 = p.add_run()
            r2.text = resto
            r2.font.size = Pt(tam)
            r2.font.color.rgb = color
            r2.font.name = "Segoe UI"
    return caja


def imagen(slide, ruta, x, y, ancho=None, alto=None):
    """Coloca una imagen si existe, y si no deja dicho que falta."""
    if not os.path.exists(ruta):
        texto(slide, x, y, Inches(5), Inches(0.6),
              f"[falta {os.path.basename(ruta)}]", tam=12, color=GRIS)
        print(f"  AVISO: falta {ruta}")
        return None
    kw = {}
    if ancho is not None:
        kw["width"] = ancho
    if alto is not None:
        kw["height"] = alto
    return slide.shapes.add_picture(ruta, x, y, **kw)


def pie(slide, cadena):
    texto(slide, Inches(0.62), Inches(6.92), Inches(12.1), Inches(0.4),
          cadena, tam=11, color=GRIS)


def titulo(slide, cadena, sub=None):
    texto(slide, Inches(0.62), Inches(0.42), Inches(12.1), Inches(0.8),
          cadena, tam=30, negrita=True)
    if sub:
        texto(slide, Inches(0.62), Inches(1.12), Inches(12.1), Inches(0.5),
              sub, tam=15, color=GRIS)


def construir():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # ---------------------------------------------------------- 1. portada
    s = nueva(prs)
    imagen(s, os.path.join(ESC, "estudio_tres_cuartos.png"),
           Inches(5.6), Inches(1.35), ancho=Inches(7.5))
    texto(s, Inches(0.7), Inches(1.6), Inches(5.0), Inches(0.5),
          "PROYECTO LINKU", tam=14, color=NARANJA, negrita=True)
    texto(s, Inches(0.7), Inches(2.1), Inches(5.0), Inches(2.0),
          "Medicion de un cable\nen tres dimensiones", tam=34, negrita=True)
    texto(s, Inches(0.7), Inches(3.9), Inches(4.8), Inches(1.4),
          "Que queremos montar en el estudio,\ny que necesitamos de ustedes",
          tam=17, color=GRIS)
    texto(s, Inches(0.7), Inches(5.6), Inches(5.0), Inches(1.2),
          "PUCP / APSCO\nNoviembre de 2026", tam=13, color=GRIS)
    pie(s, "Imagen: el montaje simulado en Blender, con las medidas reales "
           "del estudio. El cable va dibujado mas grueso para que se vea.")

    # ------------------------------------------------- 2. que es el proyecto
    s = nueva(prs)
    titulo(s, "Que es, en una frase",
           "Dos satelites unidos por un cable, y una camara que mide ese "
           "cable sin tocarlo")
    vinetas(s, Inches(0.62), Inches(1.95), Inches(5.4), [
        ("Medimos un cable de 1 mm", " tendido en el vacio, en tres "
         "dimensiones, con dos camaras separadas 100 mm."),
        ("El resultado no es una foto", ", son numeros: largo del cable, "
         "cuanto se curva, a que distancia esta cada tramo."),
        ("Antes de volar hay que probarlo", " en tierra, y hace falta un "
         "espacio largo, oscuro y con luz controlada. De ahi el estudio."),
        ("Ya esta todo simulado", ". Lo que viene en las siguientes laminas "
         "son imagenes de esa simulacion, hecha con las medidas de TV2."),
    ])
    imagen(s, os.path.join(ESC, "estudio_elevacion.png"),
           Inches(6.3), Inches(2.1), ancho=Inches(6.6))
    pie(s, "Vista de perfil del estudio simulado. Alturas y distancias "
           "reales; el grosor del cable, no.")

    # ------------------------------------------------------- 3. el montaje
    s = nueva(prs)
    titulo(s, "El montaje", "Lo que ocuparia el estudio durante la sesion")
    imagen(s, os.path.join(ESC, "estudio_planta.png"),
           Inches(0.62), Inches(1.75), ancho=Inches(8.1))
    vinetas(s, Inches(9.0), Inches(1.95), Inches(3.9), [
        ("24.5 m", " de cable tendido a lo largo del estudio"),
        ("5 m de altura", " en los dos extremos del cable"),
        ("12 luminarias", " en fila sobre el cable, a 7 m"),
        ("2 camaras", " juntas, en un extremo"),
        ("3 a 4 horas", " de ocupacion, montaje y desmontaje incluidos"),
        ("Oscuridad", ": el resto del estudio sin luz durante la medicion"),
    ], tam=16)
    pie(s, "Vista en planta. Las luminarias tapan el cable porque van justo "
           "encima de el.")

    # --------------------------------------------- 4. lo que ve la camara
    s = nueva(prs)
    titulo(s, "Lo que ve la camara",
           "Un hilo muy fino sobre fondo negro, y nada mas")
    imagen(s, os.path.join(SOL, "fig_cuadro_sol_45.jpg"),
           Inches(0.62), Inches(1.8), ancho=Inches(7.6))
    vinetas(s, Inches(8.5), Inches(2.0), Inches(4.4), [
        ("El cable ocupa 1 o 2 pixeles", " de ancho en la imagen. A 24 m es "
         "menos de un pixel."),
        ("Por eso la luz decide todo", ". Si el cable no resalta contra el "
         "fondo, no hay nada que medir."),
        ("La imagen esta aclarada", " para esta lamina. El archivo original "
         "es mas oscuro, y asi esta bien: la camara lo ve de sobra."),
    ], tam=16)
    pie(s, "Render de la simulacion, camara izquierda, 4056 x 3040.")

    # ------------------------------------------- 5. por que la luz importa
    s = nueva(prs)
    titulo(s, "Por que insistimos tanto con la luz",
           "El mismo cable, la misma camara, y solo cambia de donde llega "
           "la luz")
    imagen(s, os.path.join(SOL, "fig_45_contra_180.jpg"),
           Inches(0.62), Inches(1.85), ancho=Inches(12.1))
    texto(s, Inches(0.62), Inches(5.75), Inches(12.1), Inches(1.0),
          "A la izquierda el cable se ve completo. A la derecha, con la luz "
          "llegando desde el otro lado, nueve metros de cable simplemente no "
          "estan. No es falta de potencia: es la direccion.",
          tam=16, color=TINTA)
    pie(s, "Simulacion con una sola fuente, tipo sol. Recorte del centro del "
           "cuadro, con el brillo realzado igual en las dos.")

    # --------------------------------------------------------- 6. lo medido
    s = nueva(prs)
    titulo(s, "Esto ya esta medido, no es una impresion",
           "Dieciseis posiciones de la luz alrededor del cable")
    imagen(s, os.path.join(SOL, "fig_contraste_azimut.png"),
           Inches(0.62), Inches(1.72), alto=Inches(4.95))
    vinetas(s, Inches(9.2), Inches(2.0), Inches(3.7), [
        ("Solo un cuarto de vuelta sirve", ". Entre 0 y 67 grados el cable "
         "se ve entero."),
        ("Fuera de ahi se pierde", " entre el 10 % y el 40 % del cable."),
        ("Una fila de luminarias lo arregla", ", y es justo lo que el "
         "estudio tiene: muchas fuentes repartidas a lo largo, no una sola."),
    ], tam=15)
    pie(s, "Contraste del cable contra el fondo, en niveles de gris. Las "
           "barras rojas marcan el tramo que se vuelve invisible.")

    # --------------------------------------------- 7. el estudio ya simulado
    s = nueva(prs)
    titulo(s, "Y el estudio tambien esta simulado",
           "Las doce luminarias, vistas desde la camara, en 16 posiciones")
    imagen(s, os.path.join(ROLL, "pliego_16_angulos.jpg"),
           Inches(3.57), Inches(1.78), alto=Inches(4.6))
    pie(s, "Cada cuadro es una posicion distinta de la fila de luminarias "
           "respecto a la camara. En dos de las dieciseis una luminaria "
           "queda justo detras del cable, marcadas en rojo, y ahi la "
           "medicion se pierde. Es la unica restriccion de montaje que sale "
           "de esto.")

    # ------------------------------------------------- 8. lo que pedimos
    s = nueva(prs)
    titulo(s, "Lo que necesitamos definir con ustedes",
           "Son cuatro cosas, y con media hora alcanza")
    vinetas(s, Inches(0.62), Inches(2.1), Inches(6.0), [
        ("1. El espacio y la fecha.", " Tres o cuatro horas, en las primeras "
         "semanas de diciembre."),
        ("2. Las luminarias.", " Cuales hay, cuantas unidades iguales, y la "
         "marca y modelo exactos."),
        ("3. El tramite.", " Que documento presentamos, a quien y quien "
         "autoriza."),
        ("4. La operacion.", " Si las luces las maneja un tecnico del "
         "estudio y con quien se coordina."),
    ], tam=17)
    vinetas(s, Inches(7.1), Inches(2.1), Inches(5.8), [
        ("Por que la marca y el modelo.", " Necesitamos saber si la "
         "luminaria parpadea. Trabajamos con tiempos de exposicion del orden "
         "del ciclo de la red, y una luz que parpadee deja bandas en la "
         "imagen y la medicion se pierde. Con el modelo exacto lo "
         "verificamos nosotros en la hoja del fabricante."),
        ("Por que cuantas unidades.", " La simulacion usa doce. Con menos se "
         "puede, pero hay que rehacer el calculo de potencia y de "
         "uniformidad antes de la sesion, no durante."),
    ], tam=15)

    # -------------------------------------------------------- 9. el cierre
    s = nueva(prs)
    imagen(s, os.path.join(ESC, "orbita_anillo.png"),
           Inches(6.4), Inches(1.5), ancho=Inches(6.6))
    texto(s, Inches(0.7), Inches(2.0), Inches(5.3), Inches(1.4),
          "Lo que el estudio\nnos permite probar", tam=30, negrita=True)
    texto(s, Inches(0.7), Inches(3.5), Inches(5.3), Inches(2.0),
          "El cable en orbita recibe la luz del Sol desde una direccion que "
          "cambia todo el tiempo. En el estudio podemos reproducir ese "
          "barrido con las luminarias y comprobar, antes de volar, en que "
          "posiciones la medicion se sostiene.",
          tam=16, color=GRIS)
    texto(s, Inches(0.7), Inches(5.9), Inches(5.3), Inches(0.8),
          "Gracias. Quedamos atentos a la fecha.", tam=18,
          color=NARANJA, negrita=True)
    pie(s, "Diagrama del caso orbital: el cable, las dos camaras en un "
           "extremo, y las dieciseis posiciones del Sol que se simularon.")

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    prs.save(SALIDA)
    return SALIDA


if __name__ == "__main__":
    ruta = construir()
    print(f"escrito {ruta}  ({os.path.getsize(ruta) / 1e6:.1f} MB)")
