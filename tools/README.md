# tools

Scripts que se corren a mano. **La aplicación no importa ninguno de ellos**,
y la dependencia va solo en un sentido: `tools/` importa de `processing/`,
`camera/` y `synthetic/`, nunca al revés. Si algo de aquí hiciera falta en
tiempo de ejecución, el sitio correcto es el paquete, no esta carpeta.

Casi todos corren sin cámara, sin Blender y sin GUI. Los que no, lo dicen.

Son cuatro familias y sirven para cosas distintas.

## 1. Verificar un cambio en el trazado o en la segmentación

Aquí no hay tests unitarios: **la forma de verificar es puntuar el cambio
contra datos**, y el veredicto es siempre F1 contra la línea central
verdadera sobre escenas frescas, nunca la cobertura que el propio trazador
reporta, que cuenta píxeles visitados y premia vagar.

| script | qué contesta |
|--------|--------------|
| `audit_tracer_jumps.py` | ¿cuánto cable se inventa el trazador entre dos vértices? Lee la columna **px inventados**, no el conteo de saltos |
| `benchmark_geodesic_tracer.py` | geodésico contra `SmartWireTracker`, por familia de forma |
| `benchmark_branch_scorer.py` | el scorer aprendido contra la fórmula, de punta a punta |
| `benchmark_endpoint_model.py` | el buscador de extremos aprendido contra el clásico |
| `sweep_endpoint_gate.py` | barre los ajustes del decodificador de extremos |
| `check_fused_strands.py` | ¿el trazado recorre dos veces un tramo donde el cordón se dobla? |
| `figure_compare_tracers.py` | la misma máscara trazada por cada trazador, lado a lado |
| `compare_mask_models.py` | dos pickles de segmentador sobre los pares reales |
| `retune_mask_postproc.py` | re-ajusta umbral y cierre sin reentrenar |
| `measure_real_samples.py` | mide el archivo real y compara el generador contra él |

## 2. Calibración, sin hardware

| script | qué hace |
|--------|----------|
| `analyze_calibration_sessions.py` | diagnóstico retrospectivo de las sesiones archivadas |
| `replay_guided_session.py` | repasa una sesión guardada cuadro por cuadro, por el mismo bucle |

## 3. Medir la simulación

Leen los renders de `data/captures/` y escriben una CSV al lado del
experimento, en `SIMULATION/experimentos/<experimento>/`. **Esa CSV es la
fuente de verdad**: de ella salen las figuras, las tablas del entregable y la
página Simulation de la aplicación, y ninguna de las tres recalcula nada.

| script | qué mide |
|--------|----------|
| `medir_barrido.py` | contraste del cable en un barrido angular. Define el criterio que usan los otros dos |
| `medir_esfera.py` | la rejilla azimut por inclinación. Importa `medir` del anterior, no una copia |
| `medir_cuarto.py` | el cuarto TV2 con las luminarias reales, y comprueba la fotometría contra el modelo |
| `calculadora_luz.py` | cuántos lux le caen al cable, sin renderizar |
| `run_comparison_cases.py` | ensayo en seco de los criterios A3 sobre los casos renderizados |
| `collect_sweep.py` | junta un barrido en una carpeta de experimento |

## 4. Publicar: figuras, copias y visores

| script | qué produce |
|--------|-------------|
| `idioma.py` | **no se corre solo.** Es el diccionario que traduce las figuras al inglés |
| `fig_cuarto.py`, `fig_esfera.py`, `fig_renders.py` | las figuras de cada experimento, en los dos idiomas con `--idioma en` |
| `fig_al_informe.py` | copia las figuras `_en` a `Images/` del informe de la sesión con el nombre que usa el LaTeX |
| `armar_vistas_simulacion.py` | las copias chicas que **sí se versionan**, para que la página Simulation funcione en un clon limpio |
| `armar_esfera_web.py`, `armar_visor.py` | el visor HTML publicable. Superado por la página Simulation de la aplicación; se conserva porque lo publicado sigue vivo |
| `armar_presentacion_luis.py` | la presentación para la reunión con el estudio |

### Las dos reglas de las figuras

**El texto vive una sola vez, en español, dentro del script.** `idioma.py` lo
traduce al vuelo y avisa al terminar de lo que se le pidió traducir y no
estaba. La clave del diccionario es la frase en español, no un identificador,
para que una figura sin traducir salga entera en español en vez de mostrar
`titulo_panel_3`.

**Se realza con gamma antes de encoger, nunca al revés.** Encoger primero
reparte un cordón de 1.7 px entre tres vecinos y lo borra. Y donde se vea una
imagen realzada hay que decirlo: la curva es monótona, así que no inventa un
píxel ni cambia el orden de dos, pero la copia deja de ser proporcional a la
luz y **ninguna medida sale de ella**.
