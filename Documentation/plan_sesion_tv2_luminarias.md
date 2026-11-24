# Plan de la sesión TV2 con las luminarias reales

Escrito el 24 de noviembre de 2026, después de la respuesta de Luis Domínguez
del 23. **Sustituye al diseño de doce paneles de 1 x 1 m**, que era una
suposición nuestra y ya no aplica.

Todos los números de luminaria salen de las fichas del fabricante,
versionadas en `Sources/luminarias/` de este mismo entregable. Los de
iluminancia salen de `tools/calculadora_luz.py`, que lee esas fichas.

## Lo que cambia respecto de lo simulado hasta hoy

| | lo simulado | lo que hay |
|---|---|---|
| fuentes | 12 paneles de 1 x 1 m | **4 a 6 proyectores puntuales** |
| distribución | difusa, a lo largo | haz cónico de 45 grados |
| altura sobre el cable | 2.0 m | **4.5 a 6 m**, forzado por la cobertura |
| potencia | 4.88 kW | 7.6 a 9.1 kW |
| uniformidad | 21.8 % de no uniformidad | peor/mejor 0.39, mucho peor |

**La diferencia que manda es la cobertura.** Un panel de 1 x 1 m a 2 m de
altura baña su tramo de cable; un proyector con reflector de 45 grados a 2 m
ilumina un círculo de 1.66 m y deja el resto a oscuras. Calculado con cinco
unidades a 2 m sobre el cable, el peor punto da **38 lx** contra los 3600 del
objetivo, con picos de 44 648 lx: no es poca luz, es luz mal repartida.

La única forma de que un cono de 45 grados cubra 4 o 5 m de cable es alejarlo,
y alejarlo cuesta iluminancia con el cuadrado. Esa es toda la tensión del
diseño.

## El equipo que hay

| | unidades | CCT | potencia | reflector en la caja | parpadeo |
|---|---:|---|---:|---|---|
| **Aputure LS 1200d Pro** | 2 | 5600 K fijo | 1440 W | 15, 30 y 45 grados | 2000 FPS libre de parpadeo |
| **Aputure STORM 1200x** | 4 | 2500 a 10000 K | 1550 W | **solo 45 grados** | modo High-Speed |

Intensidad en el eje, calculada de la tabla fotométrica de cada ficha
(`I = lux * d^2`, comprobado contra las cuatro distancias publicadas, menos
del 5 % de dispersión):

| reflector | LS 1200d Pro | STORM 1200x |
|---|---:|---:|
| 15 grados | 724 045 cd | 836 700 cd |
| 30 grados | 217 055 cd | 372 538 cd |
| **45 grados** | **128 365 cd** | **178 592 cd** |
| sin reflector | 70 229 cd | 78 280 cd |

El STORM es un 39 % más intenso con el mismo reflector. Mezclarlos empeora la
uniformidad, así que en la fila van **alternados**, nunca las dos LS juntas
en un extremo.

## Las tres configuraciones que sirven

Cable a 1.5 m, reflector de 45 grados, altura de la fila optimizada:

| luminarias | largo del cable | altura fila | peor punto | uniformidad | potencia |
|---|---:|---:|---:|---:|---:|
| 6 (4 STORM + 2 LS) | 24.5 m | 6.50 m | 2 951 lx | 0.39 | 9.08 kW |
| **6 (4 STORM + 2 LS)** | **20.0 m** | **5.75 m** | **4 370 lx** | 0.41 | 9.08 kW |
| **5 (4 STORM + 1 LS)** | **18.0 m** | **6.00 m** | **4 047 lx** | 0.45 | 7.64 kW |
| 4 (4 STORM) | 16.0 m | 7.50 m | 3 388 lx | 0.66 | 6.20 kW |

### La recomendación

**Cinco luminarias, cable de 18 m a 1.5 m de altura, fila a 6.0 m.** Es lo que
Luis ofreció, cumple el objetivo con 12 % de margen y es la única que no
depende de que nos presten una sexta unidad.

**Si se quiere conservar los 24.5 m**, se puede, con las seis y aceptando
2 951 lx. Eso es el 82 % del objetivo de 3600, **pero el objetivo de 3600 lx
está dimensionado para los tres sensores candidatos, y el que vamos a llevar
es el IMX477, cuyo piso propio es 2320 lx**. Con 2 951 lx el IMX477 tiene
27 % de margen. Es una decisión legítima y hay que registrarla como tal, no
dejarla pasar en silencio.

## Lo que hay que bajar el cable, y por qué ahora es obligatorio

Para que el cono cubra su tramo hacen falta entre 4.5 y 6 m entre la fila y el
cable. Con un techo de 10 m, eso deja el cable a 4 m como mucho, y a 1.5 m se
monta a mano sin andamio.

Ya está medido lo que cuesta bajarlo (ver `SIMULATION/experimentos/sol_orbita/RESULTADOS.md`,
apéndice): el cable se ve igual, la potencia no cambia, pero el piso entra en
cuadro a 5.1 m en vez de a 17, y la fracción de cuadro encendido pasa de 5.1 %
a 32.8 %. **Por eso hace falta molton negro en el piso** desde los 5 m en
adelante. Esa es ahora una condición del montaje, no una mejora opcional.

## Lo que midieron los renders del 24 de noviembre

Hasta aquí el plan salía de `tools/calculadora_luz.py`, que es fotometría de
fuente puntual. El 24 se reconstruyó la escena de Blender con estas cinco
luminarias y se renderizó la familia entera. Está en
`SIMULATION/experimentos/estudio_luminarias_reales/RESULTADOS.md`, y tres
cosas de ahí cambian lo que hay que hacer en el estudio.

**1. El haz va VERTICAL, no inclinado 40 grados.** Esta es la que cambia una
instrucción de montaje. Todas las simulaciones anteriores inclinaban el haz,
con el argumento de que un haz desde arriba ilumina la cara de arriba del
cilindro mientras las cámaras le miran el costado. Ese argumento vale en la
vista de costado y no en la principal, que mira **a lo largo** del cable: ahí
la cámara ve el limbo del cilindro, cuyas normales apuntan en x y en z, y el
haz vertical ilumina justamente una de ellas.

| inclinación | contraste del cordón | respecto del vertical |
|---:|---:|---:|
| **0 grados** | **112.9** | --- |
| 20 grados | 104.8 | -7 % |
| 30 grados | 98.8 | -13 % |
| 50 grados | 80.9 | -28 % |
| 60 grados | 65.6 | -42 % |

No es falta de luz: inclinar 40 grados sube el peor punto de 4419 a 4597 lx,
porque un cono oblicuo estira su huella. Es luz puesta en una cara que la
cámara no ve. En la vista de costado el cordón empata, 93.6 contra 94.6, y el
fondo mejora mucho con el haz vertical: media de 9.8 niveles con el 20 % del
cuadro encendido, contra 16.5 con el 56 %.

**Para el montaje esto simplifica:** cada luminaria va justo encima del tramo
que ilumina, no 3.78 m río arriba.

**2. El molton deja de ser una recomendación.** Medido, el piso de madera
triplica el fondo medio del cuadro, de 17.5 a 50.2 niveles. Los dos albedos
siguen asumidos, 0.04 y 0.30, y son lo primero que hay que comprobar con el
fotómetro.

**3. La cadena fotométrica cierra.** Recuperando los lux del piso de molton
desde el render lineal, que es un plano lambertiano de albedo conocido, el
render entrega un 30 % más que la calculadora (razón mediana 1.27 a 1.32 sobre
24 puntos). Es la dirección y el orden que la propia calculadora anticipa, por
ignorar los rebotes de pared. O sea que **las cifras de este plan son la cota
pesimista**, que es como conviene que sea.

Un cuarto resultado que no cambia nada pero conviene saber: las cinco
luminarias reales dan más contraste que los doce paneles de 1 x 1 m que
supóniamos, 112.9 contra 68.2, con dos kilovatios menos. Un proyector
concentra su flujo en un cono y un panel lo reparte en un hemisferio.

## Ajustes de las luminarias para la sesión

- **Haz vertical, apuntando recto abajo.** Medido, no supuesto: inclinarlo
  cuesta entre el 7 y el 42 % del contraste del cordón según el ángulo, y no
  compra luz. Cada luminaria va encima del tramo que ilumina.
- **5600 K en los STORM**, para igualar a las LS, que son de CCT fijo. Mezclar
  temperaturas mete un gradiente de color a lo largo del cable que no aporta
  nada y ensucia la segmentación.
- **Modo High-Speed activado en los STORM.** Es el que garantiza ausencia de
  parpadeo a tiempos cortos. Tiene dos consecuencias que hay que conocer: la
  salida mínima sube al 20 % y los modos FX se desactivan. Ninguna nos afecta.
- **Las LS no necesitan nada**: 2000 FPS libres de parpadeo, y traen selección
  de frecuencia si hiciera falta.
- **Sin difusores ni softboxes.** Cada capa de difusión ensancha el haz y
  tira la iluminancia, que es justo lo que falta.
- **Atenuación por arriba, no por abajo**: si sobra luz se cierra el
  diafragma, no se baja la luminaria, para no entrar en el régimen donde el
  parpadeo importa.

## Lo que Jose ya respondio, 24 de noviembre

- **Fecha: viernes 11 de diciembre.** El jueves 10 no es posible, Jose y
  Neils solo tienen libre el viernes. Pedido a Luis en
  `correo_luis_cierre_viernes11.md`.
- **Largo del estudio: de 26 a 30 m**, a confirmar con Luis.
- **El piso es de madera**, asi que la tela negra pasa de recomendable a
  obligatoria. Hay que confirmar si la tela la pone el estudio.
- **Si hay parrilla.** Las luminarias se cuelgan desde arriba, no hacen
  falta tripodes. Resuelto, no se pregunta.
- **La energia alcanza.** El estudio maneja habitualmente mas luces que
  las cinco nuestras. Resuelto, no se pregunta.
- **Cinco luces bastan, con el cable a 18 m.** Verificado: 4 STORM mas
  1 LS a 6.00 m dan 4047 lx en el peor punto, el 112 % del objetivo. El
  limite de esa configuracion es 19 m de cable (3640 lx, 101 %); a 20 m
  cae al 91 %, que sigue siendo el 142 % del piso propio del IMX477.
  Con las seis se llegaria a 22 m.

## Lo que queda por preguntarle a Luis

Solo dos cosas, las unicas que ni Jose ni el calculo pueden contestar.

1. **¿Tienen el STORM 1200x Reflector Kit** (los de 15 y 30 grados)? Los
   STORM solo traen el de 45 en la caja. Con el de 30 habria mas margen.
2. **¿Podemos cubrir el piso de madera con molton negro**, unos 20 x 3 m, y
   lo tiene el estudio o lo llevamos nosotros?

Mas el contacto de los dos jefes de practica, y el procedimiento con costos y
permisos que el mismo ofrecio mandar.

## Lo que falta hacer de nuestro lado

| | tarea |
|---|---|
| 1 | ~~Rehacer la escena de Blender con 5 proyectores puntuales~~ **hecho el 24 de noviembre**, `build_projector_row` con las candelas de la ficha |
| 2 | Volver a correr el ensayo en seco de los criterios A3 sobre esa escena: la uniformidad empeora mucho y hay que saber si A3.1 aguanta |
| 3 | Medir con luxómetro el día de la sesión, cada 2 o 3 m, con la célula mirando a las luminarias, y comparar contra esta tabla |
| 4 | Decidir y registrar el largo del cable antes de la sesión, porque cambia el criterio A3.5 |

## Cómo reproducir estos números

```bash
python tools/calculadora_luz.py --listar
python tools/calculadora_luz.py --mezcla "storm1200x:45:4,ls1200d_pro:45:1" \
       --altura-luces 6.0 --altura-hilo 1.5 --hilo-y1 20.0 --onda
python tools/calculadora_luz.py --fixture storm1200x --reflector 45 --n 5 \
       --altura-hilo 1.5 --buscar-altura
```

La calculadora documenta sus tres aproximaciones: el perfil del haz fuera del
eje se modela con un coseno elevado, no hay rebotes de pared y no hay pérdidas
por difusores ni suciedad. Las dos primeras hacen que el render de Cycles dé
algo más, y la tercera que la realidad dé algo menos. **Lo que mida el
luxómetro en la sesión manda sobre todo esto.**
