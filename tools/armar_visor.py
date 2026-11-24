#!/usr/bin/env python3
"""Arma el visor publicable: index.html, datos.json y todas las imagenes.

    python tools/armar_visor.py

Deja en ``--dest`` una carpeta lista para publicar como artefacto. La pagina
no calcula nada y no lee ``data/captures``: todo lo que muestra sale del
``datos.json`` que escribe este archivo, asi que la pagina y las medidas no
pueden separarse sin que se note.

**Las imagenes del cuarto se realzan y luego se encogen, en ese orden.** El
cordon marca unas decenas de niveles sobre 255 con el fondo casi en cero, asi
que encoger primero 4056 px a 1400 reparte un cordon sub-pixel entre tres
vecinos y lo borra. Realzar primero con una curva de gamma lo levanta por
encima del promediado. Las dos operaciones son monotonas y ninguna inventa
nada, pero la copia deja de ser proporcional a la luz: ninguna medida de la
pagina sale de las imagenes, y la pagina lo dice.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402
import calculadora_luz as CL  # noqa: E402
import build_tv2_studio as S  # noqa: E402
from medir_barrido import medir, UMBRAL_CIEGO  # noqa: E402
from medir_cuarto import ultima, lux_del_piso  # noqa: E402

GAMMA = 0.42
SPEC5 = "storm1200x:45:4,ls1200d_pro:45:1"


def realzar_y_encoger(ruta, destino, ancho=1400, calidad=86, gamma=GAMMA):
    img = cv2.imread(ruta, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    v = np.clip((img.astype(np.float32) / 255.0) ** gamma * 255.0,
                0, 255).astype(np.uint8)
    if ancho and ancho < v.shape[1]:
        h = int(round(v.shape[0] * ancho / v.shape[1]))
        v = cv2.resize(v, (ancho, h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(destino, v, [int(cv2.IMWRITE_JPEG_QUALITY), calidad])
    return os.path.basename(destino)


def copiar_png(ruta, destino, ancho=1500):
    img = cv2.imread(ruta, cv2.IMREAD_COLOR)
    if img is None:
        return None
    if ancho and ancho < img.shape[1]:
        h = int(round(img.shape[0] * ancho / img.shape[1]))
        img = cv2.resize(img, (ancho, h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(destino, img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return os.path.basename(destino)


def medida(variant):
    d = ultima(variant)
    if d is None:
        return None, None, None
    meta = json.load(open(os.path.join(d, "metadata.json"), encoding="utf-8"))
    img = cv2.imread(os.path.join(d, "left.jpg"), cv2.IMREAD_GRAYSCALE)
    return d, meta, (medir(d, 5.0), img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    ap.add_argument("--esfera-web", default=os.path.join(
        "SIMULATION", "experimentos", "sol_esfera", "web"))
    args = ap.parse_args()

    dest = os.path.abspath(args.dest)
    img_dir = os.path.join(dest, "img")
    os.makedirs(img_dir, exist_ok=True)
    shutil.copy(os.path.join(ROOT, "SIMULATION", "experimentos", "visor",
                             "index.html"), os.path.join(dest, "index.html"))

    datos = {}

    # ------------------------------------------------------------ cabecera
    i5 = [CL.intensidad_cd(m, r)[0] for m, r in CL.unidades_de(SPEC5)]
    kw5 = sum(CL.LUMINARIAS[m]["w"] for m, _ in CL.unidades_de(SPEC5)) / 1000.0
    datos["lede"] = (
        "El estudio TV2 de la Facultad de Comunicaciones tiene cuatro Aputure "
        "STORM 1200x y dos LS 1200d Pro, no los doce paneles que veniamos "
        "simulando. Esto es el cuarto reconstruido con las luminarias que "
        "hay, lo que cambia respecto de lo anterior, y la esfera de "
        "direcciones desde las que el sol puede llegar al cable en orbita.")
    datos["etiquetas"] = [
        "Sesion: viernes 11 de diciembre de 2026",
        "5 luminarias, " + f"{kw5:.2f} kW",
        "Cable de 18 m a 1.5 m del piso",
        "IMX477 con el 8 mm",
        "Objetivo R5: 3600 lx en el cable"]
    datos["pie"] = ("Proyecto LINKU, PUCP dentro de APSCO. Medidas tomadas el "
                    "24 de noviembre de 2026 sobre renders de Cycles a 24 "
                    "muestras y resolucion de sensor completa.")
    datos["comandos"] = [
        "# el cuarto con las luminarias reales, y el test de a donde apuntarlas",
        "blender --background --python SIMULATION/render_studio_iterations.py -- \\",
        "        --variant TV2,TV2MADERA,TV2RECTO,TV2HAZ0,TV2HAZCAM,TV2HAZLEJOS \\",
        "        --samples 24 --scale 100 --both",
        "",
        "# la esfera del sol: 16 azimutes por 5 inclinaciones, mas los dos polos",
        "blender --background --python SIMULATION/render_studio_iterations.py -- \\",
        "        --variant SOL --sun-orbit 0,22.5,45,67.5,90,112.5,135,157.5,180,"
        "202.5,225,247.5,270,292.5,315,337.5 \\",
        "        --sun-tilt -60,-30,0,30,60 --samples 8 --scale 25",
        "",
        "# los diagramas del montaje",
        "blender --background --python SIMULATION/render_escenario.py -- \\",
        "        --only tv2_tres_cuartos,tv2_elevacion,tv2_planta,orbita_esfera",
        "",
        "# las medidas, las figuras y esta pagina",
        "python tools/medir_cuarto.py --lux",
        "python tools/medir_esfera.py --csv SIMULATION/experimentos/sol_esfera/medidas.csv",
        "python tools/fig_cuarto.py && python tools/fig_esfera.py",
        "python tools/armar_esfera_web.py && python tools/armar_visor.py --dest <carpeta>"]

    # ------------------------------------------------------------ seccion 1
    d_tv2, m_tv2, r_tv2 = medida("TV2RECTO")
    pred = ((m_tv2 or {}).get("fixtures") or {}).get("predicted") or {}
    datos["tarjetas"] = [
        dict(lab="luminarias", v="5",
             sub="cuatro STORM 1200x y una LS 1200d Pro, reflector de 45 grados"),
        dict(lab="peor punto del cable",
             v=f"{pred.get('peor_lx_cara_a_la_luz', 0):,.0f} lx",
             sub=f"el {pred.get('peor_lx_cara_a_la_luz', 0) / S.E_R5_SLOW_LX * 100:.0f} %"
                 f" del objetivo de R5, que son 3600 lx"),
        dict(lab="potencia", v=f"{kw5:.2f} kW",
             sub="frente a los 9.62 kW que pedian los doce paneles supuestos")]

    filas = []
    for modelo in ("storm1200x", "ls1200d_pro"):
        f = CL.LUMINARIAS[modelo]
        for ref in ("15", "30", "45", "bare"):
            if ref not in f["lux"]:
                continue
            I0, disp = CL.intensidad_cd(modelo, ref)
            filas.append(dict(hi=(ref == "45"), v=[
                f["nombre"], f"{f['unidades']}",
                "sin reflector" if ref == "bare" else f"{ref} grados",
                f"{I0:,.0f} cd", f"{disp * 100:.1f} %",
                "si" if ref in f["incluido"] else "no", f"{f['w']} W"]))
    datos["fichas"] = dict(
        cols=["luminaria", "unidades", "reflector", "intensidad en el eje",
              "dispersion de la ficha", "viene en la caja", "consumo"],
        filas=filas)

    # ------------------------------------------------------------ seccion 2
    esc = os.path.join(ROOT, "SIMULATION", "experimentos", "escenario")
    diag = [
        ("tv2_tres_cuartos.png", "Tres cuartos.",
         "Las cinco luminarias con su cono de 45 grados, el cable a 1.5 m y "
         "el molton en el piso."),
        ("tv2_elevacion.png", "Elevacion, ortografica.",
         "Las alturas se pueden medir sobre el dibujo. Cada luminaria va "
         "3.78 m rio arriba del punto que ilumina cuando el haz se inclina."),
        ("tv2_planta.png", "Planta.",
         "Una luminaria cada 4.5 m y la tela de 20 x 3 m."),
        ("orbita_esfera.png", "La esfera, en la escena.",
         "Cada bolita es una direccion de sol renderizada; la grande es la "
         "elegida, con su haz apuntando al cable.")]
    datos["diagramas"] = []
    for arch, tit, pie in diag:
        p = os.path.join(esc, arch)
        if not os.path.exists(p):
            continue
        n = copiar_png(p, os.path.join(img_dir, arch.replace(".png", ".jpg")))
        if n:
            datos["diagramas"].append(dict(img="img/" + n, titulo=tit, pie=pie))

    datos["porque_baja"] = (
        "<b>Por que el cable baja a 1.5 m.</b> Un cono de 45 grados a 2 m de "
        "altura ilumina 1.66 m de cable, asi que cinco de ellos sobre 18 m "
        "dejarian el peor punto en 38 lx contra picos de 44 648. Para que las "
        "huellas se toquen hacen falta de 4.5 a 6 m entre la fila y el cable, "
        "y con techo de 10 m eso no deja el cable a 5 m. A 1.5 m se tiende a "
        "mano, sin andamio, y la potencia no cambia porque la fila baja con "
        "el. Lo que cambia es que el piso entra en cuadro a 5.1 m en vez de a "
        "17, y de ahi la tela.")

    # ------------------------------------------------------------ seccion 3
    datos["haz"] = []
    for v, tit, pie in (
            ("TV2HAZ0", "Haz vertical.",
             "Las luminarias justo sobre el punto que iluminan."),
            ("TV2HAZCAM", "Inclinado 40 grados hacia las camaras.",
             "Es lo que hacian todas las variantes anteriores."),
            ("TV2HAZLEJOS", "Inclinado 40 grados lejos de las camaras.",
             "La unica de las tres que ilumina la cara del cable que la "
             "camara ve, y no gana.")):
        d, meta, par = medida(v)
        if d is None:
            continue
        r, _img = par
        n = realzar_y_encoger(os.path.join(d, "left.jpg"),
                              os.path.join(img_dir, f"haz_{v}.jpg"))
        datos["haz"].append(dict(
            img="img/" + n, titulo=tit,
            pie=pie + f" Contraste del cordon {r['contraste']:.1f} niveles."))

    # ------------------------------------------------------------ seccion 4
    datos["tela"] = []
    tela_txt = []
    for v, tit in (("TV2", "Molton negro sobre la madera."),
                   ("TV2MADERA", "Madera desnuda.")):
        d, meta, par = medida(v)
        if d is None:
            continue
        r, img = par
        n = realzar_y_encoger(os.path.join(d, "left.jpg"),
                              os.path.join(img_dir, f"tela_{v}.jpg"))
        fondo, enc = float(img.mean()), float((img > 10).mean() * 100)
        tela_txt.append(f"{tit[:-1]}: fondo medio {fondo:.1f} niveles, "
                        f"{enc:.1f} % del cuadro sobre 10 niveles")
        datos["tela"].append(dict(
            img="img/" + n, titulo=tit,
            pie=f"Fondo medio {fondo:.1f} niveles, {enc:.1f} % del cuadro "
                f"encendido, contraste del cordon {r['contraste']:.1f}."))
    datos["tela_meta"] = (
        "; ".join(tela_txt) + ". Los albedos son ASUMIDOS, 0.04 el molton y "
        "0.30 la madera barnizada, y hay que medirlos con el fotometro el dia "
        "de la sesion. Ademas la madera barnizada no es lambertiana: manda un "
        "reflejo especular que este modelo no reproduce, asi que 0.30 difuso "
        "es la version optimista del problema.")

    # ------------------------------------------------------------ seccion 5
    web = os.path.join(ROOT, args.esfera_web)
    indice_p = os.path.join(web, "indice.json")
    if os.path.exists(indice_p):
        ind = json.load(open(indice_p, encoding="utf-8"))
        esf_dir = os.path.join(img_dir, "esfera")
        os.makedirs(esf_dir, exist_ok=True)
        for e in ind["direcciones"]:
            shutil.copy(os.path.join(web, e["imagen"]),
                        os.path.join(esf_dir, e["imagen"]))
        cs = [e["contraste"] for e in ind["direcciones"] if e["contraste"]]
        zs = [e["ciego_pct"] for e in ind["direcciones"]
              if e["ciego_pct"] is not None]
        mejor = max(range(len(ind["direcciones"])),
                    key=lambda k: ind["direcciones"][k]["contraste"] or 0)
        datos["esfera"] = dict(
            ruta="img/esfera/",
            direcciones=ind["direcciones"],
            inicial=mejor,
            rango=dict(contraste=[min(cs), max(cs)], ciego=[0.0, max(zs)]),
            meta=(f"{len(ind['direcciones'])} direcciones renderizadas, "
                  f"{len(ind['azimutes'])} azimutes por "
                  f"{len(ind['inclinaciones'])} inclinaciones mas los dos "
                  f"polos. Contraste promediado desde 5 m; cable ciego es la "
                  f"fraccion del cable entero bajo {UMBRAL_CIEGO:.0f} niveles "
                  f"sobre el fondo local, que es donde la mascara ya no tiene "
                  f"nada que segmentar."))
    else:
        datos["esfera"] = dict(ruta="img/esfera/", direcciones=[], inicial=0,
                               rango=dict(contraste=[0, 1], ciego=[0, 1]),
                               meta="La esfera todavia no esta renderizada.")

    datos["figuras_esfera"] = []
    for arch, tit, pie in (
            ("fig_esfera_mapa.png", "El mapa completo.",
             "Contraste y cable ciego sobre la rejilla de azimut por "
             "inclinacion."),
            ("fig_esfera_perfiles.png", "Los perfiles.",
             "El azimut dibuja la forma y la inclinacion la desplaza. La "
             "curva gruesa es el anillo de inclinacion cero, que es lo que "
             "ya estaba medido."),
            ("fig_cuarto_luminarias.png", "El cuarto, en numeros.",
             "Los lux a lo largo del cable, el test de a donde apuntar y la "
             "tela.")):
        for base in ("sol_esfera", "estudio_luminarias_reales"):
            p = os.path.join(ROOT, "SIMULATION", "experimentos", base, arch)
            if os.path.exists(p):
                n = copiar_png(p, os.path.join(
                    img_dir, arch.replace(".png", ".jpg")), ancho=1700)
                datos["figuras_esfera"].append(
                    dict(img="img/" + n, titulo=tit, pie=pie))
                break

    # ------------------------------------------------------------ seccion 6
    razones = []
    for v in ("TV2", "TV2RECTO"):
        d = ultima(v, "left.exr")
        if d is None:
            continue
        pares, err = lux_del_piso(d)
        if not pares:
            continue
        r = [b / c for _a, b, c in pares if c > 1.0]
        razones.append(f"{v}: mediana {np.median(r):.2f}")
    datos["falta"] = [
        dict(lab="comprobado", t="La cadena fotometrica cierra",
             d="De la candela de la ficha a los watts de Blender al pixel: "
               "recuperando los lux del piso de molton, que es un plano de "
               "albedo conocido, el render entrega entre un 27 y un 32 % mas "
               "que el modelo de fuente puntual (" + "; ".join(razones) +
               "). Es la direccion y el orden que el propio modelo anticipa, "
               "porque ignora los rebotes de pared y recorta la cola del haz."),
        dict(lab="asumido", t="El albedo del piso y de la tela",
             d="0.30 la madera barnizada y 0.04 el molton negro. Ninguno esta "
               "medido. Es la diferencia entre un fondo medio de 17.5 y uno "
               "de 50.2 niveles, asi que decide si la mascara tiene que "
               "pelear contra el piso."),
        dict(lab="asumido", t="El perfil del haz fuera del eje",
             d="La ficha da el angulo de haz al 50 % de intensidad. El modelo "
               "lo extiende con un coseno elevado, n = 8.70 para 45 grados, y "
               "la escena de Blender con un cono de angulo de campo 75 grados "
               "y blend 0.8. Los dos coinciden en el medio pico por "
               "construccion y no en la cola, que es justo donde estan los "
               "huecos entre luminarias."),
        dict(lab="por preguntar", t="El kit de reflectores de las STORM",
             d="Las STORM 1200x solo traen el de 45 grados en la caja. Con el "
               "de 30 habria mas margen: 372 538 cd contra 178 592."),
        dict(lab="por medir", t="Luxometro cada 2 o 3 m el dia de la sesion",
             d="Con la celula mirando a las luminarias, que es la medida que "
               "da perfil_inclinado como e_perp. Lo que mida el luxometro "
               "manda sobre todo lo de esta pagina."),
        dict(lab="sin hacer", t="La esfera con el IMX296",
             d="El global shutter con su 6 mm esta medido en el anillo de "
               "azimut, donde dio la mitad del contraste del IMX477 y diez "
               "puntos mas de cable ciego, y en el cuarto real como TV2296. "
               "La esfera completa con ese sensor no esta renderizada.")]

    with open(os.path.join(dest, "datos.json"), "w", encoding="utf-8") as fh:
        json.dump(datos, fh, indent=1, ensure_ascii=False)

    total = 0
    for raiz, _d, fs in os.walk(dest):
        for f in fs:
            total += os.path.getsize(os.path.join(raiz, f))
    print(f"visor en {dest}")
    print(f"{total / 1e6:.1f} MB en total, "
          f"{len(datos['esfera']['direcciones'])} direcciones de esfera, "
          f"{len(datos['diagramas'])} diagramas")


if __name__ == "__main__":
    main()
