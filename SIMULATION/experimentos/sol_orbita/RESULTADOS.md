# Experimento: el sol orbitando el cable, sin cuarto

Corrido el 20 de noviembre de 2026, a pedido de la reunion del mismo dia.

## Que se hizo, y en que se diferencia del barrido de roll

El barrido anterior (`../roll_360_estudio/`) rodaba **las camaras** y dejaba
quietas las lamparas, porque mover doce lamparas de estudio es caro. Era por
tanto un control: la iluminacion del cable no podia cambiar, y medido no
cambio, mas menos 5 %.

Aqui es al reves y es el experimento de verdad. **El instrumento se queda
quieto, como va a estar montado, y lo que gira es la luz**: un objeto Sun de
Blender, sin cuarto, cuyo haz orbita alrededor del eje del propio cable en 16
pasos de 22.5 grados.

```bash
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant SOL --sun-orbit 0,22.5,45,67.5,90,112.5,135,157.5,180,202.5,225,247.5,270,292.5,315,337.5 \
        --samples 24 --both
python tools/collect_sweep.py --variant SOL --tag sun
python tools/medir_barrido.py --variant SOL --tag sun
```

Tres configuraciones, la misma escena y el mismo cable en las tres:

| variante | sensor | obturador | lente | cordon a 3 m | angulos |
|----------|--------|-----------|-------|-------------:|--------:|
| `SOL` | IMX477, 12.3 MP | rodante | 8 mm | 1.72 px | 16 |
| `SOL296W` | IMX296, 1.6 MP | **global** | **6 mm** | **0.58 px** | 16 |
| `SOL296` | IMX296, 1.6 MP | global | 16 mm | 1.55 px | 16 |

`SOL296W` es la configuracion que interesa al proyecto. La del 16 mm se
midio tambien, y queda como referencia de cuanto se gana con un telefoto que
no es la opcion elegida.

**Los mismos lumenes que el estudio.** El pedido era que al cable le llegue lo
mismo que con la fila de doce lamparas. Un Sun no tiene posicion, solo
direccion, asi que su irradiancia no cae con la distancia: puesta en
3600 / 97.58 = **36.89 W/m2**, el cable recibe los 3600 lx de R5 **en toda su
longitud**, donde la fila solo los garantiza en el punto peor. Esa es, de
hecho, la diferencia que importa entre las dos iluminaciones.

La escala de la irradiancia no decide la imagen. La exposicion sale del mismo
objetivo, asi que renderizar a 36.89 W/m2 o a los 1361 de AM0 da el mismo
pixel, ya medido sobre cuatro variantes de 3.15 kW a 180 kW. El
`metadata.json` anota las dos cifras.

## El resultado principal: el azimut del sol decide cuanto cable se ve

| azimut | contraste medio | cable invisible | tramo ciego |
|-------:|----------------:|----------------:|-------------|
| 0.0 | 55.0 | 0.1 % | --- |
| **22.5** | **62.5** | **0.0 %** | --- |
| **45.0** | **67.3** | **0.0 %** | --- |
| **67.5** | **69.8** | 1.7 % | 24.1 a 24.5 m |
| 90.0 | 67.8 | 10.4 % | 21.6 a 24.5 m |
| 112.5 | 64.7 | 17.2 % | 20.0 a 24.5 m |
| 135.0 | 59.7 | 25.8 % | 18.2 a 24.5 m |
| 157.5 | 53.3 | 33.9 % | 16.1 a 24.5 m |
| 180.0 | 46.6 | **35.8 %** | 14.4 a 23.5 m |
| 202.5 | 42.6 | 26.3 % | 13.7 a 20.1 m |
| 225.0 | 38.7 | 17.7 % | 12.8 a 18.2 m |
| 247.5 | 35.7 | 12.9 % | 11.9 a 15.2 m |
| 270.0 | 33.8 | 17.9 % | 0.4 a 14.0 m |
| 292.5 | 37.9 | 21.9 % | 1.2 a 12.8 m |
| 315.0 | 42.5 | **40.1 %** | 2.0 a 12.1 m |
| 337.5 | 49.0 | 31.4 % | 2.8 a 10.7 m |

Contraste en niveles de 8 bits sobre el fondo local, tramo de 5 a 24.5 m,
medido con `tools/medir_barrido.py`. "Invisible" es la fraccion de muestras
bajo 5 niveles, que es donde la mascara ya no tiene nada que segmentar.

**Solo un cuarto de vuelta sirve.** Entre 0 y 67.5 grados el cable se ve
entero. En el resto se pierde entre el 10 % y el 40 %, y lo importante es que
**el tramo ciego se desplaza**: empieza por el extremo lejano hacia 90 grados,
lo recorre entero hasta los 180, y hacia 270 ya se ha mudado al extremo
cercano. Ver `fig_contraste_azimut.png`, panel de abajo.

**Por que pasa.** La camara mira a lo largo del cable, asi que de cada tramo
ve una franja estrecha de la superficie del cilindro, la que esta vuelta hacia
ella. Cual sea esa franja depende de hacia donde se aparta el cable del eje
optico, y la onda hace que eso cambie a lo largo de la cuerda. Cuando el sol
ilumina la franja opuesta, ese tramo queda en silueta contra un fondo negro, y
una silueta negra sobre negro no es nada. No es falta de potencia.

**Y por eso la fila del estudio no es un sucedaneo pobre del sol.** Medida
igual, la variante `X` del estudio a roll 0 deja **1.7 %** del cable
invisible, que es el comportamiento de los mejores azimutes del sol. Muchas
fuentes repartidas a lo largo del cable no tienen un azimut unico, y ahi esta
la ventaja.

## El segundo resultado: el IMX296 con el 6 mm, que es la configuracion pedida

La configuracion del global shutter que interesa al proyecto es **el 6 mm**.
El 16 mm se midio tambien y queda abajo como referencia, pero no es la opcion.

| azimut | IMX477 8 mm | IMX296 6 mm | ciego 477 | ciego 296 |
|-------:|------------:|------------:|----------:|----------:|
| 0.0 | 55.0 | 22.4 | 0.1 % | **25.7 %** |
| **22.5** | 62.5 | 27.1 | 0.0 % | **1.0 %** |
| **45.0** | 67.3 | 31.2 | 0.0 % | **1.6 %** |
| 67.5 | 69.8 | 34.2 | 1.7 % | 10.4 % |
| 90.0 | 67.8 | 35.5 | 10.4 % | 18.3 % |
| 112.5 | 64.7 | 35.0 | 17.2 % | 26.4 % |
| 135.0 | 59.7 | 33.4 | 25.8 % | 29.0 % |
| 157.5 | 53.3 | 29.7 | 33.9 % | 36.9 % |
| 180.0 | 46.6 | 25.1 | 35.8 % | 43.2 % |
| 202.5 | 42.6 | 19.2 | 26.3 % | 49.4 % |
| 225.0 | 38.7 | 15.8 | 17.7 % | 32.0 % |
| 247.5 | 35.7 | 14.2 | 12.9 % | 24.3 % |
| 270.0 | 33.8 | 14.2 | 17.9 % | 31.1 % |
| 292.5 | 37.9 | 14.4 | 21.9 % | 43.3 % |
| 315.0 | 42.5 | 16.9 | 40.1 % | 45.8 % |
| 337.5 | 49.0 | 20.3 | 31.4 % | 40.2 % |
| **medias** | **50.0** | **24.3** | **18.3 %** | **28.7 %** |

**El 6 mm cuesta la mitad del contraste y diez puntos de cable ciego.** La
curva tiene la misma forma, el mismo minimo hacia los 270 grados, y el maximo
corrido a 90. El cordon mide 0.58 px a 3 m contra los 1.72 del IMX477, que es
de donde sale la diferencia, y se ve directamente en
`fig_dos_sensores.jpg`: el mismo campo angular, 360 px en el IMX477 y 121 en
el IMX296, y el cable pasa de linea fina a mancha de tres pixeles.

**La ventana util se encoge de cuatro azimutes a dos.** Con el IMX477 hay
cuatro angulos que dejan menos del 2 % del cable invisible (0, 22.5, 45 y
67.5); con el IMX296 de 6 mm quedan dos, 22.5 y 45. A 0 grados, que con el
IMX477 es un angulo limpio, el 6 mm ya pierde el 25.7 % del cable.

Referencia medida y descartada, el mismo sensor con el telefoto de 16 mm:
reproduce la curva del IMX477 dentro del 6 % en los 16 azimutes (52.5 contra
55.0 a 0 grados, 62.9 contra 67.3 a 45, 31.9 contra 33.8 a 270), con 1.55 px
de cordon a 3 m. Esta en `medidas_SOL296.csv`.

## Los archivos

| archivo | que es |
|---------|--------|
| `medidas_SOL.csv`, `medidas_SOL296.csv`, `medidas_SOL296W.csv` | las tablas crudas por angulo |
| `fig_contraste_azimut.png` | la curva y el mapa del tramo ciego |
| `fig_45_contra_180.jpg` | el mismo recorte con el sol a 45 y a 180 grados |
| `fig_dos_sensores.jpg` | IMX477 y IMX296 al mismo campo angular |
| `fig_cuadro_sol_45.jpg` | un cuadro entero, realzado |

Los 72 renders a resolucion de captura **no estan versionados**, porque
`data/results/` y `data/captures/` quedan fuera. Se regeneran con las ordenes
de arriba.

## Lo que este experimento no responde

- **Cycles no tiene ruido de sensor.** El fondo da 0 exacto. Todos los
  contrastes de aqui son cotas optimistas, y la ventaja del IMX477 en fotones
  recogidos por pixel no aparece.
- **El cable es un cilindro lambertiano perfecto.** Un tether real, trenzado y
  con polvo, dispersa mas en angulos rasantes, asi que el tramo ciego de un
  caso real deberia ser menos tajante que el medido aqui. La direccion del
  efecto no cambia.
- **El sol se movio en un plano perpendicular al cable.** Queda sin barrer el
  angulo entre el haz y el eje del cable, que es el otro grado de libertad y
  probablemente el que mas pesa sobre el contraste absoluto.
