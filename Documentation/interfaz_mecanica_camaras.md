# Interfaz mecánica del prototipo de cámaras LINKU

Qué tiene que aceptar la placa estéreo, y qué adaptadores hacen falta.
Fecha: 5 de noviembre de 2026.

## El objetivo

Una sola placa estéreo que acepte, sin rediseño, los tres módulos que el
proyecto quiere comparar:

1. **Raspberry Pi HQ Camera (IMX477)**, que es la que está montada hoy.
2. **Raspberry Pi Global Shutter Camera (IMX296)**, el obturador global.
3. **Arducam 64MP Pi Hawk-eye (OV64A40)**, el de más resolución.

El prototipo se construye con el IMX477, que es lo que hay. Los otros dos
tienen que poder entrar después sin volver a fabricar la placa.

## Lo que dicen los planos oficiales

Medidas tomadas de los planos mecánicos de Raspberry Pi, no de fichas
comerciales ni de estimaciones.

| | HQ Camera (IMX477) | Global Shutter (IMX296) | Hawk-eye (OV64A40) |
|---|---|---|---|
| Placa | 38.0 x 38.0 mm | 38.0 x 38.0 mm | 25 x 24 mm |
| Espesor del PCB | 1.4 mm | 1.4 mm | no publicado |
| Agujeros | 4 x ø2.5 mm | 4 x ø2.5 mm | no publicado |
| Separación entre agujeros | 30.0 x 30.0 mm | 30.0 x 30.0 mm | no publicado |
| Borde a centro de agujero | 4.0 mm | 4.0 mm | no publicado |
| Montura de lente | CS, ø36 exterior | CS, ø36 exterior | lente integrada, sin rosca |
| Profundidad total | 18.58 mm | 25.07 mm | no publicado |
| Tapa trasera | sin tapa | 39.5 x 39.5 mm, R4.75 | no publicado |

Fuentes: plano mecánico de la HQ Camera versión CS
(`RP-008200-DS-1-hq-camera-cs-mechanical-drawing.pdf`) y plano mecánico de la
Global Shutter Camera (`RP-008195-DS-1-gs-camera-mechanical-drawing.pdf`),
ambos del repositorio de datasheets de Raspberry Pi. Para la Hawk-eye, el
tamaño de placa 25 x 24 mm viene de la ficha del distribuidor y la
documentación de Arducam solo dice que conserva el formato v1/v2, sin dar
números.

## Lo primero que esto resuelve

**La HQ y la Global Shutter son mecánicamente la misma cámara.** Misma placa
de 38 x 38, mismos cuatro agujeros de ø2.5 sobre una retícula de 30 x 30,
misma montura CS, mismo eje óptico en el centro de esa retícula.

Entonces para intercambiar entre el sensor de hoy y el obturador global **no
hace falta ningún adaptador**. La placa se diseña con esa huella y las dos
entran directo. La única diferencia es la profundidad, 25.07 contra 18.58 mm,
y esos 6.49 mm están delante del plano de montaje, no detrás, así que no mueven
los agujeros ni el eje.

**El adaptador que hay que fabricar es uno solo, el de la Hawk-eye.** Es una
pieza que recibe el módulo de 25 x 24 mm y presenta hacia la placa la misma
interfaz de 38 x 38 con agujeros a 30 x 30.

## Lo que el adaptador tiene que cumplir

**1. Repetibilidad antes que precisión.** Un error de posición del eje óptico
no arruina la medición, porque la calibración lo absorbe: queda registrado en
los parámetros extrínsecos. Lo que sí la arruina es que la posición **cambie**
entre que se calibra y que se mide. Por eso el adaptador necesita algo que
ubique el módulo siempre en el mismo sitio, pines de centrado o un resalte
mecanizado, y no solo agujeros pasantes con holgura.

**2. El eje óptico queda donde está hoy.** En las cámaras de 38 x 38 el eje
cae en el centro de la retícula de agujeros. El adaptador debe dejar el eje de
la Hawk-eye en ese mismo punto, para que la distancia entre los dos ejes de la
pareja estéreo siga siendo la misma con cualquier combinación de módulos.

**3. La separación entre cámaras es 100 mm entre ejes ópticos**, que es el
valor con el que trabaja el software hoy (`baseline_mm` en
`config/camera_config.py`). Si conviene cambiarla, se cambia, pero tiene que
quedar fija y conocida.

**4. Rigidez.** Si la geometría entre las dos cámaras se mueve después de
calibrar, toda la reconstrucción 3D queda mal y no hay forma de detectarlo
mirando las imágenes. La unión entre las dos cámaras debe ser rígida, no
ajustable por el usuario.

**5. El cable plano sale por arriba.** En las placas de 38 x 38 el conector
CSI está en el borde superior. El adaptador y la placa no deben pellizcarlo ni
obligarlo a un radio cerrado.

**6. Distancia de trabajo ajustable.** Los tres módulos tienen campos de
visión muy distintos: 42.9 grados la HQ con el lente de 8 mm, 71.9 grados la
Hawk-eye con su lente integrada y 17.7 grados el obturador global con el
teleobjetivo de 16 mm. A la misma distancia los tres ven un largo de hilo
completamente diferente, así que el conjunto tiene que poder acercarse o
alejarse del hilo, aunque la geometría entre las dos cámaras quede fija.

## Lo que falta para poder pedir la pieza

1. **Patrón de agujeros y posición del eje óptico de la Hawk-eye.** Arducam no
   lo publica. Se consigue midiendo el módulo físico, si está disponible, o
   pidiéndole el plano a Arducam por su formulario de soporte. Es el único
   dato que bloquea el diseño del adaptador.
2. **Si el enfoque de la Hawk-eye se puede fijar.** La documentación de Arducam
   habla de enfoque motorizado controlado por software. El proyecto exige que
   el enfoque quede bloqueado antes de calibrar y no se toque después, porque
   mover el enfoque cambia la distancia focal y un 1 % de deriva es un 1 % de
   error de escala en toda distancia reconstruida. Un enfoque motorizado sin
   bloqueo mecánico hay que verificar que se pueda fijar por software y que
   no se reinicie al arrancar.
3. **Adaptador C-CS para el teleobjetivo de 16 mm**, que es el único lente con
   el que el obturador global sirve. Con el lente de 6 mm el hilo mide 0.59 px
   a 3 m, por debajo de un píxel, y no hay segmentación posible. Con el de
   16 mm mide 1.57 px, equivalente a lo que da el sensor de hoy.

## Consecuencia para el software, aparte

Cada módulo necesita su propia calibración: cambiar de sensor cambia la
distancia focal en píxeles, el tamaño de imagen y la separación entre centros
ópticos. El software ya permite varias calibraciones y cambiar entre ellas
(`switch_calibration_file`), falta fijar la convención de nombres, una por
sensor.
