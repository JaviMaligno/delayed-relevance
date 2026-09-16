# Spec — del bloque 1 al paper

Estado: propuesta, 2026-09-13. Sucede a `resultados-bloque1.md`, que sigue siendo la
fuente de los números ya medidos. Este documento fija **qué se afirma, qué falta medir
para poder afirmarlo, y en qué orden**.

---

## 0. La tesis

No es «SKILL.state no replica». Es esto:

> **La mitad barata del método es la cara, y su ventaja de precisión es un fenómeno de
> modelo pequeño.** El prompt O(1) se reproduce exactamente; el ahorro en factura no
> sobrevive a la caché de prefijo, porque un estado que muta es lo contrario de un prefijo
> cacheable. Y la degradación del transcript que motiva el método desaparece según sube la
> capacidad del modelo: se ve entera en Qwen-3-8B, a medias en Gemini-3-Flash y no se ve en
> absoluto en Haiku 4.5.

De ahí cuelgan cuatro contribuciones, con su estado:

| | Contribución | Estado | Qué falta |
|---|---|---|---|
| **C1** | La caché invierte la contabilidad: 7,5x en tokens → 1,4x en factura; el orden del paper (estado delante del transcript) cuesta 5,7x más | Medido en Anthropic, dos longitudes de procedimiento | Repetir en Gemini: su caché no funciona igual y el resultado **no es extrapolable** |
| **C2** | Escalera de capacidad: su efecto de precisión se apaga al subir de modelo | Medido en los dos extremos (sus Tablas 7–8 abajo; Haiku/Sonnet arriba) | **R1**: su propio modelo en nuestro entorno. Sin eso no es atribuible |
| **C3** | La limitación (2) de su §7, con número: el esquema solo protege lo que su diseñador anticipó; el campo genérico no sirve; reinyectar el hecho sí, y sin anticipar nada | Medido en dos modelos, protocolo pareado | Tercer modelo (R4) para que sea la misma escalera que C2 |
| **C4** | Su Experimento 3, medido por decisión dependiente en vez de por escenario: 93/93 contra 18/82 | Medido en dos modelos | Tercer modelo (R5). **Es confirmación, no contraejemplo** — ver §1 |

---

## 1. Decisiones cerradas, que no se re-litigan

1. **No afirmamos contradicción de ninguna limitación del paper.** Su §7 reserva el caso de
   la procedencia para tareas *cuyo objetivo es la propia historia* (auditar, explicar
   acciones pasadas); la sonda C no instancia ese antecedente. Y su Experimento 3
   (Tablas 3 y 10) ya reporta la misma dirección con el mismo mecanismo: 5–8 turnos de
   recuperación con historia en Warehouse, 8–14 en Repo, 0 con estado explícito. Lo nuestro
   es la **métrica**, no el signo.
2. **Modelo objetivo: `gemini-3-flash-preview`**, que es el de su Tabla 1, con
   `temperature=0.0` y `top_p=1.0`, sus mismos ajustes.

   > **Corregido el 2026-09-15 con dato en contra.** Esta decisión decía que con greedy
   > «las seeds vuelven a ser instancias del entorno en vez de tiradas», y de ahí que
   > bastara **una** tirada por celda. **Es falso en este proveedor.** La misma celda
   > —T=200, seed 2, ReAct, entorno del Apéndice B + Algoritmo 2, `temperature=0`,
   > `thinking_budget=0`— repetida cinco veces da **0,830 / 0,930 / 0,940 / 0,945 /
   > 0,960**: media 0,921, **sd 0,052**, amplitud 0,130.
   >
   > La dispersión no es simétrica y las trazas dicen por qué: los fallos **encadenan**.
   > Un SKU mal copiado en el paso 12 deja al modelo afirmando en el paso 16 «Shelf 0
   > (SKU-F, stored in step 12)» cuando él mismo guardó otro ahí. Casi siempre ~0,94, y
   > de vez en cuando una cascada temprana hunde la celda a 0,83.
   >
   > **Medido en dos horizontes**, el ruido de repetición es pequeño y crece con T:
   >
   > | T | repeticiones | sd | amplitud |
   > |---|---|---|---|
   > | 100 | 0,96 / 0,97 / 0,97 (rejilla 0,96) | 0,006 | 0,010 |
   > | 200 | 0,93 / 0,94 / 0,945 / 0,96 (rejilla 0,83) | 0,012 | 0,030 |
   >
   > Consecuencia operativa, y es **doble**. (a) El ruido ordinario es de medio punto a
   > punto y medio, así que los efectos de varios puntos son señal. (b) La cola sí
   > muerde: el 0,83 de la rejilla en T=200 no lo reprodujo ninguna de cuatro
   > repeticiones. Una tirada por celda puede caer en la cola y arrastrar la media de
   > cinco seeds casi dos puntos, así que **lo que se enseñe necesita repeticiones —no
   > por el ruido, sino por las colas—**, que es lo que ya exigía el punto 3.
   >
   > Evidencia con traza por paso: `results/adj_T{100,200}_*_react_s2*.jsonl`.
3. **Protocolo §7 para todo lo que se enseñe**: pocas seeds, muchas repeticiones por seed,
   acierto agregado sobre repeticiones y dispersión entre seeds aparte. Lo medido con una
   tirada por seed no entra en el paper, ni siquiera como indicio.

   > **Enmienda del 2026-09-16, medida.** La segunda mitad de esta regla —reportar la
   > dispersión **entre seeds**— da por hecho que la variación vive entre seeds y que
   > dentro de una seed el resultado es estable. **No lo es.** Con tres tiradas por
   > seed en ReAct / T=200 / entorno del Algoritmo 2:
   >
   > | seed | tiradas | recorrido |
   > |---|---|---|
   > | 0 | 0,715 / 0,825 / 0,920 | **0,205** |
   > | 1 | 0,870 / 0,920 / 0,985 | 0,115 |
   > | 2 | 0,830 … 0,985 (7 tiradas) | 0,155 |
   > | 3 | 0,905 / 0,955 / 1,000 | 0,095 |
   > | 4 | 0,875 / 0,960 / 0,985 | 0,110 |
   >
   > La dispersión **dentro** de una seed es del mismo orden que la que hay **entre**
   > seeds (media de medias 0,912, sd entre seeds 0,053). Reportar solo la segunda
   > subestima la incertidumbre alrededor de la mitad.
   >
   > Regla que sustituye a la anterior: **la barra de error de una celda se calcula
   > sobre todas sus tiradas**, no sobre las medias por seed. La dispersión entre seeds
   > se reporta además, como lo que es —cuánto varía la dificultad del guion—, no como
   > la incertidumbre de la medida.
   >
   > Y una consecuencia que no es de reporte sino de diseño: con este recorrido, **una
   > diferencia por debajo de ~5 puntos entre dos condiciones no se afirma sin tres
   > tiradas por seed en las dos**. Evidencia: `results/adj_T200_*_react_s?_p?.jsonl`.
4. **La ejecución va en GitHub Actions**, no en el portátil. Las corridas son I/O contra una
   API, la máquina local se satura y ya se perdieron tandas por eso.
5. **Los datos crudos se commitean.** El argumento del trabajo es que este tipo de
   experimento falla produciendo resultados limpios; los JSON por episodio son la prueba.

---

## 2. Infraestructura

**I1 — Adaptador de Gemini en `src/dr/llm.py`.** Hoy la clase habla solo Anthropic. Hace
falta un `GeminiClient` con la misma firma `complete(system, user, max_tokens, cache_prefix)
-> Completion`:
- REST contra `generativelanguage.googleapis.com`, `generationConfig` con `temperature: 0.0`
  y `topP: 1.0`.
- Tokens desde `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`,
  `cachedContentTokenCount`).
- `truncated = finishReason != "STOP"`. Sin esto repetimos el artefacto nº 8 en un modelo
  nuevo.
- **La caché no se implementa en el primer paso.** Gemini tiene caché implícita y caché
  explícita con TTL y mínimo de tokens; no es el corte de prefijo de Anthropic. R1 y R4–R5
  corren sin caché; C1 en Gemini es una corrida aparte (R3b) con su propio diseño.
- Reintentos como el cliente actual: 503 y 429 sí, autenticación y petición inválida no.

**I2 — `--repeats` en `replicate_table1.py` y `probe_a.py`.** Hoy la clave del checkpoint es
`f"{name}:{seed}"`, así que una repetición sobrescribe la anterior. Pasa a
`f"{name}:{seed}:{rep}"`, con el agregado sobre repeticiones y la dispersión entre seeds
reportada aparte. `diagnose_probeC.py` ya lo tiene y sirve de referencia.

**I3 — Workflow de Actions.** `workflow_dispatch` con entradas (`experiment`, `model`,
`horizons`, `seeds`, `repeats`, `runtimes`), `concurrency` por experimento para que dos
lanzamientos no se pisen el checkpoint, `timeout-minutes` por debajo del tope de 6 h del
runner, y al terminar **commit de `results/partial_*.json` a una rama `runs/<fecha>-<exp>`**.
Reanudación: el job hace checkout de esa rama antes de empezar, así una rejilla que agota el
tiempo continúa en el siguiente lanzamiento sin re-pagar episodios. La clave vive en el
secreto `GEMINI_API_KEY` del repo; el repo es público, así que el workflow es
`workflow_dispatch` **y nada más** — sin `pull_request`, que expondría el secreto a un fork.

**I4 — Cotejo del entorno contra el Apéndice B.** Su reimplementación dejó de ser a ciegas:
el paper publica el diseño de los dos entornos (B.1), el pseudocódigo del generador
(Algoritmo 2) y los cuatro prompts exactos (Apéndice A). Hay que revisar línea a línea
nuestro `warehouse.py` contra: 500 estanterías, acciones `Store`/`Ship`/`Move`/`Wait`, tres
familias de observación (`Shipment arrived`, `Customer ordered`, `Maintenance required`),
validación que rechaza la transición si la estantería está ocupada, y
`score = acciones válidas ejecutadas / eventos accionables`. Cada diferencia que quede,
declarada en una tabla. **Este cotejo se hace antes de R1**, porque R1 se interpreta contra
él.

---

## 3. Corridas, por orden de valor

### R1 — Gemini-3-Flash en nuestro Warehouse *(decide el proyecto)*

`T ∈ {10, 25, 50, 100, 200}`, 5 seeds, 4 runtimes, greedy. Es su Tabla 1 celda por celda.

No es «un modelo más»: es el diagnóstico que separa las dos explicaciones de nuestra
no-réplica. **El criterio se fija ahora, antes de ver el resultado:**

| Si ReAct en Gemini da… | Entonces | Consecuencia |
|---|---|---|
| ≈ 0,90 → 0,74 (su Tabla 1, ±0,10) | el entorno es fiel y la diferencia es el modelo | C2 queda probada; el paper sale |
| ≈ 1,00 a todos los horizontes | nuestro entorno es más fácil que el suyo | vuelta a I4; no se afirma nada sobre C2 hasta arreglarlo |
| intermedio | fidelidad parcial | se reporta la curva de los tres modelos y se declara la incertidumbre |

Referencias contra las que se lee, del propio paper:

| T | Qwen-3-8B | Gemma-4-31B | Gemini-3-Flash | Haiku 4.5 (nuestro) |
|---|---|---|---|---|
| 10 | 0,84 | 0,90 | 0,90 | 1,00 |
| 25 | 0,54 | 0,64 | 0,92 | 1,00 |
| 50 | 0,24 | 0,31 | 0,88 | 1,00 |
| 100 | 0,15 | 0,21 | 0,84 | 1,00 |
| 200 | — | — | 0,74 | 0,99 |

### R2 — Tabla 1 bajo protocolo §7

Haiku en `T ∈ {50, 200}`, 3 seeds × 8 repeticiones, cuatro runtimes. Es la tabla de cabecera
del paper y hoy está medida con una tirada por seed. Gemini no necesita repeticiones
mientras corra greedy, y esa asimetría **se declara en la tabla**, no en una nota.

### R3 — Coste con caché, por proveedor

(a) Anthropic: ya medido, se conserva. (b) Gemini: rehacer con su modelo de caché
(implícita y explícita), dos longitudes de procedimiento y los dos órdenes del bloque de
estado. Sin (b) la afirmación de C1 se limita explícitamente a Anthropic.

### R4 — Sonda A en Gemini

`k=40`, 3 seeds × 8 repeticiones, cuatro condiciones (sin campo, campo genérico, oráculo,
recordatorio). Cierra C3 en la misma escalera de tres modelos que C2.

### R5 — Sonda C en Gemini

Seeds 4, 10 y 6 (elegidas por suelo del sordo), 2 repeticiones, `skillstate` y `react`.
Tercera réplica del Experimento 3 con métrica por decisión.

### R6 — Entorno 2: Software Repository

A su especificación de B.1 (ramas, PRs, estados de CI; `Commit`, `CreatePR`, `Merge`,
`FixCI`, `Wait`; éxito = feature requests mergeadas sin romper CI), con su Tabla 6 como
objetivo a igualar:

| T | ReAct | Memory | Stateful | SKILL.state |
|---|---|---|---|---|
| 10 | 0,89 | 0,93 | 1,00 | 1,00 |
| 50 | 0,71 | 0,65 | 0,74 | 0,86 |
| 100 | 0,53 | 0,57 | 0,63 | 0,78 |

Nuestro Repo actual no discrimina porque se construyó como control, con `k` fijo a 2 y 5
pasos portantes de 34. Aquí hay especificación y cifra que igualar, así que deja de ser un
rediseño a ciegas. **Es la corrida más cara y la última**; si no sale, el paper se queda en
un entorno y se declara.

### R7 — Extremo bajo de la escalera *(opcional)*

Qwen-3-8B o Gemma-4-31B vía un proveedor de modelos abiertos. Solo si R1 deja la escalera
ambigua. No hay despliegue de ninguno de los dos en el Azure disponible.

---

## 4. Reglas de medición, vinculantes

- **Suelo del agente sordo antes de gastar.** Elegir seeds por rango medido es gratis y
  cuadruplicó la señal de la sonda C.
- **Nada con menos de ~20 observaciones por celda** entra en una tabla del paper.
- **No se afirma una diferencia menor de ~30 pp** medida con seeds distintas sin repetición.
- **Wilson siempre**; los intervalos normales dieron un 100–100 % imposible.
- **Truncamiento contado por brazo y declarado**, en todas las corridas, con el criterio de
  exclusión fijado antes de mirar los scores. Subir el tope de salida nunca ha arreglado un
  truncamiento en este proyecto: el modelo llena el presupuesto que le den.
- **Asimetrías entre brazos declaradas** (SKILL.state reintenta hasta 3 veces y ve los
  nombres del esquema; ReAct no), y toda separación a su favor se lee con esa ventaja dentro.

---

## 5. Forma del entregable

Paper corto, arXiv primero y luego un taller de agentes/evaluación o una vía de réplica
(ReproNLP, *Insights from Negative Results*, COLM). **ARR/ACL queda descartado de entrada
mientras el write-up esté publicado y firmado en el blog**, salvo que su política de
preprints diga lo contrario al mirarla.

Esqueleto: (1) qué afirma el paper y qué medimos; (2) fidelidad del entorno y sus
diferencias declaradas — I4; (3) la escalera de capacidad — R1, R2; (4) la contabilidad con
caché — R3; (5) las dos sondas como medición de sus limitaciones declaradas — R4, R5;
(6) instrumento y artefactos, que es el apartado que distingue esto de un post; (7)
limitaciones.

**Fuera de alcance, explícito**: InterCode CTF y τ-bench (sus Tablas 4), multi-agente,
decodificación restringida, y cualquier afirmación sobre cómo se entrenó ningún modelo.

---

## 6. Riesgos

- **Los autores no contestan.** Plan B: el Apéndice B basta para cotejar y la diferencia se
  declara. No bloquea nada.
- **`gemini-3-flash-preview` puede no ser el `Gemini-3-Flash` exacto de su Tabla 1.** Se
  declara como limitación y se registra el ID devuelto en cada respuesta.
- **La caché de Gemini no es la de Anthropic.** C1 se enuncia por proveedor hasta que R3b
  diga otra cosa.
- **Coste.** La rejilla completa de R1 son 5 horizontes × 5 seeds × 4 runtimes con
  horizontes de hasta 200 pasos. Se lanza por horizonte, de menor a mayor, y se para si el
  criterio de R1 ya está decidido en T=50 y T=100.

---

## 7. Puntos de control

- **CP1, tras I4 + R1.** Decide si hay paper o si hay que arreglar el entorno. Nada de R2–R6
  arranca antes.
- **CP2, tras R2 + R3.** Con eso están C1 y C2, que son el paper corto. Aquí se decide si
  R6 merece la pena o si se entrega con un entorno.
- **CP3, antes de subir a arXiv.** Revisión adversarial de cada tabla contra su JSON, y el
  cotejo de que ninguna afirmación excede su medición.
