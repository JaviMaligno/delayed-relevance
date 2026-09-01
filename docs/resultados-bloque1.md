# Réplica de SKILL.state — resultados

**Modelo:** Claude Haiku 4.5 vía Microsoft Foundry (`ai-gonvarri-foundry`); Sonnet 5 parcial.
**Protocolo:** tope de salida 600, razonamiento limitado a 60 palabras por instrucción. Sin
`temperature`: el SDK `anthropic` 1.x la ha eliminado, así que la reproducibilidad es
estadística (§6). Entorno reimplementado desde la descripción de su §4.1 — SkillExecBench no
tiene código público; se iguala la **densidad de contexto**, no el contenido literal.

**Tres hallazgos independientes**, cada uno con su experimento y ninguno derivado de los otros:

1. La ventaja de coste del método es **1,4x, no 7,5x**, una vez se paga la factura real (§3).
2. El modo de fallo que el paper atribuye al modelo se reproduce **manipulando solo el
   runtime**, sin tocar el modelo (§2).
3. Lo que salva a un agente no es retener el dato sino **tener dónde ponerlo**: 15% → 100% de
   acierto por añadir un campo al esquema (§4).

---

## 1. Réplica de la Tabla 1

| runtime | T=10 | T=25 | T=50 | ellos T=50 |
|---|---|---|---|---|
| ReAct (historia completa) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.88 |
| Memory (resumen en prosa) | 1.00 ±0.00 | 0.96 ±0.06 | **0.75 ±0.16** | 0.93 |
| Stateful (estado + historia) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.94 |
| SKILL.state (solo estado) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.96 |

Prompt medio, y ratio contra el suyo:

| runtime | T=10 | T=25 | T=50 |
|---|---|---|---|
| ReAct | 4.596 (1,41x) | 9.124 (1,51x) | 16.437 (1,38x) |
| SKILL.state | 2.136 (1,20x) | 2.139 (1,23x) | **2.157 (1,22x)** |

**La mitad de coste se reproduce; la de precisión no.** El prompt de SKILL.state es plano —
2.136 → 2.157 — mientras el de ReAct crece a 16.437: O(1) frente a O(T), tal como afirman.
Pero con historia completa, prompts de 16k y 172 eventos accionables, el modelo no comete ni
un error, y no por falta de presión de contexto: vamos un 38% por encima de su densidad. El
único brazo que se degrada es el que resume en prosa, y más que en el paper.

**Control de dificultad.** El 69–74% de los eventos son accionables y el 70% de los `Store`
reutilizan un hueco liberado, así que hay que llevar la cuenta de verdad. Pero **el hueco está
a 1,9 posiciones del tope de media (máx. 7)**: el entorno tiene memoria de corto alcance por
construcción. Alargar el horizonte añade pasos sin alejar la información de su uso — de ahí
que la variable que mueve la aguja sea `k` (§4) y no `T`.

---

## 2. El contrato del merge

El paper atribuye el 68% de los fallos en modelos abiertos a *premature state overwrite*
(§5.7). Su fórmula `Σ_{t+1} = Σ_t ⊕ ΔΣ_t` no fija la profundidad del operador, y su plantilla
del Apéndice A.4 no declara su semántica al modelo. Diseño 2×2, SKILL.state a T=50, 5 seeds;
**lo único que varía es el runtime**.

| | contrato declarado | sin declarar | efecto de declarar |
|---|---|---|---|
| **merge profundo** | **1.00 ±0.00** | 0.90 ±0.16 | +0.10 |
| **merge superficial** | 0.99 ±0.01 | **0.73 ±0.11** | **+0.27** |

**Interacción: +0.17.** No declarar el contrato duele siempre, pero cuánto depende de si el
runtime perdona. Con merge profundo el modelo que asume mal acierta igual; con merge
superficial esa misma suposición destruye el estado. **La celda correcta es la única con
desviación cero** — las otras tres van de ±0.11 a ±0.16, es decir, episodios que salen bien y
episodios que se rompen según lo que el modelo adivine.

> El modo de fallo dominante que reporta SKILL.state es reproducible en un modelo capaz sin
> tocar el modelo, manipulando solo dos decisiones del runtime que el paper no especifica.

**Recomendación:** documenta la semántica de tu operador de merge en el prompt. Es una línea,
y vale 0.27 de precisión y toda la varianza.

---

## 3. Coste efectivo: la ventaja se evapora con caché

El paper compara **tokens**; quien paga la factura compara **dinero**. Un transcript
append-only cachea casi entero y se cobra a 0,1x; un bloque de estado que muta invalida el
prefijo y se cobra completo. T=50, 3 seeds, caché activo:

| runtime | score | bruto | **efectivo** | ahorro por caché |
|---|---|---|---|---|
| ReAct | 1.00 | 826k | **152k** | **82%** |
| Stateful | 1.00 | 873k | **873k** | 0% |
| Memory | 0.87 | 313k | 313k | 0% |
| SKILL.state | 1.00 | **109k** | 109k | 0% |

**La ventaja de SKILL.state pasa de 7,54x en tokens brutos a 1,39x en coste efectivo.**

Y los dos órdenes no coinciden:

- **Por tokens:** SKILL.state < Memory < ReAct < Stateful
- **Por dinero:** SKILL.state < **ReAct** < Memory < Stateful

Tres consecuencias:

**Comprimir contexto y cachear contexto están en conflicto.** Todo método que comprime
reescribe el prefijo, y reescribir el prefijo mata la caché. Resumen, estado explícito y
estado+historia: los tres ahorran 0%. La historia append-only es la única que cachea,
precisamente porque no toca lo ya enviado.

**El orden del prompt es una variable de coste de primer orden.** ReAct y Stateful envían casi
el mismo contenido; ReAct pone la historia primero y ahorra 82%, Stateful la pone tras un
bloque de estado mutante y ahorra 0%. **El mismo contenido, en distinto orden, cuesta 5,7 veces
más**, y su plantilla del Apéndice A.3 lo coloca en el peor sitio.

**Reconcilia una anomalía de su tabla.** Su columna de totales queda ~3,5x por debajo de
horizonte × prompt medio en todos los horizontes. Con caché deja de ser inconsistente: encaja
si sus totales son facturados y su prompt medio bruto.

---

## 4. Sonda A: relevancia diferida

En el paso `t` el entorno anuncia una cuarentena de estantería; en `t+k` esa estantería es la
libre más baja y la acción correcta es saltársela. **El paso dependiente y la estantería son
idénticos para todo `k`**: solo se mueve la distancia entre la información y su uso.

Acierto en el paso dependiente, 5 seeds por celda:

| `k` | ReAct (historia) | SKILL.state | + escotilla `notes` | + esquema oráculo |
|---|---|---|---|---|
| 1 | 80% | 60% | 80% | 100% |
| 5 | · | 20% | 80% | 100% |
| 10 | · | 40% | 80% | 100% |
| 20 | · | 20% | 60% | 100% |
| 40 | **0%** | **0%** | **60%** | **100%** |

Celda decisiva (`k=40`) con muestra ampliada:

| condición | n | acierto | IC95 | score global | Σ final |
|---|---|---|---|---|---|
| sin campo | 20 | **15%** | ±16 pp | 0.898 | 173 |
| escotilla `notes` | 15 | **60%** | ±25 pp | 0.946 | 404 |
| oráculo | 11 | **100%** | ±0 pp | 0.974 | 265 |

**El fallo no es de atención ni de distancia: es de representación.** El mismo modelo, el mismo
hecho a la misma distancia, acierta 100% en vez de 15% por tener un campo donde ponerlo. Y un
campo de texto libre, **sin decir para qué sirve**, recupera la mayor parte del efecto: la
diferencia entre 60% y 100% es lo que vale saber de antemano qué importa.

**Σ permanece acotado en las tres condiciones** (~110 → ~350 caracteres, el mismo 3x para todo
`k`). La escotilla no compra robustez a cambio del O(1): sigue siendo O(1) con una constante
mayor, despreciable frente a los 16.437 tokens de la historia completa.

**ReAct a `k=40` acierta el 0%** con el boletín literalmente presente en el contexto. Conservar
no es recordar: lo que salva al agente no es haber guardado el dato, es haber decidido en el
momento de verlo que merecía guardarse.

**Réplica cruzada, parcial y no concluyente.** Sonnet 5 sin campo: 0/3, coherente con el 15% de
Haiku. Con oráculo: **1/3**, frente al 100% de Haiku sobre 11 episodios. Esa divergencia no
está explicada y n=3 no da para interpretarla.

---

## 5. Artefactos encontrados, y el patrón que forman

Siete, todos con la misma firma: **un contrato implícito entre runtime y modelo**. El runtime
asumía algo que nunca declaró, y el resultado dependía de si el modelo acertaba la suposición.

| # | Artefacto | Coste si pasa desapercibido |
|---|---|---|
| 1 | Merge superficial sobre esquema anidado | Fabrica el borrado prematuro del paper |
| 2 | Entorno 3–4x más ligero que el suyo | El brazo de historia nunca sufre |
| 3 | Tope de salida a 2.048 | 6x sus tokens; coste y densidad disparados |
| 4 | Truncamiento del razonamiento | Corta la línea `Action:`; 0.82 vs 1.00 en ReAct |
| 5 | Resumidor de Memory sin presupuesto propio | Resúmenes cortados a media frase |
| 6 | Forma del JSON del parche sin mostrar | Sonnet 8/12 parches inválidos; "Sonnet es peor" |
| 7 | Caché: fórmula, bloques y edición no aplicada | Ahorro del 624%, o caché que encarece |

Los tres primeros costaron rejillas enteras; los demás los cazó la instrumentación en minutos.

**Encontrar el mismo fenómeno siete veces por siete caminos independientes, mientras intentabas
medir otra cosa, es la señal de que es la cosa.** El paper trata el runtime como infraestructura
neutra —un operador ⊕, un formato de parche, un esquema, un orden de prompt— cuando cada una de
esas decisiones no documentadas vale entre 20 y 90 puntos, más que la diferencia entre los
métodos que compara.

**Herramientas que quedan en el repositorio** para que el octavo salga gratis:
`measure_density.py` (mide el prompt sin llamar a la API), `measure_latency.py`, contador de
truncamientos por episodio, checkpoint por episodio, y contabilidad de caché de punta a punta.

---

## 6. Limitaciones declaradas

- **Reimplementación a ciegas.** Sin código público de SkillExecBench, cualquier discrepancia
  con sus números es indistinguible de un error nuestro.
- **Densidad por encima de la suya**, 1,2–1,5x, razonablemente uniforme entre brazos tras la
  corrección de brevedad. El ratio va en la tabla, no en una nota.
- **Sin `temperature`**: eliminada del SDK. Reproducibilidad estadística, no bit a bit. Aun
  así, repetir dos seeds tras un cambio de prompt dio scores **idénticos al tercer decimal**:
  el fallo medido es estructural, no un tropiezo de muestreo.
- **Un entorno y casi un solo modelo.** Warehouse, Haiku 4.5, con Sonnet 5 solo parcial y
  divergente en una celda.
- **Memoria de corto alcance del entorno**, cuantificada en §1. Es la limitación que motiva la
  sonda A y la que hace que subir el horizonte no aporte.
- **n pequeño en varias celdas.** Los IC95 están en la tabla. Un 0% y un 100% con n=5 son la
  misma afirmación: "no lo he medido suficiente" — el 0% inicial de §4 resultó ser 15% con n=20.

## 7. Pendiente

- Sonda A en Sonnet 5 con muestra suficiente; la divergencia del oráculo (1/3) sin explicar.
- Sonda C: invalidación retroactiva e irrecuperabilidad.
- Segundo entorno (Software Repository) para separar hallazgo de dominio.
- Coste efectivo medido también en la sonda A.
