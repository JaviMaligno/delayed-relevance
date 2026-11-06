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
conserva cada forma de compactar.** Un clasificador por palabras clave (aproximado, no fiable
para cifras) marca rechazos en 1–4 de 6 episodios por brazo en Haiku y en ninguno en Luna.

Luna sí acepta el aviso, y ahí la sonda vuelve a medir compactación: `hybrid_lookup` aplica la
corrección en el primer paso dependiente en 5 de 6 episodios sin consultar nunca, frente a 0 de
5 de `summary`. Hipótesis sin comprobar: conserva literal su propia línea sobre el aviso.

## Pendiente

1. Clasificar con un juez LLM ciego, por episodio, si el agente aceptó el aviso en el paso del
   aviso; recontar la sonda C solo sobre episodios que lo aceptaron.
2. Comprobar en las trazas de Luna qué línea conserva `hybrid_lookup` tras compactar.
3. Opcional: repetir la sonda C en Haiku 5.5 declarando `correction_notice` en EVENT TYPES (cambia
   el entorno respecto al bloque 1; habría que declararlo).
4. Los episodios con 0/0 dependientes (la trayectoria del agente no generó pasos dependientes)
   no cuentan ni a favor ni en contra; revisar si alguno oculta un fallo.
