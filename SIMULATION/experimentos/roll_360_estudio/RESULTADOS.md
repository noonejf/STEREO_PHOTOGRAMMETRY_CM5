# Experimento: el riel de luz orbitando el cable, 360 grados

Corrido el 20 de noviembre de 2026. Para el informe: estos son los numeros
finales, ya corregidos de las dos trampas de medicion que se describen abajo.

## Que se hizo

Variante `X` del estudio TV2 (cuarto 30 x 15 x 10, doce lamparas de 1 x 1 m en
fila a 7 m de altura, visibles en cuadro), rodando **solo el par de camaras**
sobre el eje del propio cable, en 16 pasos de 22.5 grados.

```bash
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant X --rolls 0,22.5,45,67.5,90,112.5,135,157.5,180,202.5,225,247.5,270,292.5,315,337.5 \
        --samples 24 --both
python tools/collect_sweep.py --variant X --tag roll
```

Treinta y dos cuadros de 4056 x 3040, IMX477 con el 8 mm, base 100 mm, cable de
1 mm ondulado, 0.82 m de excursion sobre 24.5 m, naciendo en el plano del lente.

**Rodar las camaras es equivalente a orbitar la luz** y sale mucho mas barato en
tiempo de montaje: el cable y las lamparas se quedan quietos. Entre el cuadro de
0 grados y el de 112.5 los metadatos solo difieren en la posicion de las camaras,
7 cm a lo sumo sobre una base de 100 mm.

## Resultado

| Roll | Contraste del cable | Cable con lampara detras | Tramo afectado |
|------|--------------------:|-------------------------:|---------------:|
| 0.0 deg | 42.6 | 0.0 % | --- |
| 22.5 deg | 43.7 | 0.0 % | --- |
| 45.0 deg | 44.3 | 0.0 % | --- |
| 67.5 deg | 43.8 | 0.0 % | --- |
| 90.0 deg | 43.3 | 0.0 % | --- |
| **112.5 deg** | 53.2 | **3.9 %** | **0.7 m** |
| **135.0 deg** | 44.1 | **6.8 %** | **1.7 m** |
| 157.5 deg | 42.4 | 0.0 % | --- |
| 180.0 deg | 40.4 | 0.0 % | --- |
| 202.5 deg | 41.8 | 0.0 % | --- |
| 225.0 deg | 42.8 | 0.0 % | --- |
| 247.5 deg | 42.0 | 0.0 % | --- |
| 270.0 deg | 42.1 | 0.0 % | --- |
| 292.5 deg | 42.1 | 0.0 % | --- |
| 315.0 deg | 42.7 | 0.0 % | --- |
| 337.5 deg | 42.7 | 0.0 % | --- |

Contraste en niveles de 8 bits sobre el fondo local, medido en el tramo de 5 a
24 m, con la muestra centrada en la cresta y el fondo restado de un corte
perpendicular al cable. El 53.2 de 112.5 grados esta inflado por el halo de la
lampara que cruza, no es mas luz.

El cable esta completo en cuadro en los 16 angulos: 983 de 983 muestras.

## Las tres conclusiones

**1. El azimut de la luz no cambia la medicion.** 40.4 a 44.3 niveles en los 14
angulos sin lampara en el camino, un mas menos 5 % que es ruido de muestreo. Y no
podia cambiarla, porque en este experimento la luz no se mueve: ruedan las
camaras. Es el control del experimento, no un hallazgo.

**2. El hallazgo es el solape.** En 2 de los 16 angulos la fila de lamparas se
proyecta encima del cable, a 112.5 grados sobre 0.7 m de cuerda y a 135 sobre
1.7 m. Ahi el fondo local sube de 0 a 57-76 niveles y el contraste local se
desploma, que es exactamente lo que rompe la segmentacion. **Es de encuadre, no
de potencia.** Para la sesion: el riel se puede colgar en cualquier azimut
comodo siempre que su proyeccion en el cuadro no cruce la cuerda.

**3. La disparidad sigue siendo horizontal en todos los angulos.** La base
estereo rueda rigidamente con las camaras, asi que el derecho de la imagen sigue
siendo el derecho de la imagen. Lo que gira es el mundo respecto al cuadro: la
fila sale por arriba a 0 grados, por la izquierda a 90, por abajo a 180.

## Y R7 queda incumplido, con tres numeros que lo sostienen

Rodar el riel no saca las lamparas del cuadro: lo empeora.

| Azimut del riel | Medio campo | Fuera de cuadro hasta | Altura necesaria a 24.5 m |
|-----------------|------------:|----------------------:|--------------------------:|
| arriba (vertical) | 16.4 deg | 6.8 m | 7.2 m |
| al costado (horizontal) | 21.5 deg | 5.1 m | 9.6 m |
| en diagonal (esquina) | 26.2 deg | 4.1 m | 12.0 m |

El cuadro se extiende **mas** en la diagonal, asi que el mejor azimut es el que
menos campo tiene, y ese es el de arriba, donde el riel ya estaba. Con la cuerda
llegando a 24.5 m haria falta el riel a 7.2 m sobre el eje optico y el techo da
5. Ademas, medido: las lamparas en cuadro no cambian la mascara, 78 669 px
contra 79 662.

## Dos trampas de medicion, las dos pisadas primero

La primera lectura de estos mismos cuadros dio una curva de 52 a 87 niveles, 68 %
de variacion, y era falsa dos veces. Las dos valen para cualquier fotometria
futura sobre este cable.

**Los dos primeros metros de cuerda mandan sobre cualquier promedio.** Nacen en
el plano del lente y ocupan cientos de pixeles, con flujo 1400 contra los 60 del
tramo a 20 m. Por eso la tabla de arriba mide de 5 m en adelante.

**El pico de pixel no mide luz en un cable sub-pixel.** Rodar el cuadro cambia el
angulo con que la linea cruza la reja de pixeles, y el filtro de reconstruccion
de Cycles reparte el flujo entre mas vecinos o menos. Toda fotometria sale de
integrar el flujo en un corte perpendicular, y mejor del EXR lineal con
`--linear`.

## Los archivos

| archivo | que es |
|---------|--------|
| `medidas.csv` | la tabla de arriba, mas el pico crudo sin corregir, para trazar |
| `pliego_16_angulos.jpg` | los 16 cuadros izquierdos realzados, 4 x 4, los dos con lampara marcados en rojo |
| `indice.json` | el indice que dejo `tools/collect_sweep.py` |

**Los 32 cuadros a 4056 x 3040 no estan versionados**, porque `data/results/`
esta en `.gitignore` y son 37 MB. Viven en
`data/results/experimento_roll_360/`, con las copias realzadas en su
subcarpeta `realzado/`. Se regeneran con las dos ordenes de arriba.

Visor publicado, con los cuadros a resolucion original:
https://claude.ai/artifact/M9HWcyFRNKrbNTpRGGXmJZ
