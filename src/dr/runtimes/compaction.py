"""Brazos del experimento «compactar o consultar» (`docs/diseno-compactacion-vs-transcript.md`).

Todos acumulan historia como ReAct y la compactan en los mismos pasos (cada 15: antes de
mostrar los pasos 15, 30 y 45 en T=50). Lo unico que cambia entre brazos es que ven tras
compactar y si pueden consultar el transcript crudo:

| brazo            | tras compactar                                     | consulta |
|------------------|----------------------------------------------------|----------|
| `summary`        | resumen escrito por el modelo                      | no       |
| `fresh_lookup`   | nada: sesion limpia                                | si       |
| `hybrid_lookup`  | sus lineas literales; observaciones a una linea    | si       |
| `summary_lookup` | resumen                                            | si       |
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from dr.llm import Completion
from dr.runtimes.memory import PROMPT_RESUMEN, SUMMARY_MAX_TOKENS
from dr.types import Action, Observation

CADENCIA = 15
MAX_CONSULTAS = 2
MAX_LINEAS = 8

_PEDIDO_CONSULTA = re.compile(r"Lookup[*`\s]*:[*`\s]*(.+)", re.IGNORECASE)


def pedido_de_consulta(texto: str) -> str | None:
    """Palabras de la ULTIMA linea `Lookup: ...` de la respuesta, o None.

    Tolera negritas y comillas invertidas alrededor de la etiqueta, que es como lo
    escriben los modelos en Markdown; si no, una consulta legitima se leeria como paso
    sin accion y el brazo perderia por formato, no por metodo."""
    pedidos = _PEDIDO_CONSULTA.findall(texto)
    if not pedidos:
        return None
    return pedidos[-1].strip().strip("`*\"' ")


def palabras_de(consulta: str) -> list[str]:
    """Palabras de busqueda en minusculas, sin la puntuacion que las rodea.

    Se quita la puntuacion de los extremos (comillas, comas) pero no la interior: `=` y
    `-` forman parte de los identificadores del entorno (`shelf=12`, `SKU-D`)."""
    return [p for p in (w.strip("\"'`,;:.()[]{}").lower() for w in consulta.split()) if p]


@dataclass
class Consulta:
    """Registro de una consulta, para el runner: cuantas hubo y si la respuesta traia la
    linea portante (el aviso de cuarentena o de correccion) solo se sabe desde fuera."""
    paso: int
    consulta: str
    coincidencias: int
    lineas: list[str] = field(default_factory=list)


GUIA_CONSULTA = (
    "\nWHEN AND HOW TO LOOK UP\n"
    "After a compaction you no longer see the earlier events. Before an action that "
    "depends on the state of the warehouse, look up whatever could have changed or "
    "undone that state and is not in your current context: events outside the routine "
    "procedure, and the history of the specific shelf or SKU you are about to use. "
    "Search with specific words such as a shelf number, a SKU, an event type or an id; "
    "a single generic word only returns the most recent matches. If the lines you get "
    "disagree, the most recent step is the current fact."
)
"""Guia de uso, al nivel de PROMPT_RESUMEN ("anything you or the environment changed, and
anything that was undone"): el resumen recibia el que conservar y la consulta solo la
mecanica. Sin nombrar el tipo de aviso, para no dar la respuesta."""


def _contexto_de_consulta(brazo: str, guia: bool = False) -> str:
    """Lo que el modelo debe saber de la herramienta. Se anade al spec, en el system,
    para que forme parte del prefijo cacheable y sea identico en todos los pasos."""
    tras = ("the earlier history is replaced by a written summary, and the full detail is "
            "only available through lookup" if brazo == "summary_lookup" else
            "only your own replies are kept verbatim, every earlier event is cut to its "
            "first line, and the full detail is only available through lookup"
            if brazo == "hybrid_lookup" else
            "the earlier history is removed from your context and is only available "
            "through lookup")
    return (
        "\n\nTRANSCRIPT LOOKUP\n"
        f"Your context is compacted every {CADENCIA} steps. After a compaction, {tras}.\n"
        "The raw transcript of every event you have received and every reply you have "
        "given is kept verbatim and is never compacted. To search it, reply with a single "
        "line\n"
        "    Lookup: <words>\n"
        "instead of an action. You will receive up to "
        f"{MAX_LINEAS} transcript lines that contain ALL the words (case-insensitive), "
        "oldest first, each prefixed with the step it belongs to; if more lines match, "
        f"you get the {MAX_LINEAS} most recent ones. Then you are asked again for the same "
        f"event. You may look up at most {MAX_CONSULTAS} times per step; after that you "
        "must reply with an action. A lookup is not an action and is not your answer for "
        "the step."
        + (GUIA_CONSULTA if guia else "")
    )


class CompactingRuntime:
    """Base comun: historia como ReAct, compactacion periodica y consulta opcional.

    Dos registros distintos, a proposito:
    - `history`: lo que el modelo ve. Se compacta.
    - `transcript`: el registro crudo, append-only, con su paso. Nunca se compacta; es
      lo que busca `Lookup`. Solo guarda observaciones y respuestas finales: si
      guardara tambien las consultas y sus resultados, cada busqueda encontraria los
      ecos de las anteriores y llenaria las 8 lineas con ellos.
    """

    brazo = ""
    consulta = False

    def __init__(self, client, spec: str, cadencia: int = CADENCIA,
                 summary_max_tokens: int = SUMMARY_MAX_TOKENS,
                 guia_consulta: bool = False) -> None:
        self.client = client
        self.guia_consulta = guia_consulta
        self.spec = spec
        self.cadencia = cadencia
        self.summary_max_tokens = summary_max_tokens
        # Entradas (tipo, texto). El tipo lo usa el brazo hibrido para decidir que se
        # queda literal y que se reduce a una linea.
        self.history: list[tuple[str, str]] = []
        self.transcript: list[tuple[int, str]] = []
        self.pasos = 0
        self.compactaciones: list[int] = []
        self.consultas: list[Consulta] = []
        self.sin_accion_tras_consultas = 0
        # Un resumen truncado llega vacio (el CLI no da el texto parcial) y el brazo
        # pierde todo lo anterior por el tope, no por el metodo: se cuenta aparte.
        self.resumenes_truncados = 0

    # --- lo que cada brazo define -------------------------------------------------

    def _compactar(self) -> list[Completion]:
        """Sustituye la historia por lo que el brazo conserva. Devuelve las completions
        gastadas en ello, para que el runner las sume."""
        raise NotImplementedError

    def _bloque_compactado(self) -> list[str]:
        """Bloques que preceden a la historia viva (resumen, lineas hibridas)."""
        return []

    # --- comun ----------------------------------------------------------------------

    def _system(self) -> str:
        texto = f"Instructions:\n{self.spec}"
        return texto + (_contexto_de_consulta(self.brazo, self.guia_consulta) if self.consulta else "")

    def _prefijo(self) -> list[str]:
        # Troceado como ReAct: cada bloque es inmutable una vez escrito, que es lo que
        # permite cachear el prefijo con un cliente que marque puntos de corte.
        if self.compactaciones and self.consulta:
            cabecera = (f"History since the last compaction (step {self.compactaciones[-1]}; "
                        "earlier steps only via Lookup):\n")
        elif self.compactaciones:
            cabecera = f"History since the last compaction (step {self.compactaciones[-1]}):\n"
        else:
            cabecera = "History:\n"
        return self._bloque_compactado() + [cabecera] + [
            f"{_ETIQUETAS[tipo]}: {texto}\n" for tipo, texto in self.history]

    def _instruccion(self, consultas_hechas: int) -> str:
        if not self.consulta:
            return "Generate your next reasoning and action (format 'Action: <cmd>'):"
        if consultas_hechas >= MAX_CONSULTAS:
            return (f"You have used your {MAX_CONSULTAS} lookups for this step. Reply now "
                    "with your reasoning and action (format 'Action: <cmd>'):")
        return ("Generate your next reasoning and action (format 'Action: <cmd>'), or reply "
                "'Lookup: <words>' to search the raw transcript:")

    def act(self, observation: Observation) -> tuple[Action | None, list[Completion]]:
        completions: list[Completion] = []
        if self.pasos and self.pasos % self.cadencia == 0 and self.pasos not in self.compactaciones:
            completions += self._compactar()
            self.compactaciones.append(self.pasos)
        # La observacion entra en el transcript ANTES de poder consultarlo: el modelo
        # puede buscar en el evento que tiene delante, igual que lo ve.
        self._al_transcript(observation.step, f"Observation: {observation.render()}")
        pares: list[tuple[str, str]] = []
        accion: Action | None = None
        respuesta = ""
        for consultas_hechas in range(MAX_CONSULTAS + 1):
            user = (f"Latest Observation: {observation.render()}\n"
                    + "".join(f"Your lookup: {q}\n{r}\n" for q, r in pares)
                    + self._instruccion(consultas_hechas))
            completion = self.client.complete(system=self._system(), user=user,
                                              cache_prefix=self._prefijo())
            completions.append(completion)
            respuesta = completion.text
            accion = Action.parse(respuesta)
            pedido = pedido_de_consulta(respuesta) if self.consulta else None
            if accion is not None or pedido is None or consultas_hechas >= MAX_CONSULTAS:
                if accion is None and pedido is not None:
                    self.sin_accion_tras_consultas += 1
                break
            pares.append((pedido, self._buscar(observation.step, pedido)))
        self.history.append(("obs", observation.render()))
        for pedido, resultado in pares:
            self.history.append(("lookup", pedido))
            self.history.append(("resultado", resultado))
        self.history.append(("respuesta", respuesta))
        self._al_transcript(observation.step, f"Reasoning & Action: {respuesta}")
        self.pasos += 1
        return accion, completions

    def _al_transcript(self, paso: int, texto: str) -> None:
        for linea in texto.splitlines():
            if linea.strip():
                self.transcript.append((paso, linea))

    def _buscar(self, paso: int, consulta: str) -> str:
        """Hasta 8 lineas del transcript con TODAS las palabras, en orden cronologico.

        Si coinciden mas, se devuelven las 8 mas recientes: con las 8 primeras, una
        correccion posterior al registro original quedaria fuera precisamente cuando
        el registro original es lo que mas se repite, y eso sesgaria la sonda C."""
        palabras = palabras_de(consulta)
        if not palabras:
            self.consultas.append(Consulta(paso, consulta, 0))
            return "Lookup results: no search words given."
        coincidencias = [(p, linea) for p, linea in self.transcript
                         if all(w in linea.lower() for w in palabras)]
        elegidas = coincidencias[-MAX_LINEAS:]
        lineas = [f"step {p}: {linea}" for p, linea in elegidas]
        self.consultas.append(Consulta(paso, consulta, len(coincidencias), lineas))
        if not coincidencias:
            return f"Lookup results for '{consulta}': no matching lines."
        extra = (f", showing the {MAX_LINEAS} most recent" if len(coincidencias) > MAX_LINEAS
                 else "")
        return (f"Lookup results for '{consulta}' ({len(coincidencias)} matching lines{extra}, "
                "oldest first):\n" + "\n".join(lineas))

    def _resumir(self, previo: str) -> Completion:
        """Mismo prompt y mismo tope que `MemoryRuntime`: el resumen de este brazo no
        puede salir peor o mejor por un prompt distinto."""
        return self.client.complete(
            system=PROMPT_RESUMEN,
            user=f"Previous summary:\n{previo}\n\nNewly dropped turns:\n" + "\n".join(
                f"{_ETIQUETAS[tipo]}: {texto}" for tipo, texto in self.history),
            max_tokens=self.summary_max_tokens,
        )

    def state_size(self) -> int:
        return 0


_ETIQUETAS = {"obs": "Observation", "respuesta": "Reasoning & Action",
              "lookup": "Lookup", "resultado": "Lookup result"}


class SummaryRuntime(CompactingRuntime):
    """Compactacion por resumen, sin consulta: lo que hacen Claude Code y Codex."""

    brazo = "summary"
    consulta = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.summary = "(empty)"

    def _compactar(self) -> list[Completion]:
        completion = self._resumir(self.summary)
        self.resumenes_truncados += completion.truncated
        self.summary = completion.text
        self.history = []
        return [completion]

    def _bloque_compactado(self) -> list[str]:
        if not self.compactaciones:
            return []
        return [f"Summary of earlier steps (written at the last compaction):\n{self.summary}\n\n"]


class SummaryLookupRuntime(SummaryRuntime):
    """Resumen mas consulta del transcript crudo (Cursor)."""

    brazo = "summary_lookup"
    consulta = True


class FreshLookupRuntime(CompactingRuntime):
    """Sesion limpia en cada compactacion; el pasado solo existe via `Lookup`."""

    brazo = "fresh_lookup"
    consulta = True

    def _compactar(self) -> list[Completion]:
        self.history = []
        return []


def una_linea(texto: str) -> str:
    """Primera linea de una observacion. En el Warehouse es la que lleva el tipo de
    evento y los campos portantes; lo que sigue es la cola de auditoria."""
    return texto.split("\n", 1)[0]


class HybridLookupRuntime(CompactingRuntime):
    """Tras compactar: las lineas propias (razonamiento, accion, consultas) literales y
    cada observacion reducida a su primera linea (Woolford), mas consulta.

    Las lineas reducidas se acumulan entre compactaciones: el bloque compactado crece,
    pero mucho mas despacio que la historia entera."""

    brazo = "hybrid_lookup"
    consulta = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.compactadas: list[str] = []

    def _compactar(self) -> list[Completion]:
        for tipo, texto in self.history:
            if tipo in ("obs", "resultado"):
                self.compactadas.append(f"{_ETIQUETAS[tipo]}: {una_linea(texto)}\n")
            else:
                self.compactadas.append(f"{_ETIQUETAS[tipo]}: {texto}\n")
        self.history = []
        return []

    def _bloque_compactado(self) -> list[str]:
        if not self.compactaciones:
            return []
        return ["Compacted history (your own replies verbatim, events cut to one line):\n",
                *self.compactadas, "\n"]


BRAZOS = {
    "summary": SummaryRuntime,
    "fresh_lookup": FreshLookupRuntime,
    "hybrid_lookup": HybridLookupRuntime,
    "summary_lookup": SummaryLookupRuntime,
}
