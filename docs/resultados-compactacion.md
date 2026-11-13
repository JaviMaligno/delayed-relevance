# Compactar o consultar: resultados (6-nov-2026)

Diseño en `diseno-compactacion-vs-transcript.md`. Cada directorio de `results/compaction/` tiene
el JSON parcial, `trazas/`, `reporte.txt` y, en la sonda C, `juez_aviso.json`. Muestras
pequeñas (6 o 12 episodios por brazo): los IC95 (Wilson) se solapan casi siempre. Es una
lectura preliminar, no una conclusión.

## Sonda A (detalle literal a 40 pasos), Haiku 5.5, 12 episodios por brazo

| brazo | sin guía | con guía de consulta |
|---|---|---|
| `react` | 10/12 | — |
| `summary` | 9/10 | — |
| `fresh_lookup` | 3/8 | 2/8 |
| `hybrid_lookup` | 12/12 | 12/12 |
| `summary_lookup` | 11/11 | 9/10 |
| `skillstate` | 1/12 | — |

- **Haiku 5.5 no pierde el detalle con el resumen**: lo escribe en el resumen. En el bloque 1,
  Haiku 4.5 con historia completa acertaba el 0% a k=40; Haiku 5.5 el 83%. La sonda A ya casi
  no discrimina entre brazos con este modelo.
- **Empezar de cero y consultar es el peor brazo**, con o sin guía. La guía hace las consultas
  más específicas (con identificador, del 59% al 70%) pero no sube el acierto.
- **`skillstate` al 8%** reproduce el bloque 1 (15% sin campo): el esquema solo tiene
  `shelf_contents` y `last_event`, y la cuarentena apuntada en `last_event` se sobrescribe.

## Sonda C (corrección retroactiva, k=14, seeds 17/6/10), 6 episodios por brazo

### El aviso original estaba mal diseñado (también en el bloque 1)

El aviso corregía la colocación del paso 0. En **todas** las seeds medidas (bloque 1: 4, 10, 6,
0, 1, 2; aquí: 17, 6, 10) ese palé se había enviado después y la estantería se había rellenado
con otro antes del aviso. El aviso decía que nunca se colocó un palé ya enviado, y el entorno
vaciaba una estantería con otro palé. Haiku 5.5 lo rechazaba con razón: el juez ciego
(`experiments/juez_aviso.py`, Sonnet 5.5) da 23 rechazos, 12 aceptaciones y 1 dudoso en 36
episodios.

Arreglo, `--aviso-coherente`: el aviso corrige la **última** colocación en esa estantería y
nombra el palé (`pallet_id`, `sku`, `lot`). El estado verdadero y los pasos dependientes no
cambian, solo el texto (test `test_aviso_coherente_corrige_el_pale_que_hay_y_no_cambia_lo_medido`).
`--aviso-declarado` además añade `correction_notice` a EVENT TYPES. `--guia-consulta` añade al
prompt cuándo y cómo consultar, igual que el resumen recibe qué conservar.

### Resultados: pasos dependientes con la corrección aplicada

| brazo | Haiku, aviso viejo | Haiku, coherente | Haiku, coh. + guía | Haiku, coh. + declarado | Luna, aviso viejo | Luna, coherente | Luna, coh. + guía |
|---|---|---|---|---|---|---|---|
| `react` | 7/14 | 6/7 | — | 6/6 | — | — | — |
| `summary` | 5/60 | 6/6 | — | 6/6 | 1/16 | 5/31 | — |
| `fresh_lookup` | 2/44 | 3/30 | 3/30 | 3/48 | 3/19 | 3/10 | 3/16 |
| `hybrid_lookup` | 2/61 | 6/6 | 6/6 | 6/6 | 6/8 | 3/11 | 5/6 |
| `summary_lookup` | 4/60 | 5/17 | 6/6 | 6/6 | — | — | — |
| `skillstate` | 2/38 | 5/17 | — | 6/6 | — | — | — |
| aceptación del aviso (juez) | 12/36 | 33/36 | 18/18 | 33/36 | ver abajo | ver abajo | ver abajo |

El número de pasos dependientes depende de la trayectoria: el agente que aplica la corrección
llena la estantería vaciada en el primer paso y no genera más dependientes; el que no, sigue
generándolos. Por eso un brazo que falla acumula denominador.

- **Con un aviso coherente, Haiku lo acepta (33 de 36) y casi todos los brazos aciertan.** Con
  el aviso además declarado, todos salvo `fresh_lookup` dan 6/6, `skillstate` incluido.
- **`fresh_lookup` es el único brazo que falla de verdad**, en todas las condiciones y con los
  dos modelos. Casi todos sus fallos son la acción «sorda» (la que sería correcta sin el
  aviso): empieza de cero, no sabe que hubo una corrección y no la busca.
- **La guía de consulta ayuda cuando hay algo que recuperar**: `summary_lookup` 5/17 → 6/6 en
  Haiku, `hybrid_lookup` 3/11 → 5/6 en Luna. A `fresh_lookup` no le ayuda.

### Luna

Luna (GPT-6 por Codex) no escribe razonamiento visible: contesta solo `Action: ...`. El
razonamiento interno no se expone; Codex solo da un resumen si se pide
(`model_reasoning_summary`), y es de títulos de una línea en algunos pasos («Waiting for
correction guidance»): no basta para juzgar. El cliente ya lo pide y lo guarda (campo
`razonamiento` de la traza) desde el commit 4b11a07; las corridas de esta tabla son anteriores.

Lo que sí sirve es el resumen de compactación, que Luna escribe en el paso siguiente al aviso y
es texto visible (p. ej. «Step 14's confirmed correction supersedes that record: putaway never
completed, the shelf is empty»). Con él, el juez da **ACCEPTED en los 12 episodios de
`summary`** (aviso viejo y coherente). En `fresh_lookup` y `hybrid_lookup` no hay resumen y
queda UNCLEAR. (`C-luna6/juez_aviso_solo_respuesta.json` es el juicio anterior, sin resumen:
18 UNCLEAR.)

**El 5/31 de Luna en `summary` no viene del aviso.** De 31 pasos dependientes, 20 son una
tercera acción, ni la correcta ni la sorda: coloca en otra estantería libre en vez de la más
baja, que es lo que pide la política. Luna sigue peor la política en general (score medio
0,56 en `summary`, frente a 0,995 de Haiku). Ese brazo mide el seguimiento de la política,
no la corrección.

## Lo que cambia respecto al bloque 1

El 93/93 de SKILL.state frente al 18/82 de la historia se midió con el aviso incoherente. Aquí,
con Haiku 5.5:
- con el aviso viejo, `skillstate` 2/38 y `react` 7/14;
- con el aviso coherente y declarado, los dos 6/6.

### Repetición del bloque 1 con Haiku 4.5 (12-nov-2026)

`experiments/rejilla_bloque1_coherente.sh`, resultados en `results/bloque1-coherente/`. Mismas
condiciones que la L2 v2 (Haiku 4.5, seeds 4/10/6, k=10, tope 8192), 4 repeticiones, por
`claude -p` en vez de Foundry. El aviso viejo va con el mismo cliente, para que el cambio de
arnés no se lea como efecto del aviso. Medida primaria por episodio: la caja del primer paso
dependiente, la misma de la corrección publicada.

| Haiku 4.5 | aviso viejo: 1er dep. | aviso viejo: pasos | coherente: 1er dep. | coherente: pasos |
|---|---|---|---|---|
| `skillstate` | 12/12 | 12/12 | 12/12 | 12/12 |
| `react` (historia) | 3/12 | 3/69 (66 sordas) | 10/12 | 12/15 |
| Sonnet 5 `skillstate` | 12/12 | 12/12 | 12/12 | 12/12 |
| Sonnet 5 `react` | 5/12 | 8/65 | 12/12 | 12/12 |

- **La suscripción reproduce el bloque 1**: con el aviso viejo, 12/12 frente a 3/12 (publicado
  para Haiku: 24/24 frente a 1/24). El cambio de cliente no explica la diferencia.
- **Sonnet 5 (13-nov-2026)**: aviso viejo 12/12 frente a 5/12 (publicado: 22/24 frente a 9/24); coherente, 12/12 los dos. La ventaja desaparece.
- **Con el aviso coherente, la historia pasa de 3/12 a 10/12.** La ventaja del estado
  explícito baja de ~75 puntos a ~17, con IC que se solapan (n=12). La mayor parte de la
  ventaja publicada venía del aviso que contradecía la historia: el brazo de historia veía que
  el palé ya se había enviado y no aplicaba el aviso; el de estado no podía verlo.

## `fresh_ask`: preguntar a quien lee el transcript entero (13-nov-2026)

El artículo dejaba sin probar el lookup de Woolford, que delega la búsqueda en un subagente que
lee toda la historia. `fresh_ask` es `fresh_lookup` con otra herramienta: tras compactar, sesión
limpia; en vez de `Lookup: <palabras>`, el agente puede responder `Ask: <pregunta>`. Contesta
otra llamada al mismo modelo (Haiku 5.5 por `claude -p`) con el transcript crudo entero y un
system neutral (`PROMPT_RESPONDEDOR`: responder solo con el transcript, citar pasos y decir si
eventos posteriores cambian los anteriores). Mismo tope de 2 por paso; nada en el prompt del
agente nombra el aviso ni las correcciones. `experiments/rejilla_compaction_ask.sh`, resultados
en `results/compaction/C-haiku55-coh-ask/`.

### Sonda C, aviso coherente, sin guía ni aviso declarado, 6 episodios

| brazo | 1er dependiente (por episodio) | pasos dependientes | consultas portantes |
|---|---|---|---|
| `fresh_ask` | **4/6** | **6/8** | 27/33 |
| `fresh_lookup` | 2/6 | 3/30 | 1/40 |
| `summary` | 6/6 | 6/6 | — |
| `hybrid_lookup` | 6/6 | 6/6 | 0/1 |
| `summary_lookup` | 5/6 | 5/17 | 0/9 |
| `react` | 5/6 | 6/7 | — |
| `skillstate` | 5/6 | 5/17 | — |

Las filas que no son `fresh_ask` son las de `C-haiku55-coh`, ya medidas.

- **La corrección llega sin pedirla.** El agente nunca pregunta «qué ha cambiado» ni «hubo
  correcciones». De 33 preguntas (5,5 por episodio, entre 3 y 9), 30 son sobre el estado (qué
  estantería está libre, dónde está un SKU, el mapa de ocupación) y 3 son repreguntas para
  verificar una respuesta anterior, dos de ellas sobre la corrección que esa respuesta había
  traído. Ninguna genérica. El respondedor, al reconstruir el estado, aplica el aviso y lo cita:
  en los 6 episodios, la primera pregunta tras la compactación del paso 15 ya lo trae. 27 de
  33 respuestas lo citan (heurística `respuesta_portante`: `notice_id` o paso del aviso;
  comprobado que las 27 lo mencionan de forma explícita). Las 6 que no lo citan son preguntas
  que el aviso no afecta (un SKU u otras estanterías).
- **Los dos fallos ya no son de recuperación, sino de aceptación.** En s6 r0 la respuesta decía
  que la estantería 0 estaba vacía por el aviso del paso 14; el agente contestó «the step 14
  "correction" was a Wait, not a Ship» y colocó en la 1 (acción sorda). En s10 r0 el agente
  repreguntó para verificar el aviso, el respondedor contestó que el cambio «rests only on the
  notice's own fields», y el agente esperó (`Wait`) en vez de colocar. En los dos, el siguiente
  paso dependiente ya fue correcto: no hay cascada (6/8 frente a 3/30).
- **Coste**: 0,11 USD/episodio a precio de lista frente a 0,08 de `fresh_lookup`; cada pregunta
  manda el transcript entero.

Ejemplos literales:
- s17 r0, paso 15, recién compactado. *Ask*: «What is the lowest-numbered empty shelf as of
  step 15, after every Store and Ship through step 14? List each shelf's current occupant, with
  its SKU and lot.» *Respuesta*: «Lowest-numbered empty shelf as of step 15: shelf 0. All
  shelves (0, 1, and 2) are empty…», y en la lista de pasos: «Step 14: Correction notice
  COR-3619 corrects step 13. It states the putaway never completed…»
- s10 r1, paso 17. *Ask*: «Before step 17, which shelves held stock and which were empty? …»
  *Respuesta*: «Occupancy after the last Store or Ship (step 12), before the correction: … Updated
  after correction COR-2087 (step 14): Step 14 corrects step 8. Shelf 0 … was never put away…»

Lectura: con n=6 es dirección, no conclusión (IC95 del primer dependiente, 30-90%). El mecanismo
sí se ve claro: con palabras clave el agente tiene que saber qué buscar; con una pregunta sobre
el estado, quien lee la historia entera trae la corrección por su cuenta.

### Sonda A, k=40: pendiente

No llegó a arrancar: el equipo se quedó sin memoria (≈1 GB libre) mientras la rejilla esperaba
el umbral de 2,5 GB, y Claude Code mató el proceso. Para lanzarla (reanuda desde checkpoint):

    cd <worktree> && PYTHONPATH="src;." python experiments/run_compaction.py --probe A --k 40 \
      --seeds 0 3 6 8 --reps 3 --client claude-cli --model claude-haiku-5-5 \
      --arms fresh_ask --out results/compaction/A-haiku55-ask

Referencia: `fresh_lookup` 3/8 en la sonda A sin guía (12 episodios, 8 con el paso dependiente
materializado).

## Pendiente

1. Decidir con Javier la corrección de `when-the-fact-stops-being-true` (ya lleva una nota de
   corrección: 70/72 frente a 10/72) y revisar `explicit-state-misremembers`, que cita el 93/93.
2. Los episodios con 0/0 dependientes no cuentan ni a favor ni en contra; revisar si alguno
   oculta un fallo.
