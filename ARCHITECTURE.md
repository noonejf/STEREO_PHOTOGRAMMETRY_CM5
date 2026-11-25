# Mapa del repositorio

Para alguien que entra nuevo. Esto dice **dónde está cada cosa y por qué está
ahí**; el porqué de las decisiones de la pipeline está en
[`CLAUDE.md`](CLAUDE.md), que es largo y vale la pena.

## Qué es esto en una frase

Proyecto **LINKU** (PUCP dentro de APSCO): un sistema de visión estéreo que
**mide un cable delgado tendido entre dos satélites**, en 3D, a oscuras.

Dos cosas que el nombre de la carpeta no dice:

- **No devuelve una nube densa.** Devuelve escalares métricos del cable:
  longitud de arco en metros, rectitud, rango de profundidad, diámetro y
  curvatura. La nube dispersa es un subproducto. "Stereo photogrammetry" es
  una etiqueta histórica.
- **No es la tesis.** La tesis es AYNISAT, que vive en otro repo. INTISAT es
  un tercer proyecto. Nada de aquí entra en los otros dos.

Hardware: Raspberry Pi CM5 con dos Arducam HQ 477 (IMX477, 12 MP) y un lente
Arducam C1508ZM04 de 8 mm f/1.6.

## Lo primero que hay que correr

```bash
python3 main.py
```

**No hace falta tener cámaras.** Si no encuentra `libcamera` o los sensores,
arranca en *Processing Only Mode*: se pueden procesar capturas archivadas pero
no tomar nuevas. Ese es el camino normal en una PC de desarrollo con Windows,
y es donde se prueba casi todo.

No hay suite de tests. Lo que hay son scripts de medición en `tools/` que
puntúan un cambio contra datos: ésa es la forma de verificar aquí, y está
explicada en [`tools/README.md`](tools/README.md).

## El mapa

| Carpeta | Qué vive ahí | Depende de |
|---------|--------------|------------|
| `main.py` | arranque, chequeos y el tema de la aplicación | PyQt5 |
| `gui/` | las seis páginas de la ventana única y sus diálogos | `processing/`, `camera/`, `utils/` |
| `processing/` | la pipeline de medición: máscara, trazado, rectificación, triangulación, métricas | OpenCV, numpy, scipy, scikit-image |
| `camera/` | captura estéreo y calibración, incluida la guiada | los tres módulos de guía **no importan ni cámara ni PyQt**, a propósito |
| `config/` | resolución, sensor, tablero ChArUco, comandos de `libcamera` | nada |
| `utils/` | log, archivos, los dos datasets de entrenamiento | nada |
| `synthetic/` | generador de datos sintéticos y los tres entrenadores | scikit-learn |
| `calculate_cam/` | la calculadora óptica (DOF, FOV, píxeles por milímetro) | matplotlib |
| `tools/` | medir, auditar y publicar. Nunca se importan desde la aplicación | ver su README |
| `SIMULATION/` | las escenas de Blender y los experimentos de iluminación | Blender, solo fuera de la Pi |
| `Documentation/` | los entregables LaTeX y los documentos de trabajo | tectonic, vía `compilar.ps1` |
| `data/` | calibraciones, capturas, datasets, modelos y resultados | --- |

### La ventana

Una sola `QMainWindow` con un riel de iconos y un `QStackedWidget`
([`gui/main_window.py`](gui/main_window.py)):

| # | Página | Clase | Archivo |
|---|--------|-------|---------|
| 0 | Dashboard | se arma inline | `gui/main_window.py` |
| 1 | Calibration | `CalibrationPage` | `gui/calibration_dialog.py` |
| 2 | Processing | `ProcessingPage` | `gui/processing_dialog.py` |
| 3 | AI | `AIPage` | `gui/ai_page.py` |
| 4 | Optics | `OpticsPage` | `gui/optics_page.py` |
| 5 | Simulation | `SimulationPage` | `gui/simulation_page.py` |

Las páginas 4 y 5 son lectoras: la de óptica reusa la ventana de
`calculate_cam/` reparentando su widget central, y la de simulación lee las
CSV que dejaron los scripts de medición. **Ninguna de las dos recalcula
nada**, y ésa es la propiedad que hay que conservar: si una cifra de la
pantalla discrepa de un entregable, el error está en la CSV o en el script que
la escribió, nunca en la página.

## Por dónde empezar a leer, según a qué vienes

**A medir un cable.** `gui/processing_dialog.py` orquesta, y los ocho pasos de
la pipeline están tabulados en `CLAUDE.md`. El corazón es
`processing/stereo_processor.py` y `processing/wire_metrics.py`. La única
suposición que hay que tener en la cabeza desde el principio es que el paso 5
empareja **paramétricamente**, no epipolarmente.

**A calibrar.** `camera/guided_session.py` es el bucle, `camera/
calibration_guidance.py` decide qué cuadro sirve, `gui/guided_calibration.py`
es el hilo y el panel. Los tres primeros corren sin hardware, así que
`tools/replay_guided_session.py` los ejercita sobre sesiones archivadas.

**A entrenar o evaluar un modelo.** `synthetic/README.md` primero. El generador
está en `synthetic/generate.py` y los tres entrenadores son
`train_mask.py`, `train_pairings.py` y `train_endpoints.py`. El veredicto
nunca es la métrica del entrenador: es `synthetic/evaluate.py` sobre escenas
frescas.

**A la iluminación y la simulación.** `SIMULATION/README.md` primero, después
`SIMULATION/experimentos/*/RESULTADOS.md`, que son el cuaderno de cada
experimento. Para mirar los resultados sin leer código, la página Simulation de
la aplicación.

**A escribir un entregable.** `Documentation/`, uno por carpeta, compilados
con `.\compilar.ps1 "Documentation\<Carpeta>"`. Las fuentes citadas van en el
`Sources/` de cada entregable y en su `bibs/sample.bib`.

## Lo que hace tropezar

Cinco cosas que no se deducen mirando los nombres de los archivos.

**`edge_detection_tuner.py` está en la raíz y parece una herramienta de
desarrollo, pero es la pipeline.** Tiene su propio `main()`, y aun así
`gui/processing_dialog.py` importa de él `open_cable_detection_tuner_with_switch`.
Es la **única** forma en que la aplicación produce máscaras del cable. No se
mueve ni se borra.

**Hay código muerto a propósito.** `processing/wire_matcher.py` y
`StereoProcessor.process_wire_masks()` no los llama nadie y se conservan
porque son el reemplazo obvio si la suposición paramétrica del paso 5 empieza
a fallar. Llevan un cartel `[SIN USO EN EL FLUJO ACTUAL]` en su docstring. Si
agregas más, márcalo igual.

**`data/` está versionado a medias, y la regla del `.gitignore` llegó tarde.**
`data/captures/` y `data/calibration/` tienen 180 y 1073 archivos versionados de
antes de que existiera la regla que los excluye, así que la regla no los
afecta. Lo nuevo sí queda fuera. Decide a conciencia antes de agregar.

**El repositorio trabaja en español y entrega en inglés.** Los entregables de
`Documentation/` están en inglés; los comentarios, los `RESULTADOS.md` y los
scripts de figuras, en español. Las figuras salen en los dos idiomas desde una
sola fuente: el texto vive en español dentro del script y `tools/idioma.py` lo
traduce con `--idioma en`.

**Lo que está medido, lo que está derivado y lo que está asumido no es lo
mismo.** `Documentation/LINKU_CameraPayload_Paper_Dossier.md` etiqueta cada
afirmación del proyecto con su estado y lista en su sección 11 las
contradicciones entre nuestros propios entregables. Es el documento vigente.
`INFORME_TECNICO_PROYECTO_LINKU.md` es una foto del 16 de febrero de 2026 y
varias de sus afirmaciones fueron contradichas después por mediciones: se
conserva como registro, no se cita como estado actual.

## Las dos cosas que no se tocan

- `Documentation/LINKU_Project_APSCO_Deliverable_D5_Report__submitted___v2_`
  fue entregado a APSCO. **No se edita.** El que se trabaja es el casi
  idéntico `LINKU_Project_SubDeliverable_D5_CameraSystem_Report__v2_`. Busca
  `submitted` en el nombre de la carpeta antes de tocar nada bajo
  `Documentation/`.
- El capítulo 2 de `Documentation/LINKU_Experiment_TV2` registra los criterios
  de aceptación **por adelantado**. No se re-derivan al analizar; enmendarlos
  significa una revisión fechada de ese capítulo.
