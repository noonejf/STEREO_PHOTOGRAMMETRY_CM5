# PROCEDIMIENTO DETALLADO DE RECONSTRUCCIÓN 3D MEDIANTE ESTEREOVISIÓN
## Resumen del Sistema

Este documento describe el procedimiento completo para realizar reconstrucción 3D utilizando **dos cámaras web** en configuración estéreo, basado en la tesis "Reconstrucción 3D mediante el uso de un par de cámaras a modo de estereovisión" de la Escuela Politécnica Nacional de Ecuador (2014).

## 1. DESCRIPCIÓN GENERAL DEL SISTEMA

### 1.1 Objetivo
Medir distancias mediante triangulación de puntos en un par de imágenes y representarlas como una nube de puntos 3D a colores.

### 1.2 Hardware Utilizado
- **Cámaras**: 2x Logitech HD Pro Webcam C920
  - Resolución óptica: 3MP (True)
  - Resolución de video: 1080p@30fps
  - Lente: Carl Zeiss® (cristal)
  - Campo de visión diagonal: 78°
  - Enfoque automático: 20 pasos
  - Conexión: USB 2.0

### 1.3 Software y Librerías
- **Lenguaje**: C++
- **IDE**: Microsoft Visual Studio Professional
- **Librerías principales**:
  - **OpenCV 2.4.3**: Procesamiento de imágenes y visión artificial
  - **PCL 1.6.0** (Point Cloud Library): Procesamiento y visualización de nubes de puntos 3D
  - **MFC** (Microsoft Foundation Classes): Interfaz gráfica de usuario

## 2. FUNDAMENTOS TEÓRICOS

### 2.1 Modelo de Cámara Pinhole

El sistema utiliza el modelo pinhole idealizado que describe la relación matemática entre un punto 3D y su proyección en el plano de imagen:

**Ecuación de proyección:**
```
x = f * (X / Z)
y = f * (Y / Z)
```

Donde:
- `(X, Y, Z)` = coordenadas 3D del punto en el mundo real
- `(x, y)` = coordenadas 2D en el plano de imagen
- `f` = distancia focal de la cámara

### 2.2 Distorsión de Lentes

Las cámaras reales introducen dos tipos principales de distorsión:

#### 2.2.1 Distorsión Radial
```
x_corregido = x * (1 + k₁*r² + k₂*r⁴ + k₃*r⁶)
y_corregido = y * (1 + k₁*r² + k₂*r⁴ + k₃*r⁶)
```
Donde `r² = x² + y²`

#### 2.2.2 Distorsión Tangencial
```
x_corregido = x + [2*p₁*y + p₂*(r² + 2*x²)]
y_corregido = y + [p₁*(r² + 2*y²) + 2*p₂*x]
```

### 2.3 Parámetros de la Cámara

#### 2.3.1 Parámetros Intrínsecos
Matriz intrínseca M (3x3):
```
M = | fx   α   cx |
    | 0    fy  cy |
    | 0    0   1  |
```

Donde:
- `fx, fy` = distancia focal en pixeles (eje x e y)
- `cx, cy` = coordenadas del punto principal
- `α` = coeficiente de asimetría (asumido como 0)
- Coeficientes de distorsión: `k₁, k₂, k₃, p₁, p₂`

#### 2.3.2 Parámetros Extrínsecos
- **Matriz de rotación R (3x3)**: Orientación de la cámara
- **Vector de traslación T (3x1)**: Posición de la cámara

## 3. PROCESO DE CALIBRACIÓN

### 3.1 Preparación

#### 3.1.1 Patrón de Calibración
- **Tipo**: Tablero de ajedrez impreso
- **Características**:
  - Alto contraste blanco-negro
  - Esquinas interiores bien definidas
  - Dimensiones conocidas de cada cuadrado
  - El proyecto utilizó 54 esquinas interiores (configuración típica: 9x6 o similar)

#### 3.1.2 Adquisición de Imágenes para Calibración
1. Tomar **mínimo 15 pares de imágenes** del tablero de ajedrez
2. Capturar desde diferentes ángulos y distancias
3. Asegurar que el tablero completo aparezca en ambas imágenes
4. Tomar las imágenes simultáneamente con ambas cámaras
5. Mantener buena iluminación uniforme

### 3.2 Detección de Esquinas

#### 3.2.1 Pre-procesamiento de Imagen
```cpp
// Pseudocódigo del proceso
1. Convertir imagen a escala de grises
2. Normalizar brillo de la imagen
3. Aumentar contraste
4. Aplicar thresholding adaptativo
   - Umbral calculado localmente según intensidad de píxeles vecinos
   - Robusto ante cambios de iluminación
```

#### 3.2.2 Detección de Esquinas con Precisión Sub-píxel
OpenCV proporciona la función que detecta esquinas del tablero:

```cpp
// Ejemplo en OpenCV
bool found = findChessboardCorners(
    imagen_gris,
    patron_size,  // Ej: Size(9, 6) para 9x6 esquinas interiores
    esquinas,     // Vector de salida con coordenadas
    CALIB_CB_ADAPTIVE_THRESH + CALIB_CB_NORMALIZE_IMAGE
);

// Refinamiento a nivel sub-píxel
cornerSubPix(
    imagen_gris,
    esquinas,
    Size(11, 11),  // Tamaño de ventana de búsqueda
    Size(-1, -1),  // Zona muerta
    TermCriteria(TermCriteria::EPS + TermCriteria::MAX_ITER, 30, 0.1)
);
```

#### 3.2.3 Verificación Visual
- Dibujar círculos y líneas conectando las esquinas detectadas
- **Detección exitosa**: Círculos conectados con líneas en todas las esquinas
- **Detección fallida**: Círculos rojos aislados o esquinas faltantes
- Si falla, descartar el par de imágenes y capturar nuevamente

### 3.3 Definición de Coordenadas 3D del Patrón

Para el tablero de ajedrez, se definen coordenadas 3D con:
- **Plano z = 0** (todas las esquinas en el mismo plano)
- **Unidad**: Tamaño de un cuadrado del tablero
- **Origen**: Esquina superior izquierda

Coordenadas resultantes (para un tablero de 9x6 esquinas):
```
(0,0,0), (0,1,0), (0,2,0), ..., (0,8,0)
(1,0,0), (1,1,0), (1,2,0), ..., (1,8,0)
...
(5,0,0), (5,1,0), (5,2,0), ..., (5,8,0)
```

### 3.4 Calibración Individual de Cada Cámara

#### 3.4.1 Cálculo de Matrices de Homografía

Para cada imagen del tablero:
1. Se calcula una matriz de homografía H (3x3) que relaciona puntos del tablero con puntos en la imagen
2. Se utiliza el método de mínimos cuadrados para minimizar el error de reproyección

**Error a minimizar:**
```
Σᵢ [(xᵢ - (h₁₁*Xᵢ + h₁₂*Yᵢ + h₁₃)/(h₃₁*Xᵢ + h₃₂*Yᵢ + h₃₃))² + 
     (yᵢ - (h₂₁*Xᵢ + h₂₂*Yᵢ + h₂₃)/(h₃₁*Xᵢ + h₃₂*Yᵢ + h₃₃))²]
```

Con 54 esquinas por imagen, se tienen 108 ecuaciones para resolver 8 incógnitas (H₃₃ = 1).

#### 3.4.2 Cálculo de Parámetros Intrínsecos y Extrínsecos Iniciales

El sistema usa el **método de Zhang** (paper: "A Flexible New Technique for Camera Calibration"):

1. A partir del conjunto de matrices H, formar un sistema de ecuaciones
2. Resolver mediante cálculo de eigenvectores y eigenvalues
3. Obtener primera aproximación de parámetros intrínsecos (sin considerar distorsión)
4. Obtener parámetros extrínsecos para cada toma

#### 3.4.3 Cálculo de Coeficientes de Distorsión

Con los parámetros iniciales:
1. Calcular coeficientes de distorsión radial: `k₁, k₂, k₃`
2. Calcular coeficientes de distorsión tangencial: `p₁, p₂`

#### 3.4.4 Refinamiento Final

Recalcular todos los parámetros (intrínsecos y extrínsecos) considerando la distorsión, minimizando el error de reproyección total.

```cpp
// Función de OpenCV
double rms = calibrateCamera(
    puntos_objeto,        // Coordenadas 3D del tablero
    puntos_imagen,        // Coordenadas 2D detectadas
    tamano_imagen,
    matriz_intrinseca,    // Salida: matriz M
    coef_distorsion,      // Salida: [k₁, k₂, p₁, p₂, k₃]
    rvecs,                // Salida: vectores de rotación
    tvecs,                // Salida: vectores de traslación
    flags                 // Opciones de calibración
);
```

### 3.5 Calibración Estéreo

Una vez calibradas ambas cámaras individualmente, se procede a la calibración estéreo:

#### 3.5.1 Objetivo
Obtener la matriz de rotación `R` y el vector de traslación `T` que relacionan ambas cámaras.

#### 3.5.2 Relación Entre Cámaras

Con el sistema de referencia en la cámara izquierda:
```
P_izq = R⁻¹ * (P_der - T)
```

Alternativamente:
```
R_der = R * R_izq
T_der = R * T_izq + T
```

#### 3.5.3 Proceso de Calibración Estéreo

```cpp
double rms = stereoCalibrate(
    puntos_objeto,           // Coordenadas 3D del tablero (compartidas)
    puntos_imagen_izq,       // Puntos 2D en cámara izquierda
    puntos_imagen_der,       // Puntos 2D en cámara derecha
    matriz_intrinseca_izq,   // De calibración individual
    coef_distorsion_izq,     // De calibración individual
    matriz_intrinseca_der,   // De calibración individual
    coef_distorsion_der,     // De calibración individual
    tamano_imagen,
    R,                       // Salida: matriz de rotación
    T,                       // Salida: vector de traslación
    E,                       // Salida: matriz esencial
    F,                       // Salida: matriz fundamental
    flags
);
```

El algoritmo minimiza el error de reproyección considerando todos los pares de imágenes.

### 3.6 Verificación de la Calibración

#### 3.6.1 Criterios de Éxito

1. **Error RMS bajo**: Típicamente < 1 pixel
2. **Inspección visual de rectificación**:
   - Los mismos puntos deben estar en la misma línea horizontal en ambas imágenes
   - Sin distorsiones excesivas en las imágenes rectificadas
   - Líneas horizontales equidistantes atraviesan puntos correspondientes

#### 3.6.2 Si la Calibración Falla

- Repetir adquisición de imágenes con mejor iluminación
- Asegurar que el tablero sea plano y sin deformaciones
- Aumentar el número de imágenes de calibración
- Variar más los ángulos y posiciones del tablero
- Verificar que ambas cámaras capturen simultáneamente

## 4. RECTIFICACIÓN DE IMÁGENES

### 4.1 Objetivo de la Rectificación

Transformar las imágenes de ambas cámaras de modo que:
- Los planos de imagen sean coplanares
- Los ejes ópticos sean paralelos
- Las líneas epipolares sean horizontales y alineadas
- Las filas de píxeles correspondan entre ambas imágenes

### 4.2 Método de Bouguet

El sistema utiliza el **algoritmo de Bouguet**, que minimiza la distorsión de reproyección.

#### 4.2.1 Principio del Método

Cada cámara rota **la mitad de la rotación total** necesaria para lograr la alineación, distribuyendo así la distorsión equitativamente.

#### 4.2.2 Cálculo de Matrices de Rotación

**Paso 1: División de rotación total**
```
R = (r_izq)ᵀ * r_der

Donde:
- R es la matriz de rotación entre cámaras (de calibración estéreo)
- r_izq y r_der dividen R a la mitad
```

**Paso 2: Matriz de rectificación R_rect**

Define el nuevo sistema de coordenadas con ejes:

```
e₁ = T / ||T||                    (Eje X apunta en dirección de T)
e₂ = [-Tᵧ, Tₓ, 0]ᵀ / √(Tₓ² + Tᵧ²)  (Eje Y perpendicular a X y eje óptico)
e₃ = e₁ × e₂                      (Eje Z perpendicular a X e Y)

R_rect = | (e₁)ᵀ |
         | (e₂)ᵀ |
         | (e₃)ᵀ |
```

**Paso 3: Matrices de rotación finales**
```
R_izq = R_rect * r_izq
R_der = R_rect * r_der
```

#### 4.2.3 Implementación en OpenCV

```cpp
stereoRectify(
    matriz_intrinseca_izq,
    coef_distorsion_izq,
    matriz_intrinseca_der,
    coef_distorsion_der,
    tamano_imagen,
    R,                          // De calibración estéreo
    T,                          // De calibración estéreo
    R_izq,                      // Salida: rotación para img izquierda
    R_der,                      // Salida: rotación para img derecha
    P_izq,                      // Salida: matriz de proyección izquierda
    P_der,                      // Salida: matriz de proyección derecha
    Q,                          // Salida: matriz de reproyección 4x4
    flags,
    alpha,                      // 0 = recortar, 1 = mantener todos los píxeles
    nuevo_tamano
);
```

### 4.3 Proceso de Mapping (Remapeo)

#### 4.3.1 Cálculo de Mapas de Transformación

Para cada cámara, se calculan dos mapas que indican cómo transformar la imagen original a la rectificada:

```cpp
initUndistortRectifyMap(
    matriz_intrinseca,
    coef_distorsion,
    R,                    // Matriz de rotación (R_izq o R_der)
    P,                    // Matriz de proyección
    tamano_imagen,
    CV_32FC1,
    map_x,                // Salida: mapa de coordenadas X
    map_y                 // Salida: mapa de coordenadas Y
);
```

Estos mapas (`map_x` y `map_y`) se calculan **una sola vez** y se guardan para uso posterior.

#### 4.3.2 Aplicación del Remapeo

Para cada nueva imagen capturada:

```cpp
remap(
    imagen_original,
    imagen_rectificada,
    map_x,
    map_y,
    INTER_LINEAR       // Interpolación lineal
);
```

El proceso de remapeo:
1. Corrige la distorsión de lentes
2. Aplica la rotación de rectificación
3. Usa interpolación para píxeles con coordenadas no enteras

## 5. MAPA DE DISPARIDAD

### 5.1 Concepto de Disparidad

La **disparidad** es la diferencia horizontal en la posición de un punto entre las imágenes izquierda y derecha rectificadas.

```
disparidad = x_izquierda - x_derecha
```

La disparidad es inversamente proporcional a la profundidad:
```
Z = (f * T) / disparidad

Donde:
- f = distancia focal (en píxeles)
- T = distancia entre cámaras (baseline)
- Z = profundidad del punto
```

### 5.2 Proceso de Cálculo del Mapa de Disparidad

El proceso consta de 3 etapas:

#### 5.2.1 Pre-filtrado

Objetivo: Preparar las imágenes para mejorar la correspondencia

```cpp
// El algoritmo aplica:
1. Reducción de diferencias de iluminación
2. Realce de texturas
3. Normalización local del contraste
```

#### 5.2.2 Correspondencia Estéreo - Algoritmo SAD (Sum of Absolute Differences)

**Principio del método SAD:**

Para cada píxel `(x, y)` en la imagen izquierda:

1. Definir una ventana alrededor del píxel (ej: 11x11 píxeles)
2. Buscar el píxel correspondiente en la **misma fila** de la imagen derecha
3. Para cada posible coincidencia, calcular:

```
SAD(d) = Σ |I_izq(x+i, y+j) - I_der(x+i-d, y+j)|

Donde:
- d = disparidad candidata
- (i,j) recorren la ventana
- La suma se hace sobre toda la ventana
```

4. La disparidad óptima es aquella con mínimo SAD:
```
d_óptima = argmin(SAD(d)) para d ∈ [d_min, d_max]
```

**Ejemplo numérico del algoritmo SAD:**

Dada una imagen origen 3x3 y una destino 3x5:
```
I_o = | 5  9  5 |       I_d = | 7  6  1  8  2 |
      | 7  9  7 |             | 5  9  8  3  8 |
      | 8  9  8 |             | 8  9  3  6  1 |
```

Para encontrar la correspondencia del punto central (2,2):

**Ventana derecha:**
```
Resta: | 5-7  9-6  5-1 |   | -2  3  4 |     SAD_der = 29
       | 7-5  9-9  7-8 | = |  2  0 -1 |
       | 8-8  9-9  8-3 |   |  0  0  5 |
```

**Ventana central:**
```
Resta: | 5-6  9-1  5-8 |   | -1  8 -3 |     SAD_cen = 22  ← Mínimo
       | 7-9  9-8  7-3 | = | -2  1  4 |
       | 8-9  9-3  8-6 |   | -1  6  2 |
```

**Ventana izquierda:**
```
Resta: | 5-1  9-8  5-2 |   |  4  1  3 |     SAD_izq = 35
       | 7-8  9-3  7-8 | = | -1  6 -1 |
       | 8-3  9-6  8-1 |   |  5  3  7 |
```

La ventana con menor SAD es la central → **coincidencia encontrada**

#### 5.2.3 Parámetros Clave del Algoritmo SAD

**Tamaño de ventana (SADWindowSize):**
- Valores típicos: 5, 7, 9, 11, 15, 21
- **Ventanas pequeñas**: Más detalles, pero más sensibles al ruido
- **Ventanas grandes**: Más robustas, pero menos detalles

**Rango de disparidad (numDisparities):**
- Define la máxima disparidad a buscar
- Debe ser múltiplo de 16 (requisito de OpenCV)
- El proyecto usó: `numDisparities = 64`
- Determina distancia mínima medible:
```
Z_min = (f * T) / numDisparities
Z_min = (605.99 px * 9.07 cm) / 64 px = 85.88 cm
```

**Disparidad mínima (minDisparity):**
- Normalmente 0 para configuración frontal paralela
- Valores positivos reducen rango de búsqueda

**Umbral de unicidad (uniquenessRatio):**
- Típicamente 5-15
- Filtra coincidencias ambiguas
- Mayor valor = filtrado más estricto

**Diferencia máxima (disp12MaxDiff):**
- Verifica consistencia izquierda-derecha
- Típicamente 1 o -1 para desactivar

#### 5.2.4 Implementación en OpenCV

```cpp
// Crear objeto StereoBM (Block Matching)
Ptr<StereoBM> sbm = StereoBM::create(
    numDisparities,      // Ej: 64
    blockSize            // Ej: 21
);

// Configurar parámetros
sbm->setPreFilterType(StereoBM::PREFILTER_NORMALIZED_RESPONSE);
sbm->setPreFilterSize(5);
sbm->setPreFilterCap(61);
sbm->setMinDisparity(0);
sbm->setTextureThreshold(507);
sbm->setUniquenessRatio(0);
sbm->setSpeckleWindowSize(0);
sbm->setSpeckleRange(8);
sbm->setDisp12MaxDiff(1);

// Calcular mapa de disparidad
sbm->compute(
    imagen_izq_rect,     // Imagen izquierda rectificada (escala de grises)
    imagen_der_rect,     // Imagen derecha rectificada (escala de grises)
    mapa_disparidad      // Salida: Mat de 16 bits
);

// Convertir a formato utilizable (8 bits o flotante)
mapa_disparidad.convertTo(mapa_disparidad, CV_32F, 1.0/16.0);
```

**Nota:** OpenCV también ofrece **StereoSGBM** (Semi-Global Block Matching), más preciso pero más lento:

```cpp
Ptr<StereoSGBM> sgbm = StereoSGBM::create(
    minDisparity,
    numDisparities,
    blockSize,
    P1,                  // Penalización por disparidad pequeña
    P2,                  // Penalización por disparidad grande
    disp12MaxDiff,
    preFilterCap,
    uniquenessRatio,
    speckleWindowSize,
    speckleRange,
    mode
);
```

#### 5.2.5 Post-filtrado

Elimina correspondencias falsas mediante:

```cpp
// Filtrado de manchas pequeñas (speckles)
filterSpeckles(
    mapa_disparidad,
    0,                   // Nuevo valor para speckles
    speckleSize,         // Tamaño máximo de speckle
    speckleRange         // Rango de disparidad
);

// También se puede aplicar filtrado de mediana
medianBlur(mapa_disparidad, mapa_disparidad, 5);
```

Criterios de filtrado:
- Puntos sin suficiente textura
- Puntos ocluidos (visibles solo en una cámara)
- Inconsistencias en verificación izquierda-derecha
- Regiones de disparidad no única

### 5.3 Visualización del Mapa de Disparidad

#### 5.3.1 Mapa en Escala de Grises

```cpp
// Normalizar para visualización
normalize(
    mapa_disparidad,
    mapa_disparidad_normalizado,
    0, 255,
    NORM_MINMAX,
    CV_8U
);
```

Interpretación:
- **Píxeles blancos** = cercanos a la cámara (alta disparidad)
- **Píxeles negros** = lejanos de la cámara (baja disparidad)
- **Píxeles sin valor** = sin correspondencia encontrada

#### 5.3.2 Mapa de Disparidad a Colores

El proyecto implementó un esquema de color basado en rangos de distancia:

| Rango de distancia (cm) | Disparidad (px) | Color RGB      |
|-------------------------|-----------------|----------------|
| 0 - 100                 | > 55            | (255, 0, 0) Rojo |
| 100 - 137.5            | 40 - 55         | (255, 153, 0) Naranja |
| 137.5 - 175            | 31 - 40         | (255, 255, 0) Amarillo |
| 175 - 212.5            | 25 - 31         | (0, 153, 212) Cian |
| 212.5 - 250            | 22 - 25         | (0, 204, 250) Cian claro |
| 250 - 287.5            | 19 - 22         | (0, 255, 250) Cian brillante |
| 287.5 - 325            | 17 - 19         | (0, 192, 255) Azul claro |
| 325 - 362.5            | 15 - 17         | (0, 129, 255) Azul |
| 362.5 - 400            | 14 - 15         | (0, 100, 255) Azul oscuro |
| > 400                  | < 14            | (0, 0, 255) Azul profundo |
| Sin valor              | -               | (255, 255, 255) Blanco |

```cpp
// Aplicar mapa de colores
Mat mapa_color;
applyColorMap(mapa_disparidad_normalizado, mapa_color, COLORMAP_JET);
// Alternativamente, aplicar esquema personalizado
```

### 5.4 Rangos de Distancia del Sistema

Con los parámetros del proyecto:

**Datos del sistema:**
- Distancia focal: `f = 605.99 píxeles`
- Baseline (distancia entre cámaras): `T = 9.07 cm`
- Disparidad máxima: `64 píxeles`
- Disparidad mínima: `1 píxel`

**Distancia mínima detectable:**
```
Z_min = (f * T) / d_max
Z_min = (605.99 * 9.07) / 64 = 85.88 cm
```

**Distancia máxima teórica:**
```
Z_max = (f * T) / d_min
Z_max = (605.99 * 9.07) / 1 = 5496 cm = 54.96 metros
```

En la práctica, el sistema es confiable hasta **~4-8 metros** dependiendo de la textura de la escena.

## 6. RECONSTRUCCIÓN 3D

### 6.1 Reproyección a Coordenadas 3D

#### 6.1.1 Matriz de Reproyección Q

La matriz Q (4x4) permite convertir coordenadas de imagen (x, y, disparidad) a coordenadas 3D (X, Y, Z):

```
Q = | 1   0    0        -cx        |
    | 0   1    0        -cy        |
    | 0   0    0         f         |
    | 0   0   -1/Tx   (cx-cx')/Tx |

Donde:
- cx, cy = coordenadas del punto principal (cámara izquierda)
- cx' = coordenada x del punto principal (cámara derecha)
- f = distancia focal
- Tx = baseline (distancia entre cámaras)
```

Esta matriz se obtiene de `stereoRectify()`.

#### 6.1.2 Cálculo de Coordenadas 3D

Para cada píxel con disparidad válida:

```
| X |       | x |
| Y |   =   | y |
| Z | = Q * | d |
| W |       | 1 |

Coordenadas 3D finales:
X' = X / W
Y' = Y / W
Z' = Z / W
```

Implementación en OpenCV:

```cpp
reprojectImageTo3D(
    mapa_disparidad,          // Entrada: mapa de disparidad
    imagen_3D,                // Salida: imagen 3 canales (X, Y, Z)
    Q,                        // Matriz de reproyección
    handleMissingValues,      // true = filtrar puntos sin disparidad
    ddepth                    // Tipo de datos (CV_32F)
);
```

#### 6.1.3 Filtrado de Puntos

```cpp
// Filtrar puntos con disparidad inválida o muy lejanos
for cada punto (x, y):
    if disparidad[x,y] > 0 and Z < 8000:  // 8 metros
        punto_valido = true
        agregar (X, Y, Z) a nube de puntos
```

Se discriminan:
- Puntos sin disparidad calculada (blancos en el mapa)
- Puntos con Z > 8m (posibles infinitos o muy inexactos)
- Puntos con valores anómalos

### 6.2 Asignación de Color

Para cada punto 3D válido, se obtiene su color de la imagen original:

```cpp
// La imagen izquierda a color se rectifica usando el mismo mapping
remap(
    imagen_izq_color_original,
    imagen_izq_color_rectificada,
    map_x_izq,
    map_y_izq,
    INTER_LINEAR
);

// Extraer color para cada punto
for cada punto_3D[i] con coordenadas (x, y) en imagen:
    color[i] = imagen_izq_color_rectificada.at<Vec3b>(y, x);
```

### 6.3 Creación de la Nube de Puntos con PCL

```cpp
// Crear nube de puntos PCL
pcl::PointCloud<pcl::PointXYZRGB>::Ptr nube(new pcl::PointCloud<pcl::PointXYZRGB>);

// Llenar nube de puntos
for cada punto válido (X, Y, Z, R, G, B):
    pcl::PointXYZRGB punto;
    punto.x = X / 10.0;  // Convertir mm a cm si es necesario
    punto.y = Y / 10.0;
    punto.z = Z / 10.0;
    punto.r = R;
    punto.g = G;
    punto.b = B;
    nube->points.push_back(punto);

nube->width = nube->points.size();
nube->height = 1;
nube->is_dense = false;
```

### 6.4 Visualización 3D con PCL

```cpp
// Crear visualizador
pcl::visualization::PCLVisualizer::Ptr viewer(
    new pcl::visualization::PCLVisualizer("Reconstrucción 3D")
);

// Configurar visualizador
viewer->setBackgroundColor(0, 0, 0);
viewer->addPointCloud<pcl::PointXYZRGB>(nube, "nube");
viewer->setPointCloudRenderingProperties(
    pcl::visualization::PCL_VISUALIZER_POINT_SIZE, 1, "nube"
);
viewer->addCoordinateSystem(1.0);
viewer->initCameraParameters();

// Bucle de visualización
while (!viewer->wasStopped()) {
    viewer->spinOnce(100);
}
```

### 6.5 Guardado de la Nube de Puntos

```cpp
// Guardar en formato PCD (Point Cloud Data)
pcl::io::savePCDFileASCII("reconstruccion.pcd", *nube);

// Guardar en formato PLY
pcl::io::savePLYFileASCII("reconstruccion.ply", *nube);
```

## 7. PIPELINE COMPLETO DEL SISTEMA

### 7.1 Fase de Configuración Inicial (Una sola vez)

```
1. CALIBRACIÓN
   ├─ Capturar 15+ pares de imágenes del tablero de ajedrez
   ├─ Detectar esquinas en todas las imágenes
   ├─ Calibración individual de cada cámara
   │  └─ Obtener: M_izq, distorsión_izq, M_der, distorsión_der
   ├─ Calibración estéreo
   │  └─ Obtener: R (rotación), T (traslación)
   └─ Verificar visualmente con imágenes rectificadas

2. RECTIFICACIÓN (Preparación)
   ├─ Calcular matrices de rectificación (R_izq, R_der, P_izq, P_der, Q)
   └─ Generar mapas de transformación (map_x, map_y para cada cámara)
      └─ GUARDAR estos mapas para uso posterior
```

### 7.2 Fase de Operación (Para cada par de imágenes)

```
Para cada nuevo par de imágenes capturadas:

1. CAPTURA
   ├─ Capturar imagen izquierda (a color)
   └─ Capturar imagen derecha (a color) SIMULTÁNEAMENTE

2. RECTIFICACIÓN
   ├─ Convertir a escala de grises
   ├─ Aplicar remap() con mapas pre-calculados
   │  ├─ imagen_izq_rect (gris)
   │  └─ imagen_der_rect (gris)
   └─ Rectificar también la imagen izquierda a color (para colores de la nube)

3. CÁLCULO DEL MAPA DE DISPARIDAD
   ├─ Pre-filtrado de ambas imágenes
   ├─ Aplicar algoritmo StereoBM o StereoSGBM
   │  └─ Resultado: mapa_disparidad
   └─ Post-filtrado (eliminar speckles, aplicar mediana)

4. REPROYECCIÓN 3D
   ├─ Aplicar reprojectImageTo3D() con matriz Q
   │  └─ Resultado: imagen_3D (3 canales: X, Y, Z)
   ├─ Filtrar puntos inválidos (sin disparidad, Z > umbral)
   └─ Extraer colores de imagen_izq_color_rect

5. GENERACIÓN DE NUBE DE PUNTOS
   ├─ Crear pcl::PointCloud<PointXYZRGB>
   ├─ Llenar con puntos válidos (X, Y, Z, R, G, B)
   └─ Configurar propiedades (width, height, is_dense)

6. VISUALIZACIÓN Y/O GUARDADO
   ├─ Mostrar en PCLVisualizer (interactivo)
   └─ Guardar en archivo (.pcd, .ply)
```

### 7.3 Diagrama de Flujo Simplificado

```
  INICIO
    ↓
[Calibración única]
    ├─ Capturar imágenes tablero (15+)
    ├─ Calcular parámetros cámaras
    ├─ Calcular R, T (calibración estéreo)
    └─ Generar mapas de rectificación
    ↓
[Loop continuo]
    ↓
[Capturar par de imágenes]
    ↓
[Rectificar ambas imágenes]
    ↓
[Calcular mapa de disparidad]
    ↓
[Reproyectar a 3D]
    ↓
[Crear nube de puntos]
    ↓
[Visualizar / Guardar]
    ↓
  ¿Continuar? → SÍ (volver a Capturar)
    ↓ NO
  FIN
```

## 8. OPTIMIZACIÓN Y MEJORES PRÁCTICAS

### 8.1 Para la Calibración

**✓ Hacer:**
- Usar al menos 15 imágenes (el proyecto usó 15)
- Variar ángulos: frontal, lateral, inclinaciones
- Variar distancias: cerca y lejos
- Asegurar buena iluminación uniforme
- Mantener el tablero completamente plano
- Verificar detección de esquinas en todas las imágenes

**✗ Evitar:**
- Usar pocas imágenes (< 10)
- Todas las imágenes desde el mismo ángulo
- Iluminación irregular o sombras en el tablero
- Tablero deformado o doblado
- Movimiento durante la captura (imágenes borrosas)

### 8.2 Para la Configuración de Hardware

**Posicionamiento de cámaras:**
- Baseline (separación): 8-12 cm típico (el proyecto usó ~9 cm)
- **Mayor baseline** = mayor rango, pero mayor distancia mínima
- **Menor baseline** = menor distancia mínima, pero menor rango
- Mantener cámaras lo más horizontal y frontalmente alineadas posible
- Fijar cámaras rígidamente (sin vibración)

**Iluminación:**
- Luz difusa y uniforme
- Evitar sombras duras
- Evitar reflejos especulares
- Suficiente luz (no subexponer ni sobreexponer)

### 8.3 Para el Mapa de Disparidad

**Ajuste de parámetros:**

```cpp
// Para escenas con alta textura (exteriores, objetos detallados):
blockSize = 5 o 7              // Ventana pequeña
numDisparities = 64 o 96
uniquenessRatio = 15
preFilterCap = 61

// Para escenas con baja textura (interiores, superficies lisas):
blockSize = 15 o 21            // Ventana grande
numDisparities = 128
uniquenessRatio = 5
preFilterCap = 31
speckleWindowSize = 100
speckleRange = 32
```

**Balance velocidad vs calidad:**
- **StereoBM**: Más rápido, suficiente para tiempo real
- **StereoSGBM**: Más lento, mejor calidad en bordes y zonas de baja textura

### 8.4 Optimización de Rendimiento

```cpp
// Pre-calcular y cachear
1. Mapas de rectificación (una sola vez)
2. Matriz Q (una sola vez)

// Reducir resolución si es necesario
resize(imagen, imagen_small, Size(), 0.5, 0.5);  // 50% de tamaño

// Paralelización (OpenCV usa multi-threading internamente)
setNumThreads(4);  // Ajustar según CPU

// ROI (Region of Interest) si solo interesa parte de la imagen
Rect roi(100, 100, 400, 300);
Mat img_roi = imagen(roi);
```

### 8.5 Manejo de Errores Comunes

| Problema | Posible Causa | Solución |
|----------|---------------|----------|
| Mapa de disparidad muy ruidoso | Baja textura, iluminación pobre | Aumentar blockSize, mejorar iluminación |
| Pocas correspondencias | numDisparities muy bajo | Aumentar numDisparities |
| Imágenes rectificadas distorsionadas | Calibración pobre | Repetir calibración con más imágenes |
| Puntos 3D muy dispersos/ruidosos | Errores en calibración, mala iluminación | Mejorar calibración, filtrar Z > umbral |
| Las líneas no están alineadas después de rectificación | R y T incorrectos | Recalibrar sistema estéreo |
| Muy lento el cálculo | Parámetros muy altos, imagen grande | Reducir resolución, usar StereoBM, reducir numDisparities |

## 9. CÓDIGO EJEMPLO COMPLETO

### 9.1 Estructura del Proyecto

```
proyecto/
├── calibracion/
│   ├── calibrar.cpp              # Programa de calibración
│   ├── imagenes_calibracion/     # Pares de imágenes del tablero
│   └── parametros_calibracion.yml # Parámetros guardados
├── reconstruccion/
│   ├── main.cpp                  # Programa principal
│   └── gui.cpp                   # Interfaz gráfica (MFC)
├── data/
│   ├── map_x_izq.yml
│   ├── map_y_izq.yml
│   ├── map_x_der.yml
│   ├── map_y_der.yml
│   └── Q_matrix.yml
└── salida/
    └── nubes_puntos/             # Archivos .pcd, .ply
```

### 9.2 Código Principal (main.cpp)

```cpp
#include <opencv2/opencv.hpp>
#include <opencv2/calib3d.hpp>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/visualization/pcl_visualizer.h>
#include <pcl/io/pcd_io.h>

using namespace cv;
using namespace std;

class SistemaEstereo {
private:
    // Parámetros de calibración
    Mat M_izq, M_der, D_izq, D_der, R, T, Q;
    Mat map_x_izq, map_y_izq, map_x_der, map_y_der;
    
    // Parámetros del algoritmo
    Ptr<StereoBM> sbm;
    
    // Cámaras
    VideoCapture cam_izq, cam_der;
    
public:
    SistemaEstereo() {
        // Configurar algoritmo StereoBM
        sbm = StereoBM::create(64, 21);
        sbm->setPreFilterType(StereoBM::PREFILTER_NORMALIZED_RESPONSE);
        sbm->setPreFilterSize(5);
        sbm->setPreFilterCap(61);
        sbm->setMinDisparity(0);
        sbm->setTextureThreshold(507);
        sbm->setUniquenessRatio(0);
        sbm->setSpeckleWindowSize(0);
        sbm->setSpeckleRange(8);
        sbm->setDisp12MaxDiff(1);
    }
    
    bool cargarParametros(const string& archivo) {
        FileStorage fs(archivo, FileStorage::READ);
        if (!fs.isOpened()) {
            cerr << "Error al abrir archivo de parámetros" << endl;
            return false;
        }
        
        fs["M_izq"] >> M_izq;
        fs["M_der"] >> M_der;
        fs["D_izq"] >> D_izq;
        fs["D_der"] >> D_der;
        fs["R"] >> R;
        fs["T"] >> T;
        fs["Q"] >> Q;
        fs["map_x_izq"] >> map_x_izq;
        fs["map_y_izq"] >> map_y_izq;
        fs["map_x_der"] >> map_x_der;
        fs["map_y_der"] >> map_y_der;
        
        fs.release();
        return true;
    }
    
    bool inicializarCamaras(int id_izq, int id_der) {
        cam_izq.open(id_izq);
        cam_der.open(id_der);
        
        if (!cam_izq.isOpened() || !cam_der.isOpened()) {
            cerr << "Error al abrir cámaras" << endl;
            return false;
        }
        
        // Configurar resolución
        cam_izq.set(CAP_PROP_FRAME_WIDTH, 640);
        cam_izq.set(CAP_PROP_FRAME_HEIGHT, 480);
        cam_der.set(CAP_PROP_FRAME_WIDTH, 640);
        cam_der.set(CAP_PROP_FRAME_HEIGHT, 480);
        
        return true;
    }
    
    void capturarYRectificar(Mat& img_izq_rect, Mat& img_der_rect, 
                             Mat& img_izq_color_rect) {
        Mat img_izq, img_der, img_izq_gray, img_der_gray;
        
        // Capturar
        cam_izq >> img_izq;
        cam_der >> img_der;
        
        // Convertir a escala de grises
        cvtColor(img_izq, img_izq_gray, COLOR_BGR2GRAY);
        cvtColor(img_der, img_der_gray, COLOR_BGR2GRAY);
        
        // Rectificar
        remap(img_izq_gray, img_izq_rect, map_x_izq, map_y_izq, INTER_LINEAR);
        remap(img_der_gray, img_der_rect, map_x_der, map_y_der, INTER_LINEAR);
        remap(img_izq, img_izq_color_rect, map_x_izq, map_y_izq, INTER_LINEAR);
    }
    
    Mat calcularDisparidad(const Mat& img_izq_rect, const Mat& img_der_rect) {
        Mat disparidad;
        sbm->compute(img_izq_rect, img_der_rect, disparidad);
        
        // Convertir a formato utilizable
        disparidad.convertTo(disparidad, CV_32F, 1.0/16.0);
        
        // Filtrar speckles
        filterSpeckles(disparidad, 0, 100, 32);
        
        return disparidad;
    }
    
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr 
    generarNubePuntos(const Mat& disparidad, const Mat& img_color) {
        // Reproyectar a 3D
        Mat imagen_3D;
        reprojectImageTo3D(disparidad, imagen_3D, Q, true, CV_32F);
        
        // Crear nube de puntos
        pcl::PointCloud<pcl::PointXYZRGB>::Ptr nube(
            new pcl::PointCloud<pcl::PointXYZRGB>
        );
        
        // Llenar nube
        for (int y = 0; y < imagen_3D.rows; y++) {
            for (int x = 0; x < imagen_3D.cols; x++) {
                Vec3f punto_3d = imagen_3D.at<Vec3f>(y, x);
                float Z = punto_3d[2];
                
                // Filtrar puntos inválidos
                if (Z > 0 && Z < 8000) {  // Z en mm, filtrar > 8m
                    pcl::PointXYZRGB punto;
                    punto.x = punto_3d[0] / 10.0;  // mm a cm
                    punto.y = punto_3d[1] / 10.0;
                    punto.z = Z / 10.0;
                    
                    // Obtener color
                    Vec3b color = img_color.at<Vec3b>(y, x);
                    punto.b = color[0];
                    punto.g = color[1];
                    punto.r = color[2];
                    
                    nube->points.push_back(punto);
                }
            }
        }
        
        nube->width = nube->points.size();
        nube->height = 1;
        nube->is_dense = false;
        
        return nube;
    }
    
    void visualizar(pcl::PointCloud<pcl::PointXYZRGB>::Ptr nube) {
        pcl::visualization::PCLVisualizer::Ptr viewer(
            new pcl::visualization::PCLVisualizer("Reconstrucción 3D")
        );
        
        viewer->setBackgroundColor(0, 0, 0);
        viewer->addPointCloud<pcl::PointXYZRGB>(nube, "nube");
        viewer->setPointCloudRenderingProperties(
            pcl::visualization::PCL_VISUALIZER_POINT_SIZE, 1, "nube"
        );
        viewer->addCoordinateSystem(1.0);
        viewer->initCameraParameters();
        
        while (!viewer->wasStopped()) {
            viewer->spinOnce(100);
        }
    }
    
    void ejecutar() {
        Mat img_izq_rect, img_der_rect, img_izq_color_rect;
        
        while (true) {
            // Capturar y rectificar
            capturarYRectificar(img_izq_rect, img_der_rect, img_izq_color_rect);
            
            // Mostrar imágenes rectificadas
            imshow("Izquierda rectificada", img_izq_rect);
            imshow("Derecha rectificada", img_der_rect);
            
            // Calcular disparidad
            Mat disparidad = calcularDisparidad(img_izq_rect, img_der_rect);
            
            // Visualizar mapa de disparidad
            Mat disp_visual;
            normalize(disparidad, disp_visual, 0, 255, NORM_MINMAX, CV_8U);
            applyColorMap(disp_visual, disp_visual, COLORMAP_JET);
            imshow("Mapa de disparidad", disp_visual);
            
            // Tecla 's' para guardar y visualizar en 3D
            char key = waitKey(30);
            if (key == 's') {
                // Generar nube de puntos
                auto nube = generarNubePuntos(disparidad, img_izq_color_rect);
                
                // Guardar
                pcl::io::savePCDFileASCII("reconstruccion.pcd", *nube);
                cout << "Nube guardada: " << nube->points.size() << " puntos" << endl;
                
                // Visualizar
                visualizar(nube);
            }
            else if (key == 27) {  // ESC para salir
                break;
            }
        }
    }
};

int main(int argc, char** argv) {
    SistemaEstereo sistema;
    
    // Cargar parámetros de calibración
    if (!sistema.cargarParametros("parametros_calibracion.yml")) {
        return -1;
    }
    
    // Inicializar cámaras (ajustar IDs según tu sistema)
    if (!sistema.inicializarCamaras(0, 1)) {
        return -1;
    }
    
    // Ejecutar sistema
    sistema.ejecutar();
    
    return 0;
}
```

### 9.3 Compilación

**CMakeLists.txt:**
```cmake
cmake_minimum_required(VERSION 3.0)
project(SistemaEstereo)

set(CMAKE_CXX_STANDARD 11)

find_package(OpenCV REQUIRED)
find_package(PCL REQUIRED)

include_directories(${OpenCV_INCLUDE_DIRS})
include_directories(${PCL_INCLUDE_DIRS})

link_directories(${PCL_LIBRARY_DIRS})
add_definitions(${PCL_DEFINITIONS})

add_executable(reconstruccion main.cpp)

target_link_libraries(reconstruccion 
    ${OpenCV_LIBS}
    ${PCL_LIBRARIES}
)
```

**Compilar:**
```bash
mkdir build
cd build
cmake ..
make
./reconstruccion
```

## 10. RESULTADOS Y VALIDACIÓN

### 10.1 Métricas de Desempeño

El proyecto reportó los siguientes resultados:

**Error de distancia:**
- **Distancia 100 cm**: Error promedio 1-3%
- **Distancia 200 cm**: Error promedio 2-4%
- **Distancia 300 cm**: Error promedio 1-4%
- **Distancia 400 cm**: Error promedio 0.5-5%

**Rango efectivo:**
- Distancia mínima: **85.88 cm**
- Distancia máxima confiable: **4-8 metros** (dependiendo de textura)

**Resolución:**
- Densidad de puntos depende de textura de la escena
- Escenas exteriores con vegetación: Alta densidad
- Escenas interiores con paredes lisas: Baja densidad

### 10.2 Factores que Afectan la Precisión

1. **Calidad de calibración**: La base de todo
2. **Textura de la escena**: Fundamental para correspondencia
3. **Iluminación**: Debe ser uniforme y suficiente
4. **Distancia al objeto**: Precisión disminuye con distancia
5. **Baseline**: Mayor separación = mayor rango pero menor precisión cercana
6. **Resolución de cámaras**: Mayor resolución = más detalles

## 11. APLICACIONES Y EXTENSIONES

### 11.1 Aplicaciones del Sistema

- **Robótica móvil**: Navegación y evitación de obstáculos
- **Medición industrial**: Control de calidad, medición de piezas
- **Modelado 3D**: Captura de objetos y escenas
- **Realidad aumentada**: Mapeo del entorno
- **Asistencia al conducir**: Detección de distancia a vehículos
- **Vigilancia**: Detección de intrusos con información de profundidad

### 11.2 Extensión: Reconstrucción 360° (Múltiples Vistas)

El proyecto también experimentó con **reconstrucción desde múltiples perspectivas**:

```
Proceso:
1. Capturar nube de puntos desde posición inicial (Nube A)
2. Rotar/mover sistema de cámaras (ángulo θ conocido)
3. Capturar nube desde nueva posición (Nube B)
4. Aplicar transformación conocida (R, T) a Nube B
5. Fusionar Nube A + Nube B transformada
6. Resultado: Reconstrucción 360° del objeto
```

Esto sienta las bases para sistemas **SLAM (Simultaneous Localization And Mapping)** con visión estéreo.

## 12. CONCLUSIONES Y RECOMENDACIONES

### 12.1 Conclusiones Clave

1. Es posible lograr reconstrucción 3D con **hardware de bajo costo** (webcams comerciales)
2. La **calibración cuidadosa** es crítica para buenos resultados
3. El método funciona mejor en **escenas con alta textura**
4. OpenCV y PCL proporcionan herramientas robustas y probadas
5. El balance entre **velocidad y precisión** debe ajustarse según la aplicación

### 12.2 Recomendaciones

**Para calibración:**
- Usar al menos 15-20 imágenes de diferentes ángulos
- Verificar siempre visualmente la rectificación antes de continuar
- Re-calibrar si se mueven las cámaras

**Para mejor calidad:**
- Usar cámaras con buena resolución y lentes de calidad
- Asegurar baseline apropiado para el rango de distancias deseado
- Mejorar iluminación de la escena (luz difusa)
- Aumentar textura si es posible (proyectar patrón de luz estructurada)

**Para rendimiento en tiempo real:**
- Reducir resolución de imágenes
- Limitar el rango de búsqueda de disparidad
- Usar StereoBM en lugar de StereoSGBM
- Considerar implementación en GPU (CUDA)

## 13. REFERENCIAS Y RECURSOS

### 13.1 Papers Fundamentales

1. **Zhang, Z.** (2000). "A Flexible New Technique for Camera Calibration". IEEE Transactions on Pattern Analysis and Machine Intelligence.

2. **Bouguet, J-Y.** "Camera Calibration Toolbox for Matlab". Método de rectificación estéreo.

3. **Hirschmuller, H.** (2008). "Stereo Processing by Semiglobal Matching and Mutual Information". IEEE Transactions on Pattern Analysis and Machine Intelligence. (Base de SGBM)

### 13.2 Documentación Oficial

- **OpenCV**: https://docs.opencv.org/
  - Calibración: https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html
  - Visión estéreo: https://docs.opencv.org/4.x/dd/d53/tutorial_py_depthmap.html

- **PCL**: https://pointclouds.org/documentation/
  - Tutoriales: https://pcl.readthedocs.io/

### 13.3 Herramientas Útiles

- **Kalibr**: Calibración de múltiples cámaras (ROS)
- **StereoLabs ZED**: SDK alternativo con hardware dedicado
- **MeshLab**: Visualización y procesamiento de nubes de puntos
- **CloudCompare**: Análisis y comparación de nubes de puntos

---

## APÉNDICE A: TABLA DE PARÁMETROS RECOMENDADOS

| Parámetro | Valor Típico | Rango | Efecto |
|-----------|--------------|-------|--------|
| **Calibración** | | | |
| Número de imágenes | 15-20 | 10-30 | Más imágenes = mejor calibración |
| Tamaño tablero | 9x6 | 7x5 a 12x9 | Mayor = más puntos, mejor calibración |
| | | | |
| **Rectificación** | | | |
| Alpha | 0 | 0-1 | 0=recortar, 1=mantener todo |
| | | | |
| **Disparidad** | | | |
| numDisparities | 64 | 16-256 | Mayor = más rango, más lento |
| blockSize (SADWindowSize) | 21 | 5-25 (impar) | Mayor = más suave, menos detalles |
| uniquenessRatio | 15 | 5-15 | Mayor = filtrado más estricto |
| preFilterCap | 61 | 1-63 | Normalización pre-filtro |
| minDisparity | 0 | 0-64 | Offset de búsqueda |
| speckleWindowSize | 100 | 0-200 | Tamaño mínimo de región válida |
| speckleRange | 32 | 0-100 | Variación de disparidad permitida |
| disp12MaxDiff | 1 | -1,1-2 | -1=desactivar, >0=activar chequeo |
| | | | |
| **Reproyección** | | | |
| Distancia máxima | 8000 mm | 5000-15000 | Filtrar puntos lejanos |
| | | | |
| **Hardware** | | | |
| Baseline | 9 cm | 5-20 cm | Mayor = más rango |
| Resolución | 640x480 | 320x240 a 1920x1080 | Mayor = más detalles, más lento |
| FPS | 30 | 15-60 | Mayor FPS = más carga CPU |

---

## APÉNDICE B: SOLUCIÓN DE PROBLEMAS COMUNES

### Problema: "No se detectan las esquinas del tablero"

**Causas posibles:**
- Iluminación insuficiente o con sombras
- Tablero no completamente visible
- Imagen borrosa (movimiento durante captura)
- Tablero impreso con baja calidad

**Soluciones:**
1. Mejorar iluminación (luz difusa, sin sombras)
2. Asegurar que el tablero completo esté en la imagen
3. Usar trípode o estabilizar cámaras
4. Imprimir tablero en cartón rígido con impresora de alta calidad
5. Probar con `CALIB_CB_FAST_CHECK` flag

---

### Problema: "Las imágenes rectificadas están muy distorsionadas"

**Causas posibles:**
- Calibración pobre
- Pocas imágenes de calibración
- Imágenes de calibración desde ángulos muy similares
- Cámaras muy desalineadas (no frontalmente paralelas)

**Soluciones:**
1. Repetir calibración con 20+ imágenes
2. Variar significativamente los ángulos y posiciones del tablero
3. Colocar cámaras lo más alineadas posible mecánicamente
4. Usar parámetro `alpha` en `stereoRectify()` (probar 0, 0.5, 1)
5. Verificar que no haya errores en la detección de esquinas

---

### Problema: "El mapa de disparidad tiene muchos huecos (píxeles negros)"

**Causas posibles:**
- Escena con poca textura
- Parámetros muy estrictos (uniquenessRatio alto)
- Objetos ocluidos (solo visibles en una cámara)
- Superficies reflectantes o transparentes

**Soluciones:**
1. Aumentar textura de la escena (añadir objetos texturizados)
2. Reducir `uniquenessRatio`
3. Aumentar `blockSize` (ventana SAD más grande)
4. Usar SGBM en lugar de BM (mejor con baja textura)
5. Proyectar patrón de luz estructurada (para superficies lisas)
6. Ajustar iluminación para reducir reflejos

---

### Problema: "La nube de puntos es muy ruidosa o dispersa"

**Causas posibles:**
- Errores en calibración
- Mapa de disparidad ruidoso
- Objetos muy lejanos (baja precisión)
- Post-filtrado insuficiente

**Soluciones:**
1. Verificar y mejorar calibración
2. Aplicar más post-filtrado:
   ```cpp
   filterSpeckles(disparidad, 0, 200, 64);
   medianBlur(disparidad, disparidad, 5);
   ```
3. Filtrar por umbral de Z más estricto:
   ```cpp
   if (Z > 500 && Z < 5000) { ... }  // Solo 0.5m a 5m
   ```
4. Aplicar filtros estadísticos en PCL:
   ```cpp
   pcl::StatisticalOutlierRemoval<pcl::PointXYZRGB> sor;
   sor.setInputCloud(nube);
   sor.setMeanK(50);
   sor.setStddevMulThresh(1.0);
   sor.filter(*nube_filtrada);
   ```

---

### Problema: "El sistema es muy lento"

**Causas posibles:**
- Resolución de imagen muy alta
- Parámetros de disparidad muy altos
- Uso de SGBM en lugar de BM
- CPU limitada

**Soluciones:**
1. Reducir resolución:
   ```cpp
   resize(imagen, imagen, Size(), 0.5, 0.5);
   ```
2. Reducir `numDisparities` (ej: 64 en lugar de 128)
3. Reducir `blockSize` ligeramente
4. Usar StereoBM en lugar de StereoSGBM
5. Compilar OpenCV con optimizaciones (AVX, SSE)
6. Considerar implementación GPU (CUDA):
   ```cpp
   cuda::StereoBM bm = cuda::createStereoBM();
   ```
7. Procesar cada N frames en lugar de todos
8. Reducir área de interés (ROI):
   ```cpp
   Rect roi(x, y, ancho, alto);
   Mat img_roi = imagen(roi);
   ```

---

### Problema: "Los colores en la nube de puntos no coinciden"

**Causas posibles:**
- Balance de blanco diferente entre cámaras
- Exposición diferente entre cámaras
- No se rectificó la imagen a color
- Error en extracción de colores

**Soluciones:**
1. Configurar ambas cámaras con mismos parámetros:
   ```cpp
   cam_izq.set(CAP_PROP_AUTO_WB, 0);  // Desactivar auto white balance
   cam_der.set(CAP_PROP_AUTO_WB, 0);
   cam_izq.set(CAP_PROP_EXPOSURE, -5);  // Misma exposición
   cam_der.set(CAP_PROP_EXPOSURE, -5);
   ```
2. Asegurar que se rectifica también la imagen a color
3. Verificar que se usa la imagen izquierda para colores
4. Calibrar colores (balance de blancos manual)

---

Este documento proporciona un procedimiento completo y detallado para implementar un sistema de reconstrucción 3D con dos cámaras. Para preguntas específicas o problemas no cubiertos aquí, consultar la documentación oficial de OpenCV y PCL, o los papers de referencia mencionados.

**¡Éxito en tu implementación!**
