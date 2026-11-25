# El estudio TV2 con las luminarias que realmente tiene

Medido el 24 de noviembre de 2026, despues de que Luis Dominguez contestara el
23 que el TV2 dispone de **dos Aputure LS 1200d Pro y cuatro STORM 1200x**.
Todo lo simulado hasta esa fecha iluminaba el cable con doce paneles de 1 x 1 m
que eran una suposicion nuestra.

Renders de Cycles, 24 muestras, resolucion de sensor completa (4056 x 3040),
IMX477 con el 8 mm salvo donde se diga. Cable de 18 m a 1.5 m del piso, fila a
6.0 m, reflector de 45 grados en las cinco.

## Lo que cambia, en una linea

No es la potencia, es el reparto. Un panel de 1 x 1 m a 2 m de altura bana su
tramo de cable; un cono de 45 grados a 2 m ilumina un circulo de 1.66 m y deja
el resto negro. Por eso la fila tiene que subir a 6 m y el cable bajar a 1.5 m,
y por eso el piso entra en cuadro.

## Los tres resultados que cambian el montaje

### 1. El haz va VERTICAL, no inclinado

Esto contradice lo que el proyecto venia haciendo. Todas las variantes de
paneles, de la F a la C8, inclinan el haz 40 grados, y el argumento escrito en
`build_lamp_row` es que un haz desde arriba ilumina la cara de **arriba** del
cilindro mientras las camaras le miran el costado.

El argumento vale en la vista de costado y no dice nada sobre la vista de eje,
que es la principal. Ahi la camara mira a lo largo del cable, que se queda
dentro de tres grados del eje optico, asi que de cada tramo no ve el costado
del cilindro: ve el **limbo**, cuyas normales apuntan en x y en z. Un haz
vertical ilumina justamente la normal +z, que si esta en el limbo; uno
inclinado reparte su luz hacia una normal en y, que no se ve desde ninguna
parte.

Barrido completo de la inclinacion, misma escena y misma potencia:

| inclinacion del haz | contraste del cordon | respecto del vertical |
|--------------------:|---------------------:|----------------------:|
| **0 grados** | **112.9** | --- |
| 20 grados | 104.8 | -7 % |
| 30 grados | 98.8 | -13 % |
| 50 grados | 80.9 | -28 % |
| 60 grados | 65.6 | -42 % |

Y el test de tres vias, que separa la inclinacion de su direccion. Las tres con
el cable corrido a y = 5.0 para que las tres quepan en la misma sala, porque
inclinar corre cada luminaria 3.78 m rio arriba y con el haz en `+y` la primera
caeria fuera del cuarto:

| a donde apunta | contraste, fondo oscuro | contraste, cable entero |
|---|---:|---:|
| **vertical** | **110.6** | **90.7** |
| inclinado 40 hacia las camaras | 89.5 | 76.1 |
| inclinado 40 lejos de las camaras | 86.0 | 72.8 |

La direccion de la inclinacion casi no importa: lo que cuesta es inclinar. El
orden es el mismo con las dos formas de medir el contraste, que se explican mas
abajo.

**Y en la vista de costado tampoco pierde.** Ahi el cordon empata, 93.6
vertical contra 94.6 inclinado, y lo que cambia es el fondo: media de 9.8
niveles con el 20 % del cuadro encendido contra 16.5 con el 56 %. Inclinar el
haz hacia la camara le tira luz al piso y a la pared que estan en cuadro.

**Lo que esto ahorra en el montaje.** Con el haz vertical cada luminaria va
justo encima del tramo que ilumina, en vez de 3.78 m rio arriba. Es mas facil
de colgar y de explicar al jefe de practica.

**Lo que no cambia:** la iluminancia. Medido con
`calculadora_luz.perfil_inclinado`, inclinar 40 grados no baja el peor punto,
lo sube un poco, de 4419 a 4597 lx, porque un cono oblicuo estira su huella a
lo largo del cable. Asi que la perdida de contraste no es falta de luz, es luz
puesta en una cara que la camara no ve.

### 2. La tela pasa de recomendable a obligatoria, y ahora esta medido

| piso | fondo medio del cuadro | cuadro sobre 10 niveles | contraste del cordon |
|---|---:|---:|---:|
| molton negro, albedo 0.04 | 17.5 | 35.8 % | 91.1 |
| madera desnuda, albedo 0.30 | 50.2 | 36.8 % | 101.7 |

El fondo medio se triplica. El contraste del cordon **sube**, porque el piso
claro le rebota luz, y eso no es un argumento a favor de la madera: lo que la
mascara tiene que resolver no es el contraste local del cordon sino cuanto
fondo claro hay que descartar antes de llegar a el.

Los dos albedos son **ASUMIDOS**, no medidos, y son lo primero que hay que
comprobar con el fotometro. Ademas la madera barnizada no es lambertiana: manda
un reflejo especular hacia la camara que este modelo no reproduce, asi que 0.30
difuso es la version optimista del problema.

### 3. La cadena fotometrica cierra, y esta comprobada de punta a punta

De la candela de la ficha del fabricante a los watts de Blender al pixel. Dos
comprobaciones independientes.

**La conversion de candela a watts de un spot, medida y no supuesta.** Un spot
de Blender tiene intensidad `P / (4 pi)` W/sr, con cono o sin el: estrechar el
cono **no** concentra el haz, lo recorta. Un plano lambertiano blanco a 5 m
bajo un spot de `4 pi` W devolvio 0.012715 contra los 0.012732 que predice la
lectura isotropica, razon 0.9986, y un point light de la misma potencia dio el
pixel identico. El factor entre las convenciones plausibles es 4, asi que
equivocarla habria puesto todos estos renders cuatro veces oscuros.

**Los lux, recuperados del piso.** El molton es un plano lambertiano de albedo
conocido, asi que del render lineal en OpenEXR se vuelve atras con
`E = pi L / rho` y de radiometrico a lux con la eficacia luminosa de 97.58
lm/W. Veinticuatro puntos de piso entre 7.1 y 20.4 m, contra lo que predice
`calculadora_luz`:

| variante | razon medido / modelo | rango |
|---|---:|---|
| TV2, haz inclinado | 1.32 | 0.79 a 1.49 |
| TV2RECTO, haz vertical | 1.27 | 0.85 a 1.66 |

El render entrega **un 30 % mas** que el modelo de fuente puntual. Es la
direccion y el orden que el propio modelo anticipa, porque ignora los rebotes
de pared y recorta la cola del haz donde la ficha tiene una. El rango refleja
la otra diferencia conocida: el modelo extiende el haz con un coseno elevado,
n = 8.70 para 45 grados, y la escena usa un cono de angulo de campo 75 grados
con blend 0.8. Los dos coinciden en el medio pico por construccion, no en la
cola, y la cola es justo lo que llena los huecos entre luminarias.

**La primera vez esa razon salio 0.01**, que es exactamente 1/97.58. Faltaba
convertir de radiometrico a fotometrico. Queda escrito porque es el error que
se vuelve a cometer.

## La familia completa

| variante | luminarias | kW | contraste, cable entero | contraste, fondo oscuro | fondo medio | cuadro >10 | peor punto predicho |
|---|---:|---:|---:|---:|---:|---:|---:|
| **TV2RECTO**, la recomendada | 5 | 7.64 | **92.4** | **112.9** | 18.5 | 33.9 % | 4 419 lx |
| TV2, igual pero inclinada 40 | 5 | 7.64 | 77.3 | 91.1 | 17.5 | 35.8 % | 4 597 lx |
| TV2MADERA, sin tela | 5 | 7.64 | 76.0 | 101.7 | 50.2 | 36.8 % | 4 597 lx |
| TV2SEIS, con la sexta y 20 m | 6 | 9.08 | 77.9 | 90.3 | 18.4 | 36.5 % | 5 139 lx |
| TV2PANEL, los doce paneles | 12 | 9.62 | 59.5 | 68.2 | 17.5 | 39.3 % | --- |
| TV2TENSO, cable sin onda | 5 | 7.64 | 76.8 | 76.8 | 17.6 | 35.9 % | 4 964 lx |
| TV2COSTADO, de costado | 5 | 7.64 | 94.6 | --- | 16.5 | 56.3 % | --- |
| TV2COSTADO0, de costado y vertical | 5 | 7.64 | 93.6 | 93.6 | 9.8 | 20.0 % | --- |
| TV2296, global shutter con el 6 mm | 5 | 7.64 | 38.4 | 44.4 | 17.8 | 36.3 % | 4 597 lx |

**Las cinco reales le ganan a los doce paneles supuestos**, 112.9 contra 68.2,
con dos kilovatios menos. No es que cinco proyectores iluminen mas que doce
paneles: es que un proyector concentra su flujo en un cono y un panel lo
reparte en un hemisferio, y en la cuenta de la fila eso pesa mas que el numero
de unidades. Lo que los doce paneles compran es uniformidad, y la uniformidad
no es lo que limita aqui.

**El IMX296 con su 6 mm pierde a la mitad**, 44.4 contra 91.1 en la misma
escena. Coincide con lo medido en la orbita, donde dio 24.3 contra 50.0 sobre
los 16 azimutes. La causa es la misma y no es el ruido: el cordon mide 0.58 px
a 3 m contra 1.72 del IMX477.

## Las dos formas de medir el contraste, y por que hay dos

`tools/medir_barrido.py` descarta las muestras cuyo fondo local pasa de 20
niveles, porque en la orbita y en el estudio con el cable a 5 m lo unico que
puede estar detras del cordon y brillar es una lampara en cuadro.

**Con el cable a 1.5 m ese umbral ya no significa eso.** El piso entra en
cuadro a 5.1 m, asi que detras del cordon hay molton iluminado y pasa de 20 por
su cuenta. En TV2 el filtro descarta el 22 % del cable y sube el contraste de
77.3 a 91.1; en la vista de costado descarta el 100 % y devuelve `nan`.

Por eso se publican las dos: **cable entero** es lo que la mascara tiene que
resolver de verdad, y **fondo oscuro** es la comparable con todo lo medido
antes. El orden de las variantes es el mismo con las dos, asi que ninguna
conclusion de aqui depende de cual se elija.

## Lo que queda por hacer

| | |
|---|---|
| 1 | Volver a correr el ensayo en seco de los criterios A3 sobre TV2RECTO. La uniformidad con conos es mucho peor que con paneles y hay que saber si A3.1 aguanta |
| 2 | Medir con luxometro cada 2 o 3 m el dia de la sesion, con la celula mirando a las luminarias, y comparar contra la tabla de `calculadora_luz` |
| 3 | Medir el albedo del molton y el de la madera, que aqui estan asumidos |
| 4 | Preguntar a Luis por el kit de reflectores de 15 y 30 grados de las STORM |


**Para mirar esto sin leer codigo:** la pagina **Simulation** de
`main.py`, pestana *Estudio TV2*, que lista las variantes con su render
y sus cifras, leidas de `medidas_familia.csv`.

## Donde esta esto en el entregable

Todo lo de aqui esta escrito en ingles en el **capitulo 5 del informe de la
sesion**, `Documentation/LINKU_Experiment_TV2/project/chapter5.tex`, con las
tablas y las figuras. El parametro **L8** del capitulo 4, el haz vertical,
salio de aqui, y es el unico de ese capitulo que contradice lo que el
proyecto venia haciendo.

**Las figuras del entregable son las `_en`.** Los scripts de figuras sacan
las dos versiones, `python tools/fig_cuarto.py` y la misma con
`--idioma en`; el texto vive una sola vez, en espanol, en `tools/idioma.py`,
que avisa de lo que se pidio traducir y no estaba.
`python tools/fig_al_informe.py` las copia a `Images/` con el nombre que usa
el LaTeX.

## Como reproducir

```bash
# las escenas, sin renderizar, para abrirlas en Blender
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant TV2,TV2RECTO,TV2MADERA --blend-only

# la familia completa
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant TV2,TV2MADERA,TV2RECTO,TV2PANEL,TV2SEIS,TV2TENSO,TV2COSTADO,TV2296 \
        --samples 24 --scale 100 --both

# el test de tres vias y el barrido de inclinacion
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant TV2HAZ0,TV2HAZCAM,TV2HAZLEJOS --samples 24 --scale 100
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant TV2 --tilts 0,20,30,50,60 --samples 24 --scale 100

# el render lineal del que salen los lux
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant TV2,TV2RECTO,TV2MADERA --samples 24 --scale 100 --linear

# las medidas y la figura
python tools/medir_cuarto.py --lux --csv-dir SIMULATION/experimentos/estudio_luminarias_reales
python tools/fig_cuarto.py

# los diagramas del montaje
blender --background --python SIMULATION/render_escenario.py -- \
        --only tv2_tres_cuartos,tv2_elevacion,tv2_planta
```

## Archivos

| | |
|---|---|
| `fig_cuarto_luminarias.png` | los lux sobre el cable, la inclinacion y la tela |
| `fig_cuarto_lux.png` | solo el panel de los lux, que es el que entra al informe: dentro del compuesto el texto sale a menos de cuatro puntos cuando LaTeX lo encoge a 15 cm |
| `fig_renders_cuarto.png` | lo que ve la camara en seis variantes |
| `fig_renders_haz.png` | el test de tres vias, visto |
| `medidas_familia.csv` | la tabla de arriba, con la captura de cada fila |
| `medidas_inclinacion.csv` | el barrido de 0 a 60 grados |
| `medidas_lux_piso.csv` | los 72 puntos de piso, medidos contra el modelo |
| `../escenario/tv2_*.png` | los tres diagramas del montaje |
