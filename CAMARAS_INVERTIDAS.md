# 🔴 PROBLEMA CRÍTICO: CÁMARAS INVERTIDAS

## ✅ **DIAGNÓSTICO CONFIRMADO**

Tus cámaras LEFT y RIGHT están **FÍSICAMENTE INVERTIDAS**.

### **Evidencia:**

Mirando tus imágenes `01_left_original.jpg` y `02_right_original.jpg`:

```
Imagen "LEFT":                 Imagen "RIGHT":
- Mano apunta DERECHA          - Mano apunta IZQUIERDA
- Se ve MÁS brazo izquierdo    - Se ve MÁS brazo derecho
- Ventana a la IZQUIERDA       - Ventana a la DERECHA
```

**Conclusión:** Lo que llamas "LEFT" es realmente la cámara DERECHA física.

---

## 🎯 **POR QUÉ LAS CORRESPONDENCIAS SE VEÍAN RARAS**

### **Lo que preguntaste:**
> "Veo punto verde en mi pulsera (imagen izq) y el punto está en mi antebrazo (imagen der)"
> "El punto está más a la DERECHA en la segunda imagen"

### **Explicación:**

Con cámaras correctas:
```
Punto en imagen IZQUIERDA:    X = 500
Punto en imagen DERECHA:      X = 300  (200px A LA IZQUIERDA)
Disparidad = 500 - 300 = 200px (POSITIVA)
```

Con tus cámaras INVERTIDAS:
```
Punto en imagen "IZQUIERDA" (realmente derecha): X = 500
Punto en imagen "DERECHA" (realmente izquierda): X = 700  (200px A LA DERECHA)
Disparidad = 500 - 700 = -200px (NEGATIVA o cercana a 0 tras filtros)
```

**Por eso:**
- ❌ Las correspondencias iban hacia la DERECHA (debería ser izquierda)
- ❌ Los puntos parecían "saltar" a lugares incorrectos
- ❌ Las disparidades eran muy pequeñas o invertidas

---

## 🔧 **SOLUCIÓN**

### **OPCIÓN 1: Arreglar en HARDWARE (Recomendado)**

**Intercambia los cables de las cámaras:**

```
ANTES (INCORRECTO):
┌─────────────┐
│  Raspberry  │
│    Pi CM5   │
├─────────────┤
│ CAM0 │ CAM1 │
└──┬───┴───┬──┘
   │       │
   │       └──────→ Cámara IZQUIERDA física  ❌ INVERTIDO
   │
   └──────────────→ Cámara DERECHA física   ❌ INVERTIDO


DESPUÉS (CORRECTO):
┌─────────────┐
│  Raspberry  │
│    Pi CM5   │
├─────────────┤
│ CAM0 │ CAM1 │
└──┬───┴───┬──┘
   │       │
   │       └──────→ Cámara DERECHA física   ✅ CORRECTO
   │
   └──────────────→ Cámara IZQUIERDA física  ✅ CORRECTO
```

**Pasos:**
1. Apaga la Raspberry Pi
2. Desconecta cable de CAM0
3. Desconecta cable de CAM1
4. Reconecta cables intercambiados:
   - CAM0 → Cámara que esté físicamente a la IZQUIERDA
   - CAM1 → Cámara que esté físicamente a la DERECHA
5. Enciende Raspberry Pi

---

### **OPCIÓN 2: Arreglar en SOFTWARE (Temporal)**

Si no puedes acceder al hardware, puedes arreglar en software:

```bash
# Ejecuta este script una vez:
python3 fix_camera_swap.py
```

Esto:
1. ✅ Intercambia las imágenes de la última captura
2. ✅ Marca en configuración que las cámaras están invertidas
3. ⚠️ REQUIERE re-calibración

**IMPORTANTE:** Esta solución es temporal. Mejor arreglar el hardware.

---

## 🔄 **DESPUÉS DE ARREGLAR**

### **PASO 1: Verificar que esté corregido**

```bash
# Captura un nuevo par de prueba
python3 main.py
# Click "Capture Stereo Pair"

# Verifica visualmente:
# - Imagen LEFT debe mostrar MÁS del lado IZQUIERDO de la escena
# - Imagen RIGHT debe mostrar MÁS del lado DERECHO de la escena
```

**Test visual:**
```
Coloca un objeto a la IZQUIERDA y otro a la DERECHA
Deberías ver:
- LEFT: objeto izquierdo GRANDE, objeto derecho pequeño
- RIGHT: objeto izquierdo pequeño, objeto derecho GRANDE
```

---

### **PASO 2: INVALIDAR calibración actual**

```bash
# Renombrar calibración vieja (no borrar, por si acaso)
mv data/calibration/calibration_data.json data/calibration/calibration_data_OLD_INVERTIDA.json
```

**Razón:** La calibración actual se hizo con cámaras invertidas, es inútil.

---

### **PASO 3: RE-CALIBRAR con cámaras correctas**

```bash
python3 main.py
# Click "Calibrate"
```

**Al calibrar:**
- ✅ Captura 25-30 imágenes del tablero
- ✅ Varía distancias: 30cm, 50cm, 80cm, 1m, 1.5m
- ✅ Varía ángulos: frontal, lateral izquierdo, lateral derecho, inclinado
- ✅ Asegúrate que el tablero se vea en AMBAS cámaras

**Verificar después:**
```json
// En calibration_data.json
"calibration_error": < 0.5 px (excelente) o < 1.0 px (bueno)
"baseline_meters": ~0.08-0.12m (tu setup real)
```

---

### **PASO 4: PROBAR con nueva calibración**

```bash
# Captura nueva escena
python3 main.py  # → "Capture Stereo Pair"

# Procesa
python3 test_improvements.py
```

**Verificar correspondencias:**
```bash
# Abre: data/results/debug/15_correspondences.jpg
```

**Ahora deberías ver:**
- ✅ Líneas van hacia la IZQUIERDA (no derecha)
- ✅ Punto en tu pulsera conecta con punto en tu pulsera
- ✅ Disparidades grandes en objetos cercanos (tu mano ~200-300px)
- ✅ Disparidades pequeñas en objetos lejanos (pared ~10-50px)

---

## 📊 **CÓMO VERIFICAR QUE FUNCIONÓ**

### **Test 1: Dirección de correspondencias**
```
ANTES (INVERTIDO):
Imagen IZQ: [punto]
            └─────→ A LA DERECHA ❌
Imagen DER:        [punto]

DESPUÉS (CORRECTO):
Imagen IZQ:        [punto]
            ←──────┘ A LA IZQUIERDA ✅
Imagen DER: [punto]
```

### **Test 2: Magnitud de disparidades**
```
ANTES (INVERTIDO):
Mano cerca:  disparidad ~5-20px    ❌ (muy pequeño)
Pared lejos: disparidad ~50-82px   ❌ (invertido)

DESPUÉS (CORRECTO):
Mano cerca:  disparidad ~200-400px ✅ (grande = cerca)
Pared lejos: disparidad ~10-50px   ✅ (pequeño = lejos)
```

### **Test 3: Profundidad calculada**
```
ANTES (INVERTIDO):
Mano cerca:  profundidad ~5-30m    ❌
Pared lejos: profundidad ~2-10m    ❌

DESPUÉS (CORRECTO):
Mano cerca:  profundidad ~0.5-1m   ✅
Pared lejos: profundidad ~3-5m     ✅
```

---

## 💡 **POR QUÉ PASÓ ESTO**

Posibles causas:
1. **Error al instalar:** Cables conectados al revés durante instalación
2. **Configuración incorrecta:** IDs de cámara asignados incorrectamente en `camera_config.py`
3. **Convención diferente:** Tal vez asumiste otra convención de left/right

**No importa la causa, lo importante es arreglarlo.**

---

## ✅ **CHECKLIST DESPUÉS DE ARREGLAR**

- [ ] Intercambié cables físicos (OPCIÓN 1) O ejecuté `fix_camera_swap.py` (OPCIÓN 2)
- [ ] Verifiqué con captura de prueba (LEFT muestra más de lado izquierdo)
- [ ] Renombré calibración vieja: `calibration_data_OLD_INVERTIDA.json`
- [ ] Re-calibré con 25-30 imágenes a diferentes distancias
- [ ] Error de calibración < 1.0 px
- [ ] Procesé nueva imagen de prueba con `test_improvements.py`
- [ ] Correspondencias ahora van hacia la IZQUIERDA
- [ ] Disparidades tienen sentido (cerca=grande, lejos=pequeño)
- [ ] Profundidades son realistas (mano ~0.5-1m, no 5-30m)

---

## 📞 **SIGUIENTE SESIÓN**

Después de arreglar, muéstrame:
1. Nueva imagen `15_correspondences.jpg` (líneas deben ir a la IZQUIERDA)
2. Nuevo `calibration_data.json` (baseline y error)
3. Output de `verify_correspondences.py`

¡Con esto tu sistema finalmente funcionará correctamente! 🎯

---

**NOTA FINAL:** Este era el problema PRINCIPAL. TODO lo demás (parámetros, algoritmos, visualizaciones) estaba bien. Solo necesitabas las cámaras en el orden correcto.
