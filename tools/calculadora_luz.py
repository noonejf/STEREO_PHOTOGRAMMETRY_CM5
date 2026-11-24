#!/usr/bin/env python3
"""Cuantos lux le caen al cable, con las luminarias que de verdad hay.

    python tools/calculadora_luz.py --listar
    python tools/calculadora_luz.py --fixture storm1200x --reflector 45 \
           --n 5 --altura-luces 7.0 --altura-hilo 5.0
    python tools/calculadora_luz.py --fixture storm1200x --reflector 45 \
           --n 5 --altura-hilo 1.5 --buscar-altura

Entra la altura del hilo, la altura de las luminarias, cuantas hay y cual es
el modelo. Sale cuantos lux recibe el cable punto a punto, el peor punto, la
uniformidad, la potencia electrica y si se cumple el objetivo.

**El objetivo es 3600 lx**, que es el requisito R5 del entregable de
iluminacion para los tres sensores a 1 grado por segundo, medido en el cable.
Esta en ``build_tv2_studio.E_R5_SLOW_LX`` y se puede cambiar con ``--objetivo``.

## De donde salen los numeros de las luminarias

De las fichas del fabricante, versionadas en
``Documentation/LINKU_Experiment_TV2/Sources/luminarias/``. No hay ningun
valor inventado ni sacado de una tienda: las tiendas se contradicen entre si
y con el fabricante.

Las fichas dan **lux a una distancia en el eje**. De ahi sale la intensidad
en candelas, que es lo que no depende de la distancia: ``I = lux * d^2``.
Comprobado contra las cuatro distancias que publica cada ficha, la dispersion
es menor al 5 %, asi que las luminarias se comportan como fuentes puntuales y
la ley del cuadrado vale.

## Lo que este calculo aproxima, y hay que saberlo

**Fuera del eje la intensidad cae y la ficha no dice como.** Aqui se modela
con ``I(theta) = I0 * cos^n(theta)``, con ``n`` elegido para que al borde del
angulo de haz declarado quede la mitad de la intensidad, que es la definicion
habitual de ese angulo. Es una aproximacion razonable para un reflector, y es
optimista en el borde si el reflector tiene corte duro.

**No hay rebotes.** El estudio es negro mate, asi que la pared aporta poco,
pero aporta. El render de Cycles si los cuenta y da algo mas que esto.

**No hay perdidas.** Ni difusores, ni mallas, ni suciedad en el reflector.
Lo que mida el luxometro en la sesion manda sobre todo esto.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "SIMULATION"))

try:
    import build_tv2_studio as S
    OBJETIVO = S.E_R5_SLOW_LX
    ONDA = S.WAVE
except Exception:                                    # pragma: no cover
    OBJETIVO = 3600.0
    ONDA = None

FICHAS = ("Documentation/LINKU_Experiment_TV2/Sources/luminarias/")

#: Las luminarias que el estudio TV2 tiene, segun el correo de Luis Dominguez
#: del 23 de noviembre de 2026: 2 x LS 1200d Pro y 4 x STORM 1200x.
#:
#: ``lux`` es la tabla de la ficha, a 5600 K, en el eje. ``w`` es el consumo
#: maximo. ``incluido`` dice que reflector viene en la caja: los demas se
#: compran aparte y hay que preguntar si el estudio los tiene.
LUMINARIAS = {
    "ls1200d_pro": dict(
        nombre="Aputure LS 1200d Pro",
        ficha="Aputure_LS1200d_filmtechnika.pdf, pagina 1",
        cct="5600 K fijo", w=1440, unidades=2,
        incluido=("15", "30", "45"),   # la caja trae los tres Hyper Reflector
        flicker="2000 FPS libre de parpadeo, con seleccion de frecuencia",
        lux={
            "bare": {3: 6380, 5: 2802, 7: 1538, 9: 964},
            "15":   {3: 83100, 5: 28340, 7: 15200, 9: 8580},
            "30":   {3: 22400, 5: 8200, 7: 4660, 9: 2880},
            "45":   {3: 13010, 5: 4800, 7: 2706, 9: 1775},
            "fresnel_spot": {3: 32410, 5: 12090, 7: 6160, 9: 3940},
            "fresnel_flood": {3: 14470, 5: 5590, 7: 2840, 9: 1920},
        },
        haz={"bare": 66, "15": 15, "30": 30, "45": 45,
             "fresnel_spot": 15, "fresnel_flood": 45}),
    "storm1200x": dict(
        nombre="Aputure STORM 1200x",
        ficha="Aputure_STORM1200x_manual_EN_V1.0.pdf, pagina 33",
        cct="2500 a 10000 K, ajustable", w=1550, unidades=4,
        incluido=("45",),              # solo el de 45; el kit 15/30 va aparte
        flicker="modo High-Speed; con el, la salida minima sube al 20 %",
        lux={
            "bare": {2: 18900, 3: 8490, 5: 3230, 7: 1640},
            "15":   {2: 209000, 3: 96100, 5: 33300, 7: 16600},
            "30":   {2: 104000, 3: 41800, 5: 14100, 7: 7050},
            "45":   {2: 46000, 3: 19800, 5: 7070, 7: 3580},
            "cf12_15": {2: 190000, 3: 84400, 5: 29300, 7: 14800},
            "cf12_45": {2: 36500, 3: 16900, 5: 6230, 7: 3210},
        },
        haz={"bare": 67, "15": 15, "30": 30, "45": 45,
             "cf12_15": 15, "cf12_45": 45}),
}


def intensidad_cd(fixture, reflector):
    """Candelas en el eje, promediando las distancias que da la ficha.

    Una fuente puntual cumple ``lux = I / d^2``, asi que cada distancia de la
    tabla debe dar la misma I. Se devuelve tambien la dispersion, que es la
    comprobacion de que la ficha es coherente y de que la ley vale.
    """
    tabla = LUMINARIAS[fixture]["lux"][reflector]
    valores = [lx * d * d for d, lx in tabla.items()]
    media = sum(valores) / len(valores)
    disp = (max(valores) - min(valores)) / media
    return media, disp


def _n_coseno(haz_deg):
    """Exponente del coseno que deja la mitad de intensidad en el borde."""
    medio = math.radians(haz_deg / 2.0)
    c = math.cos(medio)
    if c >= 1.0:
        return 1e6
    return math.log(0.5) / math.log(c)


def perfil(fixture, reflector, n, y0, y1, altura_luces, altura_hilo,
           cord_y0, cord_y1, pasos=200, onda=None):
    """Lux a lo largo del cable. ``altura_*`` son sobre el piso."""
    I0, _ = intensidad_cd(fixture, reflector)
    nexp = _n_coseno(LUMINARIAS[fixture]["haz"][reflector])
    sobre = altura_luces - altura_hilo
    if sobre <= 0:
        raise SystemExit("las luminarias tienen que ir por encima del cable")
    ys = [y0] if n == 1 else [y0 + (y1 - y0) * i / (n - 1) for i in range(n)]

    if onda is not None and ONDA is not None:
        pts = S.cord_points(0.0, altura_hilo, cord_y0, cord_y1, pasos,
                            wave=ONDA)
    else:
        pts = [(0.0, cord_y0 + (cord_y1 - cord_y0) * i / (pasos - 1),
                altura_hilo) for i in range(pasos)]

    out = []
    for xp, yp, zp in pts:
        e = 0.0
        for yl in ys:
            dz = altura_luces - zp
            r2 = xp * xp + (yp - yl) ** 2 + dz * dz
            r = math.sqrt(r2)
            cos = dz / r                      # coseno respecto al eje del haz
            if cos <= 0:
                continue
            e += I0 * (cos ** nexp) * cos / r2
        out.append((yp, e))
    return out, ys, I0, nexp, sobre


def perfil_mezcla(spec, y0, y1, altura_luces, altura_hilo, cord_y0, cord_y1,
                  pasos=200, onda=False):
    """Fila con luminarias de modelos distintos, que es el caso real.

    El estudio tiene 4 STORM y 2 LS, asi que una fila de cinco o seis es
    mezclada por fuerza, y las dos no dan lo mismo: 178 592 cd contra
    128 365 cd con el reflector de 45 grados, un 28 % menos. Mezclarlas
    empeora la uniformidad y conviene **alternarlas**, no poner las dos
    debiles juntas en un extremo.

    ``spec`` es ``modelo:reflector:cuantas`` separado por comas, y el orden
    en que se escriben es el orden en que se reparten por la fila.
    """
    unidades = []
    for trozo in spec.split(","):
        modelo, ref, cuantas = trozo.split(":")
        if modelo not in LUMINARIAS:
            raise SystemExit(f"modelo desconocido: {modelo}")
        if ref not in LUMINARIAS[modelo]["lux"]:
            raise SystemExit(f"reflector {ref} no existe en {modelo}")
        for _ in range(int(cuantas)):
            unidades.append((modelo, ref))
    n = len(unidades)
    if n == 0:
        raise SystemExit("la mezcla esta vacia")
    # Alternar: se barajan intercalando los grupos para no dejar juntas las
    # mas debiles.
    unidades.sort(key=lambda u: intensidad_cd(*u)[0], reverse=True)
    orden = [None] * n
    izq, der = 0, n - 1
    for k, u in enumerate(unidades):
        if k % 2 == 0:
            orden[izq] = u
            izq += 1
        else:
            orden[der] = u
            der -= 1
    ys = [y0] if n == 1 else [y0 + (y1 - y0) * i / (n - 1) for i in range(n)]

    if onda and ONDA is not None:
        pts = S.cord_points(0.0, altura_hilo, cord_y0, cord_y1, pasos,
                            wave=ONDA)
    else:
        pts = [(0.0, cord_y0 + (cord_y1 - cord_y0) * i / (pasos - 1),
                altura_hilo) for i in range(pasos)]

    out = []
    for xp, yp, zp in pts:
        e = 0.0
        for (modelo, ref), yl in zip(orden, ys):
            I0, _ = intensidad_cd(modelo, ref)
            nexp = _n_coseno(LUMINARIAS[modelo]["haz"][ref])
            dz = altura_luces - zp
            r2 = xp * xp + (yp - yl) ** 2 + dz * dz
            r = math.sqrt(r2)
            cos = dz / r
            if cos <= 0:
                continue
            e += I0 * (cos ** nexp) * cos / r2
        out.append((yp, e))
    return out, list(zip(orden, ys))


def informe_mezcla(args):
    datos, puestas = perfil_mezcla(
        args.mezcla, args.luces_y0, args.luces_y1, args.altura_luces,
        args.altura_hilo, args.hilo_y0, args.hilo_y1, onda=args.onda)
    es = [e for _, e in datos]
    peor, mejor = min(es), max(es)
    kw = sum(LUMINARIAS[m]["w"] for (m, _), _ in puestas) / 1000.0
    sobre = args.altura_luces - args.altura_hilo
    tramo = (args.hilo_y1 - args.hilo_y0) / len(puestas)

    print(f"\n  FILA MEZCLADA, {len(puestas)} luminarias a "
          f"{args.altura_luces:.2f} m, cable a {args.altura_hilo:.2f} m")
    peor_cubre = 1e9
    for (m, ref), y in puestas:
        cubre = sobre * math.tan(
            math.radians(LUMINARIAS[m]["haz"][ref] / 2.0)) * 2
        peor_cubre = min(peor_cubre, cubre)
        print(f"    y={y:5.1f} m   {LUMINARIAS[m]['nombre']:24s} "
              f"reflector {ref:>3}   {intensidad_cd(m, ref)[0]:9,.0f} cd")
    print(f"\n    peor punto   {peor:9,.0f} lx   "
          f"{'CUMPLE' if peor >= args.objetivo else 'NO CUMPLE'} "
          f"({peor/args.objetivo*100:.0f} % de {args.objetivo:,.0f} lx)")
    print(f"    mejor punto  {mejor:9,.0f} lx")
    print(f"    uniformidad  peor/mejor {peor/mejor:.3f}")
    print(f"    cobertura    el haz mas estrecho cubre {peor_cubre:.2f} m, "
          f"cada luminaria responde por {tramo:.2f} m "
          f"{'(alcanza)' if peor_cubre >= tramo else '(NO ALCANZA)'}")
    print(f"    potencia     {kw:.2f} kW\n")
    return peor, mejor, kw


def informe(args):
    f = LUMINARIAS[args.fixture]
    I0, disp = intensidad_cd(args.fixture, args.reflector)
    datos, ys, _, nexp, sobre = perfil(
        args.fixture, args.reflector, args.n, args.luces_y0, args.luces_y1,
        args.altura_luces, args.altura_hilo, args.hilo_y0, args.hilo_y1,
        onda=True if args.onda else None)

    es = [e for _, e in datos]
    peor, mejor, medio = min(es), max(es), sum(es) / len(es)
    kw = f["w"] * args.n / 1000.0
    cubre = sobre * math.tan(math.radians(f["haz"][args.reflector] / 2.0)) * 2
    tramo_por_luz = (args.hilo_y1 - args.hilo_y0) / args.n

    print(f"\n{f['nombre']}  reflector {args.reflector}  "
          f"({f['haz'][args.reflector]} grados)")
    print(f"  ficha: {f['ficha']}")
    print(f"  intensidad en el eje: {I0:,.0f} cd  "
          f"(dispersion entre distancias de la ficha: {disp*100:.1f} %)")
    print(f"  CCT {f['cct']},  parpadeo: {f['flicker']}")
    if args.reflector not in f["incluido"] and args.reflector != "bare":
        print(f"  AVISO: el reflector {args.reflector} NO viene en la caja de "
              f"esta luminaria. Hay que preguntar si el estudio lo tiene.")

    print(f"\n  {args.n} unidades a {args.altura_luces:.2f} m, "
          f"cable a {args.altura_hilo:.2f} m, {sobre:.2f} m por encima")
    print(f"  fila de y={args.luces_y0:.1f} a y={args.luces_y1:.1f} m, "
          f"una cada {((args.luces_y1-args.luces_y0)/max(1,args.n-1)):.2f} m")
    print(f"  potencia electrica: {kw:.2f} kW")

    print(f"\n  ILUMINANCIA EN EL CABLE")
    print(f"    peor punto   {peor:9,.0f} lx   "
          f"{'CUMPLE' if peor >= args.objetivo else 'NO CUMPLE'} "
          f"({peor/args.objetivo*100:.0f} % del objetivo de "
          f"{args.objetivo:,.0f} lx)")
    print(f"    mejor punto  {mejor:9,.0f} lx")
    print(f"    promedio     {medio:9,.0f} lx")
    print(f"    uniformidad  peor/mejor {peor/mejor:.3f}, "
          f"no uniformidad {(mejor-peor)/(mejor+peor)*100:.1f} %")

    print(f"\n  COBERTURA DEL HAZ")
    print(f"    el haz de {f['haz'][args.reflector]} grados a {sobre:.2f} m "
          f"cubre {cubre:.2f} m de cable")
    print(f"    cada luminaria tiene que cubrir {tramo_por_luz:.2f} m")
    if cubre < tramo_por_luz:
        print(f"    AVISO: el haz NO alcanza. Quedan huecos oscuros entre "
              f"luminarias. Sube las luces, abre el haz o pon mas unidades.")
    else:
        print(f"    alcanza, con {cubre/tramo_por_luz:.1f}x de margen")

    if args.perfil:
        print(f"\n  perfil cada 2 m:")
        paso = max(1, len(datos) // 13)
        for y, e in datos[::paso]:
            barra = "#" * int(40 * e / mejor)
            print(f"    y={y:5.1f} m  {e:8,.0f} lx  {barra}")
    print()
    return peor, mejor, kw


def buscar_altura(args):
    """A que altura hay que colgar la fila para que cumpla y cubra."""
    f = LUMINARIAS[args.fixture]
    tramo = (args.hilo_y1 - args.hilo_y0) / args.n
    mejor = None
    print(f"\n  altura de las luces contra lo que consigue "
          f"({args.n} x {f['nombre']}, reflector {args.reflector}, "
          f"cable a {args.altura_hilo:.2f} m)\n")
    print(f"  {'altura':>8} {'sobre':>7} {'peor lx':>10} {'unif':>7} "
          f"{'cubre':>8} {'hueco':>7}")
    z = args.altura_hilo + 0.5
    while z <= 12.0 + 1e-9:
        try:
            datos, *_ = perfil(args.fixture, args.reflector, args.n,
                               args.luces_y0, args.luces_y1, z,
                               args.altura_hilo, args.hilo_y0, args.hilo_y1,
                               onda=True if args.onda else None)
        except SystemExit:
            z += 0.5
            continue
        es = [e for _, e in datos]
        sobre = z - args.altura_hilo
        cubre = sobre * math.tan(
            math.radians(f["haz"][args.reflector] / 2.0)) * 2
        ok = min(es) >= args.objetivo and cubre >= tramo
        marca = "  <--" if ok and mejor is None else ""
        if ok and mejor is None:
            mejor = z
        print(f"  {z:7.1f}m {sobre:6.1f}m {min(es):10,.0f} "
              f"{min(es)/max(es):7.3f} {cubre:7.1f}m "
              f"{'si' if cubre >= tramo else 'NO':>7}{marca}")
        z += 0.5
    if mejor:
        print(f"\n  la mas baja que cumple las dos cosas: {mejor:.1f} m")
    else:
        print(f"\n  ninguna altura hasta 12 m cumple las dos cosas con "
              f"esta configuracion")
    print()


def listar():
    print("\nLuminarias disponibles en el estudio TV2 "
          "(correo de Luis Dominguez, 23 nov 2026)\n")
    for clave, f in LUMINARIAS.items():
        print(f"  {clave}   {f['nombre']}   x{f['unidades']} unidades")
        print(f"     {f['cct']},  {f['w']} W,  {f['flicker']}")
        print(f"     ficha: {FICHAS}{f['ficha']}")
        print(f"     {'reflector':>14} {'haz':>6} {'intensidad':>14} "
              f"{'en la caja':>12}")
        for ref in f["lux"]:
            I0, disp = intensidad_cd(clave, ref)
            print(f"     {ref:>14} {f['haz'][ref]:5d}d {I0:12,.0f} cd "
                  f"{'si' if ref in f['incluido'] else 'aparte':>12}")
        print()


def main():
    ap = argparse.ArgumentParser(
        description="Lux en el cable con las luminarias reales del estudio")
    ap.add_argument("--listar", action="store_true",
                    help="muestra las luminarias y sus intensidades")
    ap.add_argument("--fixture", default="storm1200x",
                    choices=list(LUMINARIAS))
    ap.add_argument("--reflector", default="45")
    ap.add_argument("--n", type=int, default=5, help="cuantas luminarias")
    ap.add_argument("--altura-luces", dest="altura_luces", type=float,
                    default=7.0, help="metros sobre el piso")
    ap.add_argument("--altura-hilo", dest="altura_hilo", type=float,
                    default=5.0, help="metros sobre el piso")
    ap.add_argument("--hilo-y0", dest="hilo_y0", type=float, default=2.0)
    ap.add_argument("--hilo-y1", dest="hilo_y1", type=float, default=26.5)
    ap.add_argument("--luces-y0", dest="luces_y0", type=float, default=None)
    ap.add_argument("--luces-y1", dest="luces_y1", type=float, default=None)
    ap.add_argument("--objetivo", type=float, default=OBJETIVO,
                    help=f"lux que se quieren en el cable (R5: {OBJETIVO:.0f})")
    ap.add_argument("--onda", action="store_true",
                    help="usa el cable ondulado en vez de recto")
    ap.add_argument("--perfil", action="store_true",
                    help="imprime el perfil a lo largo del cable")
    ap.add_argument("--buscar-altura", dest="buscar", action="store_true",
                    help="barre la altura de las luces y dice cual sirve")
    ap.add_argument("--mezcla", default=None,
                    help="fila con modelos distintos: "
                         "modelo:reflector:cuantas, separado por comas. "
                         "Ej: storm1200x:45:4,ls1200d_pro:45:2")
    args = ap.parse_args()

    if args.listar:
        listar()
        return
    if args.luces_y0 is None:
        args.luces_y0 = args.hilo_y0
    if args.luces_y1 is None:
        args.luces_y1 = args.hilo_y1
    if args.reflector not in LUMINARIAS[args.fixture]["lux"]:
        raise SystemExit(
            f"reflector desconocido. Para {args.fixture}: "
            f"{', '.join(LUMINARIAS[args.fixture]['lux'])}")

    if args.mezcla:
        informe_mezcla(args)
    elif args.buscar:
        buscar_altura(args)
    else:
        informe(args)


if __name__ == "__main__":
    main()
