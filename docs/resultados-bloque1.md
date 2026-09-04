# Réplica de SKILL.state — resultados

**Modelos:** Claude Haiku 4.5 vía Microsoft Foundry (`ai-gonvarri-foundry`) y Claude Sonnet 5.
Cruzados en tres ejes (celda del oráculo, sonda C y entorno Repo); en el resto, un solo modelo.
**Entornos:** Warehouse y Software Repository, dos de los cuatro del paper.
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

**Lo que decide qué sobrevive no es el cuidado con que se midió, sino el TIPO de métrica:**

| métrica | ruido de muestreo | ejemplo | veredicto |
|---|---|---|---|
| Acierto de **un solo paso** | brutal (~50 pp) | sonda A, el 0% de ReAct | 4 afirmaciones caídas |
| **Promedio sobre ~170 eventos** | despreciable | Tabla 1, 2×2 del merge | intacto |
| **Contabilidad de tokens** | ninguno | coste efectivo (§3) | intacto |

Comprobado: la celda de la Tabla 1 remedida con 3 seeds × 6 repeticiones da **18/18 exactos,
desviación cero**. El promediado sobre 172 eventos accionables amortigua el ruido casi por
completo. Medir un **evento único** con un LLM es intrínsecamente ruidoso, y todo lo que se
cayó en este proyecto era de esa clase.

**Tres hallazgos independientes**, cada uno con su experimento y ninguno derivado de los otros:

1. La ventaja de coste del método es **1,4x, no 7,5x**, una vez se paga la factura real (§3).
2. El modo de fallo que el paper atribuye al modelo se reproduce **manipulando solo el
   runtime**, sin tocar el modelo (§2).
3. Lo que salva a un agente no es retener el dato sino **tenerlo delante en el momento de
   usarlo**. Repetir el hecho vigente en cada observación lleva a Haiku de **0/24 a 24/24** y a
   Sonnet de 12% a 83% (§4). Un campo de esquema funciona solo si **nombra qué guardar**; uno
   genérico se queda en 21%, indistinguible de no tener ninguno.

---

## 1. Réplica de la Tabla 1

### Sus condiciones, verificadas contra el paper

Antes de comparar nada, lo que su Tabla 1 dice literalmente (comprobado en el HTML de arXiv,
v3):

- **Modelo: Gemini-3-Flash.** El resto del paper evalúa además Gemma-4-31B-it y Qwen-3-8B-it.
  Ninguno de los tres es de la familia que usamos aquí. Es una diferencia deliberada —ver qué
  hace el efecto en otra familia es parte del objetivo— pero obliga a que **la primera
  explicación candidata de cualquier discrepancia sea el modelo, no el método**.
- **Horizontes: T ∈ {10, 25, 50, 100, 200}.** Su degradación de ReAct es
  0,90 → 0,92 → 0,88 → 0,84 → **0,74**. El efecto que anuncian es de escala, y **el nuestro se
  detuvo en T=50, la cuarta parte de su rango**. Corriendo T=100 y T=200 para cerrarlo.
- **Su columna «Avg Prompt» está en CARACTERES**, no en tokens. Nuestro instrumento ya
  comparaba en la misma unidad (`measure_density.py` guarda sus cifras y convierte con
  `CHARS_PER_TOKEN = 3.48`), así que **los ratios de abajo son correctos**; lo que estaba mal
  era llamarlos tokens en la prosa de este documento. Corregido.
- **Su métrica:** «Score = Successful Actions / Total Actionable Events», la misma que usamos.
- **O(T²)** es su afirmación sobre la acumulación de contexto, no O(T).

### Nuestros números

| runtime | T=10 | T=25 | T=50 | ellos T=50 (Gemini-3-Flash) |
|---|---|---|---|---|
| ReAct (historia completa) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.88 ±0.04 |
| Memory (resumen en prosa) | 1.00 ±0.00 | 0.96 ±0.06 | **0.75 ±0.16** | 0.93 ±0.03 |
| Stateful (estado + historia) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.94 ±0.00 |
| SKILL.state (solo estado) | 1.00 ±0.00 | 1.00 ±0.00 | **1.00 ±0.00** | 0.96 ±0.01 |

Prompt medio **en caracteres**, y ratio contra el suyo:

| runtime | T=10 | T=25 | T=50 | ellos T=50 |
|---|---|---|---|---|
| ReAct | 4.596 (1,41x) | 9.124 (1,51x) | 16.437 (1,38x) | 11.931 |
| SKILL.state | 2.136 (1,20x) | 2.139 (1,23x) | **2.157 (1,22x)** | 1.773 |

**La mitad de coste se reproduce.** El prompt de SKILL.state es plano —2.136 → 2.157— mientras
el de ReAct crece a 16.437: O(1) frente a O(T), tal como afirman, y a 1,2–1,4x de su densidad.

**La de precisión, no se reproduce EN ESTE RANGO.** Con historia completa, prompts de ~4.700
tokens y 172 eventos accionables, Haiku 4.5 no comete un error a T=50 donde Gemini-3-Flash
comete el 12%. El único brazo que se degrada es el que resume en prosa, y más que en el paper.
⚠️ **Afirmar más que eso exige T=100 y T=200**, que es donde su curva cae de verdad; hasta
tenerlos, la lectura correcta es «no aparece a T≤50 en Claude», no «no existe».

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

### Condición de validez del 0%, medida en la auditoría

Los tres brazos que comprimen llevan punto de corte de caché en su bloque de sistema, igual que
ReAct. Que aun así ahorren 0% tiene una causa concreta y medible: **hay un prefijo mínimo
cacheable, y la especificación de este entorno queda por debajo**.

**El umbral, medido y no supuesto** (`experiments/probe_cache_minimum.py`, búsqueda binaria
sobre Haiku 4.5, contando los tokens que reporta la propia API):

| prompt de sistema | ¿la segunda llamada lee de caché? |
|---|---|
| 2.224 tokens | no |
| 3.324 tokens | no |
| **3.984 tokens** | **no** |
| **4.116 tokens** | **sí** |
| 4.424 tokens | sí |

**El mínimo es 4.096 tokens exactos.** La especificación corta de Warehouse son 1.491, muy por
debajo: su bloque de sistema no cachea en ningún brazo. ReAct cachea porque su historia
acumulada empuja el prefijo por encima del mínimo, no porque su bloque de sistema sea distinto.

Eso convierte «los métodos que comprimen ahorran 0%» en una afirmación sobre la longitud de
NUESTRO prompt, no sobre el método — así que hay que medir el otro caso, que además es el que
se parece a un despliegue real.

### El caso del procedimiento largo

`Warehouse(long_spec=True)` añade a la especificación lo que un procedimiento operativo real
lleva y el nuestro no tenía: la referencia de los 112 campos que de verdad aparecen en los
eventos —agrupados, y diciendo de cada grupo si el procedimiento lo lee o no—, seis reglas de
excepción, y cinco ejemplos resueltos generados del propio simulador con una seed que no se usa
en ningún experimento. No es relleno: es contenido verdadero sobre este entorno.

Resultado: **5.243 tokens, verificado que cachea**. Con eso los cuatro brazos tienen prefijo
estático cacheable y la comparación de coste se puede hacer en las dos condiciones en vez de en
una sola. Corriendo.

Lo que ya se puede afirmar sin ese dato:

- **La dirección no depende de la longitud.** Un prefijo que muta invalida la caché desde el
  punto en que muta: es aritmética del mecanismo.
- **La magnitud sí.** El 1,39x pertenece a la condición «especificación por debajo del
  mínimo». El caso largo es una medida distinta, no una corrección de esta.
- **El 0% de Stateful es además de construcción**: su implementación no manda prefijo
  cacheable, coherente con que su bloque de estado va delante de la historia. Es una
  demostración del mecanismo con la plantilla del Apéndice A.3, no una medida de su código.

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

⚠️ **El 60% de la escotilla en esta tabla es ruido y quedó refutado.** Medido con
repeticiones sobre las mismas seeds da **21% (IC 9–40%)**, indistinguible de no tener campo.
Ver la medición pareada más abajo, que es la que vale.

**Σ permanece acotado en las tres condiciones** (~110 → ~350 caracteres, el mismo 3x para todo
`k`). La escotilla no compra robustez a cambio del O(1): sigue siendo O(1) con una constante
mayor, despreciable frente a los 16.437 tokens de la historia completa.

**ReAct con el boletín en el contexto: 2/12 = 17%** (IC 5–45%), medido con repeticiones. El
0% que aparecía con seeds sueltas era ruido — la cuarta afirmación de este documento que cae al
medirla bien.

Lo que **no** cambia es la conclusión: el intervalo de ReAct no se acerca al 86–100% del
recordatorio. **Conservar la historia entera y no conservar nada caen en el mismo grupo**
(17% y 0%); lo que separa es tener el hecho delante en el momento de usarlo.

| condición (Haiku, `k=40`) | acierto | IC95 |
|---|---|---|
| ReAct, historia completa | 2/12 = 17% | 5–45% |
| SKILL.state, sin campo | 0/24 = 0% | 0–14% |
| SKILL.state + recordatorio | **24/24 = 100%** | 86–100% |

### Medición pareada, con el protocolo corregido

Sonnet 5, `k=40`, **misma seed × 8 repeticiones** — el único bloque del documento medido con
el protocolo de §7. Cada seed es su propio control: lo único que cambia entre columnas es
dónde vive el hecho.

| seed | sin campo | campo libre `notes` | oráculo (en Σ) | recordatorio (en obs) |
|---|---|---|---|---|
| 0 | 3/8 = 38% | **0/8 = 0%** | 4/8 = 50% | 5/8 = 62% |
| 1 | 0/8 = 0% | 4/8 = 50% | 6/8 = 75% | 7/8 = 88% |
| 2 | 0/8 = 0% | 1/8 = 12% | 8/8 = **100%** | 8/8 = **100%** |
| **agregado** | **3/24 = 12%** | **5/24 = 21%** | **18/24 = 75%** | **20/24 = 83%** |
| IC95 Wilson | **4–31%** | **9–40%** | 55–88% | 64–93% |

Las condiciones se parten en **dos grupos que no se tocan**: {sin campo 12%, campo libre 21%}
frente a {oráculo 75%, recordatorio 83%}. Dentro de cada grupo los intervalos se solapan;
entre grupos, no.

**El campo genérico NO funciona.** 21% con intervalo 9–40%, solapado con el 12% de no tener
nada y sin llegar al 55% del oráculo. En la seed 0 saca **0/8, peor que sin campo (3/8)**: un
campo sin nombre útil puede distraer.

> ⚠️ Esta medición **retira** una recomendación anterior de este documento. Con una tirada por
> seed, el campo libre había dado 60% y se convirtió en el consejo práctico del proyecto
> ("deja una escotilla en tu esquema"). Medido con repeticiones, es falso.

Lo que queda en pie:

- **Dar sitio no basta: el sitio tiene que decir qué guardar.** El oráculo funciona porque el
  campo se llama `quarantined_shelves` y anticipa el hecho. Es decir, un runtime de estado
  explícito **solo protege contra lo que su diseñador ya previó** — la limitación L1 que el
  paper declara y no mide, ahora con número.
- **El recordatorio funciona sin exigir anticipación** (83%). El entorno emite el aviso y basta
  con no dejar de mostrarlo: no hay esquema que acertar. Es la única recomendación aplicable
  que sobrevive.
- **El efecto es absoluto donde el escenario lo permite y nulo donde no.** Seeds 1 y 2: de 0/8
  a 8/8. Seed 0: todas las condiciones entre 0% y 62%, indistinguibles.

### El recordatorio, en dos modelos

Misma seed × 8 repeticiones, diseño pareado, `k=40`:

| modelo | sin campo | recordatorio |
|---|---|---|
| **Haiku 4.5** | **0/24 = 0%** (IC 0–14%) | **24/24 = 100%** (IC 86–100%) |
| Sonnet 5 | 3/24 = 12% (IC 4–31%) | 20/24 = 83% (IC 64–93%) |

En Haiku el efecto es **absoluto**: 0/24 → 24/24, sin una sola excepción en ninguna dirección,
en las tres seeds. Los intervalos no se solapan en ninguno de los dos modelos.

**Es el resultado mejor medido del proyecto** y el único que cumple las tres condiciones a la
vez: protocolo pareado con repeticiones, réplica en dos familias de modelo, y una intervención
que **no exige anticipar nada**. El oráculo funciona pero requiere que el diseñador del esquema
ya hubiera previsto el hecho; el campo genérico no funciona; repetir lo vigente funciona sin
previsión.

### Repetir el hecho, o repetirlo destilado

El recordatorio no reinyecta el aviso: reinyecta **tres de sus quince campos**, hoistados al
principio de la observación. Eso mezclaba dos explicaciones —que el hecho esté disponible y que
esté destilado— y la objeción es evidente en cuanto se formula. Se separa con una tercera
condición, `reminder_raw`: **el aviso original entero**, verbatim, en la misma posición y bajo
la misma cabecera. Lo único que cambia es que la información llega sin destilar, 981 caracteres
en vez de 67. Ninguna de las dos añade instrucción: el aviso original ya dice
`do_not_store=true`.

Haiku 4.5, `k=40`, 3 seeds × 8 repeticiones, pareado:

| condición | acierto | IC95 Wilson | por seed |
|---|---|---|---|
| sin campo | **0/24 = 0%** | 0–14% | 0/8 · 0/8 · 0/8 |
| recordatorio **sin destilar** | **16/24 = 67%** | 47–82% | 5/8 · 4/8 · 7/8 |
| recordatorio **destilado** | **24/24 = 100%** | 86–100% | 8/8 · 8/8 · 8/8 |

**Los tres intervalos son disjuntos**, y en las tres seeds el destilado domina al crudo.

- **La disponibilidad explica dos tercios del efecto.** Repetir el aviso tal cual sube de 0% a
  67%: la mayor parte del fallo era, en efecto, que el hecho no estaba delante.
- **El tercio que falta es destilación, y es el que separa "casi siempre" de "siempre".** Con el
  mismo hecho presente en cada paso, enterrado entre catorce campos de metadatos, el agente lo
  pasa por alto una de cada tres veces.

> La recomendación práctica sobrevive y se vuelve más exigente: **no basta con reinyectar el
> registro, hay que reinyectar el campo.** Un sistema que repite el documento entero deja un
> tercio de los fallos sobre la mesa.

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

## 4.bis Sonda C: invalidación retroactiva

En el paso `t` el agente almacena en la estantería S. En `t+10` un aviso corrige que aquella
colocación nunca se completó y S está vacía. Desde ahí S es la libre más baja.

### El suelo, y por qué la primera medición era casi ciega

Un agente *perfecto pero sordo* —que ejecuta todo bien pero nunca aplica el aviso— define el
suelo. Calcularlo no cuesta una llamada, y cambia por completo qué seeds sirven:

| seed | suelo del sordo | pasos que dependen de la corrección |
|---|---|---|
| 0 | 0,931 | 2 |
| 1 | 0,893 | 3 |
| **2** | **1,000** | **0** |
| **4** | **0,522** | **11** |
| 6 | 0,846 | 4 |
| 10 | 0,759 | 7 |

Las tres seeds con las que se midió primero (0, 1, 2) aportaban **5 observaciones en total**, y
una de ellas ninguna. Las seeds 4, 10 y 6 aportan **22 por repetición**. Es la misma sonda, el
mismo coste por episodio y cuatro veces más señal: **elegir las seeds por rango medido, antes de
gastar, es gratis y decide el experimento.**

### El resultado, contado sobre pasos dependientes

La unidad no es el episodio ni la seed: es **cada paso posterior al aviso cuya acción correcta
cambia por haberlo aplicado**. Seeds 4, 10 y 6, 2 repeticiones, los dos modelos. Los episodios
con más de 3 respuestas truncadas de 50 se excluyen y se declaran: en ellos el brazo no llegó a
decidir.

| modelo | runtime | **aplica la corrección** | otros fallos | pasos sin acción | parches inválidos |
|---|---|---|---|---|---|
| Haiku 4.5 | ReAct | **3/44 — 6,8%** | 0 | 0 | 0 |
| Haiku 4.5 | SKILL.state | **44/44 — 100%** | 0 | 0 | 0 |
| Sonnet 5 | ReAct | **15/38 — 39,5%** | 5 | 1 | 0 |
| Sonnet 5 | SKILL.state | **49/49 — 100%** | 21 | 10 | 66 |

**El estado explícito no falla una sola vez: 93 de 93 pasos dependientes, en los dos modelos.**
La historia completa acierta 18 de 82.

Tres cosas que solo se ven contando así:

**1. El fallo de ReAct es de todo o nada por escenario.** En Haiku, `otra=0` en los seis
episodios: sus únicos errores son los pasos de la corrección, y los falla en bloque — 11 de 11,
7 de 7, 4 de 4. No es un agente que se despiste: es un agente impecable que **nunca actualizó
un hecho**. En Sonnet ocurre lo mismo pero de forma bimodal: en un episodio aplica los 11 y en
la repetición siguiente falla los 11.

**2. Más capacidad ayuda, y no basta.** Sonnet con historia pasa de 6,8% a 39,5%: el modelo más
capaz reconcilia la contradicción con bastante más frecuencia. Sigue perdiendo tres de cada
cinco.

**3. El estado explícito lo compra, y en Sonnet lo paga en otra moneda.** 66 parches fuera de
esquema y 10 pasos sin acción en 8 episodios, que se traducen en 21 fallos por otras causas.
En Haiku, cero. **El acierto sobre la corrección es del 100% en ambos; la fiabilidad del
corredor depende del modelo.** Es la interacción runtime × modelo del proyecto, y vive en el
modo de fallo del corredor, no en la tarea.

> Esto **contradice la limitación L2 del paper**, que predecía que el método fallaría cuando el
> objetivo dependiera de la procedencia. **Tener un único lugar donde vive la verdad es una
> ventaja cuando la verdad cambia**, y la ventaja replica en dos modelos.

**Mecanismo:** el estado explícito tiene un solo sitio que corregir, y corregirlo es la
operación que ya sabe hacer. La historia no borra nada: acumula el registro original y su
desmentido, y en cada paso posterior tiene que resolver la contradicción otra vez.

### ⚠️ La primera versión de esta sección era un artefacto

Daba Sonnet con SKILL.state 0,885 frente a ReAct 0,686, separación +0,199, presentada como
réplica. **El número se delataba solo**: +0,199 es mayor que el efecto máximo posible del aviso
en aquellas seeds (0,06 de media). Ningún resultado sobre la corrección puede superar el rango
que la corrección tiene.

Instrumentado, el brazo de ReAct en Sonnet perdía de 8 a 19 de 50 pasos por **truncamiento**
—cada respuesta cortada antes de la línea `Action:` es un paso sin acción, y cuenta como
error—. Y **subir el tope no lo arregla**: en la misma seed, 600 → 19 truncadas, 1.500 → 11,
4.000 → 18. Sonnet llena el presupuesto que le den. El truncamiento resultó además ser
dependiente del escenario: en las seeds 4 y 10 es de 0 o 1 de 50, en la 1 y la 6 es masivo.

> Un tope de salida fijo **penaliza al brazo cuyo prompt crece**, porque la respuesta se alarga
> con el transcript. Cualquier comparación entre un runtime append-only y uno de contexto
> acotado tiene que reportar la tasa de truncamiento por brazo, o la degradación que mida puede
> ser presupuestaria y no cognitiva. **El paper reporta degradación de ReAct al crecer T y no
> reporta truncamiento.**

## 4.ter ⚠️ Segundo entorno: retirado — no discrimina

Repo se construyó como control de dominio: mergear una PR invalida el CI de todas las demás
PRs abiertas de esa rama, sin evento que lo avise. Una versión anterior de este documento
reportaba una **inversión** entre modelos (Haiku +0,078 a favor del estado explícito, Sonnet
−0,124 a favor de la historia) y construía sobre ella la tesis de que la capa de estado
sustituye capacidad. **La auditoría la retira entera.** Tres motivos, cualquiera de ellos
suficiente:

**1. La dependencia está a 2 pasos, siempre.** La plantilla del generador coloca la solicitud
de merge portante exactamente dos posiciones después del merge que la invalida, en todos los
ciclos y todas las seeds. Un entorno pensado para medir relevancia diferida no tiene ninguna:
`k = 2`, fijo.

**2. El rango útil es de 15 puntos y las cuatro celdas lo agotan.** Solo 5 de 34 pasos
accionables son portantes; una política ciega —"siempre Merge" o "siempre RunTests"— saca
0,853. Instrumentando los episodios, **los cuatro brazos aciertan la regla**:

| celda | regla portante | resto de pasos | parches inválidos |
|---|---|---|---|
| Haiku · SKILL.state | 14/15 | 87/87 | 0 |
| Haiku · ReAct | 12/12 | 84/90 | — |
| Sonnet · SKILL.state | 12/13 | 84/89 | 2–14 por episodio |
| Sonnet · ReAct | todos | todos | — |

**3. Las diferencias de score venían de los pasos que no son la regla.** Haiku con ReAct
pierde 6 pasos rutinarios en la seed 2 (regla: 2 de 2). Sonnet con SKILL.state pierde 4 pasos
rutinarios en la seed 2, con 14 parches inválidos y 2 pasos sin acción. La supuesta inversión
comparaba el modo de fallo de un corredor contra el ruido de ejecución del otro.

Lo que Repo sí deja, y no es poco: **el corredor de estado explícito tiene un modo de fallo que
el de historia no tiene** —el parche rechazado por esquema, que consume los reintentos y deja
el paso sin acción— y su frecuencia depende del modelo (0 por episodio en Haiku, de 2 a 18 en
Sonnet). Eso es una propiedad real del método, medible y con consecuencias prácticas. Pero es
un resultado sobre la fiabilidad del corredor, no sobre la memoria del agente, y no autoriza
ninguna afirmación sobre qué runtime resuelve mejor la tarea.

**Para que Repo sirviera** habría que separar el merge portante de su invalidación por `k`
pasos configurable y elevar la fracción de pasos portantes muy por encima de 5 de 34. Está
pendiente y no entra en el artículo.

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
| 8 | Tope de salida calibrado sobre un modelo, aplicado a otro | 19 de 50 pasos sin acción en Sonnet; **produjo una réplica cruzada entera** |
| 9 | Entorno de control sin suelo medido ni rango útil | Cuatro celdas que aciertan la regla, leídas como una inversión entre modelos |

Los tres primeros costaron rejillas enteras; los demás los cazó la instrumentación en minutos.

**Los dos últimos aparecieron en la auditoría previa al artículo, no antes**, y los dos habían
producido un resultado que estaba escrito, con tablas e intervalos, listo para publicar. Es la
observación incómoda del proyecto: los artefactos no se manifiestan como errores, se manifiestan
como **hallazgos limpios**. El nº8 daba intervalos disjuntos; el nº9 daba una inversión de signo
con las dos separaciones significativas. Ninguno de los dos se detecta mirando la varianza.

Lo que sí los detecta, y es la parte transferible:

1. **Calcular el suelo antes que el efecto.** Un agente perfecto que ignore justo lo que quieres
   medir: si tu brazo malo saca exactamente eso, no es ruido. Si tu separación supera el rango
   entre suelo y techo, es imposible y hay un artefacto.
2. **Contar los pasos sin acción aparte de los pasos con acción incorrecta.** No son el mismo
   suceso y se arreglan de forma distinta.
3. **Descomponer el score por tipo de paso.** El promedio sobre 34 eventos esconde que solo 5
   probaban lo que decías probar.

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
- **Un entorno útil de los dos del paper.** SkillExecBench tiene dos entornos, no cuatro:
  Warehouse Management y Software Repository. Warehouse discrimina; nuestra versión de Repo se
  construyó como control y no discrimina (§4.ter), así que el proyecto tiene un solo entorno
  con resultados.
- **Familia de modelo distinta a la suya, a propósito.** Su Tabla 1 es Gemini-3-Flash y el
  resto del paper Gemma-4-31B-it y Qwen-3-8B-it; aquí se usan Claude Haiku 4.5 y Sonnet 5. Ver
  qué hace el efecto fuera de su familia es parte del objetivo, pero implica que **ninguna
  discrepancia con sus cifras puede atribuirse al método sin descartar antes el modelo**.
- **Rango de horizonte incompleto hasta que cierren T=100 y T=200.** Su curva de degradación
  vive precisamente ahí (ReAct 0,88 a T=50 pero 0,74 a T=200), y el bloque 1 se midió hasta
  T=50.
- **La réplica cruzada de modelo está cerrada en la sonda A** (celda del oráculo n=22 en ambos;
  recordatorio n=24 en ambos) **y en la sonda C** (93 pasos dependientes en el brazo de estado,
  82 en el de historia, los dos modelos). No lo está en la Tabla 1 del bloque 1.
- **Seis episodios de Sonnet con ReAct quedaron excluidos por truncamiento** y están declarados
  uno a uno en §4.bis. El criterio (>3 respuestas cortadas de 50) se fijó al ver que el
  truncamiento es masivo o inexistente según el escenario, nunca intermedio; no se fijó después
  de mirar los scores.
- **Asimetrías declaradas entre brazos**, que no son errores pero condicionan la lectura:
  SKILL.state dispone de hasta 3 intentos por paso (reintenta si el parche no valida) mientras
  ReAct dispone de uno; y recibe los nombres de los campos del esquema, que ReAct no ve. Lo
  primero le da ventaja, lo segundo también, y lo segundo es además parte del método del paper.
  Cualquier separación **a favor** de SKILL.state hay que leerla con esa ventaja dentro.
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
- **Tasa de truncamiento por brazo en toda la Tabla 1**, que se midió con el tope calibrado
  sobre Haiku y nunca se comprobó contra el otro modelo. Es el hueco más probable de que quede
  otro artefacto del nº8.
- **Por qué Sonnet emite 66 parches fuera de esquema donde Haiku emite cero.** Es la única
  asimetría grande entre modelos que queda sin explicar, y es una propiedad del método, no del
  entorno.
- **Recordatorio sin destilar en Sonnet**, para cerrar también en dos modelos el resultado de
  los tres niveles (hoy es de Haiku).
- **Rediseñar Repo o descartarlo**: `k` configurable en vez de fijo a 2, y una fracción de
  pasos portantes muy superior a 5 de 34.
- Coste efectivo medido también en la sonda A. La contabilidad de tokens por episodio solo
  entró en los tres corredores al final (commit `36e1e08`), así que el gasto de la mayor parte
  del proyecto quedó estimado y no calculado.

Cerrado desde la versión anterior de este documento: sonda C, segundo entorno, y la réplica
cruzada de modelo en ambos.
