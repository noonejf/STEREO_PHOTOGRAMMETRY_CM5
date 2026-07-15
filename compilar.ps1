# Compila los .tex de una carpeta de documento (raiz o scripts/) y guarda los PDF en su subcarpeta pdf/
# Uso: .\compilar.ps1 "Documentation\LINKU_Project_SubDeliverable_D5_CameraSystem_Report__v2_"

param(
    [Parameter(Mandatory = $true)]
    [string]$Carpeta
)

if (-not (Test-Path $Carpeta)) {
    Write-Error "No existe la carpeta: $Carpeta"
    exit 1
}

# Busca .tex en la raiz de la carpeta y en scripts/ (ambas convenciones del repo)
$texFiles = @(Get-ChildItem -Path $Carpeta -Filter *.tex -File)
$scriptsDir = Join-Path $Carpeta "scripts"
if (Test-Path $scriptsDir) {
    $texFiles += @(Get-ChildItem -Path $scriptsDir -Filter *.tex -File)
}
if ($texFiles.Count -eq 0) {
    Write-Error "No se encontro ningun archivo .tex dentro de: $Carpeta (ni en su subcarpeta scripts/)"
    exit 1
}

$pdfDir = Join-Path $Carpeta "pdf"
if (-not (Test-Path $pdfDir)) {
    New-Item -ItemType Directory -Path $pdfDir | Out-Null
}

$fallo = $false
foreach ($texFile in $texFiles) {
    tectonic $texFile.FullName --outdir $pdfDir
    if ($LASTEXITCODE -eq 0) {
        Write-Host "PDF generado en: $pdfDir\$($texFile.BaseName).pdf" -ForegroundColor Green
    } else {
        Write-Host "FALLO la compilacion de: $($texFile.Name)" -ForegroundColor Red
        $fallo = $true
    }
}
if ($fallo) { exit 1 }
