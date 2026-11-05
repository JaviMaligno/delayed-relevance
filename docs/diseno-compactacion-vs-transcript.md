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

Referencias **sin volver a pagar**, del bloque 1 con el mismo entorno, seeds y protocolo:
ReAct (transcript entero en contexto, sin compactar) y SKILL.state (estado explícito).

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
- **Sonda C, invalidación retroactiva**: un aviso corrige una colocación pasada. Seeds 4, 10 y 6
  (22 pasos dependientes por repetición). Métrica: pasos dependientes con la corrección aplicada.
  Hay que comprobar, sin llamar a la API, que al menos una compactación cae entre el aviso y los
  pasos dependientes en cada seed; si no, se mueve la cadencia y se declara.

Además, por brazo: **tasa de consulta** (pasos con al menos un `Lookup`), consultas que
devuelven la línea portante, truncamientos, pasos sin acción y coste efectivo con caché.

## Antes de gastar (gratis)

1. Tests de cada runtime con `FakeClient`.
2. **Suelo del sordo** por sonda y seed (ya existe para C).
3. **Agente perfecto que nunca consulta**: para `fresh_lookup` es el suelo; si su score se
   acerca al techo, la sonda no discrimina el brazo.
4. Densidad de contexto por brazo con `measure_density.py`.

## Modelos y presupuesto

- **Claude Haiku 4.5 por API**, el mismo del bloque 1, para que las referencias valgan.
  Sonda C: 3 seeds × 2 repeticiones × 4 brazos = 24 episodios. Sonda A: 12 × 4 = 48.
  Unos 72 episodios, **≈ 10-12 $ estimados**. El corredor corta al pasar de **15 $**
  acumulados.
- **GPT vía `codex exec`** (suscripción, sin coste de API), solo la sonda C y los brazos
  `summary`, `fresh_lookup` y `hybrid_lookup`: 18 episodios, unas 1.100 llamadas, unas 3 h en
  serie. Limitación declarada: Codex añade ~21k tokens de prompt de sistema propio en cada
  llamada, así que es otra condición, no el mismo arnés. Sin coste efectivo para este modelo.
- Una corrida cada vez, nunca dos en paralelo, lanzada con `exec` (ver README).

## Qué haría cambiar la conclusión

- Si `fresh_lookup` casi no consulta, el resultado mide la pereza del modelo, no el método. Se
  reporta la tasa de consulta junto al acierto, siempre.
- Si la consulta devuelve la línea vieja y la corrección y el modelo elige la vieja, es el
  mismo fallo del bloque 1 en otra forma, y es el hallazgo.
- Una diferencia menor que el suelo de ruido del bloque 1 (§0) no se reporta como efecto.
