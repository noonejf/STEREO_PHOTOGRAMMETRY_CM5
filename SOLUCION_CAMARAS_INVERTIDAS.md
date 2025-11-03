# SOLUCIÓN: Cámaras Montadas de Cabeza (Upside-Down)

## Problema Identificado

Las cámaras Arducam HQ 477 están **montadas físicamente de cabeza** (rotadas 180°), lo que causaba:

1. **Disparidad negativa** (-365px en lugar de +30px esperado)
2. **Imágenes invertidas** (horizontal y verticalmente)
3. **Correspondencias incorrectas** en la reconstrucción 3D
4. **Errores de rectificación** (error vertical de 38px)

### Análisis Realizado

```
Esquina #0 del tablero (esquina superior-izquierda):
  En left.jpg:  x=336.8, y=593.1
  En right.jpg: x=732.0, y=554.9

Disparidad: Δx = -395.2 px  ← NEGATIVA (INCORRECTO)
```

**Causa raíz**:
- CAM0 está físicamente a la IZQUIERDA ✓
- CAM1 está físicamente a la DERECHA ✓
- PERO ambas están **de cabeza**
- Resultado: CAM0 captura desde perspectiva derecha (invertida)

## Solución Implementada

Se agregó **rotación automática de 180°** en `camera/stereo_camera.py` líneas 177-192:

```python
# Rotar imágenes 180° porque las cámaras están montadas de cabeza
img = cv2.imread(output_file)
if img is not None:
    img_rotated = cv2.rotate(img, cv2.ROTATE_180)
    cv2.imwrite(output_file, img_rotated)
```

Esta rotación se aplica **automáticamente** a:
- ✅ Capturas de calibración
- ✅ Capturas estéreo normales
- ✅ Todas las operaciones de captura

## Pasos Siguientes (IMPORTANTE)

### ⚠️ DEBES RE-CALIBRAR EL SISTEMA

La calibración actual fue hecha con imágenes invertidas, por lo tanto **es INVÁLIDA**.

**Pasos obligatorios:**

1. **Eliminar calibración antigua:**
   ```bash
   mv data/calibration/calibration_data.json data/calibration/calibration_data_OLD_INVERTIDA.json
   ```

2. **RE-CALIBRAR desde el GUI:**
   - Abrir la aplicación: `python3 main.py`
   - Ir a "Calibrar"
   - Capturar 25 imágenes del tablero de ajedrez
   - Asegurar que las nuevas imágenes se vean **correctas** (no invertidas)

3. **Verificar disparidad positiva:**
   ```bash
   # Después de calibrar, toma una captura de prueba
   # Y ejecuta:
   python3 analyze_chessboard_stereo.py
   ```

   Deberías ver:
   ```
   ✅ Disparidad horizontal POSITIVA (+20 a +50px)
   ✅ Disparidad vertical BAJA (<2px)
   ```

## Alternativa: Montar las Cámaras Correctamente

Si prefieres **NO usar rotación en software**, puedes:

1. **Montar las cámaras al derecho** (no de cabeza)
2. **Eliminar** las líneas 177-192 de `camera/stereo_camera.py`
3. **RE-CALIBRAR**

**Ventaja**: Menor carga de procesamiento (no rotar cada captura)
**Desventaja**: Requiere modificación de hardware

## Verificación Post-Calibración

Después de re-calibrar, ejecuta:

```bash
python3 analyze_chessboard_stereo.py
```

**Resultados esperados:**

```
✅ Disparidad horizontal POSITIVA (+20 a +50px)
   → CAM0 = LEFT, CAM1 = RIGHT ✓ CORRECTO

✅ Disparidad vertical BAJA (<2px)
   → Rectificación correcta

✅ Reconstrucción 3D con profundidades correctas
   → Objetos a 1m → ~30px disparidad
   → Objetos a 2m → ~15px disparidad
```

## Archivos Modificados

- `camera/stereo_camera.py` (líneas 177-192): Rotación automática
- `SOLUCION_CAMARAS_INVERTIDAS.md` (este archivo): Documentación

## Notas Técnicas

**¿Por qué disparidad negativa es incorrecta?**

En una configuración estéreo estándar:
- Cámara LEFT ve objetos **más a la derecha** en su imagen
- Cámara RIGHT ve objetos **más a la izquierda** en su imagen
- Por lo tanto: `x_left > x_right` → disparidad positiva

Con cámaras de cabeza:
- La imagen se invierte horizontalmente
- LEFT ve objetos a la izquierda → `x_left < x_right` → disparidad negativa ❌

**Rotación 180° vs Flip Horizontal:**

No usar solo `cv2.flip(img, 1)` (flip horizontal), porque:
- Las cámaras están de cabeza → inversión horizontal **Y vertical**
- Rotación 180° = flip horizontal + flip vertical
- `cv2.rotate(img, cv2.ROTATE_180)` hace ambos

---

**Fecha**: 2025-11-03
**Problema**: Cámaras montadas de cabeza
**Solución**: Rotación automática 180° en captura
**Estado**: ⚠️ REQUIERE RE-CALIBRACIÓN
