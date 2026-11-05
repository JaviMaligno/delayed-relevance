# Compactar o consultar: diseño del experimento

**Pregunta.** Cuando la conversación de un agente se llena, ¿qué conserva mejor lo que hace
falta: resumirla (lo que hacen Claude Code y Codex), empezar una sesión limpia con el transcript
literal consultable, o un híbrido?

**Por qué no está medido ya.** En el bloque 1 (`resultados-bloque1.md`, §4.bis) el transcript
completo **en contexto** aplicó 18 de 82 correcciones, y el estado explícito 93 de 93. Pero allí
el transcript estaba siempre delante. La propuesta aquí es distinta: el transcript **no está en
contexto**, se consulta. Woolford (arXiv 2610.20116, oct-2026) mide la recuperación de hechos con
consulta a demanda, pero no la aplicación de correcciones. El hueco es ese: al buscar en el
transcript literal, ¿el agente encuentra el valor viejo o la corrección?

## Brazos

Todos compactan en los mismos pasos: **cada 15 pasos** (15, 30, 45 en `T=50`). Entre
compactaciones, todos acumulan historia como ReAct.

| brazo | qué ve tras compactar | consulta |
|---|---|---|
| `summary` | resumen escrito por el modelo | no |
| `fresh_lookup` | nada: sesión limpia | sí |
| `hybrid_lookup` | sus propias líneas de razonamiento y acción, literales; observaciones reducidas a una línea (Woolford) | sí |
| `summary_lookup` | resumen (Cursor) | sí |

Referencias, corridas de nuevo con el modelo de este experimento (el bloque 1 usó Haiku 4.5):
`react` (transcript entero en contexto, sin compactar) y `skillstate` (estado explícito).

**Consulta.** En vez de una acción, el modelo puede responder `Lookup: <palabras>`. El runtime
devuelve hasta 8 líneas del transcript crudo que contengan todas las palabras, **en orden
cronológico y con su número de paso**, y vuelve a preguntar. Máximo 2 consultas por paso. El
transcript crudo es append-only y nunca se compacta. Las líneas llevan el paso para que la
procedencia sea visible: es lo que en la investigación del sentido temporal sí ayudó.

## Sondas

Las dos del bloque 1, porque cubren los dos ejes del debate:

- **Sonda A, relevancia diferida, `k=40`**: un detalle literal (estantería en cuarentena) leído
  40 pasos antes de usarlo, con 2 o 3 compactaciones de por medio. Es el caso que el resumen
  pierde. Métrica: acierto en el paso dependiente.
- **Sonda C, invalidación retroactiva**: un aviso corrige una colocación pasada.
  **`invalidation_k=14`, seeds 17, 6 y 10.** Métrica: pasos dependientes con la corrección aplicada.

### Por qué k=14 y seeds 17, 6, 10 (y no k=10 con 4, 10, 6)

Con k=10 el aviso llega en el paso 10 y el paso decisivo —el primer `Store` posterior, el único
paso dependiente si el agente acierta— en el 11: **antes de la primera compactación, en las
tres seeds** (`experiments/precheck_compaction.py`). Los 22 dependientes del bloque 1 son los de
la cascada del agente sordo, que solo existe si el agente ya falló el paso 11. Con esa
configuración la sonda no probaba la compactación al aplicar la corrección; en la seed 6, ni
siquiera en la cascada (sus dependientes son 11–14).

La cadencia de 15 no se mueve. Se barrieron gratis `invalidation_k` 1–40 y seeds 0–19
(`experiments/barrido_sonda_c.py`): 72 configuraciones cumplen aviso < compactación ≤ paso
decisivo con la trayectoria perfecta. Como el aviso siempre corrige la primera colocación (paso
0), la colocación original y el aviso quedan ambos antes de la compactación. Se eligieron las
tres con más pasos dependientes en la cascada tras la compactación, con un único k:

| seed | colocación | aviso | compactación | paso decisivo | cascada del sordo tras compactar | suelo del sordo |
|---|---|---|---|---|---|---|
| 17 | 0 | 14 | 15 | 15 | 14 de 14 | 0,533 |
| 6 | 0 | 14 | 15 | 16 | 12 de 12 | 0,657 |
| 10 | 0 | 14 | 15 | 17 | 6 de 6 | 0,838 |

32 pasos dependientes por repetición si el brazo falla, todos con la compactación de por medio.
La seed 4 empata con la 10 (6 pasos); se prefirió la 10 porque su paso decisivo cae dos pasos
después de la compactación y no uno.

**Suelo de `fresh_lookup` en C, con trampa.** El agente perfecto que nunca consulta saca
0,867 / 0,629 / 0,784 de score, pero **acierta el paso decisivo en las tres seeds por
accidente**: al olvidarlo todo cree vacía la estantería 0, que es justo la que el aviso corrige.
En C, el acierto de `fresh_lookup` en el paso decisivo no distingue "consultó y aplicó la
corrección" de "lo olvidó todo"; hay que leerlo junto a las consultas portantes y al score.

Además, por brazo: **tasa de consulta** (pasos con al menos un `Lookup`), consultas que
devuelven la línea portante (la observación del aviso; las que solo traen su id en una línea del
propio agente se cuentan aparte), **forma de las consultas** (palabras por consulta y proporción
con un identificador: estantería, SKU o `notice_id`), truncamientos (de decisión y de resumen
por separado), pasos sin acción y coste.

### Coste: medido por el CLI y estimado con caché ideal

`claude -p` manda el prompt de usuario como **un único bloque**, así que solo cachea el system:
la historia acumulada se reescribe entera en cada paso. Medido en el piloto: `cache_read` fijo en
~2.000–2.260 tokens y `cache_creation` creciendo de 1.983 a 10.794 tokens en el paso 14, escrito
además a caché de 1 h. El coste que mide el CLI no es comparable con lo medido por API en el
bloque 1, y no se va a OpenRouter. El reporte da dos columnas:

- **`coste_lista_usd`**: medido por el CLI, a precio de lista.
- **Entrada efectiva ESTIMADA** con caché de prefijo ideal: en cada llamada, la parte del prompt
  que coincide con la llamada anterior del mismo system se cuenta a 0,1x y el resto a 1,25x. Es
  una estimación optimista (sin mínimo cacheable ni cortes por bloque), etiquetada como tal.

### Thinking de Haiku 5.5

Se mantiene el comportamiento por defecto de `claude -p`, que es el uso real: Haiku 5.5 **piensa**
(en el piloto, entre el 50 % y el 90 % de la salida). Se registra por llamada
(`thinking_tokens`). El tope de salida es 8.192 tanto para decidir como para resumir: con 1.200
en el resumen (lo heredado de `MemoryRuntime`) el thinking se comía el presupuesto y el resumen
llegaba vacío. En el piloto ninguna decisión se truncó; la mayor salida de una decisión fue de
1.243 tokens.

## Antes de gastar (gratis)

1. Tests de cada runtime con `FakeClient`.
2. **Suelo del sordo** por sonda y seed (ya existe para C).
3. **Agente perfecto que nunca consulta**: para `fresh_lookup` es el suelo; si su score se
   acerca al techo, la sonda no discrimina el brazo.
4. Densidad de contexto por brazo con `measure_density.py`.

## Modelos y presupuesto

- **Claude Haiku 5.5 vía `claude -p`** (suscripción, sin coste de API). Medido el 5-nov-2026:
  con `--setting-sources "" --strict-mcp-config --disable-slash-commands --tools ""
  --system-prompt …` el arnés añade solo ~776 tokens, y el JSON de salida trae
  `cache_creation_input_tokens`, `cache_read_input_tokens` y el coste a precio de lista.
  `--bare` no sirve: no usa el login de la suscripción. Los 6 brazos (4 nuevos + 2
  referencias). Sonda C: 3 seeds × 2 repeticiones × 6 = 36 episodios. Sonda A: 10 × 6 = 60.
- **GPT vía `codex exec`** (suscripción), modelo **`gpt-6-luna`** (el ligero de Woolford, más
  barato; comprobado que el id existe), solo la sonda C y los brazos `summary`, `fresh_lookup` y
  `hybrid_lookup`: 18 episodios. Limitación declarada: Codex añade su propio prompt de sistema
  (~17.500 tokens medidos con `--ignore-user-config`, que quita los MCP del usuario), y su JSON no
  dice qué modelo contesta.
- Una corrida cada vez, nunca dos en paralelo, lanzada con `exec` (ver README).

## Qué haría cambiar la conclusión

- Si `fresh_lookup` casi no consulta, el resultado mide la pereza del modelo, no el método. Se
  reporta la tasa de consulta junto al acierto, siempre.
- Si la consulta devuelve la línea vieja y la corrección y el modelo elige la vieja, es el
  mismo fallo del bloque 1 en otra forma, y es el hallazgo.
- Una diferencia menor que el suelo de ruido del bloque 1 (§0) no se reporta como efecto.
