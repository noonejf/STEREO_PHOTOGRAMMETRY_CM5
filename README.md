
# Sistema de Fotogrametría Estéreo CM5

## 🚀 Descripción del Proyecto

Sistema completo de fotogrametría estéreo diseñado específicamente para **Raspberry Pi CM5** con **cámaras Arducam HQ 477 (IMX477 12MP)**. Desarrollado para aplicaciones robustas en el espacio, el sistema proporciona una interfaz gráfica PyQt5 para calibración de cámaras, captura sincronizada y reconstrucción 3D de objetos.

### ✨ Características Principales

- **Interface Gráfica Intuitiva**: PyQt5 con vista previa en tiempo real
- **Calibración Automática**: Sistema robusto con tablero de ajedrez
- **Captura Sincronizada**: Minimiza diferencias temporales entre cámaras
- **Procesamiento 3D Avanzado**: Algoritmos SGBM y filtrado WLS
- **Múltiples Formatos**: Exportación PLY, XYZ, PCD, OBJ
- **Gestión Completa**: Logging, archivos, backups automáticos
- **Optimizado para Espacio**: Diseñado para misiones espaciales robustas

## 🛠️ Requisitos del Sistema

### Hardware Necesario

- **Raspberry Pi CM5** (Compute Module 5)
- **2x Cámaras Arducam HQ 477** (IMX477 12.3MP)
- **Cables CSI apropiados** para CM5 (22-pin)
- **SD Card**: Mínimo 32GB (recomendado 64GB+)
- **RAM**: Mínimo 4GB (recomendado 8GB)
- **Tablero de ajedrez** 10x7 cuadrados (9x6 esquinas internas)

### Software Base

- **Raspberry Pi OS Bookworm** (64-bit recomendado)
- **Python 3.9+**
- **libcamera-apps** (incluido en Raspberry Pi OS)
- **OpenCV 4.5+**
- **PyQt5**

## 🔧 Instalación Paso a Paso

### 1. Preparación del Sistema

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Clonar o descargar el proyecto
git clone <tu-repositorio> stereo_photogrammetry_cm5
cd stereo_photogrammetry_cm5

# Hacer ejecutable el instalador
chmod +x install_setup.py
```

### 2. Instalación Automática

```bash
# Ejecutar instalador completo
python3 install_setup.py
```

El instalador automáticamente:
- ✅ Instala todas las dependencias Python
- ✅ Configura PyQt5 y OpenCV
- ✅ Configura libcamera para las Arducam HQ 477
- ✅ Modifica `/boot/firmware/config.txt`
- ✅ Crea estructura de directorios
- ✅ Verifica la instalación

### 3. Configuración Manual de Cámaras

Si el instalador no configuró las cámaras automáticamente:

```bash
# Editar config.txt
sudo nano /boot/firmware/config.txt

# Agregar estas líneas:
camera_auto_detect=0
dtoverlay=imx477,cam0
dtoverlay=imx477,cam1
gpu_mem=128
start_x=1
```

### 4. Reiniciar y Verificar

```bash
# Reiniciar para aplicar cambios
sudo reboot

# Verificar cámaras después del reinicio
libcamera-hello --list-cameras
```

Deberías ver algo como:
```
Available cameras
-----------------
0 : imx477 [4056x3040] (/base/soc/i2c0mux/i2c@1/imx477@1a)
1 : imx477 [4056x3040] (/base/soc/i2c0mux/i2c@0/imx477@1a)
```

## 🎯 Uso del Sistema

### Iniciar la Aplicación

```bash
cd stereo_photogrammetry_cm5
python3 main.py
```

### Flujo de Trabajo Típico

#### 1. **Primera Vez: Calibración**

1. **Preparar Tablero**: Imprime un tablero de ajedrez 10x7 cuadrados
2. **Abrir Aplicación**: `python3 main.py`
3. **Vista Previa**: Presiona "▶ Iniciar Vista Previa" 
4. **Calibrar**: Presiona "🎯 Calibrar Cámaras"
5. **Seguir Instrucciones**: El sistema te guiará con countdown
6. **Mover Tablero**: Durante los 25 captures, mueve el tablero a diferentes posiciones
7. **Verificar Calidad**: El sistema evaluará automáticamente la calibración

#### 2. **Captura para Modelo 3D**

1. **Verificar Calibración**: Debe mostrar "✅ Sistema Calibrado"
2. **Vista Previa**: Asegurar que ambas cámaras funcionan
3. **Posicionar Objeto**: Coloca el objeto en el campo de visión
4. **Capturar**: Presiona "📸 Capturar para Modelo 3D"
5. **Countdown**: 10 segundos para preparar la toma
6. **Captura Automática**: Las cámaras capturan simultáneamente

#### 3. **Procesamiento 3D**

1. **Abrir Procesador**: Presiona "⚙️ Procesar Últimas Capturas"
2. **Verificar Imágenes**: El sistema carga automáticamente las últimas capturas
3. **Configurar Algoritmo**: Selecciona SGBM (recomendado) o BM (rápido)
4. **Seleccionar Formatos**: PLY, XYZ, PCD, OBJ según necesidades
5. **Procesar**: Presiona "🚀 Iniciar Procesamiento"
6. **Visualizar**: Ve mapas de disparidad, profundidad y estadísticas
7. **Exportar**: Los archivos se guardan automáticamente

## 📁 Estructura del Proyecto

```
stereo_photogrammetry_cm5/
├── main.py                     # 🚀 Aplicación principal
├── requirements.txt            # 📦 Dependencias Python
├── install_setup.py           # 🔧 Instalador automático
├── config/
│   ├── __init__.py
│   └── camera_config.py       # ⚙️ Configuración cámaras Arducam
├── gui/
│   ├── __init__.py
│   ├── main_window.py         # 🖥️ Ventana principal PyQt5
│   ├── camera_preview.py      # 📹 Vista previa cámaras
│   ├── calibration_dialog.py  # 🎯 Diálogo calibración
│   └── processing_dialog.py   # 🏗️ Diálogo procesamiento 3D
├── camera/
│   ├── __init__.py
│   ├── stereo_camera.py       # 📷 Sistema cámaras estéreo
│   └── camera_calibration.py  # 📐 Algoritmos calibración
├── processing/
│   ├── __init__.py
│   ├── stereo_processor.py    # 🧮 Procesamiento estéreo
│   └── point_cloud_generator.py # ☁️ Exportador nubes puntos
├── utils/
│   ├── __init__.py
│   ├── logger.py              # 📊 Sistema logging
│   └── file_manager.py        # 🗂️ Gestor archivos
└── data/                      # 💾 Datos del proyecto
    ├── calibration/           # 📐 Datos calibración
    ├── captures/              # 📸 Capturas estéreo
    ├── results/               # 🎯 Modelos 3D generados
    └── temp/                  # 🗑️ Archivos temporales
```

## 🔍 Componentes Técnicos

### Sistema de Cámaras (`camera/`)

- **StereoCamera**: Manejo de ambas cámaras Arducam HQ 477
- **CameraCalibrator**: Calibración robusta con validación de calidad
- **Captura Sincronizada**: Minimiza diferencias temporales (<100ms)

### Procesamiento 3D (`processing/`)

- **StereoProcessor**: Algoritmos SGBM/BM con filtrado WLS
- **PointCloudExporter**: Exportación PLY, XYZ, PCD, OBJ
- **Filtros Avanzados**: Eliminación outliers, decimado voxel

### Interfaz Gráfica (`gui/`)

- **PyQt5 Nativo**: Optimizado para Raspberry Pi
- **Vista Previa Tiempo Real**: libcamera + OpenCV
- **Controles Intuitivos**: Countdown, progreso, visualización

### Utilidades (`utils/`)

- **Logging Completo**: Archivos rotativos, colores, performance
- **Gestión Archivos**: Limpieza automática, backups, estadísticas

## ⚡ Configuraciones Avanzadas

### Optimización de Rendimiento

```python
# En camera_config.py, ajustar resoluciones:
capture_resolution: Tuple[int, int] = (3840, 2880)  # Alta calidad
preview_resolution: Tuple[int, int] = (1920, 1080)  # Balanceado
```

### Parámetros de Calibración

```python
# Tablero personalizado
calibration_board_size: Tuple[int, int] = (9, 6)     # Esquinas internas
calibration_square_size_mm: float = 25.0             # Tamaño cuadrado
min_calibration_images: int = 25                     # Mínimo imágenes
```

### Algoritmos de Matching

```python
# SGBM (Recomendado para calidad)
algorithm = "SGBM"  # Mejor calidad, más lento
algorithm = "BM"    # Mayor velocidad, menor calidad
```

## 🚨 Troubleshooting

### Problema: "No se detectaron cámaras"

**Solución:**
```bash
# Verificar config.txt
cat /boot/firmware/config.txt | grep -E "(camera|imx477)"

# Debe mostrar:
# camera_auto_detect=0
# dtoverlay=imx477,cam0
# dtoverlay=imx477,cam1

# Si no están, agregar y reiniciar:
sudo reboot
```

### Problema: "Error iniciando vista previa"

**Solución:**
```bash
# Verificar libcamera funciona:
libcamera-hello --camera 0 -t 2000
libcamera-hello --camera 1 -t 2000

# Si falla, verificar conexiones de cable CSI
# Asegurar que están en CAM0 y CAM1 del CM5
```

### Problema: "Calibración falla repetidamente"

**Verificar:**
- ✅ Tablero de ajedrez 10x7 cuadrados (9x6 esquinas)
- ✅ Iluminación uniforme sin reflejos
- ✅ Tablero completamente plano
- ✅ Mover tablero a diferentes ángulos y distancias
- ✅ Cubrir todo el campo de visión

### Problema: "PyQt5 no se instala"

**Solución Raspberry Pi 5:**
```bash
# Usar APT en lugar de pip:
sudo apt install python3-pyqt5 python3-pyqt5.qtwidgets
```

### Problema: "Procesamiento 3D muy lento"

**Optimizaciones:**
```python
# Reducir resolución de captura
capture_resolution = (2560, 1920)  # En lugar de (3840, 2880)

# Usar algoritmo BM para velocidad
algorithm = "BM"

# Reducir numDisparities
numDisparities = 64  # En lugar de 96
```

## 📈 Métricas de Rendimiento

### Tiempos Típicos (CM5 8GB)

- **Calibración**: 25 imágenes → ~3-5 minutos
- **Captura Estéreo**: ~2-3 segundos por par
- **Procesamiento 3D**: 
  - SGBM (alta calidad): ~30-60 segundos
  - BM (rápido): ~10-20 segundos
- **Exportación PLY**: ~5-15 segundos

### Calidad Esperada

- **Error Calibración**: <0.5 píxeles (excelente), <1.0 píxeles (bueno)
- **Sincronización**: <50ms diferencia entre cámaras
- **Densidad Nube**: 60-80% píxeles válidos (típico)
- **Precisión 3D**: ~1-2mm a 1 metro de distancia

## 🌟 Características Avanzadas

### Gestión Automática de Archivos

```bash
# Limpiar archivos temporales
python3 -c "from utils.file_manager import FileManager; fm = FileManager(); print(fm.cleanup_temp_files())"

# Estadísticas de uso
python3 -c "from utils.file_manager import FileManager; fm = FileManager(); print(fm.get_storage_usage())"
```

### Logging Avanzado

```python
# Los logs se guardan automáticamente en:
logs/stereo_photogrammetry.log

# Niveles configurables:
# DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Backups Automáticos

El sistema automáticamente:
- 🔄 Hace backup de configuraciones
- 🗂️ Archiva capturas antiguas
- 🧹 Limpia archivos temporales
- 📊 Genera inventarios de archivos

## 🤝 Contribución y Desarrollo

### Estructura Modular

El sistema está diseñado con arquitectura modular:

- **Fácil Extensión**: Agregar nuevos algoritmos de procesamiento
- **Configuración Flexible**: Soporte para diferentes cámaras
- **Testing Integrado**: Cada módulo incluye tests unitarios
- **Documentación Completa**: Código bien documentado

### Agregar Nuevos Formatos de Exportación

```python
# En point_cloud_generator.py
def _export_nuevo_formato(self, points, colors, output_file):
    # Implementar nuevo formato
    pass
```

## 📞 Soporte y Comunidad

### Información del Sistema

```bash
# Ver información completa del sistema:
python3 -c "from utils.logger import log_system_info; log_system_info()"
```

### Logs y Diagnóstico

```bash
# Ver logs recientes:
tail -f logs/stereo_photogrammetry.log

# Información de cámaras:
libcamera-hello --list-cameras

# Estado del sistema:
python3 main.py --test  # (si implementado)
```

## 📋 Lista de Verificación Previa al Uso

Antes de usar el sistema, verifica:

- [ ] **Hardware conectado**: CM5 + 2x Arducam HQ 477
- [ ] **Sistema actualizado**: `sudo apt update && sudo apt upgrade`
- [ ] **Instalación completada**: `python3 install_setup.py` ejecutado
- [ ] **Cámaras detectadas**: `libcamera-hello --list-cameras` muestra 2 cámaras
- [ ] **Tablero preparado**: 10x7 cuadrados impreso en papel rígido
- [ ] **Espacio suficiente**: Al menos 5GB libres para procesamiento
- [ ] **Iluminación adecuada**: Uniforme, sin reflejos fuertes

## 🎓 Casos de Uso Específicos

### Aplicaciones Espaciales
- Inspección de componentes satelitales
- Medición de separación entre satélites
- Verificación de despliegue de estructuras

### Aplicaciones Industriales
- Control de calidad 3D
- Medición de piezas manufacturadas
- Inspección automatizada

### Aplicaciones de Investigación
- Análisis de movimiento
- Mediciones científicas precisas
- Documentación 3D de especímenes

---

## 📜 Licencia

Este proyecto está diseñado para aplicaciones robustas en el espacio. Consulta los términos de licencia específicos para tu uso.

## 🏆 Créditos

Desarrollado para sistemas Raspberry Pi CM5 con cámaras Arducam HQ 477, optimizado para misiones espaciales y aplicaciones industriales robustas.

---

**¡Listo para comenzar tu aventura en fotogrametría estéreo! 🚀📸**