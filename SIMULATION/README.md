# SIMULATION

Dos escenas de Blender que existen para ser comparadas entre sí: el cable en el
estudio TV2 y el mismo cable en órbita. La medición que vale no es ninguna de
las dos por separado, es **la diferencia entre ellas pasada por la pipeline**.

Blender no abre en la PC de escritorio, así que los `.blend` de `escenas/` están
versionados a propósito: se generan aquí y se abren en la laptop.

## Para mirar las escenas

`escenas/` tiene un archivo por configuración. Ábrelos en Blender y mira
alrededor.

| archivo | qué es | luz | fondo |
|---------|--------|-----|-------|
| `TV2_S_estudio_12lamparas.blend` | el estudio, mirando por el eje del cable | 12 rectángulos de 1 x 1 m a 7 m de altura | el cuarto, 30 x 15 x 10 m, albedo 0.02 |
| `TV2_W_orbita_sol_AM0_estrellas.blend` | **la misma escena en órbita** | un Sol, AM0 | vacío negro con estrellas |
| `TV2_M_estudio_vista_de_costado.blend` | el estudio visto de perfil | las mismas 12 lámparas | el cuarto |

**S y W son la pareja que importa.** Mismo cable, misma onda, mismas dos
cámaras, mismo lente de 8 mm, misma base de 100 mm, y el haz llegando desde la
misma dirección. Lo único que cambia es la iluminación, que es justamente lo
que se quiere medir. Comparar contra `Simulation camera_64MP.blend` en vez de
contra W cambiaría también el sensor y el lente, y entonces una diferencia en
el resultado no se podría atribuir a la luz.

**Las 12 lámparas no salen en el render.** Están marcadas
`visible_camera = False`, que es el requisito R7 del entregable de
iluminación: la luz fuera de cuadro. Iluminan el cable y no aparecen en la
foto. Si las quieres ver, están en el `.blend`, colgadas en fila sobre el
cable.

### Para regenerarlos cuando cambie algo

```bash
blender --background --python SIMULATION/render_studio_iterations.py -- --variant S --blend-only
```

Son archivos derivados: salen del script en veinte segundos. Si al abrir uno no
coincide con lo que dice el código, regenéralo, no lo edites a mano.

## Para renderizar

```bash
# un par estereo, las dos camaras, a resolucion completa
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant S --samples 24 --both

# version lineal, en OpenEXR, para MEDIR fotometria
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant S --samples 24 --linear
```

La salida va a `data/captures/stereo_sim_studio<VARIANTE>_<fecha>/`, con un
`metadata.json` que registra la geometría, las lámparas, el objetivo de
iluminancia y la exposición. Esa carpeta está en `.gitignore`: los renders no
se versionan, se regeneran.

**Para cualquier medida fotométrica, usa `--linear`.** El JPEG pasa por AgX,
que es un mapeo de tonos, así que el nivel del píxel no es proporcional a la
luz que llegó. Medir el rizado de la fila sobre el JPEG dio 73 % donde la luz
tiene 17 %.

## Las dos cosas que más confunden

**1. Subir la potencia no cambia el render.** El objetivo de iluminancia
alimenta dos cosas a la vez: la potencia que necesita la fila y la exposición
con la que se revela el cuadro. Renderizadas cuatro variantes de 3.15 kW a
180 kW, las ocho imágenes salen **idénticas píxel a píxel**. Lo que la potencia
compra es tiempo de obturador en la cámara real, no una imagen más brillante.

**2. Los renders se ven oscuros y están bien.** El cordón llega a 23 niveles
sobre 255 a 8-11 m, con el fondo en 0. Es contraste de sobra para el sensor y
poco para la vista, sobre todo si el visor encoge 4056 px a 600 y reparte un
cordón sub-píxel entre siete vecinos. Para segmentarlo, el tuner tiene un
deslizador de gamma; para verlo, basta mirar al 100 %.

## Los archivos

### Lo que construye las escenas

| archivo | qué hace |
|---------|----------|
| `build_tv2_studio.py` | el estudio: cuarto, cable, fila de lámparas, par estéreo, y `build_sun()` para el caso orbital. Aquí viven las constantes de iluminancia y la forma de la onda del cable |
| `render_studio_iterations.py` | el catálogo de variantes (A a W) y el que renderiza o guarda el `.blend` |
| `build_tv2_room.py` | la escena orbital anterior, 40 x 20 x 10, con Sun. Precede al par S/W |
| `render_stereo_pair.py` | render de un par suelto |

### Los `.blend` que no genera el script

| archivo | qué es |
|---------|--------|
| `Simulation camera_64MP.blend` | la referencia orbital, la que produjo `data/captures/stereo_20260217_163259`. **Su Sol está en 3 W/m² y debería ser 1361.** La imagen sale bien porque la exposición está en 0 y compensa, pero los números del archivo están 454 veces abajo. Además su `BézierCurve` lleva cuatro modificadores HOOK: editar los puntos de control no hace nada, mandan los Empties |
| `Simulation camera_12MP.blend` | lo mismo con cámaras de 12 MP y lente de 6 mm |
| `Simulation_DarkBox.blend`, `_2.blend` | la caja oscura, anterior al cuarto TV2 |
| `TV2_Room_40x20x10.blend` + `_params.json` | la escena de `build_tv2_room.py` guardada |
| `Simulacion_DarkBox.blend1`, `Untitled*.blend1` | copias de seguridad huérfanas, sin `.blend` hermano. Si abres alguna, guárdala como `.blend` y borra el `.blend1` |

## Lo que todavía está mal y no se ha tocado

- **El Sol de `Simulation camera_64MP.blend` sigue en 3 W/m².** Son dos valores,
  `energy = 1361` y `exposure = -8.76`, y la imagen queda idéntica. Hay que
  hacerlo antes de usar esa escena para comparar contra el estudio, porque los
  dos lados tienen que estar en la misma escala.
- **La fila de rectángulos no cumple R3 ni R4.** Da 500 mm de penumbra por
  metro contra los 35 que pide R3, y 21.8 % de no uniformidad contra el 5 % de
  R4. No es cuestión de potencia: colimar se paga como 1/sen² del semiángulo.
  Por eso el estudio y la órbita conviven aquí en vez de pretender que son lo
  mismo.
