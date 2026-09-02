# Réplica de SKILL.state — resultados

**Modelo:** Claude Haiku 4.5 vía Microsoft Foundry (`ai-gonvarri-foundry`); Sonnet 5 parcial.
**Protocolo:** tope de salida 600, razonamiento limitado a 60 palabras por instrucción. Sin
`temperature`: el SDK `anthropic` 1.x la ha eliminado, así que la reproducibilidad es
estadística (§6). Entorno reimplementado desde la descripción de su §4.1 — SkillExecBench no
tiene código público; se iguala la **densidad de contexto**, no el contenido literal.

## 0. El suelo de ruido, medido

Antes de leer ninguna tabla. Misma seed, mismo prompt byte a byte, **8 repeticiones**
(Sonnet, oráculo, `k=40`):

```
seed 0: 4/8 =  50%   OK X OK X OK X OK X
seed 1: 6/8 =  75%   X OK OK OK OK OK X OK
seed 2: 8/8 = 100%   OK OK OK OK OK OK OK OK
```

**La seed 0 alterna acierto y fallo ocho veces seguidas.** Los intervalos de las tres se
solapan (22–78%, 41–93%, 68–100%): con ocho repeticiones no se distingue la seed 0 de la
seed 2. La dispersión entre seeds es de **50 puntos**.

Tres consecuencias que gobiernan todo lo demás:

1. **Una seed es una tirada, no una réplica.** `n=20 seeds` nunca fue `n=20 mediciones` de la
   condición: mezcla varianza de escenario con varianza de muestreo sin separarlas.
2. **El suelo de ruido es de decenas de puntos.** Cualquier diferencia menor de ~30 pp medida
   con seeds distintas es indistinguible de ruido.
3. **Explica las tres anomalías** que se persiguieron con hipótesis mecánicas: el 1/3 que fue
   82%, el 0% que fue 15%, y el 70% contra 95% entre dos corredores con prompts idénticos.
   Ninguna necesitaba explicación.

**Sobrevive** lo que separa decenas de puntos con muestra grande, o lo que no es una tasa de
acierto: los tres hallazgos centrales (§2, §3, §4). **Se cae** la capa de matices construida
encima, marcada con ⚠️.

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

⚠️ **Estos números son scores globales, no tasas de acierto de un solo paso**, así que no
sufren el ruido de §0 con la misma severidad: promedian 172 eventos por episodio y sus
desviaciones típicas (±0.00 a ±0.16) son mucho menores que el 50% de dispersión del acierto
puntual. Aun así, con 5 seeds por celda **el efecto principal (+0.27) es sólido y la
interacción (+0.17) es indicativa**: separar 0.90 de 1.00 pide más muestra.

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

⚠️ **Esta curva no distingue efecto de ruido.** Cada celda son 5 seeds distintas, es decir 5
tiradas de un proceso cuyo suelo de ruido es de decenas de puntos (§0). Las diferencias entre
`k` contiguos (60% → 20% → 40% → 20%) están dentro del ruido; lo único legible es el contraste
entre columnas con muestra grande. Se conserva por transparencia, no como resultado.

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
hecho a la misma distancia, acierta 100% en vez de 15% por tener un campo donde ponerlo. Son 85
puntos con n=20 y n=22: muy por encima del suelo de ruido, y el hallazgo aguanta.

⚠️ La escotilla (60%) **no se distingue del oráculo (100%) ni del resto** con esta muestra: los
20 puntos que las separan caben en el ruido. Lo que sí se sostiene es que la escotilla está muy
por encima del 15% sin campo. Es decir: **dar sitio funciona; cuánto importa el nombre del
campo, no lo sabemos**.

**Σ permanece acotado en las tres condiciones** (~110 → ~350 caracteres, el mismo 3x para todo
`k`). La escotilla no compra robustez a cambio del O(1): sigue siendo O(1) con una constante
mayor, despreciable frente a los 16.437 tokens de la historia completa.

**ReAct a `k=40` acierta el 0%** con el boletín literalmente presente en el contexto. Conservar
no es recordar: lo que salva al agente no es haber guardado el dato, es haber decidido en el
momento de verlo que merecía guardarse.

### Medición pareada, con el protocolo corregido

Sonnet 5, `k=40`, **misma seed × 8 repeticiones** — el único bloque del documento medido con
el protocolo de §7. Cada seed es su propio control: lo único que cambia entre columnas es
dónde vive el hecho.

| seed | sin campo | oráculo (en Σ) | recordatorio (en obs) |
|---|---|---|---|
| 0 | 3/8 = 38% | 4/8 = 50% | 5/8 = 62% |
| 1 | **0/8 = 0%** | 6/8 = 75% | 7/8 = 88% |
| 2 | **0/8 = 0%** | 8/8 = **100%** | 8/8 = **100%** |
| **agregado** | **3/24 = 12%** | **18/24 = 75%** | **20/24 = 83%** |
| IC95 Wilson | **4–31%** | 55–88% | 64–93% |

**El intervalo de "sin campo" no toca a los otros dos.** 63 y 71 puntos de diferencia, muy por
encima del suelo de ruido. Es la afirmación central del proyecto, y es la única medida en
diseño pareado.

Dos lecturas que solo el pareado hace visibles:

- **Oráculo y recordatorio son equivalentes** (75% vs 83%, intervalos solapados). Repetir el
  hecho en cada observación hace lo mismo que un campo de esquema con el nombre correcto —
  sin runtime de estado, sin esquema que acertar de antemano, sin operador de merge. **No
  importa dónde pongas el hecho; importa que esté en algún sitio.**
- **El efecto es absoluto donde el escenario lo permite y nulo donde no.** Seeds 1 y 2: de 0/8
  a 8/8. Seed 0: las tres condiciones entre 38% y 62%, indistinguibles. Dar sitio al hecho no
  arregla un escenario duro por otros motivos; **rescata los que fallaban solo por esto**.

### Réplica cruzada de modelo

Celda del oráculo a `k=40`, **muestras igualadas**:

| modelo | acierto | IC95 (Wilson) |
|---|---|---|
| Haiku 4.5 | **22/22 = 100%** | 85–100% |
| Sonnet 5 | **18/22 = 82%** | 66–98% |

```
Haiku    OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK OK
Sonnet   X  X  OK OK OK OK OK OK OK X  OK OK OK OK OK OK OK OK OK OK OK X
```

⚠️ **Esta comparación está retirada a la espera de la medición de ruido.** Se declaró
defendible porque los intervalos no se solapaban, pero esos intervalos asumen que cada seed es
una réplica independiente. No lo es: la celda de Sonnet remedida dio 70%, 70% y 95% con
prompts idénticos. El 82% es una de esas tiradas, y el 100% de Haiku podría serlo también.

Lo que **sí** se sostiene es que el efecto replica en las dos familias: sin campo 15% y 0%,
con campo 100% y 82%. La dirección y el orden de magnitud son los mismos. Lo que **no** puede
afirmarse todavía es que los techos difieran.

**Dos lecturas, y ambas importan:**

- **El efecto replica en las dos familias.** Sin campo: 15% (Haiku) y 0% (Sonnet). Con campo:
  100% y 82%. La dirección y la magnitud son las mismas, así que el hallazgo es sobre **diseño
  de esquemas**, no sobre un modelo concreto.
- **El techo sí depende del modelo.** Haiku aprovecha el campo perfectamente; Sonnet falla una
  de cada cinco veces con el mismo campo disponible. La recomendación se matiza: dar sitio en
  el esquema ayuda siempre, pero no garantiza por sí solo el acierto.

**Hipótesis sin comprobar** para la diferencia de techo: Sonnet emite parches mínimos —solo la
clave que cambia— mientras Haiku tiende a reemitir el estado entero, lo que le da
auto-corrección. Con merge profundo ambas estrategias son válidas, pero la de Sonnet no
re-sincroniza nunca. **No está medido**: los checkpoints guardan score, acierto y tamaño de Σ,
no los parches, así que comprobarlo exige re-correr con registro de parches.

Nota de método: esta celda empezó en **1/3** con n=3 y llegó a 82% con n=22. Se llegó a
formular una explicación mecánica para aquel 1/3 antes de comprobar que hubiera algo que
explicar. **Antes de explicar por qué dos condiciones difieren, comprobar que difieren.**

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
- **Un solo entorno.** Warehouse. La réplica cruzada de modelo está cerrada en la celda del
  oráculo (n=22 en ambos) pero no en el resto de celdas de la sonda A ni en el bloque 1.
- **Memoria de corto alcance del entorno**, cuantificada en §1. Es la limitación que motiva la
  sonda A y la que hace que subir el horizonte no aporte.
- **Las seeds no son réplicas.** Es la limitación más seria y se descubrió tarde. Con el
  prompt fijo, la única fuente de variación entre episodios de la misma seed es el muestreo
  del modelo, y es grande: 70%, 70% y 95% en tres medidas de la misma celda. Comparar
  condiciones con seeds distintas mezcla efecto y ruido. Las diferencias grandes sobreviven;
  las ajustadas no.
- **n pequeño en varias celdas.** Un 0% y un 100% con n=5 son la misma afirmación: "no lo he
  medido suficiente" — el 0% inicial de §4 resultó ser 15% con n=20, y el 1/3 de Sonnet
  resultó ser 82% con n=22.
- **Intervalos:** los normales colapsan a cero con p=0 o p=1 y produjeron un IC de 100–100%,
  imposible. Se usa Wilson.

## 7. Cambio de protocolo obligado

El spec fijaba **5 seeds por celda**. Eso no mide lo que dice medir: cada seed es una tirada.
El protocolo para todo lo que venga es **pocas seeds y muchas repeticiones por seed**, con el
acierto agregado sobre repeticiones y la dispersión entre seeds reportada aparte. Es más caro
por celda y es la única forma de separar efecto de ruido.

Regla operativa: **no afirmar una diferencia menor de ~30 puntos porcentuales** medida con
seeds distintas sin repetir.

## 8. Pendiente

- Sonda A en Sonnet 5 en el resto de celdas (sin campo y escotilla) con muestra suficiente.
- Por qué Sonnet no alcanza el techo de Haiku con el mismo campo: re-correr registrando los
  parches para contrastar la hipótesis del estilo de parcheo.
- Sonda C: invalidación retroactiva e irrecuperabilidad.
- Segundo entorno (Software Repository) para separar hallazgo de dominio.
- Coste efectivo medido también en la sonda A.
