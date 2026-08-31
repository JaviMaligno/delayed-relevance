# Bloque 1 — réplica de SKILL.state y experimento del contrato de merge

**Modelo:** Claude Haiku 4.5 vía Microsoft Foundry (`ai-gonvarri-foundry`).
**Protocolo:** 5 seeds por celda, media ± desviación típica muestral, tope de salida 600,
razonamiento limitado a 60 palabras por instrucción. Sin `temperature`: el SDK `anthropic`
1.x la ha eliminado, así que la reproducibilidad es estadística (ver §Limitaciones).

---

## 1. Réplica de la Tabla 1

Entorno Warehouse reimplementado desde la descripción de su §4.1 — SkillExecBench no tiene
código público. Se iguala la **densidad de contexto**, no el contenido literal de sus eventos.

| runtime | T=10 | T=25 | T=50 | ellos T=50 |
|---|---|---|---|---|
| ReAct (historia completa) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.88 |
| Memory (resumen en prosa) | 1.00 ±0.00 | 0.96 ±0.06 | **0.75 ±0.16** | 0.93 |
| Stateful (estado + historia) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.94 |
| SKILL.state (solo estado) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.96 |

Prompt medio por invocación, y ratio contra el suyo:

| runtime | T=10 | T=25 | T=50 |
|---|---|---|---|
| ReAct | 4.596 (1.41x) | 9.124 (1.51x) | 16.437 (1.38x) |
| Memory | 4.584 (1.39x) | 5.675 (0.89x) | 6.085 (0.80x) |
| Stateful | 4.858 (1.42x) | 9.514 (1.62x) | 17.524 (1.51x) |
| SKILL.state | 2.136 (1.20x) | 2.139 (1.23x) | **2.157 (1.22x)** |

### Qué se reproduce y qué no

**La mitad de coste se reproduce, y con claridad.** El prompt de SKILL.state es plano —
2.136 → 2.139 → 2.157 — mientras el de ReAct crece 4.596 → 9.124 → 16.437. O(1) frente a
O(T), tal como afirman.

**La mitad de precisión no se reproduce.** Con historia completa, prompts de 16k y 172
eventos accionables, el modelo no comete ni un error. No es por falta de presión de
contexto: vamos un 38% por encima de su densidad a T=50.

**El único brazo que se degrada es el que resume en prosa**, y se degrada más que en el
paper: 0.75 frente a 0.93.

**La lectura que sí se sostiene:** SKILL.state iguala a la historia completa con la octava
parte del contexto — 2.157 tokens frente a 16.437, sin perder un punto. Comprimir a estado
estructurado resulta **sin pérdida** en esta tarea; comprimir a prosa pierde un 25%. Su
tesis se sostiene como afirmación de **eficiencia**, no de capacidad: con este modelo la
historia completa no se degrada, así que el estado explícito no rescata nada — consigue lo
mismo ocho veces más barato.

### Control de dificultad

La tarea no es trivial, y el control también marca su límite:

- 69–74% de los eventos son accionables; el score se juega sobre 172 eventos reales a T=50.
- El **70%** de los `Store` reutilizan un hueco liberado por un envío anterior, así que hay
  que llevar la cuenta de ocupación de verdad.
- **Pero el hueco reutilizado está a 1,9 posiciones del tope de media (máx. 7).** La
  información que hace falta vive en los últimos pasos: el entorno tiene **memoria de corto
  alcance** por construcción.

De ahí la consecuencia de diseño: alargar el horizonte añade pasos pero no aleja la
información de su uso. Para reproducir la degradación de la historia hay que separar
**información y uso**, que es la variable `k` de la sonda A.

---

## 2. El contrato del merge (experimento propio)

El paper atribuye el 68% de los fallos en modelos abiertos a *premature state overwrite /
deletion* (§5.7). Su fórmula `Σ_{t+1} = Σ_t ⊕ ΔΣ_t` no fija la profundidad del operador, y
su plantilla del Apéndice A.4 no declara su semántica al modelo.

Diseño 2×2, SKILL.state a T=50, 5 seeds. **Lo único que varía es el runtime**: mismo modelo,
mismo entorno, misma tarea, mismas seeds.

| | contrato declarado | sin declarar | efecto de declarar |
|---|---|---|---|
| **merge profundo** | **1.00 ±0.00** | 0.90 ±0.16 | +0.10 |
| **merge superficial** | 0.99 ±0.01 | **0.73 ±0.11** | **+0.27** |

**Interacción: +0.17.**

- **No declarar el contrato duele siempre**, pero cuánto depende de si el runtime perdona.
- Con **merge profundo**, el modelo que asume mal —enviar solo la sub-clave cambiada— acierta
  igual, porque el runtime hace lo que él esperaba. Pierde 0.10, casi todo varianza.
- Con **merge superficial**, esa misma suposición destruye el estado: 0.73.
- **La celda correcta es la única con desviación cero.** Las otras tres van de ±0.11 a ±0.16:
  episodios que salen bien y episodios que se rompen según lo que el modelo adivine. La
  configuración correcta no solo puntúa más, puntúa de forma fiable — que para un runtime de
  producción importa más que la media.

### Afirmación

> El modo de fallo dominante que SKILL.state reporta es reproducible en un modelo capaz sin
> tocar el modelo, manipulando solo dos decisiones del runtime que el paper no especifica:
> la profundidad de su operador de merge y si su contrato se documenta al modelo.

No dice que su taxonomía sea falsa. Dice que existe una explicación alternativa que su
diseño no descarta, y que un experimento de cuatro celdas la distingue.

**Recomendación accionable para quien implemente esto:** documenta la semántica de tu
operador de merge en el prompt. Es una línea, y vale 0.27 de precisión y toda la varianza.

---

## 3. Limitaciones declaradas

- **Reimplementación a ciegas.** SkillExecBench no tiene código público. Cualquier
  discrepancia con sus números es indistinguible de un error nuestro.
- **Densidad por encima de la suya**, entre 1,2x y 1,5x, y de forma razonablemente uniforme
  entre brazos tras la corrección de brevedad. El ratio va en la tabla, no en una nota.
- **Su columna de tokens totales es internamente inconsistente**: horizonte × prompt medio
  excede su total por ~3,5x en todos los horizontes, así que solo el prompt medio es
  comparable directamente.
- **Sin `temperature`**: eliminada del SDK, no disponible en ningún modelo. La
  reproducibilidad es estadística, no bit a bit.
- **Un solo modelo y un solo entorno.** Haiku 4.5 y Warehouse. El segundo modelo y el resto
  de sus entornos quedan pendientes.
- **Memoria de corto alcance** del entorno, cuantificada arriba. Es la limitación que motiva
  la sonda A.

## 4. Artefactos encontrados y corregidos durante la calibración

Todos tenían la misma firma —un parámetro del corredor corrompiendo la métrica de un brazo—
y por eso el repositorio incluye instrumentación para cazarlos:

1. **Merge superficial sobre esquema anidado** fabricaba el borrado prematuro.
2. **Entorno 3–4x más ligero** que el suyo: el brazo de historia nunca sufría.
3. **Tope de salida a 2.048**: coste y densidad disparados (6x sus tokens en ReAct).
4. **Truncamiento del razonamiento**: cortaba la línea `Action:` y penalizaba a ReAct
   (0.82 frente a 1.00 en las seeds afectadas).
5. **Resumidor de Memory sin presupuesto propio**: resúmenes cortados a media frase.

Herramientas que quedan en el repositorio para que el siguiente salga gratis:
`measure_density.py` (mide el prompt sin llamar a la API), contador de truncamientos por
episodio, y checkpoint por episodio.
