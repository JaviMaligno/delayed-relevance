# Medir el instrumento antes que el fenómeno

Notas de método de una réplica de [SKILL.state](https://arxiv.org/abs/2608.26263). Ocho
artefactos encontrados; el más caro no estaba en el código sino en cómo interpretábamos lo
medido. Esto es lo que habríamos querido saber antes de empezar.

---

## 1. La regla

**Antes de medir un fenómeno, mide cuánto se mueve tu instrumento cuando el fenómeno no
cambia.**

En un experimento con LLMs eso significa: fija el prompt byte a byte y repítelo N veces. Lo
que varíe es tu suelo de ruido. Ninguna diferencia por debajo de ese suelo es un resultado, y
sin conocerlo no sabes cuál es.

Nosotros lo hicimos el tercer día, después de construir media docena de conclusiones encima
de mediciones que no lo distinguían. El número, cuando llegó:

```
seed 0: 4/8 =  50%   OK X OK X OK X OK X
seed 1: 6/8 =  75%   X OK OK OK OK OK X OK
seed 2: 8/8 = 100%   OK OK OK OK OK OK OK OK
```

Mismo escenario, mismo prompt, ocho repeticiones. La seed 0 alterna acierto y fallo ocho veces
seguidas. **Cincuenta puntos de dispersión** entre escenarios que suponíamos equivalentes.

Con eso encima de la mesa, cualquier diferencia menor de ~30 puntos porcentuales medida con
escenarios distintos era ruido. Varias de nuestras conclusiones lo eran.

---

## 2. El error concreto: confundir escenario con réplica

Corríamos cinco escenarios por condición y tratábamos el resultado como `n=5`. No lo era:
cada escenario se corría **una vez**, así que cada medición era una tirada de una moneda con
sesgo desconocido. `n=5 escenarios` no es `n=5 mediciones de la condición` — mezcla dos
varianzas sin separarlas:

- **entre escenarios**: unos son más difíciles que otros;
- **dentro de un escenario**: el mismo prompt da resultados distintos.

Si la segunda es del orden de la primera, cambiar de escenario no aporta información propia y
la comparación mide ruido.

**El síntoma que lo delató**, y que tardamos en leer: dos corridas de la misma celda dieron la
misma tasa **fallando en escenarios distintos**. Si el escenario fuera lo que manda, fallarían
los mismos.

**El protocolo correcto es el contrario del intuitivo:** pocos escenarios y muchas
repeticiones por escenario, no muchos escenarios una vez cada uno. Cuesta más por celda y es
lo único que separa efecto de ruido.

---

## 3. Diseño pareado: el mismo escenario como su propio control

Comparar la condición A en los escenarios 0–9 contra la B en los escenarios 0–9, con una
tirada cada uno, compara dos muestras ruidosas. Comparar A y B **en el mismo escenario,
repetido**, hace que el escenario se cancele.

La diferencia no es cosmética. Nuestra tabla pareada final:

| escenario | sin campo | oráculo | recordatorio |
|---|---|---|---|
| 0 | 3/8 = 38% | 4/8 = 50% | 5/8 = 62% |
| 1 | **0/8 = 0%** | 6/8 = 75% | 7/8 = 88% |
| 2 | **0/8 = 0%** | 8/8 = 100% | 8/8 = 100% |

Los agregados (12%, 75%, 83%) dan el resultado. Pero solo el pareado enseña que **el efecto es
absoluto en los escenarios 1 y 2 y nulo en el 0**: la intervención no arregla un escenario que
ya es duro por otros motivos, rescata los que fallaban solo por eso. Ese matiz desaparece al
promediar escenarios distintos.

---

## 4. Señales de que estás midiendo tu instrumento

Cada una nos costó al menos un día.

**Números redondos con muestra pequeña.** Un 0% y un 100% con n=5 son la misma afirmación:
"no lo he medido suficiente". Nuestro 0% resultó ser 15% con n=20; un 1/3 resultó ser 82% con
n=22. En ambos casos habíamos empezado a construir la explicación antes de ampliar la muestra.

**La explicación mecánica prematura.** Ante un número raro, el instinto es explicarlo. Llegamos
a formular una hipótesis convincente sobre el estilo de parcheo de un modelo para justificar un
1/3 que era ruido. **Antes de explicar por qué dos condiciones difieren, comprobar que
difieren.**

**El intervalo imposible.** La fórmula normal da error estándar cero cuando p vale 0 o 1, y
produce intervalos como "100–100%". Usa Wilson.

**Un número que va en la dirección que te conviene.** El nuestro fue un "ahorro del 624%" con
coste negativo, por restar tokens cacheados de un total que ya los excluía. Si un resultado
apoya tu tesis y es raro, es sospechoso por partida doble.

**Un modelo mejor que rinde peor.** Sonnet 5 sacaba 0.477 donde Haiku sacaba 0.898. No era el
modelo: nuestro formato de parche era ambiguo y uno de los dos lo adivinaba bien. Habríamos
publicado "Sonnet 5 es peor con estado explícito", que es falso.

---

## 5. Instrumentación que se paga sola

Tres cosas que convirtieron artefactos de "una rejilla entera perdida" en "quince minutos".

**Medir el coste del experimento sin ejecutarlo.** El tamaño del prompt se calcula con un
oráculo local, sin una sola llamada a la API. Nuestra primera calibración gastó una rejilla
completa para descubrir que el entorno era tres veces más ligero que el del paper. Después esa
comprobación era gratis y de diez segundos. *Aviso*: la herramienta debe modelar la longitud de
respuesta del modelo, no solo la de las observaciones — la primera versión ignoraba eso y dio
por calibrado un entorno que estaba al doble.

**Contar los truncamientos.** Una respuesta cortada por el tope de salida parte el JSON y hace
fallar al método por el tope, no por el método. Sin contarlo, el artefacto se lee como
resultado. Cuando saltó el aviso, la comprobación fue inmediata: los episodios con
truncamientos puntuaban 0.82 y los limpios 1.00.

**Checkpoint por episodio.** Cada episodio se guarda al terminar y al relanzar se saltan los
hechos. Convierte cualquier caída —red, memoria, proceso huérfano— en una molestia en vez de
una pérdida. Lo teníamos en dos corredores de tres; el que no lo tenía perdió ocho episodios
pagados a la primera caída.

---

## 6. Contratos implícitos: el patrón de fondo

Siete de nuestros ocho artefactos tenían la misma forma. **El runtime asumía algo que nunca
declaró, y el resultado dependía de si el modelo acertaba la suposición.**

- La profundidad del operador de merge.
- Si esa profundidad se le dice al modelo (vale 27 puntos, y con interacción).
- La forma exacta del JSON esperado (un modelo la adivinaba, otro no).
- El presupuesto de salida del resumidor.
- El orden de los bloques en el prompt (vale un 82% de la factura).
- Si un hecho imprevisto tiene dónde guardarse.

Ninguna de esas decisiones aparece en el paper que replicábamos, y cada una mueve el resultado
más que la diferencia entre los métodos que compara. **Un runtime no es infraestructura neutra:
es un conjunto de contratos, y los que no escribes los rellena el modelo adivinando.**

La recomendación práctica que sale de aquí es barata: **escribe el contrato en el prompt**.
Cuánto vale una línea que diga cómo se aplica tu parche: 27 puntos de precisión y toda la
varianza.

---

## 7. Resumen operativo

1. Mide el ruido del instrumento **antes** que el fenómeno: prompt fijo, N repeticiones.
2. Pocos escenarios y muchas repeticiones, no al revés.
3. Compara en diseño pareado: el mismo escenario es su propio control.
4. No afirmes diferencias por debajo del suelo de ruido medido. En nuestro caso, ~30 puntos.
5. Ante un número extremo con muestra pequeña, amplía muestra antes de explicarlo.
6. Sospecha el doble de los resultados que te convienen.
7. Instrumenta los modos de fallo del corredor (truncamiento, desbordes, reintentos), no solo
   la métrica.
8. Checkpoint por episodio, siempre.
