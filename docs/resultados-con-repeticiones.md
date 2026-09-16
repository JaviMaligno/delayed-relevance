# Lo que queda en pie cuando se repite cada celda

Este documento existe porque la primera tanda de resultados con `gemini-3-flash-preview`
se midió con **una tirada por celda**, amparada en una premisa del spec —que con greedy
las seeds son instancias del entorno— que luego se midió y resultó falsa. Al repetir,
**tres de las cuatro conclusiones que se habían escrito se cayeron**.

Todas las cifras de aquí son medias sobre 15 o más tiradas, con la barra de error
calculada sobre las tiradas y no sobre las medias por seed (spec §1.3, enmienda).

## 1. El entorno no explica nada

I4 encontró tres diferencias entre nuestro Warehouse y su Apéndice B. Las tres están
cerradas detrás de banderas y ninguna mueve a ReAct:

| Condición (ReAct, T=200, tope 8192) | Tiradas | Score |
|---|---|---|
| Línea base | 15 | 0,905 ± 0,070 |
| Entorno del Algoritmo 2 (mantenimiento + rechazo + sin telemetría) | 19 | 0,913 ± 0,072 |

Diferencia **+0,008**, 0,3 errores estándar. Cero.

> **Qué se afirmó antes y por qué era falso.** Se reportó un efecto de −5,8 puntos y
> «las cinco seeds bajan». Comparaba contra una línea base medida con **tope de salida
> 600** mientras la condición nueva iba a 8192, y ambas columnas tenían una tirada por
> seed. Al igualar el tope y repetir, el efecto desaparece.

## 2. El ruido denso sí degrada, pero no gradualmente

| Ruido (eventos/turno) | Nuestro (15 tiradas) | Suyo |
|---|---|---|
| 0 | 0,961 ± 0,037 | 0,88 |
| 5 | 0,952 ± 0,066 | 0,68 |
| 20 | 0,959 ± 0,056 | 0,61 |
| 50 | 0,859 ± 0,121 | 0,53 |

De 0 a 50: **−0,103, 3,1 errores estándar**. La suya: −0,350.

Los niveles 0, 5 y 20 son el mismo número. Todo el efecto está en el salto a 50, y lo
que más cambia no es la media sino la **dispersión**, que se triplica: con 50
distractores el modelo no es peor de forma estable, es errático.

> **Qué se afirmó antes.** Que la degradación era «monótona en el ruido» (0,976 →
> 0,924 → 0,864). Era el orden accidental de tres tiradas sueltas separadas por menos
> de una desviación típica.

## 3. Memory replica; ReAct no

| Celda | Nuestro | Suyo | Diferencia |
|---|---|---|---|
| Memory, T=100 | 0,886 ± 0,105 (15) | 0,87 | +0,016 (0,6 SE) |
| ReAct, T=200 | 0,913 ± 0,072 (19) | 0,74 | **+0,173 (7 SE)** |
| SKILL.state, T=200 | 1,000 ± 0,000 | 0,94 | +0,060 |

**El resultado del proyecto es la última fila de la tercera columna.** Con su modelo,
sus ajustes de decodificación, su entorno reconstruido en las tres dimensiones que su
propio apéndice permite cotejar y densidad de contexto por encima de la suya, el
runtime que arrastra historia completa **no se degrada como ellos reportan**.

Lo que sí se reproduce es la dirección de su tesis: el estado explícito no degrada
(1,000 en todas las condiciones medidas) y el transcript sí, cuando el ruido aprieta.

## 4. La adjudicación de los fallos

De 45 fallos examinados con la respuesta del modelo delante (cuatro trazas completas de
ReAct en T=200):

| Clase | Nº | % |
|---|---|---|
| Estado: estantería equivocada | 30 | 67 % |
| Acción equivocada | 7 | 16 % |
| Copia: campos del evento | 7 | 16 % |
| No parsea | 1 | 2 % |

Dos tercios son el modo de fallo que el experimento mide. La copia —consecuencia de
nuestro JSON de cuatro campos frente a su acción posicional de dos, hueco 4 de I4— es
el 16 %: existe, se declara, y no manda.

Los fallos **encadenan**, y eso explica la cola izquierda de la distribución. Ejemplo
literal de una traza: en el paso 12 el modelo guarda el SKU de otro palé; en el paso 16
afirma «Shelf 0 (SKU-F, stored in step 12)» cuando él mismo guardó SKU-B ahí.

## 5. Lo que este documento no puede decir

- **No se ha probado que el Apéndice B no tenga efecto.** Se ha medido que, con la
  potencia disponible, no se detecta uno por encima de ~5 puntos.
- **`gemini-3-flash-preview` puede no ser su `Gemini-3-Flash`**. Riesgo declarado desde
  el principio; el ID que responde se registra en cada corrida.
- **Un entorno reimplementado no es su entorno.** Se ha igualado lo que su apéndice
  permite cotejar; el hueco 5 de I4 —qué hueco elige su ground truth en `Store`— sigue
  sin respuesta de los autores.
