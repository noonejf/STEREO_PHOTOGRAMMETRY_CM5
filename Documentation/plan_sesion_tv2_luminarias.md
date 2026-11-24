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

## Ajustes de las luminarias para la sesión

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

## Lo que hay que preguntarle a Luis

1. **¿Tienen el STORM 1200x Reflector Kit** (los de 15 y 30 grados)? Los
   STORM solo traen el de 45 en la caja. Con los de 30 habría más margen.
2. **¿Cuánta potencia hay disponible**, y en cuántos circuitos? Son 7.6 a
   9.1 kW continuos. No es una pregunta menor con seis cabezas de 1.5 kW.
3. **¿De qué color es el piso y podemos cubrirlo** con molton negro en unos
   20 x 3 m? Es condición para que la medición funcione.
4. **¿Cuál es el largo útil real del estudio?** Todo lo simulado asume 30 m.
5. **¿Hay parrilla, y a qué altura?** Necesitamos colgar a 6 m o montar en
   trípodes de esa altura.
6. **¿Jueves 10 o viernes 11?** Hay que elegir uno.

## Lo que falta hacer de nuestro lado

| | tarea |
|---|---|
| 1 | Rehacer la escena de Blender con 5 proyectores puntuales en vez de 12 paneles, con el cono de 45 grados y la intensidad de la ficha |
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
