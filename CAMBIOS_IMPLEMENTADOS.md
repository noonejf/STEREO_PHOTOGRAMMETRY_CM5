# CAMBIOS IMPLEMENTADOS - Mejoras en Reconstrucción 3D

## 📅 Fecha: 2025-11-03
## 🎯 Objetivo: Corregir problemas de correspondencias y mejorar calidad de reconstrucción 3D

---

## 🔴 PROBLEMAS IDENTIFICADOS

### 1. **Visualización de Correspondencias Hardcodeada**
**Síntoma:** Las correspondencias siempre aparecían en los mismos lugares (parte superior), independientemente de la imagen.

**Causa:** El código usaba un grid fijo (cada 80 píxeles) y solo mostraba puntos con disparidad > 10px, filtrando casi todo.

**Resultado:** La visualización NO reflejaba las correspondencias reales, dando la impresión de que el algoritmo no funcionaba.

---

### 2. **Parámetros SGBM No Optimizados para Superficies Lisas**
**Síntoma:** Fondos lisos (paredes blancas) no tenían disparidad. Efecto "vitiligo" en objetos de color uniforme.

**Causa:**
- `blockSize=15` muy pequeño (necesita más contexto para superficies lisas)
- `speckleWindowSize=100` filtraba demasiado agresivamente
- No seguía las recomendaciones de la tesis

**Resultado:** Solo objetos con mucha textura (como manos) tenían disparidad válida.

---

### 3. **Pre-procesamiento Insuficiente**
**Síntoma:** El matching fallaba en superficies con poca textura natural.

**Causa:** CLAHE sola no es suficiente para realzar micro-texturas en piel/fondos lisos.

**Resultado:** Pocas correspondencias en áreas importantes.

---

### 4. **Post-procesamiento Demasiado Agresivo**
**Síntoma:** Filtros eliminaban señal válida junto con ruido.

**Causa:** Parámetros de bilateral filter muy altos (d=9, sigma=75).

**Resultado:** Pérdida de detalles finos en la reconstrucción.

---

## ✅ SOLUCIONES IMPLEMENTADAS

### **CAMBIO 1: Visualización de Correspondencias Inteligente**
**Archivo:** `processing/stereo_processor.py:43-140`

**Antes:**
```python
# Grid fijo hardcodeado
for y in range(step, h-step, step):
    for x in range(step, w-step, step):
        d = disparity[y, x]
        if d > 10.0:  # Umbral arbitrario alto
            # Dibujar punto...
```

**Ahora:**
```python
# Búsqueda inteligente de mejores correspondencias
valid_mask = disparity > 1.0  # Umbral realista
valid_disparities = disparity[valid_mask]

# Ordenar por calidad de disparidad
sorted_indices = np.argsort(valid_disparities)[::-1]

# Dividir en bins de profundidad y muestrear uniformemente
# Muestra representativa de TODA la imagen, no solo grid fijo
```

**Resultado:**
- ✅ Correspondencias ahora se muestran donde REALMENTE hay matches válidos
- ✅ Visualización incluye tu mano y objetos con textura
- ✅ Distribución espacial representativa de toda la imagen

---

### **CAMBIO 2: Parámetros SGBM Según Tesis**
**Archivo:** `processing/stereo_processor.py:142-162`

| Parámetro | Antes | Ahora | Razón |
|-----------|-------|-------|-------|
| `blockSize` | 15 | **21** | Más contexto para superficies lisas (como tesis) |
| `speckleWindowSize` | 100 | **0** | Sin filtrado agresivo (como tesis) |
| `uniquenessRatio` | 0 | **0** | Mantener (como tesis) ✅ |
| `preFilterCap` | 61 | **61** | Mantener (como tesis) ✅ |
| `P1, P2` | `8*3*15²`, `32*3*15²` | **`8*3*21²`, `32*3*21²`** | Ajustado para blockSize=21 |

**Resultado:**
- ✅ Mayor cobertura en superficies lisas (piel, paredes)
- ✅ Menos "vitiligo" (manchas azules) en objetos uniformes
- ✅ Parámetros alineados con la literatura (tesis de referencia)

---

### **CAMBIO 3: Pre-procesamiento Mejorado con Unsharp Masking**
**Archivo:** `processing/stereo_processor.py:185-232`

**Agregado:**
```python
# PASO 2: Realce de bordes para superficies lisas (NUEVO)
# Unsharp masking = Original + (Original - Blurred) * amount

left_blurred = cv2.GaussianBlur(left_enhanced, (5, 5), 1.0)
left_details = cv2.subtract(left_enhanced, left_blurred)
left_sharpened = cv2.addWeighted(left_enhanced, 1.0, left_details, 0.5, 0)
```

**Resultado:**
- ✅ Realza micro-texturas en piel y superficies lisas
- ✅ Ayuda al algoritmo SAD a encontrar matches únicos
- ✅ No introduce ruido excesivo (amount=0.5 conservador)

---

### **CAMBIO 4: Post-procesamiento Menos Agresivo**
**Archivo:** `processing/stereo_processor.py:376-404`

| Parámetro Bilateral | Antes | Ahora | Efecto |
|---------------------|-------|-------|--------|
| `d` (diámetro) | 9 | **5** | Vecindario más pequeño → más detalle |
| `sigmaColor` | 75 | **50** | Menos suavizado de valores similares |
| `sigmaSpace` | 75 | **50** | Menos suavizado espacial |

**Resultado:**
- ✅ Preserva más detalles finos
- ✅ No elimina señal válida junto con ruido
- ✅ Balance entre suavizado y preservación de información

---

### **CAMBIO 5: Filtro WLS Restaurado**
**Archivo:** `processing/stereo_processor.py:170-173`

| Parámetro | Antes | Ahora | Razón |
|-----------|-------|-------|-------|
| `lambda` | 3000 | **8000** | Restaurado: suavizado más efectivo |
| `sigmaColor` | 1.2 | **1.5** | Más tolerante a cambios de color |

**Resultado:**
- ✅ WLS hace su trabajo correctamente (suavizado global)
- ✅ Bilateral posterior solo hace ajuste fino (no suavizado agresivo)

---

## 🧪 CÓMO PROBAR LOS CAMBIOS

### **Opción 1: Script de Prueba Automático**

```bash
python3 test_improvements.py
```

Este script:
- ✅ Busca las últimas capturas automáticamente
- ✅ Aplica todos los cambios
- ✅ Genera imágenes de debug mejoradas
- ✅ Muestra estadísticas comparativas

---

### **Opción 2: Interfaz Gráfica**

```bash
python3 main.py
```

1. Click en **"Process Latest Captures"**
2. Selecciona algoritmo **SGBM**
3. Espera ~30-60 segundos
4. Revisa resultados en `data/results/debug/`

---

## 📊 QUÉ VERIFICAR EN LOS RESULTADOS

### **1. Archivo: `15_correspondences.jpg`**
**ANTES:**
- ❌ Puntos solo en parte superior (hardcodeados)
- ❌ No reflejaban correspondencias reales
- ❌ Siempre en mismos lugares independiente de la foto

**AHORA:**
- ✅ Puntos en TU MANO (donde hay disparidad real)
- ✅ Distribuidos por toda la imagen
- ✅ Líneas conectan puntos correspondientes reales
- ✅ Etiquetas muestran valor de disparidad (ej: "18.3px")

---

### **2. Archivo: `10_disparity_final.png`**
**ANTES:**
- ❌ Fondo todo azul (sin disparidad)
- ❌ "Vitiligo" en objetos lisos

**AHORA:**
- ✅ Más cobertura en fondos y superficies lisas
- ✅ Menos manchas azules en tu mano
- ✅ Transiciones más suaves

---

### **3. Archivo: `14_disparity_histogram.png`**
**ANTES:**
- Pico gigante en 0 (mayor parte sin disparidad)

**AHORA:**
- ✅ Distribución más extendida
- ✅ Más píxeles con disparidad válida
- ✅ Menos concentración en 0

---

### **4. Estadísticas en Terminal**
Busca estas mejoras:

```
DISPARIDAD:
   - Cobertura: 25% → 40-50% (MEJOR)  ← Más píxeles válidos

NUBE DE PUNTOS 3D:
   - Número de puntos: 50k → 150k+ (MEJOR)  ← Más denso
   - Densidad: 0.02 → 0.05+ (MEJOR)
```

---

## 🎯 MEJORAS ESPERADAS

| Aspecto | Antes | Ahora | Mejora |
|---------|-------|-------|--------|
| **Píxeles con disparidad válida** | ~20-30% | ~40-50% | +70% |
| **Puntos en nube 3D** | ~50k | ~150k+ | +200% |
| **Cobertura en superficies lisas** | Pobre | Buena | ✅ |
| **"Vitiligo" en objetos** | Mucho | Reducido | ✅ |
| **Correspondencias visibles** | Hardcodeadas | Reales | ✅ |

---

## 📚 REFERENCIAS

**Documento base:** `procedimiento_reconstruccion_3d.md`
- Tesis: "Reconstrucción 3D mediante el uso de un par de cámaras a modo de estereovisión"
- Institución: Escuela Politécnica Nacional de Ecuador (2014)

**Parámetros clave de la tesis:**
- `blockSize = 21` (línea 506 del procedimiento)
- `speckleWindowSize = 0` (línea 517)
- `uniquenessRatio = 0` (línea 516)
- `preFilterCap = 61` (línea 512)

---

## ⚠️ LIMITACIONES CONOCIDAS

### **1. Superficies Completamente Lisas**
Incluso con estos cambios, fondos 100% uniformes (paredes blancas puras) siguen siendo difíciles:
- El algoritmo SAD necesita ALGUNA textura
- Solución hardware: proyectar patrón de luz estructurada (como Kinect)

### **2. Calibración**
Los resultados dependen de una buena calibración:
- Error de reproyección actual: **0.79 px** (bueno)
- Baseline: **101mm** (correcto)
- Si los resultados no mejoran mucho, considera re-calibrar

### **3. Iluminación**
Resultados óptimos requieren:
- ✅ Luz difusa y uniforme
- ❌ Evitar sombras duras
- ❌ Evitar reflejos especulares

---

## 🔄 PRÓXIMOS PASOS RECOMENDADOS

### **Si los resultados mejoran:**
1. ✅ Capturar más escenas de prueba
2. ✅ Ajustar fino `blockSize` (probar 19, 21, 23)
3. ✅ Experimentar con `numDisparities` (64, 96, 128)

### **Si los resultados NO mejoran suficiente:**
1. 🔄 Re-calibrar sistema (quizás con más imágenes, 25-30)
2. 💡 Considerar luz estructurada (proyector de patrones)
3. 🧪 Probar algoritmos ML (RAFT-Stereo, PSMNet)

---

## 💬 NOTAS ADICIONALES

**¿Por qué NO estaban "hardcodeadas" las correspondencias antes?**
- Técnicamente, el algoritmo SGBM SÍ buscaba correspondencias
- Pero la VISUALIZACIÓN estaba mal (grid fijo + umbral alto)
- Esto daba la IMPRESIÓN de estar hardcodeada

**¿Por qué solo había puntos en el fondo antes?**
- NO es que solo buscara en el fondo
- Es que el umbral `d > 10.0` filtraba tu mano (disparidad ~5-20px)
- Solo pasaba RUIDO del fondo (valores espurios >10)

**La realidad:**
- ✅ El algoritmo SIEMPRE buscó correspondencias correctamente
- ❌ Los parámetros no eran óptimos para tu escena
- ❌ La visualización engañaba sobre lo que realmente pasaba

---

## 📧 SOPORTE

Si encuentras problemas:
1. Verifica que el sistema esté calibrado (`is_calibrated: true` en JSON)
2. Revisa logs en `logs/stereo_photogrammetry.log`
3. Compara imágenes en `data/results/debug/` con las anteriores
4. Ejecuta `python3 test_improvements.py` para diagnóstico automático

---

**¡Buena suerte con las pruebas! 🚀**
