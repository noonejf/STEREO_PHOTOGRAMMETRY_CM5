# La esfera de direcciones del sol sobre un cable tendido

Medido el 24 de noviembre de 2026. Amplia el barrido de azimut de
`../sol_orbita/RESULTADOS.md`, que recorria un circulo maximo, a la rejilla
completa: **16 azimutes por 5 inclinaciones mas los dos polos, 82
direcciones**. Lo pidio el profesor en la reunion del 21, y tenia razon en
pedirlo aunque la respuesta sea que el azimut es el eje que manda.

Sin cuarto, un objeto Sun de Blender, IMX477 con el 8 mm, cable ondulado de
24.5 m, 24 muestras y resolucion de sensor completa. El cable y el par estereo
no se mueven: lo que gira es el haz.

**Convenio de angulos**, el de `build_sun` y el mismo que usa el visor y el
diagrama: el haz viaja en `(cos t sin o, -sin t, -cos t cos o)`, con `o` el
azimut y `t` la inclinacion. A 0 y 0 el sol viene de arriba, perpendicular al
cable; a 90 de azimut, del lado -x; a 180, de abajo. La inclinacion tumba el
haz **a lo largo del propio cable**: positiva, el sol esta del lado del extremo
lejano y el haz viaja hacia las camaras; negativa, el sol esta detras de las
camaras.

**La fila de inclinacion cero es el anillo ya publicado**, no se volvio a
renderizar. Misma variante, mismos ajustes, y asi la fila de cero coincide
exactamente con la tabla de `sol_orbita` en vez de parecerse.

## El resultado: el azimut decide **cuanto** cable se ve, la inclinacion
## decide **cuan brillante** es

Promediando el eje contrario:

| inclinacion | contraste medio | cable ciego | direcciones con el cable entero |
|---:|---:|---:|---:|
| -89 (el sol detras de las camaras) | 26.0 | 11.7 % | 0 de 1 |
| -60 | 39.6 | 21.3 % | 2 de 16 |
| -30 | 49.9 | 18.5 % | 3 de 16 |
| **0** | **51.7** | **18.3 %** | 3 de 16 |
| +30 | 45.4 | 19.6 % | 3 de 16 |
| +60 | 29.1 | 25.4 % | 1 de 16 |
| +89 (el sol al final del cable) | 0.6 | 82.1 % | 0 de 1 |

| azimut | contraste medio | cable ciego | direcciones con el cable entero |
|---:|---:|---:|---:|
| 0.0 | 36.1 | 16.4 % | 3 de 7 |
| **22.5** | 51.7 | **0.0 %** | **5 de 5** |
| **45.0** | 56.1 | **0.6 %** | **4 de 5** |
| 67.5 | **58.2** | 3.7 % | 0 de 5 |
| 90.0 | 57.2 | 11.8 % | 0 de 5 |
| 112.5 | 54.8 | 19.4 % | 0 de 5 |
| 135.0 | 50.9 | 27.9 % | 0 de 5 |
| 157.5 | 45.5 | 35.2 % | 0 de 5 |
| 180.0 | 39.6 | 38.4 % | 0 de 5 |
| 202.5 | 35.6 | 28.5 % | 0 de 5 |
| 225.0 | 31.9 | 22.5 % | 0 de 5 |
| 247.5 | 29.2 | 16.4 % | 0 de 5 |
| 270.0 | 28.2 | 20.2 % | 0 de 5 |
| 292.5 | 31.1 | 25.9 % | 0 de 5 |
| 315.0 | 35.1 | **42.1 %** | 0 de 5 |
| 337.5 | 40.3 | 33.1 % | 0 de 5 |

**Mirar `fig_esfera_mapa.png` ahorra leer las dos tablas.** El mapa de cable
ciego sale a **rayas verticales**: cada columna es casi constante de arriba
abajo, o sea que la inclinacion no cambia cuanto cable se ve. El mapa de
contraste tiene ademas un gradiente horizontal, porque la inclinacion si cambia
cuanto brilla.

En `fig_esfera_perfiles.png` es lo mismo por el otro lado: las cinco curvas de
contraste son **la misma forma desplazada**, y las cinco de cable ciego caen
unas encima de otras.

**Lo que esto significa para el barrido anterior:** el anillo ya contestaba la
pregunta que importa. La esfera no lo desmiente, lo confirma, y ahora eso esta
medido en vez de supuesto. Doce de las 82 direcciones dejan el cable entero
visible, el 15 %, y las doce caen en azimut 22.5 y 45 con cualquier inclinacion
entre -60 y +60.

## Los dos polos no son simetricos, y esa asimetria es el resultado mas util

A inclinacion +-89 el haz corre casi paralelo al cable y el azimut deja de
significar nada. Las dos direcciones son fisicamente opuestas y dan cosas
opuestas:

| polo | de donde viene el sol | contraste | cable ciego |
|---|---|---:|---:|
| **-89** | detras de las camaras, el haz se aleja | **26.0** | 11.7 % |
| **+89** | del extremo lejano, el haz viene hacia la camara | **0.6** | **82.1 %** |

Con el sol a la espalda de las camaras el cable sigue siendo medible: 26
niveles de contraste y solo el 12 % ciego, peor que el mejor caso pero
utilizable. Con el sol al final del cable, a contraluz, **se pierde el 82 % del
cable** y lo que queda marca medio nivel.

Es el caso que hay que poder reconocer en vuelo, porque no se elige: si la
geometria orbital pone el sol detras del tether visto desde las camaras, la
medicion no es mala, es imposible, y conviene saberlo antes y no despues.

## El mejor y el peor

| | azimut | inclinacion | contraste | cable ciego |
|---|---:|---:|---:|---:|
| mejor | 67.5 | 0 | 69.8 | 1.7 % |
| mejor con el cable entero | 22.5 | 0 | 62.5 | 0.0 % |
| peor | 0 | +89 | 0.6 | 82.1 % |
| peor que no es un polo | 247.5 | +60 | 16.7 | 23.6 % |

Que el maximo de contraste (67.5) no coincida con el maximo de cable visible
(22.5 a 45) no es una contradiccion: a 67.5 el cable brilla mas en promedio
pero el extremo lejano ya empieza a apagarse, 1.7 % de cable ciego contra 0.0.
Para una medicion de largo de arco importa mas no perder tramo que brillar.

## Como leer estas cifras

El contraste esta en niveles de 8 bits sobre el fondo local, promediado desde
los 5 m. **No desde el principio del cable**: el cordon nace en el plano del
lente y sus primeros dos metros llevan 1400 niveles contra 60 a 20 m, asi que
dominarian el promedio y lo que se mediria seria la distancia, no la luz.

El cable ciego es la fraccion del cable **entero** bajo 5 niveles, que es
donde la mascara ya no tiene nada que segmentar. Ese si se cuenta desde el
principio, porque la pregunta es que fraccion del cable no se puede segmentar y
el tramo cercano es parte del cable. Los dos dominios y el umbral viven en
`tools/medir_barrido.py` y la esfera importa su `medir`, no una copia.

## Dos trampas que costaron el barrido entero y conviene no repetir

**1. Renderizar a 25 % de escala no hace una version barata de la misma
imagen, borra el sujeto.** La primera pasada de la esfera salio a
`--scale 25` copiando los ajustes de una prueba vieja del anillo. A 1014 px el
cordon mide 0.43 px a 3 m en vez de 1.72, y las 82 direcciones devolvieron
contraste entre 0.5 y 2.8 con el 97 % del cable ciego, contra el 50 de media
del anillo. Se tiraron y se repitieron. Ahora el metadata anota la resolucion
**del archivo**, con el porcentaje aplicado, y no la nominal, que era lo que
hacia que el error no se viera.

**2. Las carpetas de la esfera tambien casan con el patron del anillo.** Se
llaman `..._sun000.0_inc-60.0_...`, asi que `stereo_sim_studioSOL_sun*` las
recoge, y como el lector se queda con la mas reciente por angulo, el anillo
publicado paso a medirse sobre renders de la esfera: su contraste cayo de 55.0
a 1.9 y nada en la salida decia por que. `medir_barrido` ahora descarta
explicitamente los nombres con `_inc`.

## Lo que falta

| | |
|---|---|
| 1 | La misma esfera con el IMX296 y su 6 mm. En el anillo dio la mitad del contraste, 24.3 contra 50.0, y diez puntos mas de cable ciego |
| 2 | Renderizar el polo -89 con varios azimutes, para confirmar que ahi el azimut de verdad no importa en vez de suponerlo de un solo render |
| 3 | Pasar las direcciones del borde por la pipeline completa, no solo por el medidor: contraste no es lo mismo que mascara segmentable |

## Donde esta esto en el entregable

En ingles, con las tablas y las figuras, es el **capitulo 6 del informe de la
sesion**, `Documentation/LINKU_Experiment_TV2/project/chapter6.tex`. Va
despues del capitulo del cuarto porque el cuarto es el sustituto y esto es lo
sustituido: acota la condicion que la sesion reproduce.

Las figuras del entregable son las `_en`, que saca `tools/fig_esfera.py
--idioma en` y copia `tools/fig_al_informe.py`.

## Como reproducir

```bash
# las 64 direcciones nuevas; la fila de inclinacion cero es el anillo ya hecho
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant SOL \
        --sun-orbit 0,22.5,45,67.5,90,112.5,135,157.5,180,202.5,225,247.5,270,292.5,315,337.5 \
        --sun-tilt=-60,-30,30,60 --samples 24 --scale 100

# los polos. OJO: --sun-tilt con signo igual, separado por espacio argparse
# lee el -60 como si fuera una opcion y el barrido no corre
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant SOL --sun-orbit 0 --sun-tilt=-89,89 --samples 24 --scale 100

python tools/medir_esfera.py --csv SIMULATION/experimentos/sol_esfera/medidas.csv
python tools/fig_esfera.py

# el diagrama de la esfera en la escena, y el visor
blender --background --python SIMULATION/render_escenario.py -- --only orbita_esfera
python tools/armar_esfera_web.py --ancho 1600
python tools/armar_visor.py --dest <carpeta>
```

## Archivos

| | |
|---|---|
| `medidas.csv` | las 82 direcciones, con la captura de cada una |
| `fig_esfera_mapa.png` | contraste y cable ciego sobre la rejilla |
| `fig_esfera_perfiles.png` | una curva por inclinacion |
| `fig_renders_polos.png` | los dos polos y el caso perpendicular, vistos |
| `web/` | miniaturas realzadas e `indice.json` para el visor. **No versionado**: se rehace con `tools/armar_esfera_web.py` |
| `../escenario/orbita_esfera.png` | la esfera dibujada en la escena, con el sol como esfera |
