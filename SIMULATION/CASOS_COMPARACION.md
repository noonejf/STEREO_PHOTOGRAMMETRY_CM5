# Casos de comparación: ensayo en seco de los criterios de la sesión

## Qué es esto y qué no es

**No es una tabla de criterios nueva.** Los criterios ya están registrados por
adelantado en `Documentation/LINKU_Experiment_TV2`, capítulo 2, tabla
`tab:crit-pipeline`, y no se re-derivan al analizar. Esto es otra cosa:
**correr esos mismos criterios sobre pares renderizados**, antes de la sesión.

Eso compra tres cosas:

1. **Pone a prueba los criterios, no solo la pipeline.** Si un criterio resulta
   inmedible o está mal definido, sale ahora y no en TV2 con el estudio
   alquilado.
2. **Da una predicción.** Cuáles van a pasar y cuáles no, con número, antes de
   la sesión.
3. **Mide la brecha estudio contra órbita**, que es lo único que puede
   responder si TV2 vale como validación del caso de vuelo. R3 y R4 no se
   pueden cumplir con lámparas, así que la salida no es fingir que se cumplen,
   es medir cuánto cuesta incumplirlos.

**Y aquí el ensayo es más exigente que la sesión.** A3.5 compara contra el
largo medido con cinta métrica; en el render la verdad es exacta, el generador
conoce el centro del cable punto a punto. Lo que aquí se mide con 0.1 % de
incertidumbre, en TV2 se medirá con una cinta.

## La matriz

Un caso base y una variación por caso, para que un fallo se pueda atribuir a
una sola cosa. Ocho pares estéreo, dieciséis cuadros.

| # | caso | entorno | vista | forma | lámparas | variante | qué pone a prueba |
|---|------|---------|-------|-------|----------|----------|-------------------|
| 1 | **base estudio** | TV2 | eje | ondulada | ocultas | `S` ✅ | la referencia contra la que se compara todo |
| 2 | **órbita** | AM0 | eje | ondulada | --- | `W` ✅ | **la comparación**: cuánto cambia el resultado al perder el haz paralelo y ganar un cuarto detrás |
| 3 | lámparas en cuadro | TV2 | eje | ondulada | **visibles** | `X` ✅ | R7 relajado: nueve lámparas saturadas en cuadro |
| 4 | costado | TV2 | **costado** | ondulada | ocultas | `M` ✅ | la vista que mide largo de arco sin compresión |
| 5 | órbita costado | AM0 | **costado** | ondulada | --- | falta | par del 4 |
| 6 | cuerda recta | TV2 | eje | **recta** | ocultas | falta | **A3.6**, rectitud ≥ 0.97, que solo tiene sentido con el cable tenso |
| 7 | órbita recta | AM0 | eje | **recta** | --- | falta | par del 6 |
| 8 | onda fuerte | TV2 | eje | **onda × 2** | ocultas | falta | estrés del trazador: más curvatura, más tramo degenerado |

Cuatro ya están renderizadas. Faltan cuatro, unos 20 minutos de render.

## Qué se mide en cada caso

Los siete criterios registrados, más los errores contra la verdad que el
generador conoce y la sesión real no va a tener.

| id | criterio registrado | umbral |
|----|---------------------|--------|
| A3.1 | la máscara es **una sola componente conexa** en las dos imágenes | ≥ 80 % de los pares |
| A3.2 | el detector devuelve **exactamente dos extremos** en las dos | ≥ 80 % |
| A3.3 | el trazado automático **llega al extremo lejano** sin intervención | ≥ 50 % |
| A3.4 | fracción de muestras que **sobrevive a los filtros** de `compute_wire_metrics` | ≥ 90 % por par |
| A3.5 | **largo de arco** contra el largo real | ± 10 % |
| A3.6 | **rectitud**, con el cable tenso | ≥ 0.97 |
| A3.7 | al menos una corrida completa con nube exportada y escalares | ≥ 1 |

Y además, porque aquí se puede y en la sesión no:

| medida | contra qué | por qué importa |
|--------|------------|-----------------|
| cobertura y precisión de la máscara | el centro verdadero del cable | A3.1 dice "una componente", no dice si es **la correcta** |
| F1 del trazado | la línea central verdadera | A3.3 dice "llega", no dice por dónde |
| error de Z por tramo | la distancia verdadera | A3.5 es un escalar; esto dice **dónde** falla |
| largo de arco crudo y suavizado | el arco verdadero | ver el defecto de abajo |

## Dos cosas que este ensayo ya va a destapar, y conviene esperarlas

**A3.4 y A3.5 se pisan.** `wire_metrics.py:109` suma los segmentos de la nube
cruda sin suavizar. Medido sobre el par de costado: el arco crudo da 23.307 m
donde la verdad son 9.466, **+146 %**, y suavizando la profundidad antes de
integrar da 9.492 m, +0.27 %. El ruido de profundidad por punto, 34 mm rms, es
más grande que el paso entre puntos, así que cada tramito mide su propio ruido
y la suma crece sin límite. A3.5 pide ± 10 % y la pipeline tal como está no
puede acercarse. **Esto hay que arreglarlo antes de la sesión, no después**, o
A3.5 falla por un defecto conocido en vez de por la física.

**A3.6 solo se puede evaluar en los casos 6 y 7.** La rectitud es la cuerda
entre extremos dividida por el arco, así que un cable deliberadamente ondulado
da un número bajo que no significa nada. Por eso la matriz tiene el par recto.

## Cómo se corre

Los cuatro casos que faltan:

```bash
blender --background --python SIMULATION/render_studio_iterations.py -- \
        --variant <CASO> --samples 24 --both
```

Y el ensayo completo, pendiente de escribir, debería ser un `tools/` que tome
las ocho carpetas, las pase por la pipeline sin modificar y escriba esta misma
tabla rellena. Que sea la aplicación sin tocar es parte del criterio: el
capítulo dice "by running the application unmodified".

## Lo que este ensayo NO puede responder

- **Ruido de sensor.** Cycles no tiene. El fondo del render mide 0 exacto; el
  real será el ruido de lectura más lo que se filtre por las puertas. Todos los
  contrastes de aquí son cotas optimistas.
- **Luz parásita, sincronización, deriva térmica, vibración.** Nada de eso está
  simulado.
- **La calibración.** Estos pares usan la geometría exacta. La sesión usará una
  calibración con incertidumbre, y A1.2 permite error de escala focal que se
  traslada entero al largo de arco.

Por eso el ensayo predice y no certifica. Un criterio que falla aquí va a
fallar en TV2; uno que pasa aquí puede fallar igual allá.

---

# Resultado del ensayo, 18 de noviembre de 2026

Corrido con `tools/run_comparison_cases.py`, sobre los ocho casos, con los
módulos de la aplicación sin modificar.

| caso | A3.1 | A3.2 | A3.3 | A3.4 | A3.5 | A3.6 | cobertura | precisión |
|------|------|------|------|------|------|------|-----------|-----------|
| 1 base estudio | **NO** | sí | sí | --- | --- | --- | 85 % | 30 % |
| 2 órbita | **NO** | sí | sí | --- | --- | --- | 85 % | 33 % |
| 3 lámparas en cuadro | **NO** | sí | sí | 93 % | **+50.3 %** | --- | 84 % | 29 % |
| 4 costado estudio | sí | sí | sí | --- | --- | --- | **100 %** | **69 %** |
| 5 costado órbita | sí | sí | sí | --- | --- | --- | **100 %** | **64 %** |
| 6 cable tenso | sí | sí | sí | 100 % | **+9.4 %** | 0.975 | 100 % | 14 % |
| 7 tenso en órbita | sí | sí | sí | 100 % | **+9.1 %** | 0.975 | 100 % | 15 % |
| 8 onda fuerte | **NO** | sí | sí | 60 % | **+18.2 %** | --- | 98 % | 49 % |

## Lo que responde

**TV2 vale como validación del caso de vuelo.** Los pares estudio contra
órbita coinciden: el caso 6 da +9.4 % y el 7 da +9.1 %, con rectitud 0.975 los
dos; el 4 y el 5 se comportan igual. **Perder el haz paralelo y meter un cuarto
detrás no mueve la medición.** Esa es la justificación para incumplir R3 y R4,
y ahora tiene número en vez de argumento.

## Lo que destapa, en orden de gravedad

**1. La pipeline no puede procesar la vista de costado.**
`stereo_processor.py:1388` calcula `disp = x_left - x_right`, disparidad
horizontal. En la vista de costado el par va apilado verticalmente, porque con
la base paralela al cable el emparejamiento queda indeterminado, así que la
disparidad real está en Y. El matching devuelve 1389 matches con orientación
limpia y rango válido, y `compute_wire_metrics` los descarta todos por
`disp <= 0`. Es justo la vista donde el largo de arco significa algo y la que
mejor puntúa en todo lo demás.

**2. A3.1 falla en los tres casos de cable ondulado visto por el eje** y pasa
en los de costado y en los tensos. La máscara se parte donde el cable se
comprime contra el punto de fuga. Tres de ocho: el criterio pide 80 % de los
pares y el ensayo da 62.5 %.

**3. A3.5 falla en dos de los tres casos donde llegó a calcularse**, y esto es
después de arreglar el largo de arco, que por sí solo daba +144 %. Queda error
de otra fuente, todavía sin identificar.

**4. A3.6 pasa por cinco milésimas.** 0.975 contra un umbral de 0.97, con
geometría exacta, sin ruido de sensor y sin error de calibración. En TV2 ese
margen no existe. O se revisa el umbral, con su revisión fechada como manda el
capítulo 2, o A3.6 va a fallar por tolerancia y no por el cable.

## Lo que el ensayo no puede responder

Sigue valiendo lo de arriba: sin ruido de sensor, sin luz parásita, con
geometría exacta en vez de calibrada. **Un criterio que falla aquí va a fallar
en TV2. Uno que pasa aquí puede fallar igual allá.**
