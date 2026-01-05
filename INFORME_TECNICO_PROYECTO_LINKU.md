# INFORME TÉCNICO COMPLETO
## Proyecto LINKU: Sistema de Fotogrametría Estéreo para Reconstrucción 3D de Cables en Entornos Espaciales

---

**Proyecto:** Sistema de Visión Estéreo para Misión Espacial Dual-Satélite
**Objetivo:** Reconstrucción 3D de cable de conexión entre satélites mediante fotogrametría estéreo
**Hardware:** Raspberry Pi CM5 + Cámaras Arducam IMX477 (12MP)
**Entorno de Operación:** Oscuridad total con iluminación mínima controlada
**Estado del Proyecto:** En desarrollo activo - Fase 2 de pruebas

---

## ÍNDICE

1. [Contexto y Motivación del Proyecto](#1-contexto-y-motivación-del-proyecto)
2. [Evolución del Hardware](#2-evolución-del-hardware)
3. [Fase 1: Validación en Condiciones Ideales](#3-fase-1-validación-en-condiciones-ideales)
4. [Transición y Aprendizajes](#4-transición-y-aprendizajes)
5. [Fase 2: Reconstrucción en Oscuridad](#5-fase-2-reconstrucción-en-oscuridad)
6. [Arquitectura del Software](#6-arquitectura-del-software)
7. [Solución Innovadora: Wire Tracking con Máscaras](#7-solución-innovadora-wire-tracking-con-máscaras)
8. [Resultados Actuales y Desafíos](#8-resultados-actuales-y-desafíos)
9. [Próximos Pasos](#9-próximos-pasos)
10. [Conclusiones](#10-conclusiones)

---

## 1. CONTEXTO Y MOTIVACIÓN DEL PROYECTO

### 1.1 Objetivo de la Misión Espacial

El proyecto **LINKU** tiene como objetivo desarrollar un sistema de visión estéreo capaz de reconstruir tridimensionalmente un **cable de conexión entre dos satélites** en el espacio. Esta tecnología es crítica para:

- **Verificación de despliegue:** Confirmar que el cable se ha desplegado correctamente después del lanzamiento
- **Monitoreo de integridad:** Detectar deformaciones, torsiones o daños en el cable durante la misión
- **Navegación relativa:** Obtener información geométrica precisa para maniobras de los satélites
- **Análisis de dinámica:** Estudiar el comportamiento del cable bajo diferentes condiciones orbitales

### 1.2 Desafíos Únicos del Entorno Espacial

El entorno espacial presenta condiciones extremadamente desafiantes para la fotogrametría tradicional:

| Condición | Desafío para Visión Estéreo |
|-----------|----------------------------|
| **Oscuridad total** | Sin luz ambiente, solo iluminación solar directa |
| **Fondo negro uniforme** | Algoritmos SGBM/BM requieren textura/relieve para matching |
| **Objeto delgado (cable)** | Difícil de segmentar y extraer características |
| **Sin referencias visuales** | No hay puntos de referencia para validar profundidad |
| **Contraste extremo** | Cable iluminado vs fondo completamente negro |

Estos desafíos motivaron el desarrollo de un enfoque **no convencional** que se aparta de los métodos tradicionales de fotogrametría estéreo.

---

## 2. EVOLUCIÓN DEL HARDWARE

### 2.1 Etapa Inicial: Arducam 2MP (Duración: ~2 meses)

**Especificaciones:**
- **Cámaras:** 2x Arducam 2MP (básicas)
- **Resolución:** 1920x1080 píxeles
- **Plataforma:** Raspberry Pi 3/4
- **Baseline (separación):** ~10cm

**Resultados Obtenidos:**
- ✅ **Validación conceptual exitosa** con objetos de alto relieve (cajas, botellas)
- ✅ **Formas generales bien reconstruidas** en condiciones ideales
- ❌ **Resolución insuficiente** para cables delgados
- ❌ **Ruido alto** en condiciones de baja iluminación

**Herramientas Complementarias Probadas:**

Durante esta etapa se utilizó **Agisoft Metashape**, software comercial de fotogrametría profesional, para:
- **Validar la viabilidad** del concepto de reconstrucción 3D con estéreo
- **Comparar resultados** entre software comercial y desarrollo propio
- **Entender limitaciones** de métodos tradicionales

**Resultados con Metashape:**
- ✅ Reconstrucción **excelente de escenas completas** con múltiples objetos y fondo con relieve
- ✅ Cable reconstruido satisfactoriamente **cuando hay contexto espacial** (pared, objetos cercanos)
- ❌ **Fallo total** en escenario minimalista: cable solo sobre fondo negro sin relieve
- ❌ Confirmó que **algoritmos tradicionales requieren textura** en toda la escena

> **Conclusión clave:** Incluso software comercial de alta gama falla en escenarios sin relieve. Se necesitaba un enfoque diferente.

### 2.2 Transición a Arducam HQ IMX477 12MP

**Motivación del Cambio:**
1. **Mayor resolución:** 4056x3040 px (12MP) vs 1920x1080 (2MP) → 6x más píxeles
2. **Mejor sensor:** IMX477 de Sony (usado en cámaras profesionales)
3. **Mayor sensibilidad:** Fundamental para condiciones de baja luz
4. **Soporte nativo CM5:** Integración óptima con Raspberry Pi CM5

**Fecha de Implementación:** Pendiente de confirmación (al recibir pedidos)

**Especificaciones Técnicas Finales:**

| Componente | Especificación |
|------------|----------------|
| **Cámaras** | 2x Arducam HQ 477 (IMX477 12.3MP) |
| **Procesador** | Raspberry Pi CM5 (Compute Module 5) |
| **Resolución de captura** | 3840x2880 píxeles (alta calidad) |
| **Resolución de preview** | 1920x1440 píxeles (balanceado) |
| **Baseline calibrado** | ~100-101mm (variable según calibración) |
| **Interfaz** | CSI (Camera Serial Interface) - 2 canales |
| **Soporte físico** | Estructura custom de montaje dual adaptable |

**Diseño del Soporte:**
- Estructura que sostiene 2 cámaras verticales
- Separación fija de 10cm (100mm) entre centros ópticos
- Permite ajuste de altura y ángulo
- Material: (especificación pendiente)

---

## 3. FASE 1: VALIDACIÓN EN CONDICIONES IDEALES

### 3.1 Objetivo de la Fase

Validar el sistema de visión estéreo en **condiciones controladas y óptimas** antes de enfrentar el desafío de la oscuridad total.

**Parámetros de la Fase 1:**
- ✅ Iluminación ambiente normal (interior con luz artificial/natural)
- ✅ Fondos con textura variable (paredes, muebles, suelo)
- ✅ Objetos de diferentes tamaños y complejidades
- ✅ Distancias de trabajo: 0.5m - 2.0m

### 3.2 Metodología

#### 3.2.1 Calibración del Sistema

El sistema implementa calibración robusta usando **tablero de ajedrez**:

**Especificaciones del Tablero:**
- **Tamaño:** 10x7 cuadrados (9x6 esquinas internas detectables)
- **Tamaño de cuadrado:** 24mm x 24mm
- **Material:** Impreso en papel rígido de alto contraste
- **Proceso:** 25-30 capturas en diferentes posiciones y ángulos

**Algoritmo de Calibración:**
1. **Detección de esquinas:** `cv2.findChessboardCorners()` con refinamiento subpixel
2. **Calibración individual:** Matriz intrínseca K y coeficientes de distorsión D para cada cámara
3. **Calibración estéreo:** Matriz de rotación R y vector de traslación T entre cámaras
4. **Rectificación:** Cálculo de matrices P1, P2 y la crucial matriz Q
5. **Validación:** Error de reproyección < 1.0 píxeles (típicamente 0.5-0.8 px)

**Datos Guardados en `calibration_data.json`:**
```json
{
  "K1": "Matriz intrínseca cámara izquierda (3x3)",
  "K2": "Matriz intrínseca cámara derecha (3x3)",
  "D1": "Distorsión cámara izquierda (5 coeficientes)",
  "D2": "Distorsión cámara derecha (5 coeficientes)",
  "R": "Rotación relativa entre cámaras (3x3)",
  "T": "Traslación (baseline) en metros (3x1)",
  "P1, P2": "Matrices de proyección rectificadas",
  "Q": "Matriz de reproyección 3D (4x4) - CLAVE para conversión 2D→3D"
}
```

#### 3.2.2 Objetos de Prueba

Se probaron diversos objetos para caracterizar el rendimiento:

| Tipo de Objeto | Características | Resultado |
|----------------|----------------|-----------|
| **Cajas** | Alto relieve, bordes definidos | ✅ Excelente (formas bien definidas) |
| **Botellas** | Superficies curvas, reflexión moderada | ✅ Muy bueno (geometría capturada) |
| **Manos/silueta** | Textura de piel, contornos complejos | ⚠️ Bueno (algunas zonas lisas fallan) |
| **Cable de estaño** | Delgado (~2-5mm), uniforme | ❌ Pobre (se mezcla con fondo) |

**Imágenes de resultados disponibles** (pueden adjuntarse al informe).

### 3.3 Pipeline de Procesamiento Estéreo Tradicional

#### 3.3.1 Flujo Completo

```
[1] CAPTURA SINCRONIZADA
    ↓
    stereo_camera.py → capture_stereo_pair()
    ├─ libcamera-jpeg --camera 0 (LEFT)
    └─ libcamera-jpeg --camera 1 (RIGHT)
    ↓
[2] RECTIFICACIÓN
    ↓
    stereo_processor.py → rectify_images()
    ├─ Corrige distorsión de lentes (K1, D1, K2, D2)
    ├─ Alinea imágenes (R, T)
    └─ Genera mapas de rectificación
    ↓
    Resultado: Líneas epipolares HORIZONTALES
    (Mismo punto 3D → misma fila Y en ambas imágenes)
    ↓
[3] CÁLCULO DE DISPARIDAD
    ↓
    Algoritmo: SGBM (Semi-Global Block Matching)
    ├─ Para cada píxel (x,y) en LEFT
    ├─ Buscar píxel correspondiente en RIGHT (solo en fila y)
    ├─ Comparar bloques usando SAD/NCC
    └─ Disparidad d = x_left - x_right
    ↓
    Resultado: Mapa de disparidad (cada píxel tiene valor d)
    ↓
[4] FILTRADO
    ↓
    ├─ WLS Filter (suavizado global)
    ├─ Bilateral Filter (preserva bordes)
    └─ Outlier removal (valores inconsistentes)
    ↓
[5] CONVERSIÓN A PROFUNDIDAD
    ↓
    Fórmula: Z = (focal × baseline) / disparidad
    ↓
    Resultado: Mapa de profundidad (metros)
    ↓
[6] GENERACIÓN DE NUBE DE PUNTOS 3D
    ↓
    Usando matriz Q:
    [X, Y, Z, W] = Q × [x, y, disparidad, 1]
    (X, Y, Z) = (X/W, Y/W, Z/W)
    ↓
[7] EXPORTACIÓN
    ↓
    Formatos: PLY, XYZ, PCD, OBJ
```

#### 3.3.2 Parámetros Clave del SGBM

Basados en literatura académica y tesis de referencia:

```python
# Parámetros optimizados (Fase 1)
minDisparity = 0              # Inicio de búsqueda
numDisparities = 96           # Rango de búsqueda (múltiplo de 16)
blockSize = 17                # Tamaño de ventana de comparación
uniquenessRatio = 5           # Confianza mínima del match
speckleWindowSize = 50        # Filtro de ruido moderado
speckleRange = 16             # Tolerancia de variación
P1 = 8 * 3 * blockSize²       # Penalización suavidad pequeña
P2 = 32 * 3 * blockSize²      # Penalización suavidad grande
preFilterCap = 61             # Límite de preprocesamiento
```

**Referencia:** Tesis "Reconstrucción 3D mediante el uso de un par de cámaras a modo de estereovisión", Escuela Politécnica Nacional de Ecuador (2014).

### 3.4 Resultados de la Fase 1

#### 3.4.1 Métricas de Desempeño

**Con objetos de alto relieve (cajas, botellas):**

| Métrica | Valor Típico | Calidad |
|---------|--------------|---------|
| Píxeles con disparidad válida | 40-60% | ✅ Buena |
| Puntos en nube 3D | 150k-500k | ✅ Denso |
| Error de reproyección | 0.5-0.8 px | ✅ Excelente |
| Profundidad a 1m | 0.9-1.1m | ✅ Preciso |
| Tiempo de procesamiento (SGBM) | 30-60s | ✅ Aceptable |

**Con siluetas humanas/manos:**

| Métrica | Valor Típico | Calidad |
|---------|--------------|---------|
| Píxeles con disparidad válida | 20-40% | ⚠️ Moderada |
| Puntos en nube 3D | 50k-150k | ⚠️ Disperso |
| "Vitiligo" (manchas sin disparidad) | Presente en piel lisa | ⚠️ Problema |
| Forma general | Reconocible pero plana | ⚠️ Limitado |

**Observaciones Clave:**
1. ✅ **Algoritmos funcionan correctamente** cuando hay textura y relieve
2. ❌ **Superficies lisas (piel, paredes) presentan discontinuidades** ("efecto vitiligo")
3. ❌ **Fondo sin relieve causa "explosión"** de la nube de puntos (valores inconsistentes)
4. ❌ **Cable delgado se pierde** entre el ruido o no se distingue del fondo

#### 3.4.2 Problema Crítico Identificado: Dependencia del Relieve

**Visualización del Problema:**

```
ESCENARIO CON RELIEVE (Funciona):
┌─────────────────────────────┐
│  Pared con textura    [📦]  │  ← Muchos features para matching
│   [🪑]     [🧍]             │  ← Sillas, personas, objetos
│        Cable ~~~~           │  ← Cable reconstruido por contexto
└─────────────────────────────┘

ESCENARIO SIN RELIEVE (Falla):
┌─────────────────────────────┐
│  ███████████████████████   │  ← Fondo negro uniforme
│        Cable ~~~~           │  ← Cable solo, SIN contexto
│  ███████████████████████   │  ← NO hay features para matching
└─────────────────────────────┘
           ↓
    Algoritmo SGBM:
    ¿Qué píxel de RIGHT corresponde a este de LEFT?
    → TODAS las posiciones del fondo negro son idénticas
    → Disparidad ambigua/errónea
    → Nube de puntos "explota" espacialmente
```

**Experimento Definitivo con Metashape:**

Para confirmar que no era un problema de implementación, se probó con **Agisoft Metashape** (software comercial profesional):

| Escenario | Resultado Metashape | Conclusión |
|-----------|---------------------|------------|
| Cable + pared + objetos | ✅ Reconstrucción excelente | Contexto permite matching |
| Cable solo sobre negro | ❌ Fallo completo | Confirma limitación algorítmica |

> **Decisión Estratégica:** No tiene sentido optimizar parámetros SGBM si el problema es **conceptual**, no de implementación. Se necesita un enfoque radicalmente diferente.

---

## 4. TRANSICIÓN Y APRENDIZAJES

### 4.1 Razones para Pasar a Fase 2

La Fase 1 cumplió su propósito de **validación técnica**, pero reveló que:

1. **El escenario real (espacio) es fundamentalmente diferente:**
   - ❌ No habrá paredes, suelo, o referencias visuales
   - ❌ No habrá textura ambiental
   - ❌ Solo el cable sobre fondo negro infinito

2. **Seguir optimizando SGBM era contraproducente:**
   - Ya se probaron parámetros de literatura académica
   - Ya se validó con software comercial (Metashape)
   - El problema NO es de parámetros, es de **falta de información visual**

3. **El tiempo invertido debe enfocarse en el problema real:**
   - No tiene sentido perfeccionar algo que no se usará
   - Mejor enfrentar el desafío de oscuridad desde el inicio

### 4.2 Período de Exploración con Arducam 2MP

**Duración:** ~2 meses

**Actividades:**
- ✅ Pruebas extensivas con Metashape
- ✅ Intentos de mejorar segmentación del cable
- ✅ Experimentos con diferentes fondos y condiciones de luz
- ❌ Intentos fallidos de crear máscaras precisas del cable (se mezclaba con bordes de objetos)

**Lecciones Aprendidas:**

| Intento | Metodología | Resultado | Aprendizaje |
|---------|-------------|-----------|-------------|
| Máscaras automáticas | Detección de bordes + flood fill | ❌ Cable se mezcla con fondo | Objetos delgados necesitan procesamiento específico |
| SGBM en toda la imagen | Parámetros estándar | ❌ Explosión espacial | Fondo uniforme causa ambigüedad |
| Segmentación semántica | Umbralización simple | ❌ Cable muy delgado | Resolución 2MP insuficiente |

**Conclusión:** Se necesitaba:
1. **Mayor resolución:** Migrar a IMX477 12MP
2. **Entorno controlado:** Construir cámara oscura
3. **Enfoque no tradicional:** Abandonar SGBM puro, usar información geométrica del cable

---

## 5. FASE 2: RECONSTRUCCIÓN EN OSCURIDAD

### 5.1 Diseño de la Cámara Oscura

#### 5.1.1 Especificaciones Físicas

**Materiales y Construcción:**
- **Material:** Trupán de 9mm (MDF)
- **Diseño:** Fusion 360 (CAD)
- **Manufactura:** Corte CNC personalizado
- **Ensamblaje:** Estructura modular con adaptadores removibles

**Dimensiones:**
- **Largo:** 80 cm
- **Ancho:** 50 cm
- **Alto:** 60 cm
- **Volumen total:** 240 litros (~0.24 m³)

**Características Especiales:**
- ✅ Interior pintado de negro mate (minimizar reflexiones)
- ✅ Espacio para cámara de adaptadores removible (flexibilidad experimental)
- ✅ Sellado de luz (oscuridad total controlada)
- ✅ Acceso frontal para colocación/ajuste del cable

#### 5.1.2 Sistema de Iluminación

**Configuración Actual:**
- **Fuente:** LED de lámpara desarmada
- **Posición:** Interior de la caja
- **Intensidad:** Sin análisis lumínico formal aún
- **Función:** Simula iluminación solar tenue del espacio

**Próximas Mejoras:**
- [ ] Caracterización de lúmenes necesarios
- [ ] Estudio de ángulo óptimo de iluminación
- [ ] Posible uso de LED direccional de alta potencia
- [ ] Simulación de iluminación solar difusa

### 5.2 Configuración del Cable de Prueba

**Objeto de Estudio:**
- **Tipo:** Cable de estaño (temporal)
- **Grosor:** ~2-5mm (estimado)
- **Color:** Plateado/gris metálico
- **Posición:** Tendido sobre el piso negro mate de la caja
- **Distancia a cámaras:** ~50cm (altura de la caja)

> **Nota:** El cable definitivo de la misión espacial aún no ha sido proporcionado. Las pruebas actuales usan cable de estaño como proxy.

**Configuración de Fondo:**
- **Piso:** Negro mate (simula espacio)
- **Paredes:** Negro mate
- **Objetivo:** Diferenciar cable del fondo mediante iluminación controlada

### 5.3 Condiciones de Captura

**Parámetros de Cámara:**

| Parámetro | Valor | Justificación |
|-----------|-------|---------------|
| Resolución | 3840x2880 px | Máxima calidad para cable delgado |
| Exposición | Manual (cerrado) | Control preciso de luz |
| ISO/Gain | Bajo | Minimizar ruido en oscuridad |
| Enfoque | Manual (máximo cierre de obturador posible) | Maximizar nitidez del cable |
| White Balance | Manual | Consistencia entre LEFT/RIGHT |

**Ajustes Críticos:**
- ✅ **Obturador cerrado al máximo** para enfoque óptimo
- ⚠️ **Limitación:** Cierre excesivo reduce entrada de luz
- ⚠️ **Balance:** Enfoque vs iluminación (compromiso necesario)

**Sincronización:**
- **Método:** Captura casi simultánea vía `libcamera-jpeg` en threads paralelos
- **Diferencia temporal:** <100ms (aceptable para objetos estáticos)

### 5.4 El Nuevo Desafío: Cable en Oscuridad Total

**Análisis del Problema:**

```
IMAGEN LEFT (ejemplo):                IMAGEN RIGHT:
┌──────────────────────┐            ┌──────────────────────┐
│ ████████████████████ │            │ ████████████████████ │
│ ████████████████████ │            │ ████████████████████ │
│ ███╭──cable──╮██████ │            │ ██████╭──cable──╮███ │
│ ████████████████████ │            │ ████████████████████ │
└──────────────────────┘            └──────────────────────┘
  Fondo negro + Cable iluminado       (Mismo cable, posición desplazada)

PROBLEMA SGBM:
- Fondo negro: [0, 0, 0] en todos lados → NO hay features
- Cable: [200, 200, 200] uniforme → Intensidad similar en todo el cable
- ¿Cómo matchear punto específico del cable entre LEFT y RIGHT?
  → IMPOSIBLE solo con intensidad
```

**Por qué Fallan los Métodos Tradicionales:**

1. **SGBM requiere textura local:**
   - Compara bloques de píxeles (ej: 17x17)
   - Necesita variación de intensidad dentro del bloque
   - Cable uniforme → todos los bloques parecen iguales

2. **Métodos de gradiente (Sobel) también fallan:**
   - Solo detectan bordes del cable
   - Bordes izquierdo y derecho del cable son ambiguos (geometría simétrica)
   - No hay suficientes features únicas para matching robusto

3. **Esqueletización produce "raíces":**
   - Thinning algorithms generan ramificaciones espurias
   - Cable aparece como "tallo" principal con múltiples "pelos" laterales
   - Geometría ruidosa, no representa la forma real

---

## 6. ARQUITECTURA DEL SOFTWARE

### 6.1 Estructura General del Proyecto

```
stereo_photogrammetry_cm5/
├── main.py                          # Punto de entrada (PyQt5 GUI)
├── requirements.txt                 # Dependencias Python
│
├── config/
│   └── camera_config.py             # Gestión de configuración y calibración
│
├── camera/
│   ├── stereo_camera.py             # Interfaz con libcamera (captura)
│   ├── camera_calibration.py        # Algoritmos de calibración
│   └── frame_synchronizer.py        # Sincronización temporal
│
├── gui/
│   ├── main_window.py               # Ventana principal
│   ├── calibration_dialog.py        # Diálogo de calibración interactivo
│   ├── processing_dialog.py         # Diálogo de procesamiento 3D
│   └── camera_preview.py            # Vista previa en tiempo real
│
├── processing/
│   ├── stereo_processor.py          # Pipeline estéreo (SGBM/BM)
│   ├── point_cloud_generator.py     # Exportador de nubes 3D
│   ├── wire_matcher.py              # Matching guiado para cables (Fase 2)
│   ├── endpoint_detector.py         # Detección automática de extremos
│   ├── smart_wire_tracker.py        # Solución de laberinto (NUEVO)
│   └── [otros wire planners...]     # Iteraciones anteriores
│
├── utils/
│   ├── logger.py                    # Sistema de logging
│   └── file_manager.py              # Gestión de archivos
│
└── data/
    ├── calibration/                 # Sesiones de calibración
    │   └── calibration_data.json    # Parámetros calibrados
    ├── captures/                    # Capturas estéreo
    └── results/                     # Nubes 3D exportadas
        └── debug/                   # Imágenes de depuración
```

### 6.2 Componentes Clave

#### 6.2.1 Sistema de Configuración (`config/camera_config.py`)

**Responsabilidades:**
- Cargar/guardar configuración de cámaras
- Gestionar datos de calibración (K1, K2, D1, D2, R, T, Q)
- Validar estado del sistema (`is_calibrated()`)
- Proveer parámetros a otros módulos

**Formato de Datos de Calibración:**

```json
{
  "left_camera_matrix": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
  "right_camera_matrix": [...],
  "left_distortion": [k1, k2, p1, p2, k3],
  "right_distortion": [...],
  "rotation_matrix": [...],
  "translation_vector": [Tx, Ty, Tz],
  "essential_matrix": [...],
  "fundamental_matrix": [...],
  "Q_matrix": [...],  // CRÍTICA para reproyección 3D
  "calibration_error": 0.52,
  "calibration_date": "2025-01-04T12:00:00"
}
```

#### 6.2.2 Sistema de Captura (`camera/stereo_camera.py`)

**Interfaz con Hardware:**
```python
def capture_stereo_pair(self, countdown_seconds=10):
    """
    Captura sincronizada usando libcamera-jpeg

    Proceso:
    1. Countdown visual para preparación
    2. Lanzamiento simultáneo de 2 threads
    3. Ejecución paralela:
       - Thread A: libcamera-jpeg --camera 0 ...
       - Thread B: libcamera-jpeg --camera 1 ...
    4. Espera de completación
    5. Validación de imágenes capturadas
    6. Guardado en data/captures/stereo_TIMESTAMP/
    """
```

**Características:**
- ✅ Captura casi simultánea (<100ms diferencia)
- ✅ Validación de existencia de archivos
- ✅ Organización automática por timestamp
- ✅ Soporte para parámetros personalizados (resolución, exposición, ISO)

#### 6.2.3 Sistema de Calibración (`camera/camera_calibration.py`)

**Pipeline de Calibración:**

```python
def calibrate_from_session(session_path):
    """
    1. Cargar pares de imágenes (left_X.jpg, right_X.jpg)
    2. Para cada par:
       a. Detectar esquinas de ajedrez
       b. Refinar detección con cornerSubPix
       c. Validar calidad (nitidez, contraste, cobertura)
    3. Calibración individual de cada cámara:
       - cv2.calibrateCamera() → K, D, rvecs, tvecs
    4. Calibración estéreo:
       - cv2.stereoCalibrate() → R, T, E, F
    5. Rectificación:
       - cv2.stereoRectify() → P1, P2, Q
    6. Guardar en calibration_data.json
    """
```

**Métricas de Calidad:**
- **Error de reproyección:** Debe ser <1.0 px (ideal <0.5 px)
- **Cobertura del tablero:** 10%-80% del área de imagen
- **Nitidez:** Varianza del Laplaciano >3.0
- **Contraste:** Desviación estándar >30

#### 6.2.4 Procesador Estéreo (`processing/stereo_processor.py`)

**Clase Principal:** `StereoProcessor`

**Métodos Clave:**

```python
class StereoProcessor:
    def __init__(self, camera_config):
        """Carga calibración y configura algoritmos SGBM/BM"""

    def rectify_images(self, left, right):
        """Rectifica imágenes usando calibración"""
        # Usa cv2.remap con mapas precalculados

    def compute_disparity(self, left, right, algorithm='SGBM'):
        """Calcula mapa de disparidad"""
        # SGBM: Alta calidad, lento (~30-60s)
        # BM: Rápido, menor calidad (~10-20s)

    def disparity_to_depth(self, disparity):
        """Convierte disparidad a profundidad (metros)"""
        # Z = (focal × baseline) / disparidad

    def generate_point_cloud(self, left_img, disparity):
        """Genera nube de puntos 3D"""
        # Usa matriz Q para reproyección
        # (X,Y,Z) = Q × (x, y, d, 1)

    def process_stereo_pair(self, left, right):
        """Pipeline completo: rectificar → disparidad → profundidad → 3D"""
```

**Configuración SGBM (Fase 1):**

```python
sgbm = cv2.StereoSGBM_create(
    minDisparity=0,
    numDisparities=96,           # Rango de búsqueda
    blockSize=17,                # Tamaño de ventana
    uniquenessRatio=5,           # Confianza
    speckleWindowSize=50,        # Filtro de ruido
    speckleRange=16,
    P1=8 * 3 * 17**2,           # Penalización suavidad
    P2=32 * 3 * 17**2,
    preFilterCap=61,
    mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
)
```

#### 6.2.5 Generador de Nubes de Puntos (`processing/point_cloud_generator.py`)

**Formatos de Exportación:**

| Formato | Características | Uso Típico |
|---------|----------------|------------|
| **PLY** | ASCII/Binary, colores, normales | CloudCompare, MeshLab |
| **XYZ** | Solo coordenadas (X Y Z) | MATLAB, Python simple |
| **PCD** | Point Cloud Data (PCL format) | ROS, PCL library |
| **OBJ** | Mesh opcional | Blender, Maya |

**Funcionalidades:**
- ✅ Downsampling voxel (reducir densidad)
- ✅ Estimación de normales
- ✅ Filtrado estadístico de outliers
- ✅ Preservación de colores RGB

#### 6.2.6 Interfaz Gráfica (`gui/main_window.py`)

**Diseño Modular:**

```
┌────────────────────────────────────────┐
│  Main Window (PyQt5)                   │
├────────────────────────────────────────┤
│  [Calibrate] [Preview] [Capture]       │
│                                        │
│  ┌──────────────┐  ┌──────────────┐  │
│  │  LEFT        │  │  RIGHT       │  │
│  │  Preview     │  │  Preview     │  │
│  └──────────────┘  └──────────────┘  │
│                                        │
│  Status: ✅ Sistema Calibrado          │
│  Baseline: 101mm | Error: 0.52px      │
│                                        │
│  [Process Latest Captures]             │
└────────────────────────────────────────┘
```

**Diálogos Especializados:**

1. **CalibrationDialog:**
   - Captura de 25 pares de imágenes con countdown
   - Validación en tiempo real (esquinas detectadas)
   - Procesamiento en background thread
   - Reporte de calidad final

2. **ProcessingDialog:**
   - Selección de imágenes a procesar
   - Configuración de algoritmo (SGBM/BM/Wire-guided)
   - **NUEVO:** Configuración de filtro de cable (Fase 2)
   - Visualización de resultados (disparidad, profundidad, confianza)
   - Exportación a múltiples formatos

---

## 7. SOLUCIÓN INNOVADORA: WIRE TRACKING CON MÁSCARAS

### 7.1 Evolución del Enfoque

Tras confirmar que los métodos tradicionales fallan sin relieve, se desarrolló un enfoque completamente nuevo basado en **geometría explícita del cable**.

**Cronología de Soluciones Probadas:**

| Iteración | Enfoque | Archivo | Resultado | Motivo Descarte |
|-----------|---------|---------|-----------|-----------------|
| V1 | Matching de gradientes (Sobel) | `wire_matcher.py` | ❌ Ambiguo | Bordes simétricos |
| V2 | Skeleton + A* path planning | `intelligent_wire_path_planner.py` | ❌ Raíces | Thinning genera ruido |
| V3 | Topology-aware planning | `topology_aware_wire_planner.py` | ⚠️ Complejo | Detección de nudos innecesaria |
| V4 | Distance Transform + Backtracking | `robust_wire_tracker.py` | ⚠️ Bueno | Uso de skeleton |
| **V5** | **Smart Wire Tracker (ACTUAL)** | `smart_wire_tracker.py` | ✅ **Óptimo** | **Sin skeleton, fluido** |

### 7.2 Solución Actual: SmartWireTracker V5

#### 7.2.1 Filosofía del Diseño

**Principio Fundamental:**
> "Tratar la máscara del cable como un **laberinto** a resolver, donde el objetivo es encontrar un camino fluido y continuo desde un extremo al otro."

**Diferencias Clave con Enfoques Previos:**

| Aspecto | Métodos Anteriores | SmartWireTracker V5 |
|---------|-------------------|---------------------|
| **Base de trabajo** | Skeleton (adelgazado) | Máscara completa (sin adelgazar) |
| **Detección de cruces** | Análisis topológico de nudos | Análisis de conectividad local |
| **Radio de marcado** | Fijo | **Adaptativo** (Distance Transform) |
| **Backtracking** | Limitado | **DFS completo** con memoria |
| **Detección de paralelas** | No | **Sí** (evita saltos entre líneas) |

#### 7.2.2 Algoritmo Detallado

**Entrada:**
- `mask`: Máscara binaria del cable (255=cable, 0=fondo) - **SIN esqueletizar**
- `start`: Punto de inicio (x, y) - detectado automáticamente
- `end`: Punto final (x, y) - detectado automáticamente

**Proceso:**

```python
class SmartWireTracker:
    def __init__(self, mask, start, end):
        # 1. Calcular Distance Transform
        self.distance_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        # Esto da el grosor local del cable en cada píxel

        # 2. Inicializar estado
        self.path = [start]
        self.visited_map = np.zeros_like(mask)  # Mapa de áreas cubiertas
        self.decision_points = []  # Stack para backtracking

    def track_wire(self, max_iterations=10000):
        current = self.start

        while current != self.end and iterations < max_iterations:
            # 1. Marcar área visitada (CLAVE)
            self._mark_visited(current)

            # 2. Buscar candidatos en radio de búsqueda
            candidates = self._find_candidates(current)

            # 3. Filtrar candidatos ya visitados
            valid = [c for c in candidates if self.visited_map[c] == 0]

            # 4. Analizar opciones con momentum
            momentum = self._get_momentum_direction()  # Últimos 5 puntos
            flow_options = self._analyze_flow_options(
                current, valid, momentum, direction_to_end
            )

            # 5. Decisión de siguiente paso
            if len(flow_options) == 1:
                next_step = flow_options[0]  # Camino único

            elif len(flow_options) > 1:
                # BIFURCACIÓN: guardar punto de decisión
                sorted_opts = self._sort_options(current, flow_options, momentum)
                next_step = sorted_opts[0]  # Tomar mejor opción
                alternatives = sorted_opts[1:]  # Guardar resto

                self.decision_points.append(DecisionPoint(
                    location=current,
                    alternatives=alternatives,
                    chosen_index=len(self.path)
                ))

            else:
                # SIN OPCIONES: BACKTRACKING
                if not self._perform_backtracking():
                    break  # No hay dónde retroceder, fallo
                current = self.path[-1]
                continue

            # 6. Avanzar
            self.path.append(next_step)
            current = next_step

        return {'path': self.path, 'success': True, 'coverage': ...}
```

**Componentes Críticos:**

### A) Marcado Adaptativo (`_mark_visited`)

**Problema:** ¿Qué tan grande debe ser el área marcada como "visitada"?

- **Muy pequeña:** El tracker puede pasar dos veces por la misma zona
- **Muy grande:** Puede bloquear caminos válidos en cables anchos

**Solución:** Usar Distance Transform para adaptar el radio al grosor local

```python
def _mark_visited(self, point):
    x, y = point

    # 1. Obtener grosor local del cable
    dt_point = self.distance_transform[y, x]

    # 2. Buscar grosor máximo en vecindad pequeña (8px)
    dt_max_local = np.max(self.distance_transform[y-8:y+8, x-8:x+8])

    # 3. Promedio ponderado (70% punto + 30% máximo local)
    effective_distance = dt_point * 0.7 + dt_max_local * 0.3

    # 4. Radio adaptativo = 1.5x + margen
    adaptive_radius = int(effective_distance * 1.5) + 4
    adaptive_radius = clip(adaptive_radius, min_coverage_radius, max_coverage_radius)

    # 5. Marcar círculo de píxeles de cable como visitados
    circular_mask = create_circle(point, adaptive_radius)
    self.visited_map[circular_mask & (mask > 0)] = 255
```

**Resultado:**
- ✅ Zonas delgadas del cable: radio pequeño (~8-12 px)
- ✅ Zonas anchas: radio grande (~20-30 px)
- ✅ Cobertura uniforme sin bloquear caminos válidos

### B) Detección de Líneas Paralelas (`_detect_parallel_lines`)

**Problema Específico de Cables:**

Cables pueden tener partes que corren paralelas pero separadas:

```
      Cable doblado sobre sí mismo:

      ════════╗
              ║   ← Dos secciones paralelas
      ════════╝      muy cerca

      ¿Cómo evitar saltar entre ellas?
```

**Solución:**

```python
def _detect_parallel_lines(self, current, options, momentum):
    # 1. Calcular vector perpendicular al momentum
    perp = [-momentum[1], momentum[0]]

    # 2. Proyectar cada opción en dirección perpendicular
    projections = []
    for opt in options:
        opt_vec = opt - current
        lateral_proj = dot(opt_vec, perp)  # Distancia lateral
        forward_proj = dot(opt_vec, momentum)  # Distancia adelante
        projections.append((lateral_proj, forward_proj, opt))

    # 3. Agrupar por distancia lateral
    groups = []
    for i, (lat, fwd, opt) in enumerate(projections):
        if i == 0 or abs(lat - projections[i-1][0]) > wire_radius * 0.8:
            groups.append([opt])  # Nueva línea paralela
        else:
            groups[-1].append(opt)  # Misma línea

    return groups
```

**Aplicación en `_sort_options`:**

```python
def _sort_options(self, current, options, momentum):
    for opt in options:
        # ... cálculos de score ...

        # PENALIZACIÓN POR SALTO LATERAL
        parallel_groups = self._detect_parallel_lines(current, options, momentum)
        if len(parallel_groups) > 1:
            lateral_dist = self._get_lateral_distance(current, opt, momentum)
            if lateral_dist > wire_radius * 1.1:
                total_score -= 800  # Penalización suave
```

**Resultado:**
- ✅ Tracker prefiere continuar en la misma línea
- ✅ Solo salta a línea paralela si la actual se agota
- ✅ Evita zigzag entre secciones paralelas

### C) Backtracking (DFS)

**Concepto:** Cuando el tracker se atasca (sin opciones válidas), debe poder **retroceder** a una decisión anterior y probar una alternativa.

```python
def _perform_backtracking(self):
    while self.decision_points:
        last_dp = self.decision_points[-1]

        if not last_dp.alternatives:
            # Este punto no tiene más opciones, descartar
            self.decision_points.pop()
            continue

        # Tenemos alternativas!

        # 1. Identificar segmento "malo"
        cut_index = last_dp.chosen_index + 1
        bad_segment = self.path[cut_index:]

        # 2. Des-marcar área visitada del segmento malo
        for p in bad_segment:
            self._unmark_visited(p)

        # 3. Cortar path
        self.path = self.path[:cut_index]

        # 4. Tomar siguiente alternativa
        next_option = last_dp.alternatives.pop(0)
        self.path.append(next_option)
        self._mark_visited(next_option)

        return True  # Backtracking exitoso

    return False  # No hay dónde volver
```

**Ventajas:**
- ✅ Explora **todas las posibilidades** (DFS completo)
- ✅ No se rinde en la primera bifurcación errónea
- ✅ Garantiza encontrar camino si existe

### D) Continuidad Geométrica (`_sort_options`)

**Objetivo:** Priorizar opciones que mantengan un camino **fluido y natural**.

**Factores Considerados:**

| Factor | Peso | Descripción |
|--------|------|-------------|
| **Continuidad geométrica** | 1200 | `cos(θ)` entre momentum y dirección al candidato |
| **Continuidad de grosor** | 600 | Similitud de Distance Transform |
| **Centralidad** | 300 | Preferencia por centro del cable (DT alto) |
| **Progreso hacia fin** | 0.5 | Acercamiento al endpoint |
| **Penalización lateral** | -800 | Evitar saltos a líneas paralelas |

**Fórmula:**

```python
total_score = (
    geometric_score * 1200 +      # ¿Qué tan recto sigue?
    thickness_score * 600 +       # ¿Mantiene grosor similar?
    centeredness_score * 300 +    # ¿Está en el centro del cable?
    dist_to_end * 0.5 +           # ¿Se acerca al final?
    lateral_penalty               # ¿Salta a otra línea?
)
```

**Resultado:**
- ✅ Paths suaves sin cambios bruscos de dirección
- ✅ Respeta el grosor natural del cable
- ✅ Evita zigzags y rutas erráticas

#### 7.2.3 Detección Automática de Endpoints

**Clase:** `EndpointDetector` (`processing/endpoint_detector.py`)

**Métodos Disponibles:**

1. **Skeleton-based (recomendado):**
   ```python
   skeleton = thinning(mask)
   neighbors = count_neighbors(skeleton)
   endpoints = pixels_with_1_neighbor(skeleton)
   # Tomar los 2 más alejados
   ```

2. **Contour-based:**
   ```python
   contour = find_largest_contour(mask)
   approximate = approxPolyDP(contour)
   # Encontrar puntos extremos del polígono
   ```

3. **Distance Transform-based:**
   ```python
   dt = distance_transform(mask)
   centerline = threshold(dt, 0.5 * max(dt))
   skeleton = thin(centerline)
   endpoints = find_endpoints(skeleton)
   ```

**Visualización:**
- ✅ Verde: Punto de inicio (START)
- ✅ Rojo: Punto final (END)
- ✅ Se guardan en `data/results/debug/endpoints_{left|right}.png`

#### 7.2.4 Integración en el Pipeline Principal

**Flujo Modificado (Fase 2):**

```
[1] Usuario crea máscaras manualmente
    ↓
    edge_detection_tuner.py (GUI interactiva)
    ├─ Ajuste de parámetros Canny
    ├─ Visualización en tiempo real
    └─ Guardado: cable_mask_left.png, cable_mask_right.png
    ↓
[2] AUTOMÁTICO: Wire Tracking
    ↓
    processing_dialog.py → open_cable_filter_config()
    ├─ Detectar endpoints (EndpointDetector)
    ├─ Ejecutar SmartWireTracker para LEFT
    ├─ Ejecutar SmartWireTracker para RIGHT
    └─ Guardar resultados: wire_tracking_result
    ↓
    Resultado:
    {
        'left': {
            'start': (x, y),
            'end': (x, y),
            'path': [(x1,y1), (x2,y2), ...],  # Lista de puntos
            'coverage': 0.92  # 92% del cable cubierto
        },
        'right': { ... }
    }
    ↓
[3] FUTURO: Matching guiado entre paths
    ↓
    wire_matcher.py (en desarrollo)
    ├─ Para cada punto en path_left
    ├─ Buscar correspondiente en path_right
    ├─ Calcular disparidad punto a punto
    └─ Generar nube de puntos 3D del cable
```

**Código de Integración (`processing_dialog.py`):**

```python
def open_cable_filter_config(self):
    # 1. Abrir GUI de creación de máscaras
    result = open_cable_detection_tuner_with_switch(left_img, right_img)

    if result is not None:
        self.cable_mask_left, self.cable_mask_right = result

        # 2. NUEVO: Procesar máscaras con wire tracker
        processor = StereoProcessor(self.camera_config)

        wire_result = processor.process_wire_masks(
            self.cable_mask_left,
            self.cable_mask_right,
            save_debug=True
        )

        if wire_result['success']:
            self.wire_tracking_result = wire_result

            # Actualizar UI
            self.filter_status_label.setText(
                "✅ Filtro configurado + Wire tracking OK"
            )

            # Mostrar estadísticas
            QMessageBox.information(self, "Éxito",
                f"LEFT: {len(wire_result['left']['path'])} puntos "
                f"(Cov: {wire_result['left']['coverage']*100:.1f}%)\n"
                f"RIGHT: {len(wire_result['right']['path'])} puntos "
                f"(Cov: {wire_result['right']['coverage']*100:.1f}%)"
            )
```

**Código del Procesador (`stereo_processor.py`):**

```python
def process_wire_masks(self, mask_left, mask_right, save_debug=False):
    from processing.endpoint_detector import detect_wire_endpoints
    from processing.smart_wire_tracker import SmartWireTracker

    # Detectar endpoints en LEFT
    start_left, end_left = detect_wire_endpoints(
        mask_left, method="skeleton", visualize=save_debug
    )

    # Tracking en LEFT
    tracker_left = SmartWireTracker(mask_left, start_left, end_left)
    track_result_left = tracker_left.track_wire(max_iterations=10000)

    if save_debug:
        tracker_left.visualize('data/results/debug/wire_path_left.png')

    # Repetir para RIGHT
    start_right, end_right = detect_wire_endpoints(mask_right, ...)
    tracker_right = SmartWireTracker(mask_right, start_right, end_right)
    track_result_right = tracker_right.track_wire(...)

    return {
        'success': True,
        'left': track_result_left,
        'right': track_result_right
    }
```

#### 7.2.5 Visualizaciones de Debug

El sistema genera automáticamente imágenes de debug para análisis:

**Archivos Generados (`data/results/debug/`):**

| Archivo | Contenido | Utilidad |
|---------|-----------|----------|
| `endpoints_left.png` | Máscara + endpoints detectados (verde/rojo) | Validar detección de extremos |
| `endpoints_right.png` | Idem para RIGHT | Idem |
| `wire_path_left.png` | Máscara + área visitada + path | **Análisis principal** |
| `wire_path_right.png` | Idem para RIGHT | Idem |

**Leyenda de `wire_path_*.png`:**

```
Colores:
- Gris oscuro:         Máscara original del cable
- Rojo transparente:   Área visitada/cubierta por el path
- Cian brillante:      Path generado (línea central)
- Amarillo:            Puntos de decisión (bifurcaciones)
- Verde:               START
- Rojo:                END
```

**Ejemplo de Visualización:**

```
wire_path_left.png:
┌──────────────────────────────────────┐
│  ████████████████████████████████   │  ← Fondo negro
│  ███🟢═══════════════════════╗███   │  ← START (verde) + cable
│  ███║ŘŘŘ Área visitada ŘŘŘŘ║███   │  ← Rojo = visitado
│  ███║                         ║███   │
│  ███╚═══════════════════════🔴███   │  ← END (rojo)
│  ████████████████████████████████   │
│         Path en cian ─────────      │  ← Línea del path
└──────────────────────────────────────┘

Cobertura: 92.3%
Path: 1847 puntos
```

---

## 8. RESULTADOS ACTUALES Y DESAFÍOS

### 8.1 Logros Alcanzados

#### 8.1.1 Sistema Funcional Completo

✅ **Software Robusto:**
- Sistema modular con separación clara de responsabilidades
- GUI intuitiva (PyQt5) para calibración, captura y procesamiento
- Logging completo con rotación de archivos
- Manejo de errores y validaciones en todos los puntos críticos

✅ **Calibración Estable:**
- Error de reproyección consistente <1.0 píxeles
- Baseline correctamente estimado (~100mm)
- Parámetros intrínsecos bien caracterizados

✅ **Captura Sincronizada:**
- Diferencia temporal <100ms entre cámaras
- Integración nativa con `libcamera` en CM5
- Soporte para ajustes manuales de exposición y enfoque

✅ **Procesamiento 3D (Fase 1):**
- SGBM funciona correctamente en escenarios con textura
- Exportación a múltiples formatos (PLY, XYZ, PCD, OBJ)
- Visualizaciones de debug extensas

#### 8.1.2 Innovación en Wire Tracking

✅ **Path Generation Exitoso:**
- SmartWireTracker logra generar paths completos de extremo a extremo
- Cobertura típica del cable: 85-95%
- Backtracking funciona correctamente (encuentra caminos en laberintos complejos)

✅ **Detección Automática de Endpoints:**
- 3 métodos implementados (skeleton, contour, distance transform)
- Tasa de éxito alta en cables simples
- Visualizaciones claras para validación manual

### 8.2 Desafíos Actuales

#### 8.2.1 Calidad de las Máscaras Generadas

**Problema Principal:**

> "Cuando intento hacer el esqueleto de la cuerda se ve horrible, era como una raíz - la cuerda era el tallo pero había múltiples pelos de raíz que no eran realmente el esqueleto."

**Análisis Técnico:**

```
MÁSCARA IDEAL (suave):          MÁSCARA REAL (ruidosa):

    ════════╗                      ════╦══╗  ← Bifurcaciones espurias
            ║                          ║░░║  ← Ruido de borde
            ║                         ╬║  ║  ← "Pelos" laterales
            ╚════════                 ╚╩══╝  ← Grosor irregular
```

**Causas Identificadas:**

1. **Detección de bordes demasiado sensible:**
   - Parámetros Canny capturan ruido y pequeñas irregularidades
   - Cable real tiene imperfecciones (no es perfectamente cilíndrico)
   - Iluminación desigual crea sombras que se detectan como bordes

2. **Thinning algorithms producen ramificaciones:**
   - Algoritmo de Zhang-Suen (usado en `cv2.ximgproc.thinning`) es sensible a ruido
   - Pequeñas protuberancias en la máscara generan "pelos" en el skeleton
   - No hay información geométrica para distinguir "tallo" de "rama"

3. **SmartWireTracker V5 mitiga pero no resuelve:**
   - Al NO usar skeleton directamente, evita el problema de "raíces"
   - Pero si la máscara original tiene "islas" o "protuberancias", el tracker puede enredarse

**Impacto en Geometría:**

| Problema de Máscara | Efecto en Path | Severidad |
|---------------------|----------------|-----------|
| Islas aisladas | Tracker intenta conectarlas (zigzag) | ⚠️ Moderado |
| Protuberancias laterales | Path puede desviarse hacia ellas | ⚠️ Moderado |
| Grosor irregular | Path puede no seguir eje central | ⚠️ Moderado |
| Gaps (huecos) | Backtracking excesivo o fallo | 🔴 Alto |
| Cruces no reales | Decisiones incorrectas | 🔴 Alto |

#### 8.2.2 Falta de Fluidez Geométrica

**Problema:**

> "El camino se enreda y se confunde y genera formas no fluidas. Si es una espiral, debería tener una espiral fluida, lo cual aún no se consigue."

**Ejemplo Visual:**

```
CABLE REAL (espiral suave):     PATH GENERADO (errático):

    ╭─────╮                        ╭──╮
   │       │                      ╱│  │╲
   │       │                     ││  │ │
   │       │                     │╰─╮│ │
    ╰─────╯                      ╰──┼┼─╯
                                    ╰╯
```

**Causas Raíz:**

1. **Decisiones locales sin visión global:**
   - El tracker toma decisiones paso a paso (greedy)
   - No tiene conocimiento de la geometría global del cable
   - Puede elegir caminos localmente óptimos pero globalmente sub-óptimos

2. **Parámetros de scoring no capturan "fluidez":**
   - Continuidad geométrica (cos θ) solo mira un paso atrás (momentum)
   - No considera curvatura suave a largo plazo
   - No penaliza cambios bruscos de curvatura

3. **Máscaras ruidosas amplifican el problema:**
   - Protuberancias crean "opciones tentadoras" que desvían el path
   - El tracker explora ramas erróneas antes de hacer backtracking
   - Backtracking puede generar discontinuidades en la geometría

**Soluciones Propuestas (Próximos Pasos):**

| Solución | Descripción | Complejidad |
|----------|-------------|-------------|
| **Máscaras más limpias** | Pre-procesar con morfología (closing, opening) | Baja |
| **Suavizado gaussiano** | Aplicar blur suave a máscara antes de tracking | Baja |
| **Post-procesamiento del path** | Spline fitting sobre path generado | Media |
| **Curvatura en scoring** | Agregar factor de suavidad de curva | Media |
| **Lookahead limitado** | Explorar N pasos adelante antes de decidir | Alta |
| **Optimización global** | Ajustar path completo después de generarlo | Alta |

#### 8.2.3 Casos Complejos: Cruces y Solapamientos

**Situación Problemática:**

Cuando el cable se cruza sobre sí mismo:

```
Vista desde cámara:
    ║
    ╬  ← ¿Qué hacer aquí? ¿Seguir recto o girar?
    ║
```

**Estado Actual:**
- ⚠️ SmartWireTracker detecta bifurcación
- ⚠️ Crea punto de decisión
- ⚠️ Puede tomar decisión incorrecta (seguir la rama equivocada)
- ⚠️ Backtracking eventualmente corrige, pero puede dejar geometría irregular

**Necesidad:**
- Información de **profundidad** (disparidad) para disambiguar
- Conocer qué parte del cable está "adelante" y cuál "atrás"
- Actualmente NO disponible (tracking se hace en 2D independiente)

#### 8.2.4 Matching Estéreo Aún No Implementado

**Estado Actual:**
- ✅ Paths generados para LEFT y RIGHT independientemente
- ❌ NO hay matching punto-a-punto entre paths
- ❌ NO se calcula disparidad del cable
- ❌ NO se genera nube de puntos 3D del cable

**Desafío Técnico:**

Incluso con paths precisos, el matching entre LEFT y RIGHT es complejo:

```
PATH LEFT:                PATH RIGHT:
╭─────╮                   ╭─────╮
│     │                   │     │  ← Cables se ven similares
│     │  ¿Match?  ←→      │     │     pero con desplazamiento
│     │                   │     │
╰─────╯                   ╰─────╯

Problema:
- Paths pueden tener diferente número de puntos
- Orden de puntos puede variar (si tracking empezó por extremos opuestos)
- Secciones del cable pueden tener diferente visibilidad entre LEFT/RIGHT
```

**Soluciones en Exploración:**

1. **Correspondencia de segmentos:**
   - Dividir paths en segmentos de longitud similar
   - Usar geometría (ángulos, curvaturas) para matchear segmentos
   - Implementado parcialmente en `geometric_wire_matcher.py`

2. **Matching guiado por gradientes:**
   - Para puntos emparejados geométricamente, refinar con NCC de gradientes
   - Código base en `wire_matcher.py`

3. **Registración de curvas 3D:**
   - Assumir geometría similar entre LEFT/RIGHT
   - Usar ICP (Iterative Closest Point) para alinear paths
   - Requiere implementación adicional

### 8.3 Métricas de Desempeño Actual

#### 8.3.1 Wire Tracking (SmartWireTracker V5)

**En Máscaras de Buena Calidad:**

| Métrica | Valor Típico | Comentario |
|---------|--------------|------------|
| Cobertura del cable | 85-95% | ✅ Excelente |
| Tiempo de procesamiento | 5-15 segundos | ✅ Rápido |
| Puntos en path | 800-2000 | ✅ Denso |
| Backtracking activado | 10-30% iteraciones | ✅ Normal |
| Success rate | ~90% | ✅ Alto |

**En Máscaras Ruidosas:**

| Métrica | Valor Típico | Comentario |
|---------|--------------|------------|
| Cobertura del cable | 60-80% | ⚠️ Moderado |
| Tiempo de procesamiento | 15-45 segundos | ⚠️ Lento (más backtracking) |
| Puntos en path | 500-1500 | ⚠️ Disperso |
| Backtracking activado | 40-60% iteraciones | ⚠️ Alto |
| Success rate | ~60-70% | ⚠️ Inestable |
| Geometría fluida | Baja | 🔴 Problema principal |

#### 8.3.2 Endpoint Detection

| Método | Success Rate | Comentario |
|--------|--------------|------------|
| Skeleton-based | ~85% | ✅ Recomendado para cables simples |
| Contour-based | ~70% | ⚠️ Falla con geometría compleja |
| Distance Transform | ~80% | ✅ Robusto para cables gruesos |

**Casos de Fallo Comunes:**
- ❌ Cables con loops cerrados (sin endpoints claros)
- ❌ Múltiples componentes desconectados en la máscara
- ❌ Endpoints muy cercanos (cable en U cerrada)

---

## 9. PRÓXIMOS PASOS

### 9.1 Mejoras Inmediatas (Corto Plazo)

#### 9.1.1 Optimización de Máscaras

**Prioridad:** 🔴 Alta

**Tareas:**
1. **Pre-procesamiento morfológico:**
   ```python
   # Cerrar gaps pequeños
   kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
   mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

   # Eliminar ruido
   mask_clean = cv2.morphologyEx(mask_closed, cv2.MORPH_OPEN, kernel)

   # Suavizar bordes
   mask_smooth = cv2.GaussianBlur(mask_clean, (5, 5), 1.0)
   _, mask_final = cv2.threshold(mask_smooth, 127, 255, cv2.THRESH_BINARY)
   ```

2. **Parámetros Canny optimizados:**
   - Reducir sensibilidad para evitar "pelos"
   - Probar diferentes umbrales para cable específico
   - Implementar ajuste adaptativo según iluminación

3. **Validación visual:**
   - Implementar herramienta de comparación antes/después
   - Permitir ajuste manual de parámetros en tiempo real
   - Guardar presets para diferentes condiciones

**Resultado Esperado:**
- Máscaras sin protuberancias espurias
- Grosor más uniforme
- Paths más fluidos

#### 9.1.2 Post-Procesamiento de Paths

**Prioridad:** 🟠 Media-Alta

**Tareas:**
1. **Spline Fitting:**
   ```python
   from scipy.interpolate import splprep, splev

   # Path original (puede tener zigzags)
   path = tracker.path  # [(x1,y1), (x2,y2), ...]

   # Ajustar spline suave
   tck, u = splprep([x_coords, y_coords], s=smoothing_factor, k=3)

   # Generar path suavizado
   u_new = np.linspace(0, 1, num_points)
   x_smooth, y_smooth = splev(u_new, tck)

   path_smooth = list(zip(x_smooth, y_smooth))
   ```

2. **Filtro de curvatura:**
   - Detectar cambios bruscos de dirección
   - Suavizar localmente sin perder geometría global
   - Preservar features importantes (giros reales del cable)

3. **Validación geométrica:**
   - Asegurar que path suavizado sigue dentro de la máscara
   - No se desvíe más de N píxeles del path original
   - Mantener cobertura >80%

**Resultado Esperado:**
- Paths geométricamente suaves
- Espirales fluidas
- Mejor representación de geometría real

#### 9.1.3 Interfaz de Refinamiento Manual

**Prioridad:** 🟡 Media

**Concepto:**
Permitir al usuario corregir manualmente puntos problemáticos del path.

**Funcionalidades:**
- Visualización interactiva del path sobre máscara
- Click para agregar/eliminar puntos
- Drag-and-drop para ajustar posición
- Undo/Redo
- Guardado de paths corregidos

**Beneficio:**
- Combinación de automatización + experticia humana
- Útil para casos complejos donde tracker falla
- Datos de correcciones manuales pueden entrenar futuros modelos ML

### 9.2 Desarrollo de Matching Estéreo (Mediano Plazo)

**Prioridad:** 🔴 Alta (siguiente hito crítico)

#### 9.2.1 Correspondencia Geométrica

**Enfoque:**
Usar la geometría 3D inherente del cable para establecer correspondencias.

**Algoritmo Propuesto:**

```python
def match_wire_paths(path_left, path_right):
    """
    Estrategia:
    1. Normalizar paths (misma longitud paramétrica)
    2. Para cada punto en LEFT, encontrar candidatos en RIGHT usando:
       - Geometría local (curvatura similar)
       - Restricción epipolar (misma fila Y después de rectificación)
       - Orden secuencial (monoton icidad)
    3. Refinar con NCC de gradientes
    """

    # 1. Parametrizar paths (0 a 1)
    s_left = parametrize_by_arc_length(path_left)
    s_right = parametrize_by_arc_length(path_right)

    # 2. Resamplear a mismo número de puntos
    num_points = min(len(path_left), len(path_right))
    path_left_resampled = resample(path_left, num_points)
    path_right_resampled = resample(path_right, num_points)

    # 3. Para cada punto, calcular características locales
    for i in range(num_points):
        p_left = path_left_resampled[i]

        # Curvatura local
        k_left = compute_curvature(path_left_resampled, i)

        # Buscar en RIGHT con curvatura similar
        candidates_right = []
        for j in range(i-window, i+window):
            p_right = path_right_resampled[j]
            k_right = compute_curvature(path_right_resampled, j)

            if abs(k_left - k_right) < threshold:
                # Verificar restricción epipolar
                if abs(p_left[1] - p_right[1]) < epipolar_tolerance:
                    candidates_right.append(j)

        # Refinar con NCC de gradientes
        best_match = refine_with_ncc(p_left, candidates_right, img_left, img_right)

        # Calcular disparidad
        disparities[i] = p_left[0] - best_match[0]
```

**Implementación:**
- Extender `geometric_wire_matcher.py`
- Integrar con `stereo_processor.py`

#### 9.2.2 Generación de Nube de Puntos del Cable

**Una vez matcheados los paths:**

```python
def generate_wire_point_cloud(path_left_matched, path_right_matched, disparities, Q_matrix):
    """
    Para cada par de puntos matcheados:
    1. Obtener coordenadas 2D (x_left, y_left) y disparidad d
    2. Reproyectar a 3D usando matriz Q
    3. Generar puntos 3D del cable
    """

    points_3d = []

    for (x_left, y_left), d in zip(path_left_matched, disparities):
        # Reproyección 3D
        point_homogeneous = Q @ [x_left, y_left, d, 1]
        X = point_homogeneous[0] / point_homogeneous[3]
        Y = point_homogeneous[1] / point_homogeneous[3]
        Z = point_homogeneous[2] / point_homogeneous[3]

        points_3d.append([X, Y, Z])

    # Exportar
    export_to_ply(points_3d, colors, "wire_3d.ply")
```

**Validación:**
- Comparar con ground truth (si disponible)
- Verificar consistencia geométrica (cable continuo, sin saltos)
- Analizar cobertura espacial

### 9.3 Investigación y Escalamiento (Largo Plazo)

#### 9.3.1 Caracterización de Iluminación

**Objetivo:** Determinar condiciones óptimas de iluminación que simulen espacio.

**Experimentos:**
1. **Barrido de intensidad:**
   - Probar 10-100 lúmenes en incrementos
   - Medir SNR (Signal-to-Noise Ratio) en imágenes
   - Identificar mínimo funcional

2. **Ángulo de iluminación:**
   - LED frontal vs lateral vs cenital
   - Medir contraste cable-fondo
   - Simular iluminación solar direccional

3. **Espectro de luz:**
   - LED blanco vs amarillo vs infrarrojo
   - Evaluar reflectancia del cable real (cuando esté disponible)

**Resultado Esperado:**
- Especificaciones técnicas de sistema de iluminación
- Protocolo de configuración para misión real

#### 9.3.2 Migración a Cable Real de la Misión

**Cuando se reciba el cable definitivo:**

1. **Caracterización física:**
   - Grosor exacto
   - Material y reflectancia
   - Comportamiento bajo iluminación controlada

2. **Ajuste de parámetros:**
   - Re-calibrar detección de bordes
   - Ajustar wire_radius en SmartWireTracker
   - Validar endpoints detection

3. **Pruebas exhaustivas:**
   - Diferentes configuraciones (recto, curvo, espiral)
   - Diferentes distancias (0.3m - 1.0m)
   - Diferentes ángulos de cámara

#### 9.3.3 Validación con Ground Truth

**Metodología:**

1. **Mediciones físicas:**
   - Usar cinta métrica/calibrador para medir cable real
   - Fotografiar con escala de referencia
   - Crear modelo 3D de referencia (CAD o escaneo 3D)

2. **Comparación:**
   - Superponer nube de puntos generada con ground truth
   - Calcular error RMS (Root Mean Square)
   - Identificar zonas de mayor desviación

3. **Iteración:**
   - Ajustar parámetros según errores observados
   - Repetir hasta error <5mm (objetivo)

#### 9.3.4 Posible Integración de Machine Learning

**Si el enfoque geométrico no alcanza precisión requerida:**

**Opciones:**

1. **Semantic Segmentation (U-Net/DeepLabV3):**
   - Entrenar red para segmentar cable
   - Generar máscaras más limpias automáticamente
   - Requiere dataset etiquetado (~500-1000 imágenes)

2. **Stereo Matching con CNN (RAFT-Stereo, PSMNet):**
   - Redes pre-entrenadas en datasets de estéreo
   - Fine-tuning en imágenes de cables
   - Mayor precisión que SGBM en objetos delgados

3. **Path Planning con RL (Reinforcement Learning):**
   - Agente aprende a seguir cable de forma fluida
   - Recompensa por cobertura + fluidez geométrica
   - Experimental, requiere mucho compute

**Consideraciones:**
- Requiere hardware adicional (GPU)
- Tiempo de desarrollo significativo
- Trade-off entre precisión y complejidad

---

## 10. CONCLUSIONES

### 10.1 Estado del Proyecto

El proyecto **LINKU** ha evolucionado desde una idea inicial de fotogrametría estéreo tradicional hacia un **sistema especializado** para reconstrucción 3D de cables en entornos de oscuridad total. Este cambio de enfoque fue guiado por:

1. **Validación empírica** de que métodos tradicionales (SGBM, Metashape) fallan sin relieve ambiental
2. **Iteración sistemática** a través de múltiples enfoques (gradientes, skeleton, topology-aware)
3. **Innovación técnica** con el desarrollo del SmartWireTracker (laberinto + backtracking)

**Estado Actual:**

| Componente | Completitud | Calidad |
|------------|-------------|---------|
| **Hardware** | 90% | ✅ Listo (pendiente cable final) |
| **Calibración** | 100% | ✅ Robusto y validado |
| **Captura sincronizada** | 100% | ✅ Funcional |
| **GUI** | 95% | ✅ Completo e intuitivo |
| **Procesamiento tradicional (Fase 1)** | 100% | ✅ Validado en entorno ideal |
| **Creación de máscaras** | 100% | ✅ Herramienta interactiva |
| **Wire Tracking (2D)** | 85% | ⚠️ Funcional, necesita refinamiento |
| **Endpoint detection** | 80% | ⚠️ Funcional, casos edge fallan |
| **Matching estéreo (3D)** | 30% | 🔴 En desarrollo |
| **Nube de puntos de cable** | 0% | 🔴 No implementado |

### 10.2 Aprendizajes Clave

#### 10.2.1 Técnicos

1. **La calibración es fundamental:**
   - Un error de calibración de 14x en profundidad hace inútil el mejor algoritmo
   - Invertir tiempo en calibración correcta ahorra debugging posterior
   - Validar baseline y focal length con medidas físicas

2. **El entorno dicta la solución:**
   - No todos los problemas de visión estéreo se resuelven con SGBM
   - Ausencia de textura requiere enfoques no convencionales
   - La geometría del objeto (cable) es información valiosa

3. **La visualización es crítica:**
   - Imágenes de debug incorrectas pueden engañar sobre el funcionamiento real
   - Invertir en herramientas de visualización ahorra tiempo de debugging
   - Validar visualmente cada etapa del pipeline

4. **Iteración sobre perfección:**
   - Mejor tener 5 versiones probadas que 1 versión "perfecta" sin probar
   - Cada iteración (V1-V5 del wire tracker) aportó aprendizajes
   - El código experimental es tan valioso como el código productivo

#### 10.2.2 Metodológicos

1. **Validación con herramientas comerciales:**
   - Probar con Metashape confirmó que no era problema de implementación
   - Ahorró semanas de optimización innecesaria de parámetros

2. **Documentación continua:**
   - Crear `.md` con cada cambio significativo facilita revisión
   - Futuros desarrolladores (o uno mismo en 3 meses) agradecen el contexto

3. **División en fases:**
   - Fase 1 (ideal) validó componentes básicos
   - Fase 2 (oscuridad) ataca el problema real sin desperdiciar tiempo

### 10.3 Viabilidad del Proyecto

**¿Es viable reconstruir 3D del cable en oscuridad?**

**Respuesta:** ✅ **Sí, con las siguientes condiciones:**

1. **Máscaras de alta calidad:**
   - Pre-procesamiento morfológico reduce ruido
   - Ajuste fino de parámetros Canny para cada setup
   - Posiblemente ML para segmentación más robusta

2. **Paths geométricamente correctos:**
   - Post-procesamiento con splines
   - Validación de fluidez
   - Refinamiento manual en casos complejos

3. **Matching estéreo especializado:**
   - No usar SGBM tradicional
   - Aprovechar geometría de paths
   - Combinar con gradientes/NCC para precisión

4. **Iluminación controlada:**
   - Caracterización de lúmenes óptimos
   - Simulación de condiciones espaciales reales
   - Protocolo de configuración documentado

**Tiempo Estimado para Completar:**
- **Corto plazo (1-2 meses):** Máscaras limpias + paths fluidos
- **Mediano plazo (2-4 meses):** Matching estéreo funcional
- **Largo plazo (4-6 meses):** Validación completa + documentación de misión

### 10.4 Impacto y Aplicaciones

**Más Allá de LINKU:**

El sistema desarrollado tiene aplicaciones potenciales en:

1. **Inspección de infraestructura:**
   - Cables de alta tensión
   - Puentes colgantes
   - Tuberías industriales

2. **Robótica:**
   - Manipulación de cables por robots
   - Navegación en entornos oscuros

3. **Defensa/Seguridad:**
   - Detección de alambres de trampa
   - Inspección de estructuras

4. **Investigación académica:**
   - Publicaciones en visión por computadora
   - Dataset de cables en condiciones adversas
   - Algoritmos de path planning adaptativos

### 10.5 Recomendación Final

**Para el equipo de desarrollo:**

1. **Priorizar calidad de máscaras:**
   - Invertir tiempo en ajustar pre-procesamiento
   - Probar diferentes configuraciones de iluminación
   - Validar visualmente cada mejora

2. **No subestimar el matching:**
   - Es el componente más crítico restante
   - Considerar consultar con expertos en geometría computacional
   - Probar múltiples enfoques en paralelo

3. **Documentar experimentos:**
   - Cada configuración probada (iluminación, parámetros, etc.)
   - Resultados cuantitativos (cobertura, error, tiempo)
   - Imágenes representativas

4. **Prepararse para iteración:**
   - El cable real de la misión puede comportarse diferente
   - Tener sistema flexible para ajustes rápidos
   - Mantener versiones anteriores funcionales (backup)

**Para la misión espacial:**

El sistema tiene potencial real de funcionar en el espacio, **pero requiere:**
- ✅ Validación exhaustiva en Tierra
- ✅ Caracterización con cable de vuelo
- ✅ Protocolo de iluminación bien definido
- ✅ Sistema de respaldo (redundancia)
- ✅ Métricas de confianza en reconstrucción

**El camino está trazado, los fundamentos son sólidos, y la visión es alcanzable.** 🚀

---

## ANEXOS

### A. Glosario Técnico

| Término | Definición |
|---------|------------|
| **Baseline** | Distancia entre centros ópticos de las dos cámaras (~100mm en este proyecto) |
| **Disparidad** | Diferencia en píxeles de la posición de un punto entre imagen LEFT y RIGHT |
| **Rectificación** | Transformación de imágenes para que líneas epipolares sean horizontales |
| **Matriz Q** | Matriz 4x4 que transforma (x, y, disparidad) → (X, Y, Z) en espacio 3D |
| **SGBM** | Semi-Global Block Matching - algoritmo de cálculo de disparidad |
| **Distance Transform** | Mapa que indica distancia de cada píxel al borde más cercano |
| **Backtracking (DFS)** | Retroceder en decisiones previas para explorar alternativas (Depth-First Search) |
| **Skeleton** | Versión adelgazada de una forma binaria (eje central) |
| **Spline** | Curva suave que interpola o aproxima puntos |

### B. Referencias Bibliográficas

1. **Tesis de Referencia (Parámetros SGBM):**
   - "Reconstrucción 3D mediante el uso de un par de cámaras a modo de estereovisión"
   - Escuela Politécnica Nacional de Ecuador, 2014

2. **OpenCV Documentation:**
   - Stereo Rectification: https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html
   - StereoBM/StereoSGBM: https://docs.opencv.org/4.x/dd/d53/tutorial_py_depthmap.html

3. **Algoritmos de Thinning:**
   - Zhang-Suen Algorithm (1984)
   - Implementación: `cv2.ximgproc.thinning()`

4. **Agisoft Metashape:**
   - Software comercial de fotogrametría: https://www.agisoft.com/

### C. Archivos Clave del Código

**Para Desarrolladores Futuros:**

| Propósito | Archivo Principal | Líneas Clave |
|-----------|-------------------|--------------|
| Calibración | `camera/camera_calibration.py` | 60-150 (detección esquinas), 200-350 (calibración estéreo) |
| Captura | `camera/stereo_camera.py` | 80-150 (captura sincronizada) |
| Procesamiento | `processing/stereo_processor.py` | 142-162 (parámetros SGBM), 318-392 (rectificación), 392-650 (disparidad) |
| Wire Tracking | `processing/smart_wire_tracker.py` | 56-145 (algoritmo principal), 187-243 (marcado adaptativo), 334-400 (scoring) |
| Endpoint Detection | `processing/endpoint_detector.py` | 25-80 (skeleton-based), 82-120 (contour-based) |
| GUI Principal | `gui/main_window.py` | Todo el archivo |
| Processing Dialog | `gui/processing_dialog.py` | 1142-1250 (integración wire tracker) |

### D. Historial de Versiones del Software

| Versión | Fecha (aprox.) | Cambios Principales |
|---------|----------------|---------------------|
| v0.1 | (Fase inicial) | Sistema básico con Arducam 2MP, SGBM estándar |
| v0.5 | (Tras migrar a IMX477) | Calibración robusta, GUI mejorada |
| v1.0 | (Fin Fase 1) | Sistema completo funcional en entorno ideal |
| v1.5 | (Inicio Fase 2) | Cámara oscura, primeros intentos wire matching |
| v2.0 | (Actual) | SmartWireTracker V5, integración completa máscaras |
| v2.5 | (Próximo) | Matching estéreo funcional, nube de puntos de cable |

---

**FIN DEL INFORME TÉCNICO**

*Documento preparado para: Proyecto LINKU - Sistema de Fotogrametría Estéreo para Misión Espacial Dual-Satélite*

*Fecha: Enero 2025*

*Versión: 1.0*

---
