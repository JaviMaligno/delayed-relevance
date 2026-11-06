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
  más específicas (con identificador, del 40% al 70%) pero no sube el acierto.
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

Con el aviso bien diseñado, la ventaja del estado explícito sobre la historia desaparece en
esta sonda. El bloque 1 era Haiku 4.5, que aplicaba el aviso viejo sin cuestionarlo; habría
que repetirlo con Haiku 4.5 y el aviso coherente para saber si su resultado se sostiene.

## Pendiente

1. Repetir el bloque 1 (Haiku 4.5) con `--aviso-coherente` para decidir si el artículo
   publicado sobre SKILL.state necesita una corrección.
2. Los episodios con 0/0 dependientes no cuentan ni a favor ni en contra; revisar si alguno
   oculta un fallo.
