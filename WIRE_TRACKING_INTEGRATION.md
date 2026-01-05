# Integración de Smart Wire Tracker

Este documento explica cómo se ha integrado el **SmartWireTracker** en el flujo de procesamiento de estéreo para cables.

## Resumen del Flujo

El sistema ahora detecta automáticamente endpoints y genera paths precisos para cables después de crear máscaras manualmente.

```
Usuario → Selecciona Imágenes → Configura Filtro de Cable (Manual)
    ↓
Crea máscaras LEFT y RIGHT manualmente (edge_detection_tuner)
    ↓
[AUTOMÁTICO] → Detecta Endpoints → Ejecuta SmartWireTracker
    ↓
Genera paths precisos para LEFT y RIGHT
    ↓
Procesamiento 3D usa paths optimizados
```

## Componentes Nuevos

### 1. EndpointDetector (`processing/endpoint_detector.py`)

Detecta automáticamente los puntos de inicio y fin del cable en una máscara binaria.

**Métodos disponibles:**
- `skeleton` (recomendado): Usa esqueletización para encontrar endpoints
- `contour`: Usa análisis de contornos
- `distance_transform`: Usa transformada de distancia

**Uso:**
```python
from processing.endpoint_detector import detect_wire_endpoints

start, end = detect_wire_endpoints(
    mask,
    method="skeleton",
    visualize=True,
    vis_output_path="endpoints.png"
)
```

### 2. SmartWireTracker (`processing/smart_wire_tracker.py`)

Genera un path preciso desde start hasta end usando:
- Distance Transform para ancho adaptativo
- Backtracking (DFS) para manejar bifurcaciones
- Detección de líneas paralelas
- Sin detección de nudos (versión limpia)

**Características:**
- Marca área visitada con radio adaptativo al grosor del cable
- Maneja cruces e intersecciones
- Retrocede automáticamente si se atasca
- Genera visualizaciones de debug

**Uso:**
```python
from processing.smart_wire_tracker import SmartWireTracker

tracker = SmartWireTracker(mask, start, end)
result = tracker.track_wire(max_iterations=10000)

print(f"Path: {len(result['path'])} puntos")
print(f"Cobertura: {result['coverage']*100:.1f}%")

tracker.visualize('wire_path.png')
```

### 3. StereoProcessor.process_wire_masks()

Método integrado en `StereoProcessor` que:
1. Detecta endpoints en ambas máscaras (LEFT y RIGHT)
2. Ejecuta SmartWireTracker en ambas
3. Valida resultados
4. Retorna paths y estadísticas

**Uso:**
```python
processor = StereoProcessor(camera_config)

result = processor.process_wire_masks(
    mask_left,
    mask_right,
    save_debug=True
)

if result['success']:
    left_path = result['left']['path']
    right_path = result['right']['path']
```

## Flujo en ProcessingDialog

### Ubicación: `gui/processing_dialog.py`

Cuando el usuario hace clic en **"Configurar Filtro de Cable"**:

1. Se abre `edge_detection_tuner_with_switch()` para crear máscaras manualmente
2. Usuario dibuja máscaras para LEFT y RIGHT
3. Al cerrar el tuner, se ejecuta **automáticamente**:

```python
# Crear procesador temporal
processor = StereoProcessor(self.camera_config)

# Procesar máscaras con wire tracker
wire_result = processor.process_wire_masks(
    self.cable_mask_left,
    self.cable_mask_right,
    save_debug=True
)
```

4. Si tiene éxito:
   - Guarda `self.wire_tracking_result` con los paths
   - Actualiza el status label: ✅ "Filtro configurado + Wire tracking OK"
   - Muestra estadísticas en el mensaje de éxito

5. Si falla:
   - Usa solo las máscaras básicas sin paths optimizados
   - Actualiza el status label: ⚠️ "Filtro OK, Wire tracking falló"

## Imágenes de Debug Generadas

Cuando `save_debug=True`, se crean las siguientes imágenes en `data/results/debug/`:

```
endpoints_left.png       → Visualización de endpoints detectados (LEFT)
endpoints_right.png      → Visualización de endpoints detectados (RIGHT)
wire_path_left.png       → Path generado sobre máscara (LEFT)
wire_path_right.png      → Path generado sobre máscara (RIGHT)
```

**Leyenda de visualización:**
- **Gris oscuro**: Máscara original del cable
- **Rojo semitransparente**: Área visitada/cubierta por el path
- **Cian brillante**: Path generado (línea)
- **Amarillo**: Puntos de decisión (bifurcaciones)
- **Verde**: Punto de inicio (START)
- **Rojo**: Punto final (END)

## Datos Disponibles Después del Tracking

Después de ejecutar el wire tracking, `self.wire_tracking_result` contiene:

```python
{
    'success': True/False,
    'left': {
        'start': (x, y),          # Punto de inicio
        'end': (x, y),            # Punto final
        'path': [(x1,y1), ...],   # Lista de puntos del path
        'coverage': 0.0-1.0,      # Porcentaje de cobertura
        'success': True/False
    },
    'right': {
        # ... mismo formato que 'left'
    }
}
```

## Uso Futuro de los Paths

Los paths generados pueden usarse para:

1. **Matching guiado entre LEFT y RIGHT**
   - Usar `WireMatcher` con los paths como guía
   - Correlación NCC punto a punto a lo largo del path

2. **Validación de disparidad**
   - Verificar que la disparidad sea consistente a lo largo del cable
   - Filtrar outliers basándose en la geometría del path

3. **Reconstrucción 3D optimizada**
   - Generar nube de puntos densa solo a lo largo del cable
   - Mejorar precisión usando la topología del path

## Ejemplo Completo de Uso

```python
from processing.stereo_processor import StereoProcessor
from config.camera_config import CameraConfig
import cv2

# 1. Cargar configuración
config = CameraConfig()

# 2. Cargar máscaras creadas manualmente
mask_left = cv2.imread('cable_mask_left.png', cv2.IMREAD_GRAYSCALE)
mask_right = cv2.imread('cable_mask_right.png', cv2.IMREAD_GRAYSCALE)

# 3. Procesar con wire tracker
processor = StereoProcessor(config)
result = processor.process_wire_masks(mask_left, mask_right, save_debug=True)

# 4. Verificar resultados
if result['success']:
    print(f"✓ LEFT: {len(result['left']['path'])} puntos")
    print(f"  Cobertura: {result['left']['coverage']*100:.1f}%")
    print(f"✓ RIGHT: {len(result['right']['path'])} puntos")
    print(f"  Cobertura: {result['right']['coverage']*100:.1f}%")

    # 5. Usar paths para matching
    left_path = result['left']['path']
    right_path = result['right']['path']

    # TODO: Implementar matching usando paths
else:
    print("❌ Wire tracking falló")
```

## Solución de Problemas

### El endpoint detection no encuentra endpoints

**Causas comunes:**
- Máscara tiene ruido o múltiples componentes
- Cable es muy grueso y no tiene endpoints claros
- Skeleton es muy complejo con muchas ramificaciones

**Soluciones:**
1. Limpiar la máscara antes de procesar:
   ```python
   # Eliminar componentes pequeños
   kernel = np.ones((5,5), np.uint8)
   mask_clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
   ```

2. Probar diferentes métodos:
   ```python
   start, end = detect_wire_endpoints(mask, method="contour")
   ```

### El wire tracker se atasca o no llega al final

**Causas comunes:**
- Gaps (huecos) en la máscara
- Cable se cruza consigo mismo múltiples veces
- Endpoints mal detectados

**Soluciones:**
1. Cerrar gaps pequeños:
   ```python
   kernel = np.ones((3,3), np.uint8)
   mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
   ```

2. Verificar visualmente los endpoints:
   ```python
   detect_wire_endpoints(mask, visualize=True, vis_output_path="check.png")
   ```

3. Ajustar parámetros del tracker:
   ```python
   tracker.search_radius = 25  # Aumentar búsqueda
   tracker.step_size = 3       # Pasos más pequeños
   ```

### Cobertura baja (<80%)

**Causas comunes:**
- Radio de marcado muy pequeño
- Cable muy ancho y path muy fino

**Soluciones:**
1. Verificar visualización para entender qué áreas no se cubren
2. Ajustar parámetros de cobertura:
   ```python
   tracker.min_coverage_radius = 10
   tracker.max_coverage_radius = 40
   ```

## Próximos Pasos

1. **Integrar con WireMatcher**
   - Usar paths generados para guiar el matching estéreo
   - Implementar correlación NCC a lo largo de los paths

2. **Optimizar procesamiento 3D**
   - Aplicar SGBM solo en región del cable
   - Usar paths para validar disparidad

3. **Mejorar visualización**
   - Mostrar paths en la interfaz de ProcessingDialog
   - Overlay de paths sobre imágenes rectificadas

## Archivos Modificados

- `processing/endpoint_detector.py` (NUEVO)
- `processing/smart_wire_tracker.py` (Ya existía, sin cambios)
- `processing/stereo_processor.py` (Agregado `process_wire_masks()`)
- `gui/processing_dialog.py` (Agregado llamada automática al wire tracker)

## Referencias

- [SmartWireTracker](processing/smart_wire_tracker.py) - Implementación del tracker
- [EndpointDetector](processing/endpoint_detector.py) - Detección de extremos
- [StereoProcessor](processing/stereo_processor.py) - Integración en pipeline
- [ProcessingDialog](gui/processing_dialog.py) - Integración en GUI
