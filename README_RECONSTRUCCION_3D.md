# Proceso Completo de Reconstrucción 3D - Fotogrametría Estéreo

## Tabla de Contenidos

1. [Introducción al Problema](#introducción-al-problema)
2. [Fundamentos Matemáticos](#fundamentos-matemáticos)
3. [Pipeline Completo de Reconstrucción](#pipeline-completo-de-reconstrucción)
4. [Implementación Detallada por Módulo](#implementación-detallada-por-módulo)
5. [Matrices de Calibración: Explicación Profunda](#matrices-de-calibración-explicación-profunda)
6. [Algoritmos de Matching Estéreo](#algoritmos-de-matching-estéreo)
7. [Flujo de Datos Completo](#flujo-de-datos-completo)
8. [Análisis de Errores y Troubleshooting](#análisis-de-errores-y-troubleshooting)

---

## Introducción al Problema

### ¿Qué es la Fotogrametría Estéreo?

La fotogrametría estéreo es una técnica que **reconstruye información tridimensional (X, Y, Z)** a partir de **dos imágenes 2D** del mismo objeto tomadas desde posiciones ligeramente diferentes.

**Concepto clave:** Los humanos tenemos dos ojos separados ~6.5cm. Nuestro cerebro compara ambas imágenes y calcula profundidad. Este sistema hace lo mismo con cámaras.

### El Problema Fundamental a Resolver

Dado:
- **Imagen izquierda** con un objeto en coordenadas `(x_left, y_left)` en píxeles
- **Imagen derecha** con el **mismo objeto** en coordenadas `(x_right, y_right)` en píxeles

Queremos calcular:
- **Posición 3D** del objeto en el mundo real: `(X, Y, Z)` en metros

**Desafío principal:** ¿Cómo encontrar qué píxel en la imagen derecha corresponde al mismo punto físico que un píxel dado en la imagen izquierda?

---

## Fundamentos Matemáticos

### Geometría Epipolar

#### Líneas Epipolares

Cuando un punto 3D `P` en el mundo se proyecta en dos cámaras:
- En la cámara izquierda aparece en `p_left`
- En la cámara derecha aparece en `p_right`

**Restricción epipolar:** `p_right` DEBE estar sobre una línea específica en la imagen derecha llamada **línea epipolar**.

Sin rectificación:
```
Imagen izquierda          Imagen derecha
    │                         │
    │ p_left (x1,y1)          │
    │                         │ Línea epipolar (curva o diagonal)
    │                         │  ╱
    │                         │ ╱ p_right podría estar en cualquier
    │                         │╱  punto de esta línea
    └─────────────            └──────────
```

Con rectificación (nuestro objetivo):
```
Imagen izquierda          Imagen derecha
    │                         │
    │ p_left (x1,y1)          │ p_right (x2,y1)  ← MISMA FILA Y
    │─────────────────────────│─────────────────── Línea epipolar HORIZONTAL
    │                         │
    └─────────────            └──────────
```

### Triangulación Estéreo

Una vez que sabemos la correspondencia entre `p_left` y `p_right`, podemos calcular la posición 3D mediante **triangulación**:

```
        P (X,Y,Z)  ← Punto en el mundo 3D
       ╱ ╲
      ╱   ╲
     ╱     ╲
 C_left  C_right  ← Centros ópticos de cámaras
```

**Fórmula de disparidad:**
```
disparidad (d) = x_left - x_right
```

**Fórmula de profundidad:**
```
Z = (f × B) / d

Donde:
  f = focal length (longitud focal en píxeles)
  B = baseline (distancia entre cámaras en metros)
  d = disparidad (diferencia horizontal en píxeles)
```

**Ejemplo numérico:**
- Focal length: `f = 1500` píxeles
- Baseline: `B = 0.10` metros (10 cm entre cámaras)
- Disparidad: `d = 50` píxeles

```
Z = (1500 × 0.10) / 50 = 3.0 metros
```

**Interpretación física:**
- **Objetos cercanos:** Gran diferencia en posición entre imágenes → Alta disparidad → Z pequeño
- **Objetos lejanos:** Pequeña diferencia → Baja disparidad → Z grande

---

## Pipeline Completo de Reconstrucción

El sistema realiza **5 etapas** para convertir imágenes 2D en modelos 3D:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ETAPA 1: CALIBRACIÓN                              │
│  - Captura 25 imágenes con tablero de ajedrez                       │
│  - Detecta esquinas del patrón (9×6 puntos)                         │
│  - Calcula parámetros intrínsecos (fx, fy, cx, cy, distorsión)     │
│  - Calcula parámetros extrínsecos (R, T entre cámaras)             │
│  - Guarda matrices en calibration_data.json                          │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    ETAPA 2: CAPTURA ESTÉREO                          │
│  - Usuario posiciona objeto en FOV                                   │
│  - Sistema captura simultáneamente:                                  │
│      • left.jpg (3840×2880, IMX477 CAM0)                           │
│      • right.jpg (3840×2880, IMX477 CAM1)                          │
│  - Sincronización: <50ms diferencia temporal                         │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    ETAPA 3: RECTIFICACIÓN                            │
│  - Carga matrices de calibración                                     │
│  - Elimina distorsión de lentes                                      │
│  - Alinea imágenes epipolares (líneas horizontales)                 │
│  - Genera left_rectified.jpg y right_rectified.jpg                  │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    ETAPA 4: CÁLCULO DE DISPARIDAD                    │
│  - Algoritmo SGBM/BM busca correspondencias                         │
│  - Para cada píxel (x,y) en left:                                    │
│      • Busca píxel correspondiente en right (misma fila y)          │
│      • Calcula disparidad: d = x_left - x_right                     │
│  - Genera disparity_map (valores 0-160 píxeles)                     │
│  - Aplica filtros: mediana, WLS, statistical outlier removal        │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    ETAPA 5: RECONSTRUCCIÓN 3D                        │
│  - Usa matriz Q de reproyección                                      │
│  - Para cada píxel válido (x, y, d):                                 │
│      • Calcula X = f(x, cx, d)                                       │
│      • Calcula Y = f(y, cy, d)                                       │
│      • Calcula Z = (f × B) / d                                       │
│  - Extrae colores RGB de imagen original                             │
│  - Filtra outliers (Z < 0.3m, Z > 5m, estadísticos)                │
│  - Exporta nube de puntos (PLY, XYZ, PCD, OBJ)                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementación Detallada por Módulo

### MÓDULO 1: Calibración (`camera/camera_calibration.py`)

#### Propósito

La calibración resuelve **dos problemas fundamentales**:

1. **Parámetros intrínsecos:** Cómo cada cámara convierte puntos 3D a 2D (modelo de cámara pinhole)
2. **Parámetros extrínsecos:** Cómo están posicionadas las cámaras en el espacio relativo

#### Proceso Paso a Paso

##### Paso 1.1: Captura de Imágenes con Patrón

**Archivo:** `gui/calibration_dialog.py:185-220`

```python
def capture_calibration_image(self):
    """
    Captura un par estéreo del tablero de ajedrez.

    El tablero debe tener:
    - 10×7 casillas (9×6 esquinas internas detectables)
    - Tamaño de casilla: 24mm × 24mm
    """

    # Captura sincronizada
    left_path, right_path = self.stereo_camera.capture_calibration_pair(
        session_id=f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    # Guarda en: data/calibration/calibration_TIMESTAMP/
    #   ├── left_01.jpg
    #   ├── right_01.jpg
    #   ├── left_02.jpg
    #   └── ... (hasta 25 pares)
```

**¿Por qué 25 imágenes?**
- Cubrir todo el campo de visión (FOV)
- Diferentes ángulos de rotación (±15°, ±30°, ±45° en X, Y, Z)
- Diferentes distancias (30cm, 60cm, 100cm)
- Redundancia para validación estadística

##### Paso 1.2: Detección de Esquinas

**Archivo:** `camera/camera_calibration.py:180-210`

```python
def detect_chessboard_corners(image_path, board_size=(9, 6)):
    """
    Detecta esquinas del tablero de ajedrez con precisión sub-pixel.

    Args:
        image_path: Ruta a imagen del tablero
        board_size: Tupla (cols, rows) de esquinas internas

    Returns:
        corners: Array numpy (N, 1, 2) con coordenadas (x, y) de esquinas
        success: Boolean indicando si se detectaron todas las esquinas
    """

    # Cargar imagen
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detección inicial de esquinas
    ret, corners = cv2.findChessboardCorners(
        gray,
        board_size,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH |
              cv2.CALIB_CB_NORMALIZE_IMAGE |
              cv2.CALIB_CB_FAST_CHECK
    )

    if not ret:
        return None, False

    # Refinamiento sub-pixel (CRÍTICO para precisión)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners_refined = cv2.cornerSubPix(
        gray,
        corners,
        winSize=(11, 11),    # Ventana de búsqueda 11×11
        zeroZone=(-1, -1),   # No usar zona muerta
        criteria=criteria    # Precisión: 0.001 píxeles
    )

    return corners_refined, True
```

**Visualización de esquinas detectadas:**
```
Tablero de ajedrez 10×7:
┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
│     │█████│     │█████│     │█████│     │█████│     │█████│
├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│█████│     │█████│     │█████│     │█████│     │█████│     │
├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│     │█████│  ●  │█████│  ●  │█████│  ●  │█████│  ●  │█████│  ← Esquinas detectadas (●)
├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│█████│     │█████│     │█████│     │█████│     │█████│     │
└─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘

Total esquinas internas: 9 columnas × 6 filas = 54 puntos
```

##### Paso 1.3: Calibración Monocular (cada cámara por separado)

**Archivo:** `camera/camera_calibration.py:245-285`

```python
def calibrate_single_camera(object_points, image_points, image_size):
    """
    Calcula parámetros intrínsecos y distorsión de una cámara.

    Args:
        object_points: Lista de arrays (Nx3) con coordenadas 3D del tablero
                       Ejemplo: [[0,0,0], [24,0,0], [48,0,0], ...] en mm
        image_points: Lista de arrays (Nx2) con coordenadas 2D detectadas
                      Ejemplo: [[245.3, 189.7], [267.1, 190.2], ...]
        image_size: Tupla (width, height) de imagen

    Returns:
        camera_matrix: Matriz 3×3 con parámetros intrínsecos
        dist_coeffs: Array 1×5 con coeficientes de distorsión
        rvecs: Vectores de rotación por imagen
        tvecs: Vectores de traslación por imagen
        mean_error: Error de reproyección promedio en píxeles
    """

    # Preparar puntos 3D del tablero (coordenadas reales en mm)
    # Asume que el tablero está en Z=0
    objp = np.zeros((board_size[0] * board_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2)
    objp *= square_size  # Escala por tamaño de casilla (24mm)

    # Calibración usando el modelo de cámara pinhole
    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points,
        image_points,
        image_size,
        None,  # Matriz inicial (None = estimar automáticamente)
        None,  # Coeficientes iniciales
        flags=cv2.CALIB_RATIONAL_MODEL  # Modelo de 8 coeficientes (k1-k6, p1-p2)
    )

    # Validación: Calcular error de reproyección
    total_error = 0
    for i in range(len(object_points)):
        # Proyectar puntos 3D de vuelta a 2D usando parámetros calculados
        projected_points, _ = cv2.projectPoints(
            object_points[i],
            rvecs[i],
            tvecs[i],
            camera_matrix,
            dist_coeffs
        )

        # Calcular distancia euclidiana entre puntos detectados y reproyectados
        error = cv2.norm(image_points[i], projected_points, cv2.NORM_L2) / len(projected_points)
        total_error += error

    mean_error = total_error / len(object_points)

    return camera_matrix, dist_coeffs, rvecs, tvecs, mean_error
```

**Interpretación de camera_matrix:**
```python
camera_matrix = [[fx,  0, cx],
                 [ 0, fy, cy],
                 [ 0,  0,  1]]

# fx, fy: Focal length en píxeles (horizontal y vertical)
#   - Relaciona tamaño en mundo 3D con tamaño en imagen 2D
#   - Valor típico: 1000-2000 para IMX477 a 3840×2880
#   - fx ≠ fy si los píxeles no son cuadrados (raro en cámaras modernas)

# cx, cy: Punto principal (centro óptico en píxeles)
#   - Punto donde el eje óptico interseca el plano de imagen
#   - Idealmente: (width/2, height/2)
#   - En realidad: Puede estar descentrado 10-50 píxeles
```

**Interpretación de dist_coeffs:**
```python
dist_coeffs = [k1, k2, p1, p2, k3, k4, k5, k6]  # 8 coeficientes con RATIONAL_MODEL

# k1, k2, k3, k4, k5, k6: Distorsión radial
#   - Efecto "barril" (k < 0): Líneas rectas se curvan hacia afuera
#   - Efecto "almohada" (k > 0): Líneas rectas se curvan hacia adentro
#   - Más pronunciado en bordes de imagen

# p1, p2: Distorsión tangencial
#   - Causada por desalineación de elementos de lente
#   - Típicamente muy pequeña en lentes de calidad
```

**Criterio de calidad:**
```
mean_error < 0.3 píxeles: EXCELENTE ★★★★★
mean_error < 0.5 píxeles: MUY BUENO ★★★★☆
mean_error < 1.0 píxeles: ACEPTABLE ★★★☆☆
mean_error > 1.0 píxeles: POBRE → Re-calibrar
```

##### Paso 1.4: Calibración Estéreo (relación entre cámaras)

**Archivo:** `camera/camera_calibration.py:315-360`

```python
def stereo_calibrate(object_points, left_image_points, right_image_points,
                     left_matrix, left_dist, right_matrix, right_dist,
                     image_size):
    """
    Calcula la transformación rígida entre las dos cámaras.

    Args:
        object_points: Lista de arrays (Nx3) con puntos 3D del tablero
        left_image_points: Lista de arrays (Nx2) de puntos detectados en cámara izquierda
        right_image_points: Lista de arrays (Nx2) de puntos detectados en cámara derecha
        left_matrix, left_dist: Parámetros intrínsecos de cámara izquierda
        right_matrix, right_dist: Parámetros intrínsecos de cámara derecha
        image_size: Tupla (width, height)

    Returns:
        R: Matriz de rotación 3×3 (cámara derecha respecto a izquierda)
        T: Vector de traslación 3×1 (distancia entre cámaras en metros)
        E: Matriz esencial 3×3
        F: Matriz fundamental 3×3
    """

    # Criterios de convergencia
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5)

    # Calibración estéreo
    ret, _, _, _, _, R, T, E, F = cv2.stereoCalibrate(
        object_points,
        left_image_points,
        right_image_points,
        left_matrix, left_dist,
        right_matrix, right_dist,
        image_size,
        criteria=criteria,
        flags=cv2.CALIB_FIX_INTRINSIC  # NO reoptimizar parámetros intrínsecos
    )

    return R, T, E, F
```

**Interpretación de matrices de salida:**

**1. Matriz de Rotación R (3×3):**
```python
# Describe cómo la cámara derecha está ROTADA respecto a la izquierda
# Ejemplo: Cámaras perfectamente alineadas (sin rotación)
R = [[1, 0, 0],
     [0, 1, 0],
     [0, 0, 1]]  # Matriz identidad

# Ejemplo: Cámara derecha rotada 5° en eje Y (convergencia)
R ≈ [[ 0.996,  0,     0.087],
     [ 0,      1,     0    ],
     [-0.087,  0,     0.996]]
```

**2. Vector de Traslación T (3×1):**
```python
# Distancia entre los centros ópticos de las cámaras
T = [Tx, Ty, Tz]  # En milímetros o metros (según escala de calibración)

# Ejemplo: Cámaras horizontales separadas 10cm
T = [100, 0, 0]  # mm
# Tx = 100mm (baseline horizontal)
# Ty = 0mm (sin desplazamiento vertical)
# Tz = 0mm (en el mismo plano frontal)

# La magnitud de Tx (baseline) determina:
# - Baseline grande → Mejor precisión en profundidad, menor rango
# - Baseline pequeño → Menor precisión, mayor rango
```

**3. Matriz Esencial E (3×3):**
```python
# Relaciona puntos 3D entre ambas cámaras (coordenadas calibradas)
# Ecuación: p_right^T × E × p_left = 0
# Donde p son puntos normalizados (sin distorsión)

# E codifica R y T en una sola matriz
E = [R|T]  # Notación simbólica
```

**4. Matriz Fundamental F (3×3):**
```python
# Relaciona puntos 2D entre imágenes (con distorsión)
# Ecuación: p_right^T × F × p_left = 0

# F relaciona píxeles observados directamente
# Útil para búsqueda de correspondencias
```

##### Paso 1.5: Cálculo de Rectificación

**Archivo:** `camera/camera_calibration.py:390-440`

```python
def compute_stereo_rectification(left_matrix, left_dist, right_matrix, right_dist,
                                  image_size, R, T):
    """
    Calcula transformaciones para rectificar imágenes estéreo.

    OBJETIVO: Transformar ambas imágenes para que:
      1. Las líneas epipolares sean HORIZONTALES
      2. Puntos correspondientes estén en la MISMA FILA Y
      3. Solo difieran en columna X (disparidad)

    Args:
        left_matrix, left_dist: Intrínsecos cámara izquierda
        right_matrix, right_dist: Intrínsecos cámara derecha
        image_size: (width, height)
        R, T: Transformación entre cámaras

    Returns:
        R1: Rotación de rectificación para cámara izquierda (3×3)
        R2: Rotación de rectificación para cámara derecha (3×3)
        P1: Matriz de proyección izquierda (3×4)
        P2: Matriz de proyección derecha (3×4)
        Q: Matriz de reproyección 3D (4×4) ← ¡LA MÁS IMPORTANTE!
        roi_left, roi_right: Regiones de interés válidas
    """

    # Calcular rectificación de Bouguet
    R1, R2, P1, P2, Q, roi_left, roi_right = cv2.stereoRectify(
        left_matrix, left_dist,
        right_matrix, right_dist,
        image_size,
        R, T,
        alpha=0,  # 0 = Recorta píxeles inválidos, 1 = Mantiene todos
        newImageSize=image_size
    )

    # Generar mapas de remapping
    left_map1, left_map2 = cv2.initUndistortRectifyMap(
        left_matrix, left_dist,
        R1, P1,
        image_size,
        cv2.CV_32FC1  # Formato float32 para precisión
    )

    right_map1, right_map2 = cv2.initUndistortRectifyMap(
        right_matrix, right_dist,
        R2, P2,
        image_size,
        cv2.CV_32FC1
    )

    return {
        'R1': R1, 'R2': R2,
        'P1': P1, 'P2': P2,
        'Q': Q,
        'left_map1': left_map1, 'left_map2': left_map2,
        'right_map1': right_map1, 'right_map2': right_map2,
        'roi_left': roi_left, 'roi_right': roi_right
    }
```

**Interpretación de matriz Q (reproyección 3D):**

Esta es **LA MATRIZ CLAVE** para reconstrucción 3D:

```python
Q = [[1,  0,  0,        -cx      ],
     [0,  1,  0,        -cy      ],
     [0,  0,  0,         f       ],
     [0,  0,  -1/Tx,  (cx-cx')/Tx]]

# Componentes:
# - cx, cy: Centro óptico de cámara izquierda
# - cx': Centro óptico de cámara derecha
# - f: Focal length promedio
# - Tx: Baseline (componente X del vector T)
```

**Cómo usar Q para reproyección:**
```python
# Para un píxel (x, y) con disparidad d, obtener (X, Y, Z):

# 1. Crear vector homogéneo
homogeneous = [x, y, d, 1]

# 2. Multiplicar por Q
point_3d_homogeneous = Q @ homogeneous

# 3. Dividir por componente W (normalizar)
X = point_3d_homogeneous[0] / point_3d_homogeneous[3]
Y = point_3d_homogeneous[1] / point_3d_homogeneous[3]
Z = point_3d_homogeneous[2] / point_3d_homogeneous[3]

# Resultado: Coordenadas 3D en milímetros (o metros según escala)
```

**Ejemplo numérico completo:**
```python
# Parámetros de calibración
cx, cy = 1920, 1440  # Centro óptico
f = 1500             # Focal length
Tx = 100             # Baseline = 10cm

# Matriz Q
Q = [[1,    0,    0,      -1920  ],
     [0,    1,    0,      -1440  ],
     [0,    0,    0,       1500  ],
     [0,    0,  -0.01,   1920*0.01]]

# Píxel de ejemplo
x, y, d = 2000, 1500, 50  # Píxel ligeramente a la derecha del centro, disparidad 50

# Cálculo
homogeneous = [2000, 1500, 50, 1]
result = Q @ homogeneous = [2000-1920, 1500-1440, 1500, -0.01*50 + 1920*0.01]
                          = [80, 60, 1500, 18.7]

# Normalizar
X = 80 / 18.7 ≈ 4.28 mm
Y = 60 / 18.7 ≈ 3.21 mm
Z = 1500 / 18.7 ≈ 80.2 mm  ← Profundidad en milímetros
```

##### Paso 1.6: Almacenamiento de Calibración

**Archivo:** `config/camera_config.py:180-230`

```json
{
  "calibration_date": "2025-01-28T14:35:22",
  "num_images_used": 25,

  "left_camera": {
    "matrix": [[1523.4, 0, 1918.7],
               [0, 1524.1, 1438.2],
               [0, 0, 1]],
    "distortion": [-0.342, 0.127, -0.001, 0.0008, -0.023],
    "reprojection_error_pixels": 0.42
  },

  "right_camera": {
    "matrix": [[1521.8, 0, 1922.3],
               [0, 1522.5, 1441.8],
               [0, 0, 1]],
    "distortion": [-0.338, 0.124, -0.0012, 0.0009, -0.021],
    "reprojection_error_pixels": 0.38
  },

  "stereo_params": {
    "rotation_matrix": [[0.9998, -0.0012, 0.0201],
                        [0.0013, 0.9999, -0.0034],
                        [-0.0201, 0.0035, 0.9998]],
    "translation_vector": [102.3, -0.8, 1.2],
    "baseline_mm": 102.3,
    "essential_matrix": [...],
    "fundamental_matrix": [...]
  },

  "rectification": {
    "Q_matrix": [[1, 0, 0, -1918.7],
                 [0, 1, 0, -1438.2],
                 [0, 0, 0, 1523.9],
                 [0, 0, -9.774e-3, 18.775]],
    "R1": [...],
    "R2": [...],
    "P1": [...],
    "P2": [...]
  }
}
```

---

### MÓDULO 2: Captura Estéreo (`camera/stereo_camera.py`)

#### Propósito

Capturar pares de imágenes sincronizadas de las dos cámaras Arducam HQ 477.

#### Implementación

**Archivo:** `camera/stereo_camera.py:145-210`

```python
class StereoCamera:
    def __init__(self, camera_config):
        self.camera_config = camera_config
        self.verify_cameras()

    def verify_cameras(self):
        """
        Verifica que libcamera detecte exactamente 2 cámaras IMX477.
        """
        result = subprocess.run(
            ['libcamera-hello', '--list-cameras'],
            capture_output=True,
            text=True
        )

        # Parsear salida
        cameras_found = result.stdout.count('imx477')

        if cameras_found != 2:
            raise RuntimeError(f"Se esperaban 2 cámaras, se encontraron {cameras_found}")

        return True

    def capture_stereo_pair(self, session_id=None):
        """
        Captura par estéreo sincronizado.

        TIMING CRÍTICO:
          - Objetivo: <50ms diferencia entre capturas
          - Aceptable: <100ms
          - Objetos estáticos: Sin restricción

        Args:
            session_id: Identificador de sesión (default: timestamp)

        Returns:
            Tupla (left_path, right_path) con rutas de archivos
        """

        if session_id is None:
            session_id = f"stereo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Crear directorio de sesión
        output_dir = Path(f"data/captures/{session_id}")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Configuración de captura
        settings = self.camera_config.get_capture_settings()
        width, height = settings['resolution']
        exposure = settings['exposure']
        gain = settings['gain']

        # Paths de salida
        left_path = output_dir / "left_capture.jpg"
        right_path = output_dir / "right_capture.jpg"

        # CAPTURA CÁMARA IZQUIERDA (CAM0)
        t_start = time.time()

        left_cmd = (
            f"libcamera-jpeg "
            f"--camera 0 "
            f"--width {width} --height {height} "
            f"--shutter {exposure} "
            f"--gain {gain} "
            f"--denoise off "      # Mantener detalles originales
            f"--awb auto "          # Auto white balance
            f"--immediate "         # Sin preview
            f"--nopreview "
            f"-o {left_path}"
        )

        subprocess.run(left_cmd, shell=True, check=True, capture_output=True)
        t_left = time.time()

        # PEQUEÑO DELAY para estabilización
        time.sleep(0.01)  # 10ms

        # CAPTURA CÁMARA DERECHA (CAM1)
        right_cmd = left_cmd.replace("--camera 0", "--camera 1").replace(str(left_path), str(right_path))
        subprocess.run(right_cmd, shell=True, check=True, capture_output=True)
        t_right = time.time()

        # Log timing
        time_diff = (t_right - t_left) * 1000  # Convertir a ms
        logger.info(f"Captura estéreo completada. Diferencia temporal: {time_diff:.1f}ms")

        if time_diff > 100:
            logger.warning(f"Diferencia temporal alta ({time_diff:.1f}ms). "
                          "Considerar sincronización hardware para objetos en movimiento.")

        return str(left_path), str(right_path)
```

**Estructura de salida:**
```
data/captures/stereo_20250128_143542/
├── left_capture.jpg   # 3840×2880, ~2.5MB, JPEG calidad 95
└── right_capture.jpg  # 3840×2880, ~2.5MB, JPEG calidad 95
```

---

### MÓDULO 3: Procesamiento Estéreo (`processing/stereo_processor.py`)

Este módulo es el **CORAZÓN** del sistema de reconstrucción 3D.

#### Paso 3.1: Carga y Preparación

**Archivo:** `processing/stereo_processor.py:85-130`

```python
class StereoProcessor:
    def __init__(self, calibration_data):
        """
        Inicializa procesador con datos de calibración.

        Args:
            calibration_data: Dict con matrices de calibración
        """
        self.calibration_data = calibration_data

        # Extraer matrices clave
        self.Q = np.array(calibration_data['Q_matrix'])
        self.left_map1 = calibration_data['left_map1']
        self.left_map2 = calibration_data['left_map2']
        self.right_map1 = calibration_data['right_map1']
        self.right_map2 = calibration_data['right_map2']

        # Parámetros geométricos
        self.focal_length = self.Q[2, 3]
        self.baseline = abs(1.0 / self.Q[3, 2])  # En metros o mm según escala

        logger.info(f"StereoProcessor inicializado:")
        logger.info(f"  - Focal length: {self.focal_length:.2f}")
        logger.info(f"  - Baseline: {self.baseline:.2f} mm")

    def load_images(self, left_path, right_path):
        """
        Carga par estéreo desde disco.
        """
        left_img = cv2.imread(left_path)
        right_img = cv2.imread(right_path)

        if left_img is None or right_img is None:
            raise ValueError("Error cargando imágenes")

        logger.info(f"Imágenes cargadas: {left_img.shape}")
        return left_img, right_img
```

#### Paso 3.2: Rectificación de Imágenes

**Archivo:** `processing/stereo_processor.py:155-185`

```python
def rectify_images(self, left_img, right_img):
    """
    Aplica rectificación epipolar a par estéreo.

    ANTES:
      - Líneas epipolares pueden ser diagonales o curvas
      - Búsqueda de correspondencias en 2D (lenta)

    DESPUÉS:
      - Líneas epipolares horizontales
      - Búsqueda solo en 1D (fila fija, variar columna)
      - Acelera 10-50× el algoritmo de matching

    Args:
        left_img, right_img: Imágenes BGR numpy arrays

    Returns:
        left_rect, right_rect: Imágenes rectificadas
    """

    # Aplicar transformación de remapping
    # Los mapas ya contienen corrección de distorsión + rotación de rectificación
    left_rect = cv2.remap(
        left_img,
        self.left_map1,
        self.left_map2,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    right_rect = cv2.remap(
        right_img,
        self.right_map1,
        self.right_map2,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    # Opcional: Dibujar líneas horizontales para validación
    if logger.level == logging.DEBUG:
        debug_img = np.hstack((left_rect, right_rect))
        for y in range(0, debug_img.shape[0], 50):
            cv2.line(debug_img, (0, y), (debug_img.shape[1], y), (0, 255, 0), 1)
        cv2.imwrite('debug/rectified_with_lines.jpg', debug_img)

    logger.info("Rectificación completada")
    return left_rect, right_rect
```

**Visualización del efecto:**

```
ANTES DE RECTIFICACIÓN:
Left Image                      Right Image
  ●                               ●  ← Mismo punto 3D
   \                             /
    \   Línea epipolar          /    (NO horizontal)
     \  (diagonal)             /
      ●─────────────────────●

DESPUÉS DE RECTIFICACIÓN:
Left Image                      Right Image
  ●─────────────────────────────●  ← Mismo punto, MISMA FILA Y
                                      Solo difiere en X (disparidad)
```

#### Paso 3.3: Cálculo de Disparidad con SGBM

**Archivo:** `processing/stereo_processor.py:215-290`

```python
def compute_disparity_sgbm(self, left_rect, right_rect):
    """
    Calcula mapa de disparidad usando Semi-Global Block Matching.

    ALGORITMO SGBM (Hirschmuller 2008):
      1. Para cada píxel (x,y) en left:
         a. Definir bloque de búsqueda (blockSize × blockSize)
         b. Buscar mejor match en right en rango [x-numDisp, x]
         c. Evaluar función de costo (SAD, NCC, etc.)

      2. Agregación global:
         - Penalizar cambios abruptos de disparidad (P1, P2)
         - Agregar costos en 8-16 direcciones radiales
         - Seleccionar disparidad de mínimo costo global

      3. Post-procesamiento:
         - Validación left-right consistency
         - Filtrado de outliers por unicidad
         - Remoción de speckles (regiones pequeñas)

    Args:
        left_rect, right_rect: Imágenes rectificadas (BGR)

    Returns:
        disparity: Mapa de disparidad (numpy array float32, rango 0-numDisp)
    """

    # Convertir a escala de grises (SGBM requiere un canal)
    left_gray = cv2.cvtColor(left_rect, cv2.COLOR_BGR2GRAY)
    right_gray = cv2.cvtColor(right_rect, cv2.COLOR_BGR2GRAY)

    # Parámetros SGBM
    window_size = 5       # Tamaño de bloque (5×5 píxeles)
    min_disp = 0          # Disparidad mínima
    num_disp = 96         # Rango de disparidad (debe ser múltiplo de 16)

    # Crear objeto StereoSGBM
    stereo = cv2.StereoSGBM_create(
        minDisparity=min_disp,
        numDisparities=num_disp,
        blockSize=window_size,

        # Parámetros de regularización
        P1=8 * 3 * window_size**2,    # Penalización para cambios ±1
        P2=32 * 3 * window_size**2,   # Penalización para cambios > 1

        # Factor 3 es número de canales (aunque usamos grayscale)
        # P2 > P1 para favorecer superficies suaves

        # Validación y filtrado
        disp12MaxDiff=1,              # Max diferencia en check left-right
        uniquenessRatio=10,           # Ganador debe ser 10% mejor que segundo
        speckleWindowSize=100,        # Tamaño mínimo de región válida (píxeles)
        speckleRange=32,              # Rango máximo de disparidad en región

        # Pre-procesamiento
        preFilterCap=63,              # Límite de saturación de pre-filtro

        # Modo de operación
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY  # 8 direcciones + 8 adicionales
    )

    # Computar disparidad
    # Resultado: Array int16 con disparidad * 16 (formato de punto fijo)
    disparity_16bit = stereo.compute(left_gray, right_gray)

    # Convertir a float32 y dividir por 16
    disparity = disparity_16bit.astype(np.float32) / 16.0

    # Marcar píxeles inválidos como 0
    disparity[disparity < 0] = 0

    logger.info(f"Disparidad calculada (SGBM):")
    logger.info(f"  - Rango: [{disparity.min():.2f}, {disparity.max():.2f}]")
    logger.info(f"  - Píxeles válidos: {np.sum(disparity > 0)} / {disparity.size}")

    return disparity
```

**Interpretación visual del mapa de disparidad:**

```
Mapa de disparidad (imagen 3840×2880):
  Valor de píxel = disparidad en píxeles

  0     = Sin match encontrado (negro)
  1-20  = Objetos MUY LEJANOS (azul oscuro)
  20-40 = Objetos LEJANOS (azul claro)
  40-60 = Objetos MEDIOS (verde)
  60-80 = Objetos CERCANOS (amarillo/naranja)
  80+   = Objetos MUY CERCANOS (rojo)
```

**Visualización con mapa de color:**
```python
# Normalizar a rango 0-255
disparity_norm = cv2.normalize(disparity, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

# Aplicar colormap JET (azul=lejos, rojo=cerca)
disparity_color = cv2.applyColorMap(disparity_norm, cv2.COLORMAP_JET)
cv2.imwrite('disparity_map.png', disparity_color)
```

#### Paso 3.4: Filtrado de Disparidad

**Archivo:** `processing/stereo_processor.py:320-380`

```python
def filter_disparity(self, disparity, left_rect):
    """
    Aplica filtros para mejorar calidad del mapa de disparidad.

    Pipeline de filtrado:
      1. Filtro mediano → Elimina ruido de "sal y pimienta"
      2. WLS Filter → Suaviza mientras preserva bordes
      3. Consistency check → Valida left-right

    Args:
        disparity: Mapa de disparidad crudo
        left_rect: Imagen izquierda rectificada (para guiar filtrado)

    Returns:
        disparity_filtered: Mapa de disparidad mejorado
    """

    # PASO 1: Filtro mediano (elimina píxeles aislados)
    disparity_uint8 = disparity.astype(np.uint8)
    disparity_median = cv2.medianBlur(disparity_uint8, ksize=5)

    logger.debug("Filtro mediano aplicado (kernel 5×5)")

    # PASO 2: Weighted Least Squares (WLS) Filter
    # Este filtro usa la imagen de intensidad como guía para:
    #   - Suavizar áreas uniformes
    #   - Preservar bordes fuertes

    left_gray = cv2.cvtColor(left_rect, cv2.COLOR_BGR2GRAY)

    # Crear filtro WLS
    wls_filter = cv2.ximgproc.createDisparityWLSFilter(self.stereo_matcher)
    wls_filter.setLambda(8000)       # Fuerza de suavizado (mayor = más suave)
    wls_filter.setSigmaColor(1.5)    # Sensibilidad a bordes (menor = más preservación)

    # Aplicar filtro
    disparity_wls = wls_filter.filter(
        disparity_median.astype(np.float32),
        left_gray,
        None,
        right_disparity=None  # Si tuviéramos right→left también, mejoraría
    )

    logger.info("Filtro WLS aplicado")

    # PASO 3: Validación de rango
    disparity_wls[disparity_wls < 0] = 0
    disparity_wls[disparity_wls > 160] = 0

    # Estadísticas
    valid_pixels = np.sum(disparity_wls > 0)
    total_pixels = disparity_wls.size
    validity_percent = 100.0 * valid_pixels / total_pixels

    logger.info(f"Píxeles válidos después de filtrado: {validity_percent:.1f}%")

    return disparity_wls
```

#### Paso 3.5: Reproyección a 3D

**Archivo:** `processing/stereo_processor.py:410-490`

```python
def compute_point_cloud(self, disparity, left_rect):
    """
    Convierte mapa de disparidad 2D a nube de puntos 3D.

    PROCESO:
      1. Usa cv2.reprojectImageTo3D con matriz Q
      2. Obtiene array (H, W, 3) con coordenadas [X, Y, Z]
      3. Extrae colores RGB de imagen original
      4. Filtra puntos inválidos y outliers
      5. Retorna arrays numpy (N, 3) de puntos y colores

    Args:
        disparity: Mapa de disparidad filtrado
        left_rect: Imagen izquierda rectificada (para colores)

    Returns:
        points: Array (N, 3) con coordenadas [X, Y, Z] en mm
        colors: Array (N, 3) con colores [R, G, B] en rango 0-255
    """

    # PASO 1: Reproyección usando matriz Q
    points_3d = cv2.reprojectImageTo3D(disparity, self.Q)

    # points_3d.shape = (height, width, 3)
    # points_3d[y, x] = [X, Y, Z] en mm (según escala de calibración)

    logger.info(f"Reproyección 3D completada: {points_3d.shape}")

    # PASO 2: Extraer colores
    colors = cv2.cvtColor(left_rect, cv2.COLOR_BGR2RGB)

    # PASO 3: Crear máscara de validez
    # Filtrar píxeles donde:
    #   - Disparidad > 0 (tiene correspondencia)
    #   - Z dentro de rango razonable

    mask_disparity = disparity > 0
    mask_z_min = points_3d[:, :, 2] > 100      # Z > 100mm (objetos muy cercanos son ruido)
    mask_z_max = points_3d[:, :, 2] < 5000     # Z < 5000mm (5 metros máximo)

    # Combinar máscaras
    mask = mask_disparity & mask_z_min & mask_z_max

    # PASO 4: Filtrar outliers extremos en X, Y
    # Esto elimina artefactos de bordes y errores de correspondencia
    x_coords = points_3d[:, :, 0]
    y_coords = points_3d[:, :, 1]

    mask_x = np.abs(x_coords) < 10000  # ±10 metros en X
    mask_y = np.abs(y_coords) < 10000  # ±10 metros en Y

    mask = mask & mask_x & mask_y

    # PASO 5: Aplicar máscara y aplanar
    points = points_3d[mask].reshape(-1, 3)
    colors = colors[mask].reshape(-1, 3)

    # Estadísticas
    num_points = points.shape[0]
    total_pixels = disparity.size
    density = 100.0 * num_points / total_pixels

    logger.info(f"Nube de puntos generada:")
    logger.info(f"  - Puntos válidos: {num_points:,}")
    logger.info(f"  - Densidad: {density:.1f}%")
    logger.info(f"  - Rango X: [{points[:,0].min():.1f}, {points[:,0].max():.1f}] mm")
    logger.info(f"  - Rango Y: [{points[:,1].min():.1f}, {points[:,1].max():.1f}] mm")
    logger.info(f"  - Rango Z: [{points[:,2].min():.1f}, {points[:,2].max():.1f}] mm")

    return points, colors
```

**Ejemplo de transformación:**

```
Píxel en imagen rectificada:
  (x, y) = (2000, 1500)
  disparidad = 50

Aplicar matriz Q:
  [2000]       [1, 0, 0, -1920]   [2000 - 1920]     [80]
  [1500]   →   [0, 1, 0, -1440] × [1500 - 1440]  =  [60]
  [  50]       [0, 0, 0,  1500]   [      1500 ]     [1500]
  [   1]       [0, 0,-0.01, 19.2] [-0.01*50+19.2]   [18.7]

Normalizar (dividir por W):
  X = 80 / 18.7 ≈ 4.28 mm
  Y = 60 / 18.7 ≈ 3.21 mm
  Z = 1500 / 18.7 ≈ 80.2 mm

Punto 3D final: (4.28, 3.21, 80.2) mm desde el centro de cámara izquierda
```

#### Paso 3.6: Filtrado Estadístico de Outliers

**Archivo:** `processing/stereo_processor.py:520-575`

```python
def remove_statistical_outliers(self, points, colors, nb_neighbors=20, std_ratio=2.0):
    """
    Elimina puntos outliers usando análisis estadístico.

    ALGORITMO:
      1. Para cada punto, calcular distancia promedio a sus K vecinos más cercanos
      2. Calcular media μ y desviación estándar σ de todas las distancias
      3. Eliminar puntos con distancia > μ + (std_ratio × σ)

    Esto elimina:
      - Puntos flotantes aislados (errores de matching)
      - Artefactos de bordes
      - Ruido en superficies

    Args:
        points: Array (N, 3) de coordenadas 3D
        colors: Array (N, 3) de colores RGB
        nb_neighbors: Número de vecinos a considerar
        std_ratio: Umbral en desviaciones estándar

    Returns:
        points_clean: Array (M, 3) con M < N (outliers removidos)
        colors_clean: Array (M, 3) de colores correspondientes
    """

    import open3d as o3d

    # Crear nube de puntos Open3D
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(colors / 255.0)  # Normalizar a [0, 1]

    logger.info(f"Aplicando Statistical Outlier Removal:")
    logger.info(f"  - Puntos iniciales: {len(pcd.points):,}")
    logger.info(f"  - Vecinos: {nb_neighbors}")
    logger.info(f"  - Umbral: {std_ratio}σ")

    # Aplicar filtro
    pcd_filtered, ind = pcd.remove_statistical_outlier(
        nb_neighbors=nb_neighbors,
        std_ratio=std_ratio
    )

    # Extraer arrays
    points_clean = np.asarray(pcd_filtered.points)
    colors_clean = (np.asarray(pcd_filtered.colors) * 255).astype(np.uint8)

    removed = len(pcd.points) - len(pcd_filtered.points)
    removed_percent = 100.0 * removed / len(pcd.points)

    logger.info(f"Filtrado completado:")
    logger.info(f"  - Puntos removidos: {removed:,} ({removed_percent:.1f}%)")
    logger.info(f"  - Puntos restantes: {len(points_clean):,}")

    return points_clean, colors_clean
```

---

### MÓDULO 4: Exportación (`processing/point_cloud_generator.py`)

#### Formato PLY (Recomendado)

**Archivo:** `processing/point_cloud_generator.py:125-175`

```python
def export_ply_binary(points, colors, output_file):
    """
    Exporta nube de puntos a formato PLY binario.

    PLY (Polygon File Format / Stanford Triangle Format):
      - Formato estándar para nubes de puntos y mallas
      - Soportado por: MeshLab, CloudCompare, Blender, Open3D
      - Binario: Compacto (~15 bytes/punto)
      - ASCII: Legible pero 3-5× más grande

    Args:
        points: Array (N, 3) de coordenadas [X, Y, Z]
        colors: Array (N, 3) de colores [R, G, B] (0-255)
        output_file: Ruta de salida
    """

    num_points = len(points)

    # Header PLY
    header = f"""ply
format binary_little_endian 1.0
comment Generated by Stereo Photogrammetry CM5
comment Author: Raspberry Pi CM5 + Arducam HQ 477
element vertex {num_points}
property float x
property float y
property float z
property uchar red
property uchar green
property uchar blue
end_header
"""

    with open(output_file, 'wb') as f:
        # Escribir header (ASCII)
        f.write(header.encode('ascii'))

        # Escribir datos (binario)
        for i in range(num_points):
            # Pack: 3 floats (12 bytes) + 3 uchars (3 bytes) = 15 bytes por punto
            data = struct.pack(
                '<fffBBB',  # < = little-endian, f = float32, B = uint8
                points[i, 0], points[i, 1], points[i, 2],
                colors[i, 0], colors[i, 1], colors[i, 2]
            )
            f.write(data)

    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
    logger.info(f"PLY binario guardado: {output_file} ({file_size_mb:.2f} MB)")
```

#### Formato XYZ (Simple)

**Archivo:** `processing/point_cloud_generator.py:205-235`

```python
def export_xyz(points, colors, output_file):
    """
    Exporta a formato XYZ (texto simple).

    Formato: X Y Z R G B (un punto por línea)
    Ventajas: Universal, fácil de parsear
    Desventajas: Archivos grandes, sin metadata
    """

    with open(output_file, 'w') as f:
        for i in range(len(points)):
            f.write(f"{points[i,0]:.3f} {points[i,1]:.3f} {points[i,2]:.3f} "
                    f"{colors[i,0]} {colors[i,1]} {colors[i,2]}\n")

    logger.info(f"XYZ guardado: {output_file}")
```

---

## Matrices de Calibración: Explicación Profunda

### Matriz de Cámara (Intrínsecos)

```python
K = [[fx,  0, cx],
     [ 0, fy, cy],
     [ 0,  0,  1]]
```

**Significado físico:**
- **fx, fy (focal length):** Distancia desde el centro óptico al sensor en píxeles
  - Relaciona tamaño angular con tamaño en píxeles
  - fx ≠ fy solo si píxeles no son cuadrados (raro)
  - Valor típico: 1000-2000 para resoluciones 1920×1080 a 3840×2880

- **cx, cy (punto principal):** Coordenadas del centro óptico
  - Idealmente: (width/2, height/2)
  - En práctica: Desplazado 10-50 píxeles debido a ensamblaje de lente

**Cómo se usa:**
```python
# Proyección de punto 3D (X, Y, Z) a punto 2D (x, y)
x = fx * (X / Z) + cx
y = fy * (Y / Z) + cy
```

### Coeficientes de Distorsión

```python
dist = [k1, k2, p1, p2, k3]  # Modelo estándar
dist = [k1, k2, p1, p2, k3, k4, k5, k6]  # Modelo racional (CALIB_RATIONAL_MODEL)
```

**Distorsión radial (k1, k2, k3, k4, k5, k6):**
```python
r² = x² + y²  # Distancia al centro

x_distorted = x * (1 + k1*r² + k2*r⁴ + k3*r⁶ + ...)
y_distorted = y * (1 + k1*r² + k2*r⁴ + k3*r⁶ + ...)

# k1 < 0: Distorsión de barril (bordes se alejan)
# k1 > 0: Distorsión de almohada (bordes se acercan)
```

**Distorsión tangencial (p1, p2):**
```python
x_distorted = x + [2*p1*x*y + p2*(r² + 2*x²)]
y_distorted = y + [p1*(r² + 2*y²) + 2*p2*x*y]

# Causada por desalineación de elementos de lente
```

### Matriz de Rotación y Traslación (Extrínsecos)

**Rotación R (3×3):**
```python
# Matriz ortogonal (R × R^T = I)
# det(R) = 1
# Cada fila/columna es un vector unitario

# Ejemplo: Rotación de θ grados en eje Y
R_y(θ) = [[ cos(θ), 0, sin(θ)],
          [      0, 1,      0],
          [-sin(θ), 0, cos(θ)]]
```

**Traslación T (3×1):**
```python
T = [Tx, Ty, Tz]  # Vector de desplazamiento

# En sistema estéreo horizontal típico:
T ≈ [baseline, 0, 0]
# Tx = baseline (distancia horizontal entre cámaras)
# Ty ≈ 0 (sin offset vertical)
# Tz ≈ 0 (en el mismo plano frontal)
```

### Matriz Q (Reproyección 3D)

**Estructura:**
```python
Q = [[1,  0,  0,        -cx      ],
     [0,  1,  0,        -cy      ],
     [0,  0,  0,         f       ],
     [0,  0,  -1/Tx,  (cx-cx')/Tx]]

# Derivación matemática:
# Z = f × Tx / d                    (profundidad)
# X = (x - cx) × Z / f              (coordenada horizontal)
# Y = (y - cy) × Z / f              (coordenada vertical)

# Combinando en forma matricial:
# [X]       [x - cx        ]
# [Y]   = Q [y - cy        ]
# [Z]       [d            ]
# [W]       [1            ]

# Donde (X, Y, Z) = (X/W, Y/W, Z/W) son las coordenadas 3D finales
```

---

## Algoritmos de Matching Estéreo

### SGBM (Semi-Global Block Matching)

**Paper original:** Hirschmuller, H. (2008). "Stereo Processing by Semiglobal Matching and Mutual Information"

#### Principio

Combina:
1. **Matching local:** Compara bloques de píxeles
2. **Optimización global:** Penaliza cambios abruptos de disparidad

#### Algoritmo Paso a Paso

```
PARA cada píxel (x, y) en imagen izquierda:

  PASO 1: Calcular costo de matching
  PARA cada disparidad d en [0, numDisparities]:
    bloque_left = left_img[y-w:y+w, x-w:x+w]
    bloque_right = right_img[y-w:y+w, (x-d)-w:(x-d)+w]

    # Calcular similitud (varias opciones):
    # - SAD (Sum of Absolute Differences)
    # - SSD (Sum of Squared Differences)
    # - NCC (Normalized Cross Correlation)
    # - Census Transform

    cost[x, y, d] = similitud(bloque_left, bloque_right)
  FIN PARA

  PASO 2: Agregación de costos en múltiples direcciones
  PARA cada dirección r en {0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°}:
    PARA cada píxel a lo largo de la dirección:
      # Programación dinámica:
      # Costo agregado = costo_local + min(costos vecinos + penalizaciones)

      L_r(x, y, d) = cost(x, y, d) + min(
        L_r(x-1, y, d),           # Misma disparidad → sin penalización
        L_r(x-1, y, d-1) + P1,    # Cambio ±1 → penalización P1
        L_r(x-1, y, d+1) + P1,
        min_d(L_r(x-1, y, d')) + P2  # Cambio > 1 → penalización P2
      )
    FIN PARA
  FIN PARA

  PASO 3: Seleccionar disparidad de mínimo costo
  disparity[x, y] = argmin_d( sum_r(L_r(x, y, d)) )
FIN PARA

PASO 4: Post-procesamiento
  - Validación left-right consistency
  - Filtrado de unicidad
  - Remoción de speckles
```

#### Parámetros Clave

```python
# blockSize: Tamaño de ventana de matching
#   Pequeño (3-5): Alta resolución, sensible a ruido
#   Grande (9-15): Suave, pierde detalles
blockSize = 5

# numDisparities: Rango de búsqueda
#   = max_disparidad / 16 * 16  (debe ser múltiplo de 16)
#   Relacionado con: profundidad_min = (f × baseline) / numDisp
numDisparities = 96  # Permite disparidades 0-96 píxeles

# P1, P2: Penalizaciones de suavidad
#   P1: Cambio pequeño (±1 píxel)
#   P2: Cambio grande (> 1 píxel)
#   P2 >> P1 para favorecer superficies suaves
P1 = 8 * 3 * blockSize^2
P2 = 32 * 3 * blockSize^2

# uniquenessRatio: Umbral de unicidad
#   Ganador debe superar al segundo por este porcentaje
#   Alto (15-20): Conservador, menos puntos
#   Bajo (5-10): Agresivo, más ruido
uniquenessRatio = 10  # 10%

# speckleWindowSize: Tamaño mínimo de región conectada
#   Elimina "islas" pequeñas de ruido
speckleWindowSize = 100  # píxeles

# speckleRange: Variación máxima dentro de región
#   Disparidades deben ser similares en región conectada
speckleRange = 32  # píxeles
```

### BM (Block Matching)

#### Principio

Matching puramente local:
1. Para cada píxel, comparar bloque en left con bloques en right
2. Seleccionar disparidad de mínimo costo
3. No hay agregación global (más rápido pero menos robusto)

#### Comparación SGBM vs BM

| Aspecto | SGBM | BM |
|---------|------|-----|
| **Calidad** | Alta | Media |
| **Velocidad** | Lenta (30-60s) | Rápida (10-20s) |
| **Áreas sin textura** | Robusto | Falla |
| **Bordes** | Bien definidos | Borrosos |
| **Oclusiones** | Maneja bien | Problemas |
| **Memoria** | Alta | Baja |
| **Uso recomendado** | Producción | Pruebas rápidas |

---

## Flujo de Datos Completo

### Diagrama de Transformación de Datos

```
┌─────────────────────────────────────────────────────────────────────┐
│ CAPTURA: data/captures/stereo_TIMESTAMP/                            │
│   ├── left_capture.jpg    3840×2880 BGR uint8 [0, 255]            │
│   └── right_capture.jpg   3840×2880 BGR uint8 [0, 255]            │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ RECTIFICACIÓN: Aplicar cv2.remap()                                  │
│   - Elimina distorsión de lentes                                    │
│   - Alinea líneas epipolares horizontalmente                        │
│   - Output: left_rect, right_rect  (3840×2880 BGR uint8)          │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ CONVERSIÓN A GRAYSCALE: cv2.cvtColor(BGR2GRAY)                     │
│   - SGBM requiere un solo canal                                     │
│   - Output: left_gray, right_gray  (3840×2880 uint8)              │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ CÁLCULO DE DISPARIDAD: stereo.compute()                            │
│   - Algoritmo SGBM/BM                                               │
│   - Output: disparity_raw  (3840×2880 int16) × 16                 │
│             Rango: -16 a numDisp×16 (formato punto fijo)           │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ CONVERSIÓN A FLOAT: disparity.astype(float32) / 16.0               │
│   - Output: disparity  (3840×2880 float32)                        │
│             Rango: 0.0 a numDisp (píxeles de disparidad)           │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ FILTRADO: Mediana + WLS + Outlier removal                          │
│   - Elimina ruido, suaviza, preserva bordes                        │
│   - Output: disparity_filtered  (3840×2880 float32)               │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ REPROYECCIÓN 3D: cv2.reprojectImageTo3D(disparity, Q)              │
│   - Convierte (x, y, d) → (X, Y, Z)                                │
│   - Output: points_3d  (3840×2880×3 float32)                      │
│             Cada píxel = [X, Y, Z] en mm                            │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ FILTRADO GEOMÉTRICO: Aplicar máscaras                              │
│   - Eliminar Z < 100mm, Z > 5000mm                                 │
│   - Eliminar |X|, |Y| > 10000mm                                    │
│   - Eliminar disparidad == 0                                        │
│   - Output: points  (N×3 float32), colors  (N×3 uint8)           │
│             Típicamente N ≈ 60-80% de píxeles totales              │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ FILTRADO ESTADÍSTICO: remove_statistical_outlier()                 │
│   - Elimina puntos aislados (ruido)                                │
│   - Output: points_clean  (M×3), colors_clean  (M×3)              │
│             M ≈ 0.95 × N (elimina ~5% outliers)                    │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ EXPORTACIÓN: Guardar en formatos estándar                          │
│   ├── point_cloud.ply  (binario, 15 bytes/punto)                  │
│   ├── point_cloud.xyz  (ASCII, ~40 bytes/punto)                   │
│   ├── point_cloud.pcd  (PCL format)                               │
│   └── point_cloud.obj  (Wavefront, importable en Blender)         │
└─────────────────────────────────────────────────────────────────────┘
```

### Tamaños de Datos Típicos

```
Para imagen 3840×2880 (11.06 megapíxeles):

CAPTURA:
  left_capture.jpg:  ~2.5 MB (JPEG 95% calidad)
  right_capture.jpg: ~2.5 MB
  Total:             ~5 MB

PROCESAMIENTO (en RAM):
  left_rect (BGR):        3840×2880×3 × 1 byte  = 33.2 MB
  right_rect (BGR):       3840×2880×3 × 1 byte  = 33.2 MB
  left_gray:              3840×2880   × 1 byte  = 11.1 MB
  right_gray:             3840×2880   × 1 byte  = 11.1 MB
  disparity (float32):    3840×2880   × 4 bytes = 44.2 MB
  points_3d (float32):    3840×2880×3 × 4 bytes = 132.7 MB

  Pico de memoria:        ~300-400 MB (con overhead de OpenCV/Python)

EXPORTACIÓN:
  Suponiendo 7M puntos válidos (65% densidad):

  PLY binario:    7M × 15 bytes      = 105 MB
  XYZ ASCII:      7M × 40 bytes      = 280 MB
  PCD:            Similar a PLY      = ~110 MB
  OBJ:            Similar a XYZ      = ~290 MB
```

---

## Análisis de Errores y Troubleshooting

### Error Tipo 1: Calibración Pobre

**Síntomas:**
- Error de reproyección > 1.0 píxeles
- Líneas no horizontales en imagen rectificada
- Modelos 3D distorsionados o "doblados"

**Causas:**
1. Pocas imágenes de calibración (<15)
2. Poca variedad de posiciones/ángulos
3. Tablero de ajedrez defectuoso (impresión borrosa, no plano)
4. Iluminación pobre (bajo contraste)

**Soluciones:**
```python
# 1. Aumentar número de imágenes
min_calibration_images = 30  # En lugar de 25

# 2. Validar detección de esquinas
corners_detected = cv2.findChessboardCorners(img, (9, 6))
if not corners_detected:
    print("❌ No se detectaron esquinas - mejorar iluminación o reemplazar tablero")

# 3. Verificar error de reproyección por imagen
for i, (objp, imgp, rvec, tvec) in enumerate(calibration_data):
    projected, _ = cv2.projectPoints(objp, rvec, tvec, mtx, dist)
    error = cv2.norm(imgp, projected, cv2.NORM_L2) / len(projected)

    if error > 1.0:
        print(f"⚠️ Imagen {i} tiene error alto: {error:.2f} px - considerar eliminarla")

# 4. Usar flag de refinamiento
cv2.calibrateCamera(..., flags=cv2.CALIB_RATIONAL_MODEL | cv2.CALIB_THIN_PRISM_MODEL)
```

### Error Tipo 2: Matching Fallido

**Síntomas:**
- Mapa de disparidad mayormente negro (sin correspondencias)
- Muy pocos puntos 3D (<20% densidad)
- Puntos solo en bordes/esquinas

**Causas:**
1. Falta de textura en la escena
2. Iluminación muy diferente entre cámaras
3. Objetos fuera de rango de disparidad
4. Oclusiones severas

**Soluciones:**
```python
# 1. Aumentar rango de disparidad
numDisparities = 160  # En lugar de 96 (permite objetos más cercanos)

# 2. Ajustar blockSize según textura
# Poca textura → blockSize grande (11-15)
# Mucha textura → blockSize pequeño (3-5)
blockSize = 11

# 3. Reducir umbrales de filtrado
uniquenessRatio = 5      # En lugar de 10 (más permisivo)
speckleWindowSize = 50   # En lugar de 100 (permite regiones más pequeñas)

# 4. Usar pre-filtro más agresivo
stereo.setPreFilterCap(63)  # Máximo permitido
stereo.setPreFilterSize(9)

# 5. Visualizar raw disparity sin filtros
cv2.imwrite('debug_disparity_raw.png', (disparity * 255 / numDisparities).astype(np.uint8))
# Si raw también está vacío → problema de calibración o escena sin textura
```

### Error Tipo 3: Outliers Excesivos

**Síntomas:**
- Nube de puntos con "ruido" flotante
- Puntos muy alejados del objeto principal
- "Nubes" de puntos en el aire

**Causas:**
1. Errores de matching en áreas uniformes
2. Reflejos especulares
3. Bordes de imagen con distorsión residual

**Soluciones:**
```python
# 1. Aumentar agresividad de SOR
points_clean, colors_clean = remove_statistical_outliers(
    points, colors,
    nb_neighbors=30,     # En lugar de 20
    std_ratio=1.5        # En lugar de 2.0 (más estricto)
)

# 2. Aplicar filtrado geométrico más estricto
mask_z = (points[:, 2] > 200) & (points[:, 2] < 3000)  # Rango más acotado
mask_xy = (np.abs(points[:, 0]) < 2000) & (np.abs(points[:, 1]) < 2000)

# 3. Usar radius outlier removal (alternativa a statistical)
pcd_filtered = pcd.remove_radius_outlier(nb_points=16, radius=10.0)

# 4. Voxel downsampling (también reduce ruido)
pcd_downsampled = pcd_filtered.voxel_down_sample(voxel_size=2.0)  # 2mm
```

### Error Tipo 4: Precisión Insuficiente

**Síntomas:**
- Objetos aparecen "en escalera" (cuantización visible)
- Medidas inconsistentes (variabilidad >5mm)
- Superficie ruidosa en objetos planos

**Causas:**
1. Baseline demasiado pequeño o grande
2. Resolución insuficiente
3. numDisparities demasiado bajo

**Soluciones:**
```python
# 1. Optimizar baseline
# Regla empírica: baseline ≈ 1/10 de distancia de trabajo
# Para objetos a 1m → baseline ≈ 10cm
# Para objetos a 50cm → baseline ≈ 5cm

# 2. Aumentar resolución de captura
capture_resolution = (4056, 3040)  # Máxima de IMX477

# 3. Aumentar resolución de disparidad
numDisparities = 128  # Más niveles de profundidad

# 4. Usar submatcheo sub-píxel
# (OpenCV no lo soporta directamente, pero se puede implementar)

# 5. Validar precisión teórica:
# ΔZ/Z² = (1 / baseline) × (ΔZ_camera / f)
#
# Donde:
#   ΔZ = error en profundidad
#   Z = distancia al objeto
#   baseline = distancia entre cámaras
#   ΔZ_camera = error de disparidad (típicamente 1 píxel)
#   f = focal length
#
# Ejemplo:
baseline = 100  # mm
Z = 1000        # mm (1 metro)
f = 1500        # píxeles
disparity_error = 1  # píxel

depth_error = (Z * Z * disparity_error) / (f * baseline)
print(f"Error teórico en profundidad: ±{depth_error:.2f} mm")
# Con estos parámetros: ±6.67 mm
```

### Validación de Resultados

**Checklist de calidad:**

```python
# 1. Calibración
assert reprojection_error < 0.5, "Calibración debe ser <0.5 px"
assert baseline > 50 and baseline < 200, "Baseline típico: 5-20 cm"

# 2. Rectificación
# Verificar que líneas son horizontales:
# - Dibujar líneas en imagen concatenada
# - Inspeccionar visualmente

# 3. Disparidad
valid_pixels = np.sum(disparity > 0)
total_pixels = disparity.size
density = valid_pixels / total_pixels
assert density > 0.4, f"Densidad muy baja: {density*100:.1f}% (debería ser >40%)"

# 4. Puntos 3D
z_mean = np.mean(points[:, 2])
z_std = np.std(points[:, 2])
assert z_std / z_mean < 0.5, "Excesiva variación en Z (objeto plano debería tener std/mean < 0.2)"

# 5. Exportación
assert os.path.exists(output_ply), "Archivo PLY no generado"
assert os.path.getsize(output_ply) > 1024*1024, "PLY demasiado pequeño (<1MB) - pocos puntos"
```

---

## Conclusión

Este documento detalla el proceso completo de reconstrucción 3D implementado en el sistema de fotogrametría estéreo para Raspberry Pi CM5. Los componentes clave son:

1. **Calibración:** Determina parámetros intrínsecos/extrínsecos de las cámaras
2. **Rectificación:** Alinea imágenes para simplificar búsqueda de correspondencias
3. **Matching:** Encuentra píxeles correspondientes y calcula disparidad
4. **Reproyección:** Convierte disparidad 2D en coordenadas 3D usando matriz Q
5. **Filtrado:** Elimina ruido y outliers para obtener modelo limpio
6. **Exportación:** Guarda en formatos estándar de la industria

Para soporte adicional:
- Revisar logs: `logs/stereo_photogrammetry.log`
- Validar calibración: error < 0.5 píxeles
- Verificar densidad de puntos: >60% es excelente
- Inspeccionar mapa de disparidad visualmente

**Última actualización:** 2025-01-28