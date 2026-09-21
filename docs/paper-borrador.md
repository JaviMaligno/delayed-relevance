# El runtime no es infraestructura: una réplica de SKILL.state

**Borrador.** Todas las cifras salen de mediciones de este repositorio, con traza por
paso y datos crudos en la rama `runs/table1-gemini-3-flash-preview-vertex`. Escrito en
español para revisión; la versión de arXiv habrá que traducirla.

---

## 1. Qué afirma el paper y qué medimos

[SKILL.state](https://arxiv.org/abs/2608.26263) sostiene que un agente que mantiene
**estado explícito** ejecuta procedimientos largos mucho mejor que uno que arrastra la
conversación entera, y que la diferencia crece con el horizonte. Su Tabla 1 lo enseña
con Gemini-3-Flash en un almacén simulado: ReAct cae de 0,90 a 0,74 entre 10 y 200
pasos mientras SKILL.state se queda en 0,94.

Nosotros reimplementamos su entorno desde la descripción del artículo —SkillExecBench
no es público— y medimos tres cosas:

1. **Si la escalera se reproduce** con su mismo modelo y sus mismos ajustes de
   decodificación (§3).
2. **Cuánto cuesta realmente cada runtime** cuando se cuenta dinero y no tokens (§4).
3. **Qué protege exactamente el estado explícito**, mediante dos sondas dirigidas a
   las limitaciones que el propio artículo declara y no mide (§5).

La conclusión corta: **su tesis se sostiene, su jerarquía casi, su magnitud no, y su
contabilidad de coste se invierte en cuanto se factura**. Y lo que más pesa en todo el
experimento no es ninguno de los métodos comparados, sino decisiones de implementación
del runtime que el artículo trata como neutras.

---

## 2. Fidelidad del entorno, y sus diferencias declaradas

El artículo publica el diseño del entorno (Apéndice B.1), el pseudocódigo del generador
(Algoritmo 2) y los prompts (Apéndice A), así que el cotejo no es a ciegas.

**Coincide**: 500 estanterías de ocupación única, el espacio de acciones
(`Store`/`Ship`/`Move`/`Wait`), la destrucción de la pieza en `Ship`, la métrica
(acciones válidas ejecutadas / eventos accionables) y el determinismo por seed.

**No coincidía, y se ha cerrado detrás de banderas** (`--apendice-b`,
`--sin-telemetria`):

| Diferencia | Qué se hizo |
|---|---|
| No generábamos eventos de mantenimiento, así que `Move` nunca se ejercía | Implementados: 6–11 por episodio de 50 pasos |
| Una acción inválida se aplicaba en vez de rechazarse | Rechazo con observación de error local, como su B.1 |
| Un tercio de nuestros pasos era telemetría no accionable | Retirada: su Algoritmo 2 no tiene familia no accionable |

**Cerrar las tres no cambia el resultado.** ReAct en T=200, con el mismo tope de salida
y 15 tiradas por condición: 0,905 ± 0,070 con el entorno original y 0,913 ± 0,072 con
el entorno corregido. Diferencia +0,008, **0,3 errores estándar**.

**Diferencias que quedan, declaradas**:

- **Nuestras acciones llevan cuatro campos** (`shelf`, `sku`, `units`, `lot`) frente a
  las suyas posicionales de dos. Hay más que acertar por acción, y va en contra de la
  hipótesis «nuestro entorno es más fácil». La adjudicación de fallos (§6) mide cuánto
  pesa: el 16 %.
- **Nuestras observaciones son más verbosas.** El emparejamiento es por **densidad de
  contexto**, no por contenido literal. En T=200, prompt medio de ReAct: 58.127 tokens
  frente a sus 48.007 — **por encima del suyo**.
- **Qué hueco elige su ground truth en `Store`** no está especificado. Nosotros tomamos
  el libre más bajo. Es la única diferencia que requiere preguntar a los autores.

---

## 3. La escalera de capacidad

Entorno fiel al Apéndice B, `gemini-3-flash-preview` vía Vertex, `temperature=0`,
`top_p=1` (sus ajustes), **15 tiradas por celda** (5 seeds × 3 repeticiones), 304
episodios con traza por paso. Entre paréntesis, su Tabla 1.

| T | ReAct | Memory | Stateful | SKILL.state |
|---|---|---|---|---|
| 10 | 0,993 ± 0,026 (0,90) | 1,000 ± 0,000 (1,00) | 1,000 ± 0,000 (1,00) | 1,000 ± 0,000 (1,00) |
| 25 | 0,955 ± 0,050 (0,92) | 0,987 ± 0,042 (0,99) | 1,000 ± 0,000 (1,00) | 1,000 ± 0,000 (1,00) |
| 50 | 0,936 ± 0,057 (0,88) | 0,953 ± 0,077 (0,93) | 0,996 ± 0,008 (0,94) | 1,000 ± 0,000 (0,96) |
| 100 | 0,960 ± 0,063 (0,84) | 0,839 ± 0,096 (0,87) | 0,995 ± 0,008 (0,91) | 1,000 ± 0,000 (0,94) |
| 200 | 0,913 ± 0,072 (0,74) | 0,810 ± 0,083 (0,84) | 0,912 ± 0,126 (0,88) | 1,000 ± 0,000 (0,94) |

Caídas de T=10 a T=200 (nuestra / suya): ReAct −0,080/−0,160 · Memory −0,190/−0,160 ·
Stateful −0,088/−0,120 · **SKILL.state 0,000/−0,060**.

**Qué se reproduce.** Su tesis central, y con margen: SKILL.state no falla **ni una vez
en 75 episodios** de hasta 200 pasos. Es el único brazo con caída cero; el suyo pierde
seis puntos. También se reproduce el orden general — los dos runtimes con estado
explícito por encima de los dos que reconstruyen del texto.

**Qué no se reproduce.** La magnitud: todos nuestros brazos degradan aproximadamente la
mitad. En T=200 nuestro ReAct queda **17 puntos por encima** del suyo, y la distancia
crece con el horizonte (+0,09 en T=10, +0,17 en T=200). No lo explican el modelo (es el
suyo), el razonamiento (medido a dos órdenes de magnitud, §6), el tope de salida, ni
ninguno de los tres huecos del entorno.

**Dónde se rompe su jerarquía.** Memory queda último en nuestro entorno y ellos lo
ponen por encima de ReAct. **Es una diferencia nuestra, no un hallazgo**: nuestro
resumidor comprime a 5.874 tokens de prompt medio en T=200 donde el suyo ocupa 84.364.
Su «Memory (Summary)» apenas resume; conserva casi tanto contexto como ReAct.

### El ruido denso (su Experimento 2)

T=50 fijo, distractores anexados a la observación bajo su cabecera, 15 tiradas por
nivel:

| Ruido (eventos/turno) | Nuestro ReAct | Suyo |
|---|---|---|
| 0 | 0,961 ± 0,037 | 0,88 |
| 5 | 0,952 ± 0,066 | 0,68 |
| 20 | 0,959 ± 0,056 | 0,61 |
| 50 | 0,859 ± 0,121 | 0,53 |

De 0 a 50 eventos: **−0,103, 3,1 errores estándar**. La suya, −0,350. **El efecto
existe y no es gradual**: 0, 5 y 20 son el mismo número; todo está en el salto a 50. Y
lo que más cambia no es la media sino la dispersión, que se triplica: con 50
distractores el modelo no es peor de forma estable, es **errático**.

---

## 4. La contabilidad con caché

El artículo compara **tokens**; quien paga la factura compara **dinero**. Un transcript
append-only cachea casi entero; un bloque de estado que muta invalida el prefijo.

Medido en Anthropic (Haiku 4.5, T=50, 3 seeds, caché activa):

| Runtime | Score | Tokens brutos | Coste efectivo | Ahorro por caché |
|---|---|---|---|---|
| ReAct | 1,00 | 826k | **152k** | **82 %** |
| Stateful | 1,00 | 873k | 873k | 0 % |
| Memory | 0,87 | 313k | 313k | 0 % |
| SKILL.state | 1,00 | **109k** | 109k | 0 % |

**La ventaja de SKILL.state pasa de 7,54x en tokens a 1,39x en factura**, y el orden se
invierte: por tokens SKILL.state < Memory < ReAct < Stateful; por dinero SKILL.state <
**ReAct** < Memory < Stateful.

Tres consecuencias:

1. **Comprimir contexto y cachear contexto están en conflicto.** Todo método que
   comprime reescribe el prefijo, y reescribir el prefijo mata la caché.
2. **El orden del prompt es una variable de coste de primer orden.** ReAct y Stateful
   envían casi lo mismo; ReAct pone la historia primero y ahorra 82 %, Stateful la pone
   tras un bloque mutante y ahorra 0 %. **El mismo contenido, en distinto orden, cuesta
   5,7 veces más** — y su plantilla del Apéndice A.3 lo coloca en el peor sitio.
3. **Reconcilia una anomalía de su tabla.** Su columna de totales queda ~3,5x por
   debajo de horizonte × prompt medio. Con caché encaja: sus totales serían facturados
   y su prompt medio, bruto.

### Y no es extrapolable entre proveedores

Medido en Vertex con `gemini-3-flash-preview`:

- **No hay caché implícita.** Cuatro llamadas idénticas con 20.016 tokens de prefijo y
  el campo `cachedContentTokenCount` **ni siquiera aparece** en la respuesta.
- **La explícita funciona** —20.013 de 20.016 tokens descontados— pero **no sirve para
  ReAct**: su prefijo crece en cada paso, así que habría que recrear el objeto de caché
  cada turno, pagando la escritura, para cachear algo que no se va a repetir. Sirve para
  un bloque **fijo** y grande: el perfil de un procedimiento largo, no el de una
  historia acumulada.

Enunciado resultante, más fuerte que el inicial: **la ventaja de coste del estado
explícito no depende de la caché; el proveedor solo cambia cuánto la disimula.**

---

## 5. Dos sondas sobre sus limitaciones declaradas

El artículo declara dos limitaciones sin medirlas. Las medimos.

### L1: el estado explícito solo protege lo previsto

Un hecho llega en el paso `t` y cambia la acción correcta en `t+40`. Sonnet 5, **misma
seed × 8 repeticiones**, cada seed es su propio control:

| Condición | Acierto en el paso dependiente | IC95 |
|---|---|---|
| Sin campo donde guardarlo | 12 % (3/24) | 4–31 % |
| Campo libre `notes` | 21 % (5/24) | 9–40 % |
| Campo del esquema que nombra el hecho | **75 %** (18/24) | 55–88 % |
| Recordatorio pegado a la observación | **83 %** (20/24) | 64–93 % |

Las condiciones se parten en dos grupos que no se tocan. **Dar sitio no basta: el sitio
tiene que decir qué guardar.** Un runtime de estado explícito protege contra lo que su
diseñador ya previó — que es exactamente la limitación L1, ahora con número.

> Esta medición **retiró** una recomendación anterior del propio proyecto. Con una
> tirada por seed, el campo libre daba 60 % y se había convertido en el consejo
> práctico («deja una escotilla en tu esquema»). Con repeticiones es falso.

### L2: invalidación retroactiva

Un hecho anunciado deja de ser cierto más tarde. Contado sobre **pasos dependientes**,
no episodios:

| Modelo | Runtime | Aplica la corrección |
|---|---|---|
| Haiku 4.5 | ReAct | 3/44 — 6,8 % |
| Haiku 4.5 | SKILL.state | **44/44 — 100 %** |
| Sonnet 5 | ReAct | 15/38 — 39,5 % |
| Sonnet 5 | SKILL.state | **49/49 — 100 %** |

**El estado explícito no falla una sola vez: 93 de 93.** La historia completa acierta 18
de 82. Y el fallo de ReAct es de todo o nada por escenario: en Haiku falla los 11 pasos
de un episodio, los 7 de otro, los 4 del tercero. No es un agente que se despiste; es un
agente impecable que **nunca actualizó un hecho**.

**Alcance declarado**: las dos sondas están medidas con Claude (Haiku 4.5 y Sonnet 5),
no con Gemini. Replicarlas en el tercer modelo está pendiente.

---

## 6. Instrumento y artefactos

Este es el apartado que distingue esto de un post, y el que más nos ha costado.

**Nueve artefactos catalogados** en el primer bloque, todos con la misma firma: un
contrato implícito entre runtime y modelo. El runtime asumía algo que nunca declaró, y
el resultado dependía de si el modelo acertaba la suposición. Los tres primeros
costaron rejillas enteras; **dos aparecieron en la auditoría previa a publicar, y ambos
habían producido un resultado escrito, con tablas e intervalos, listo para enviar**.

En este segundo bloque aparecieron cuatro más, y conviene enumerarlos porque son
transferibles:

1. **El greedy no garantiza reproducibilidad.** El protocolo asumía que con
   `temperature=0` las seeds son instancias del entorno y basta una tirada por celda.
   La misma celda repetida cinco veces da entre 0,830 y 0,960. **Tres conclusiones ya
   escritas se cayeron al repetir**: un efecto de entorno de −5,8 puntos que resultó
   ser +0,008, una curva de ruido «monótona» que resultó plana, y una estimación de
   ruido de once puntos que resultó ser una cola.
2. **La distribución tiene cola izquierda porque los fallos encadenan.** El ruido
   ordinario es de 0,006 (T=100) a 0,012 (T=200), pero una tirada suelta puede caer en
   0,83. Lo que obliga a repetir no es el ruido: son las colas.
3. **El corredor descartaba las respuestas del modelo.** Guardaba el score y los
   tokens, así que `correct=False` era un cero indistinguible: no se podía saber si el
   modelo perdió la cuenta del estado —lo que el experimento mide— o copió mal un campo
   del JSON. Con la respuesta guardada, la adjudicación de 45 fallos da **30 de estado
   (67 %), 7 de acción equivocada, 7 de copia (16 %), 1 sin parsear**.
4. **Un episodio truncado contado como completo.** La agregación contaba ficheros, no
   pasos; un episodio de 163 pasos de 200 entró en la media. El sesgo fue de dos
   milésimas, pero solo se descubrió porque se verificó por rutina.

Ejemplo de por qué la traza importa, literal de un episodio: en el paso 12 el modelo
guarda el SKU de otro palé; en el paso 16 afirma *«Shelf 0 (SKU-F, stored in step 12)»*
cuando él mismo guardó SKU-B ahí. **El error temprano contamina las decisiones
posteriores** — y eso, no el ruido de muestreo, es lo que produce la cola.

**Lo transferible**, y es la tesis de este apartado: el artículo trata el runtime como
infraestructura neutra —un operador de merge, un formato de parche, un esquema, un orden
de prompt— cuando cada una de esas decisiones no documentadas vale entre 20 y 90 puntos,
**más que la diferencia entre los métodos que compara**.

**Artefactos del repositorio**: entorno con banderas de fidelidad, traza por paso en el
esquema del lector, verificador de completitud, medidor de densidad sin llamar a la API,
contador de truncamientos, checkpoint por episodio y contabilidad de caché de punta a
punta.

---

## 7. Limitaciones

- **`gemini-3-flash-preview` puede no ser su `Gemini-3-Flash`.** Riesgo declarado desde
  el principio; el ID que responde se registra en cada corrida.
- **Un entorno reimplementado no es su entorno.** Se ha igualado lo que su apéndice
  permite cotejar, y las diferencias que quedan están en §2. La elección de hueco en
  `Store` sigue sin respuesta de los autores.
- **Memory no es comparable con el suyo.** Nuestro resumidor comprime cinco veces más.
  Lo medido es nuestra política de resumen, no «el resumen» como categoría.
- **No se ha probado que los huecos del entorno no tengan efecto**; se ha medido que,
  con la potencia disponible, no se detecta uno por encima de ~5 puntos.
- **Las sondas están medidas con Claude, no con Gemini.**
- **Un solo entorno.** El segundo (Software Repository) se retiró: no discriminaba entre
  runtimes y habría añadido ruido sin información.
- **SKILL.state en 1,000 sin varianza también significa que la tarea no discrimina por
  arriba.** Que no falle no prueba que sea infalible: prueba que aquí el techo es el
  techo.
