# I4 — Nuestro Warehouse contra el Apéndice B del paper

Cotejo línea a línea de `src/dr/envs/warehouse.py` contra la especificación que el
paper sí publica: **Apéndice B.1** (diseño del entorno), **Algoritmo 2** (generador) y
**Apéndice A.4** (prompt del runtime). Hasta ahora la réplica se declaraba «a ciegas»;
no lo es, y esto es lo que se puede comprobar sin una sola llamada a la API.

Se hace **antes de R1** porque R1 se interpreta contra este documento: si Gemini no
degrada en nuestro entorno, la explicación candidata es que el entorno sea más fácil, y
la lista de abajo es donde hay que buscarla.

## Lo que coincide

| Elemento | Ellos (B.1 / Alg. 2) | Nosotros | |
|---|---|---|---|
| Estanterías | 500, `shelf_0`…`shelf_499`, una o ninguna pieza | `SHELF_COUNT = 500` | ✅ |
| Espacio de acciones | `Store`, `Ship`, `Move`, `Wait` | los cuatro, en `apply()` | ✅ |
| `Ship` destruye la pieza | sí | `self.shelves[shelf] = None` | ✅ |
| Métrica | acciones válidas ejecutadas / eventos accionables | `score()` en `metrics.py`, idéntica | ✅ |
| Generador determinista por seed | `rng = Random(seed)`, misma secuencia para todos los brazos | `_build_script` con `random.Random(self.seed)`, guion fijado antes del episodio | ✅ |
| Ground truth al margen del agente | `UpdateGroundTruth` en el generador | el guion se construye entero antes de correr | ✅ |

## Lo que no coincide

Ordenadas por sospecha de efecto sobre la degradación de ReAct, que es lo que R1 mide.

### 1. No hay eventos de mantenimiento, así que `Move` nunca se ejerce ⚠️ *el hueco serio*

Su Algoritmo 2 sortea entre `Receive`, `Order` y `Maintenance` —las tres accionables— y
`Maintenance required on [shelf]` obliga a **reubicar**: hay que saber a la vez dónde
está la pieza y qué estantería está libre. Nuestro `_build_script` sortea entre
`inbound_pallet`, `outbound_order` y `telemetry`: **`Move` está implementado y jamás se
pide**.

Es la única acción del espacio que cruza dos partes del estado en un solo paso, y es
justo el tipo de decisión donde un transcript acumulado debería estorbar más que un
estado explícito. Si nuestro entorno es más fácil que el suyo, esta es la primera
candidata.

### 2. Una acción inválida no se rechaza: se aplica ⚠️

Ellos: *«Invalid actions (e.g., storing an item on an occupied shelf) return a local
error observation and reject the state transition»*, y `Store` valida que la estantería
esté vacía antes de colocar.

Nosotros: `apply()` valida el **rango** del índice y nada más. Un `Store` sobre una
estantería ocupada **sobrescribe** el contenido en silencio, y no existe la observación
de error local en ningún punto del entorno.

El signo del efecto no es obvio y por eso no se puede despachar: su rechazo protege el
mundo y devuelve señal correctiva al agente; nuestra sobrescritura corrompe el mundo y
no avisa. Lo segundo debería castigar más a quien lleva mal la cuenta, no menos — pero
también borra la evidencia del error en pasos posteriores.

### 3. Nuestro caso base lleva dentro su Experimento 2 ⚠️

Nuestra tercera familia de evento, `telemetry`, **no** está en su Env 1: es literalmente
su **ruido del Apéndice C** (telemetría de robots, sensores, OCR de cámara), que ellos
inyectan solo en el Experimento 2 y de otra forma — *anexado a la observación de un
evento real*, bajo una cabecera `--- BACKGROUND TELEMETRY ---`, explícitamente
`Non-State-Altering`.

En nuestro entorno es un **paso propio y no accionable**, que queda fuera del
denominador del score. Consecuencias: nuestro caso base no es su caso base (mezcla Exp 1
con algo de Exp 2), el 69–74 % de eventos accionables medido en §1 de los resultados
sale de aquí, y el ruido no ejerce la presión que ejerce el suyo, porque no compite con
una decisión dentro del mismo paso.

### 4. Las acciones llevan cuatro campos, no dos

Ellos: `Store <item_id> <empty_shelf_id>`, texto posicional. Nosotros:
`Store({"shelf": 3, "sku": "...", "units": 7, "lot": "L-1234"})`, JSON, con `units` y
`lot` que hay que copiar bien del evento o la acción cuenta como fallida.

Esta diferencia va **en contra** de la hipótesis de «nuestro entorno es más fácil»: hay
más que acertar por acción. Conviene decirlo en la misma frase que las tres de arriba.

### 5. Reglas inventadas para desambiguar

- **SKU repetible.** En el suyo cada estantería guarda *un identificador de pieza*;
  en el nuestro los SKU se repiten, así que `Ship` necesita una regla: la estantería de
  número más bajo que lo contenga. Está declarada en `spec()`, pero es nuestra.
- **Qué hueco elige el ground truth en `Store`.** El suyo llama a `FindEmptyShelves` y
  no dice cuál toma; el nuestro toma el libre más bajo. Si el suyo elige otro, la tarea
  no es la misma. **Esto sí hay que preguntárselo a los autores.**

### 6. Verbosidad de las observaciones — diferencia deliberada

Sus observaciones son una línea (`Customer ordered item_12`); las nuestras, registros de
cuatro líneas con veintitantos campos. Es intencionado: el emparejamiento es por
**densidad de contexto** (1,2–1,4x la suya), no por contenido, porque SkillExecBench no
es público. Se queda como está y se declara.

## Veredicto

El cotejo **no** invalida el bloque 1, pero acota qué se puede afirmar con él: lo medido
es un Warehouse emparejado en densidad, con el mismo espacio de acciones y la misma
métrica, al que le faltan **la familia de eventos que obliga a reubicar** y **el rechazo
de acciones inválidas**, y que trae ruido de su Experimento 2 dentro del caso base.

Recomendación, para el punto de control CP1 y no antes: implementar (1) y (2) detrás de
una bandera —`--apendice-b`— en vez de cambiar el entorno por debajo. Cambiarlo sin
bandera invalida de golpe todo lo ya medido y deja el proyecto sin línea base; con
bandera, R1 puede correrse en las dos variantes y la diferencia entre ellas **es** la
medida de cuánto pesaba el hueco.

Lo que no se decide aquí: si Gemini degrada en la variante actual, esta lista deja de
ser urgente y pasa a ser una nota de limitaciones.
