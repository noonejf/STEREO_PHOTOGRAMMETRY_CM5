# Cola de renders

Lo que falta renderizar, en una lista, para que no se renderice mientras se
trabaja. Decision de Jose el 26 de noviembre de 2026: los renders del estudio
tardan unos **4 minutos por angulo con las dos camaras** y dejan la maquina
inservible mientras corren, asi que se apuntan aqui y se lanzan al final del
dia.

Lo corre `tools/correr_cola_renders.ps1`, que **solo renderiza**: deja
carpetas en `data/captures/` y una bitacora en `logs/cola_renders_*.log`, y no
escribe ninguna CSV. Medir es el paso de la mañana siguiente, a mano, porque
una medida mala se publica sola en las tablas del capitulo 5.

## Programado para hoy, 18:30

Tarea de Windows `LINKU_cola_renders`. Tres barridos de inclinacion, los tres
sobre la **misma sala, el mismo cable y las mismas cinco luminarias reales**,
con la unica diferencia de a donde apuntan. Unos 65 minutos en total.

| # | barrido | variante | angulos | para que |
|---|---------|----------|---------|----------|
| 1 | el haz viaja **lejos** de las camaras | `TV2HAZLEJOS` | 0 a 60, paso 10 | es la unica direccion que ilumina la cara del cable que la camara ve, y hoy solo esta medida a 40 grados |
| 2 | el haz viaja **hacia** las camaras | `TV2HAZCAM` | 0 a 60, paso 10 | la direccion de todas las variantes de paneles, para que la comparacion sea angulo contra angulo y no solo a 40 |
| 3 | el haz **de costado**, atravesando el cable | `TV2HAZLADO` | 0, 20, 40, 60 | direccion nueva: cae sobre el limbo del cilindro, que es lo que la camara resuelve de cada tramo |

Dos controles que salen gratis de que sean la misma escena:

- A **inclinacion 0** los tres barridos son la misma escena, y tienen que dar
  la misma cifra. Si no la dan, el barrido no esta midiendo la direccion.
- Esa escena a 0 ya existe como `TV2HAZ0`, medida en el test de tres vias, asi
  que hay una tercera cifra con la que cuadrarlos.

**Lo que esto NO es.** El barrido publicado en `tab:tilt` del capitulo 5 corre
sobre la geometria `TV2`, con el cable de y = 2 a 20. Estos tres corren sobre
la del test de tres vias, cable de y = 5 a 23, porque inclinar en `+y` corre
cada luminaria 3.78 m rio arriba y con el cable arrancando en 2.0 la primera
caeria fuera de la sala. Son dos barridos distintos y no se mezclan: el
colector de `tools/medir_cuarto.py` solo recoge `stereo_sim_studioTV2_tilt*`,
asi que estas carpetas **no entran** en `medidas_inclinacion.csv` hasta que
alguien escriba su colector. Eso es a proposito.

## En cola, sin fecha

| # | render | por que no esta programado |
|---|--------|---------------------------|
| 4 | la esfera del sol completa con el **IMX296 y su 6 mm** | item abierto del capitulo 6. Son 112 direcciones, o sea un trabajo de toda la noche, y hace falta una variante `SOL296` que todavia no existe |
| 5 | las direcciones del borde de la esfera por **la pipeline completa** | item abierto del capitulo 6. No es un render, es procesar los que ya hay |
| 6 | el barrido de inclinacion de `TV2` con **`dof` encendido** | solo hace falta si estos renders se usan para entrenar el segmentador: el metro cercano sale nitido y en la realidad seria un borron grande |

## Como se programo

```powershell
schtasks /Create /TN LINKU_cola_renders /SC ONCE /ST 18:30 /F `
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\u_inras\Desktop\PROJECTS\STEREO_PHOTOGRAMMETRY_CM5\tools\correr_cola_renders.ps1"

schtasks /Query  /TN LINKU_cola_renders          # ver si sigue puesta
schtasks /Run    /TN LINKU_cola_renders          # lanzarla ahora
schtasks /Delete /TN LINKU_cola_renders /F       # quitarla
```

Es una tarea `ONCE`, de un solo disparo: hay que volver a crearla cada dia que
se quiera, y eso es deliberado, porque una cola que se dispara sola todas las
noches renderiza lo de ayer.
