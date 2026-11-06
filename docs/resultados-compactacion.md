# Compactar o consultar: resultados de la rejilla (6-nov-2026)

Diseño en `diseno-compactacion-vs-transcript.md`. Reportes completos en
`results/compaction/{C-haiku55,C-luna6,A-haiku55}/reporte.txt`; trazas en cada `trazas/`.
Muestras pequeñas: los IC95 (Wilson) se solapan casi siempre. Esto es una lectura
preliminar, no una conclusión.

## Sonda A (detalle literal a 40 pasos), Haiku 5.5, 12 episodios por brazo

| brazo | acierto en el paso dependiente | consultas (pasos con Lookup) |
|---|---|---|
| `react` | 10/12 (83%) | — |
| `summary` | 9/10 (90%) | — |
| `fresh_lookup` | 3/8 (38%) | 10,7% |
| `hybrid_lookup` | 12/12 (100%) | 0,3% |
| `summary_lookup` | 11/11 (100%) | 1,3% |
| `skillstate` | 1/12 (8%) | — |

- **Haiku 5.5 no pierde el detalle con el resumen**: lo escribe en el resumen. En el bloque 1,
  Haiku 4.5 con historia completa acertaba el 0% a k=40; Haiku 5.5 el 83%. La sonda A ya casi
  no discrimina entre brazos con este modelo, salvo uno.
- **Empezar de cero y consultar es el peor brazo** (38%). Consulta en el 11% de los pasos, con
  palabras sueltas, y solo 5 de 87 consultas devuelven el aviso.
- **`skillstate` al 8% no es un fallo del arnés**: es el resultado del bloque 1 (15% sin campo,
  n=20). El esquema solo tiene `shelf_contents` y `last_event`; el modelo apunta la cuarentena
  en `last_event` y el siguiente evento la sobrescribe (traza `skillstate_s0_r0`, paso 9 → 49).

## Sonda C (corrección retroactiva, k=14, seeds 17/6/10), 6 episodios por brazo

Pasos dependientes con la corrección aplicada:

| brazo | Haiku 5.5 | GPT-6 Luna |
|---|---|---|
| `react` | 7/14 | — |
| `summary` | 5/60 | 1/16 |
| `fresh_lookup` | 2/44 | 3/19 |
| `hybrid_lookup` | 2/61 | **6/8** |
| `summary_lookup` | 4/60 | — |
| `skillstate` | 2/38 | — |

**Confusor encontrado en las trazas: Haiku 5.5 a menudo no acepta el aviso.** El
`correction_notice` no es un tipo de evento definido en el prompt (deliberado desde el
bloque 1). Haiku 4.5 lo aplicaba: `skillstate` 44/44. Haiku 5.5, en muchos episodios, lo
declara no verificable y «marca la discrepancia» sin tocar su mapa de ocupación (traza
`skillstate_s6_r0`, paso 14: «COR-9898 is not a defined event type and I can't verify its
claim, so I won't change occupancy»). Ese episodio falla los 12 dependientes por eso, no por la
compactación: el aviso y la decisión de ignorarlo ocurren antes de compactar.

Consecuencia: **en Haiku 5.5, la sonda C mide sobre todo si el modelo cree el aviso, no qué
conserva cada forma de compactar.** Juez ciego (`experiments/juez_aviso.py`, Sonnet 5.5, por
suscripción; `juez_aviso.json` en cada directorio): Haiku rechaza el aviso en 24 de 36
episodios, lo acepta en 11 y 1 queda sin decidir. Revisados a mano 5 veredictos: correctos.

**No sabemos si Luna acepta el aviso.** Codex solo devuelve `Action: Wait({})`, sin
razonamiento, así que el juez marca los 18 episodios como UNCLEAR. (Una versión anterior de
este documento decía que Luna lo aceptaba; salía de no encontrar palabras de rechazo en un
texto vacío.) El 6 de 8 de `hybrid_lookup` con Luna no es, por tanto, una medida limpia de
la compactación. Lo que sí se ve en las trazas: Luna no escribe razonamiento, así que el
híbrido no conserva «sus líneas», sino la primera línea de cada evento, y la del aviso ya
lleva `shelf=0 | … | shelf_is_now=empty` (traza `hybrid_lookup_s17_r0`, paso 15).

## Fallo de diseño de la sonda C (afecta también al bloque 1)

El aviso corrige la colocación del paso 0 (`corrects_step=0`, `putaway_never_completed`).
En **todas** las seeds medidas, ese palé se envió después desde la misma estantería y la
estantería se rellenó con otro antes del aviso (`experiments/` → comprobación con la
política correcta):

| seeds | toques a la estantería entre el paso 0 y el aviso |
|---|---|
| bloque 1, k=10: 4, 10, 6, 0, 1, 2 | todas: Ship y Store de otros palés (la 2, solo un Ship) |
| compactación, k=14: 17, 6, 10 | todas (p. ej. seed 17: Ship 5, Store 7, Ship 12, Store 13) |

El aviso dice que nunca se colocó un palé que ya se había enviado, y el entorno vacía una
estantería que tiene otro palé. Rechazarlo, como hace Haiku 5.5, es razonable. Esto pone en
duda la lectura del bloque 1 (estado explícito 93/93 frente a historia 18/82): el brazo de
estado solo ve la ocupación actual y no puede notar la contradicción; el de historia sí.

Arreglo, detrás de la bandera `--aviso-coherente` (por defecto apagada, para replicar lo
antiguo): el aviso corrige la **última** colocación en esa estantería y nombra el palé
(`pallet_id`, `sku`, `lot`). El estado verdadero y los pasos dependientes no cambian, solo el
texto (test `test_aviso_coherente_corrige_el_pale_que_hay_y_no_cambia_lo_medido`).

Además, la consulta tenía una asimetría: el resumen recibe qué conservar
(`PROMPT_RESUMEN`), la consulta solo la mecánica. `--guia-consulta` añade cuándo y cómo
consultar, sin nombrar el tipo de aviso. Rejilla 2: `experiments/rejilla_compaction_2.sh`.

## Pendiente

1. Rejilla 2: sonda C con el aviso coherente (Haiku y Luna), guía de consulta, y al final el
   aviso además declarado en EVENT TYPES.
2. Con Luna, la aceptación del aviso solo puede leerse por lo que hace después, no por lo que
   dice: definir esa lectura antes de usar sus cifras.
3. Revisar el artículo publicado sobre SKILL.state si la sonda C coherente cambia el resultado.
4. Los episodios con 0/0 dependientes (la trayectoria del agente no generó pasos dependientes)
   no cuentan ni a favor ni en contra; revisar si alguno oculta un fallo.
