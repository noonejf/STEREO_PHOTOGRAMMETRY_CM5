# Corre la cola de renders de SIMULATION/experimentos/COLA_RENDERS.md.
#
# Existe porque los renders del estudio tardan unos 4 minutos por angulo con
# las dos camaras y bloquean la maquina mientras corren, asi que se lanzan al
# final del dia y no mientras se trabaja. La cola la dispara una tarea de
# Windows, LINKU_cola_renders, que se registra con:
#
#   schtasks /Create /TN LINKU_cola_renders /SC ONCE /ST 18:30 /F /TR \
#     "powershell -NoProfile -ExecutionPolicy Bypass -File <ruta de este archivo>"
#
# RENDERIZA Y NADA MAS. No mide, no escribe ninguna CSV y no toca ningun
# entregable: lo unico que deja son carpetas nuevas en data/captures y una
# bitacora en logs/. Medir es un paso que se revisa a mano al dia siguiente,
# porque una CSV mala se publica sola en las tablas del capitulo 5.

$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$blender = "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
$script = Join-Path $repo "SIMULATION\render_studio_iterations.py"
$log = Join-Path $repo ("logs\cola_renders_" + (Get-Date -Format "yyyyMMdd_HHmm") + ".log")

function Decir($texto) {
    $linea = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $texto
    Write-Output $linea
    Add-Content -Path $log -Value $linea -Encoding utf8
}

if (-not (Test-Path $blender)) {
    Decir "FALLO: no esta $blender"
    exit 1
}

Set-Location $repo

# Un elemento por barrido. El nombre es para la bitacora; los argumentos van
# despues del `--`, que es como Blender se los pasa al script.
# Cuidado con los angulos negativos: argparse lee `--tilts -10` como una
# opcion, asi que la lista se pasa pegada con `=`.
$cola = @(
    @{ nombre = "haz LEJOS de las camaras, 0 a 60 grados";
       args = @("--variant", "TV2HAZLEJOS", "--tilts=0,10,20,30,40,50,60",
                "--samples", "24", "--scale", "100", "--both") },
    @{ nombre = "haz HACIA las camaras, 0 a 60 grados";
       args = @("--variant", "TV2HAZCAM", "--tilts=0,10,20,30,40,50,60",
                "--samples", "24", "--scale", "100", "--both") },
    @{ nombre = "haz DE COSTADO, 0 a 60 grados";
       args = @("--variant", "TV2HAZLADO", "--tilts=0,20,40,60",
                "--samples", "24", "--scale", "100", "--both") }
)

Decir ("cola de " + $cola.Count + " barridos, bitacora en " + $log)
$inicio = Get-Date
$fallos = 0

foreach ($trabajo in $cola) {
    Decir ("--> " + $trabajo.nombre)
    $t0 = Get-Date
    & $blender --background --python $script -- @($trabajo.args) 2>&1 |
        Add-Content -Path $log -Encoding utf8
    $min = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
    if ($LASTEXITCODE -ne 0) {
        $fallos++
        Decir ("FALLO con codigo " + $LASTEXITCODE + ", " + $min + " min")
    } else {
        Decir ("listo en " + $min + " min")
    }
}

$total = [math]::Round(((Get-Date) - $inicio).TotalMinutes, 1)
Decir ("cola terminada en " + $total + " min, " + $fallos + " fallos")
Decir "siguiente paso, a mano y revisando: tools/medir_cuarto.py"
