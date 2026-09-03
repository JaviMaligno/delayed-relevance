"""Software Repository: el segundo entorno de SkillExecBench (su §4.1).

Grafo relacional de ramas, PRs y estados de CI. A diferencia de Warehouse, donde cada
estanteria es independiente, aqui **una sola accion altera el estado de varias
entidades**: mergear una PR invalida el CI de todas las PRs que apuntan a la misma
rama. Esa densidad de dependencias es lo que el paper dice que lo distingue, y es lo
que lo hace util como control: si un hallazgo aparece en los dos entornos, no es del
dominio.

Implementa el mismo protocolo `Environment` que Warehouse, asi que los cuatro runtimes
y las dos sondas funcionan sin tocarlos.

CONTROL DE DIFICULTAD SUPERADO: la regla portante se activa en el 50% de los merges a
T=50 y el 40% a T=25, con el 68% de eventos accionables. Un agente que la ignore cae de
forma medible. La primera version generaba por sesgo aleatorio y daba entre 5% y 22%
segun el horizonte, que es un entorno que no discrimina; se reescribio el generador
para construir el guion DESDE EL RESULTADO.

Decisiones tomadas con lo aprendido en el bloque 1:
  - la metrica es un promedio sobre eventos accionables, nunca un acierto puntual;
  - los contratos del entorno (que invalida que) se DECLARAN en la especificacion, no
    se dejan a que el modelo los adivine;
  - la densidad de contexto se iguala con la de Warehouse, ya calibrada contra el paper.
"""
from __future__ import annotations

import random

from dr.types import Action, Observation

# Dos ramas, no cinco: con cinco, dos PRs abiertas rara vez coincidian en la misma y
# la regla de invalidacion apenas se activaba (6 de 37 merges). Un entorno donde la
# regla portante casi nunca aplica no discrimina entre runtimes: mide otra cosa.
RAMAS = ["main", "develop"]
AUTORES = ["dev_alba", "dev_bruno", "dev_carmen", "dev_diego", "dev_elena"]
SUITES = ["unit", "integration", "e2e", "contract", "smoke"]
EQUIPOS = ["plataforma", "pagos", "identidad", "datos"]
ETIQUETAS = ["ninguna", "revisado", "sin_incidencias", "cambio_menor", "rutinario"]


def _cola_auditoria(rng: random.Random) -> str:
    """Metadatos no portantes. Iguala la densidad de contexto de Warehouse."""
    return (
        f"\n  evento_id=EVT-{rng.randint(100000, 999999)} "
        f"| registrado=2026-09-{rng.randint(10, 28)}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z "
        f"| origen={rng.choice(['ci-runner-a', 'ci-runner-b', 'webhook', 'cli'])} "
        f"| version_esquema={rng.randint(3, 9)}.{rng.randint(0, 9)} "
        f"| latencia_ms={rng.randint(5, 900)} | reintentos={rng.randint(0, 3)}\n"
        f"  equipo={rng.choice(EQUIPOS)} | revisores={rng.randint(1, 4)} "
        f"| comentarios={rng.randint(0, 25)} | lineas_anadidas={rng.randint(5, 900)} "
        f"| lineas_borradas={rng.randint(0, 400)} | ficheros={rng.randint(1, 30)}\n"
        f"  runner={rng.choice(['linux-x64', 'linux-arm', 'macos-14'])} "
        f"| duracion_s={rng.randint(30, 1800)} | cache_hit={rng.choice(['true', 'false'])} "
        f"| artefactos={rng.randint(0, 6)} | cobertura_pct={rng.uniform(60, 99):.1f}\n"
        f"  politica_merge=squash | firma_verificada=true | rama_protegida=true "
        f"| etiqueta={rng.choice(ETIQUETAS)} | fin_registro=true"
    )


class Repo:
    """Ramas, PRs y CI. Cada PR apunta a una rama y tiene un estado de CI.

    Regla portante y unica fuente de dificultad: **mergear una PR invalida el CI de
    todas las demas PRs abiertas que apuntan a la misma rama**. Para actuar bien hay
    que recordar que PRs hay abiertas, a que rama apunta cada una y cual tiene el CI
    en verde ahora mismo — informacion que solo existe en la historia acumulada.
    """

    def __init__(self, horizon: int, seed: int) -> None:
        self.horizon = horizon
        self.seed = seed
        # pr -> {"rama": str, "ci": "verde"|"rojo"|"pendiente", "abierta": bool}
        self.prs: dict[str, dict] = {}
        self.step_index = 0
        self.dependent_step: int | None = None
        self.invalidation_from: int | None = None
        self.script: list[Observation] = self._build_script()

    def _build_script(self) -> list[Observation]:
        """Construye el guion DESDE EL RESULTADO, no por sesgo aleatorio.

        La unidad es un ciclo de dos PRs sobre la misma rama:
          1. se abre A            -> RunTests
          2. CI de A en verde     -> Approve
          3. se abre B            -> RunTests
          4. CI de B en verde     -> Approve
          5. se pide integrar A   -> Merge   (valido; INVALIDA a B)
          6. se pide integrar B   -> RunTests (la regla portante: B ya no esta verde)

        Dos solicitudes de merge por ciclo y exactamente una exige recordar la regla:
        50% por construccion, y estable en cualquier horizonte. Generar por sesgo
        aleatorio daba entre el 5% y el 22% segun el horizonte, que es un entorno que
        no discrimina.
        """
        rng = random.Random(self.seed)
        script: list[Observation] = []

        def telemetria(paso: int) -> Observation:
            texto = (
                f"EVENTO telemetria | metrica={rng.choice(['cola_ci', 'uso_runners', 'latencia_git'])} "
                f"| valor={rng.uniform(1, 200):.1f} | estado=nominal "
                f"| ventana=15m | requiere_accion=false\n"
                f"  panel=infra | umbral_superado=false | guardia={rng.choice(AUTORES)}"
                + _cola_auditoria(rng)
            )
            return Observation(step=paso, text=texto, actionable=False)

        def abrir(paso: int, pr: str, rama: str) -> Observation:
            texto = (
                f"EVENTO pr_abierta | pr={pr} | rama_destino={rama} "
                f"| autor={rng.choice(AUTORES)} | commits={rng.randint(1, 12)} "
                f"| estado_ci=pendiente | borrador=false | conflictos=ninguno\n"
                f"  titulo=cambio_rutinario_{rng.randint(100, 999)} "
                f"| base_sha={rng.randint(10**7, 10**8):x} "
                f"| head_sha={rng.randint(10**7, 10**8):x} "
                f"| aprobaciones={rng.randint(0, 3)} | bloqueada=false"
                + _cola_auditoria(rng)
            )
            return Observation(step=paso, text=texto, actionable=True)

        def ci_ok(paso: int, pr: str) -> Observation:
            texto = (
                f"EVENTO ci_finalizado | pr={pr} | resultado=exito "
                f"| suite={rng.choice(SUITES)} | fallos=0 "
                f"| duracion_s={rng.randint(60, 1200)}\n"
                f"  reintentos_ci=0 | flaky_detectado=false "
                f"| commit_probado={rng.randint(10**7, 10**8):x} "
                f"| entorno=ci-prod | paralelismo={rng.randint(1, 16)}"
                + _cola_auditoria(rng)
            )
            return Observation(step=paso, text=texto, actionable=True)

        def pedir_merge(paso: int, pr: str) -> Observation:
            texto = (
                f"EVENTO solicitud_merge | pr={pr} | solicitante={rng.choice(AUTORES)} "
                f"| urgencia={rng.choice(['normal', 'alta', 'baja'])} "
                f"| ventana_despliegue=abierta\n"
                f"  aprobaciones_requeridas=2 | aprobaciones_obtenidas=2 "
                f"| checklist_completo=true | rollback_preparado=true"
                + _cola_auditoria(rng)
            )
            return Observation(step=paso, text=texto, actionable=True)

        # Plantilla del ciclo: cada entrada produce un evento. `None` es telemetria,
        # que se intercala para diluir y para dar eventos no accionables.
        plantilla = ["abrir_a", "ci_a", None, "abrir_b", "ci_b", None,
                     "merge_a", None, "merge_b"]
        paso = 0
        while paso < self.horizon:
            rama = rng.choice(RAMAS)
            a = f"PR-{rng.randint(1000, 9999)}"
            b = f"PR-{rng.randint(1000, 9999)}"
            for etiqueta in plantilla:
                if paso >= self.horizon:
                    break
                if etiqueta is None:
                    script.append(telemetria(paso))
                elif etiqueta == "abrir_a":
                    script.append(abrir(paso, a, rama))
                elif etiqueta == "ci_a":
                    script.append(ci_ok(paso, a))
                elif etiqueta == "abrir_b":
                    script.append(abrir(paso, b, rama))
                elif etiqueta == "ci_b":
                    script.append(ci_ok(paso, b))
                elif etiqueta == "merge_a":
                    script.append(pedir_merge(paso, a))
                elif etiqueta == "merge_b":
                    script.append(pedir_merge(paso, b))
                paso += 1
        return script

    def reset(self) -> Observation:
        self.prs = {}
        self.step_index = 0
        return self.script[0]

    def observe(self) -> Observation:
        return self.script[self.step_index]

    @property
    def done(self) -> bool:
        return self.step_index >= self.horizon

    @staticmethod
    def _campo(texto: str, nombre: str) -> str | None:
        for trozo in texto.split(" | "):
            clave, _, valor = trozo.partition("=")
            if clave.strip() == nombre:
                return valor.strip()
        return None

    def expected_action(self) -> Action:
        obs = self.observe()
        if not obs.actionable:
            return Action(name="Wait")
        pr = self._campo(obs.text, "pr") or ""
        if "pr_abierta" in obs.text:
            return Action(name="RunTests", args={"pr": pr})
        if "ci_finalizado" in obs.text:
            return Action(name="Approve", args={"pr": pr})
        # solicitud_merge: solo si esa PR tiene el CI verde AHORA MISMO.
        estado = self.prs.get(pr)
        if estado is not None and estado["ci"] == "verde" and estado["abierta"]:
            return Action(name="Merge", args={"pr": pr})
        return Action(name="RunTests", args={"pr": pr})

    def apply(self, action: Action) -> None:
        obs = self.observe()
        pr = self._campo(obs.text, "pr")
        if action.name == "RunTests" and pr:
            rama = self._campo(obs.text, "rama_destino")
            actual = self.prs.get(pr, {})
            self.prs[pr] = {
                "rama": rama or actual.get("rama", "main"),
                "ci": "pendiente",
                "abierta": True,
            }
        elif action.name == "Approve" and pr and pr in self.prs:
            self.prs[pr]["ci"] = "verde"
        elif action.name == "Merge" and pr and pr in self.prs:
            rama = self.prs[pr]["rama"]
            self.prs[pr]["abierta"] = False
            # LA REGLA PORTANTE: mergear invalida el CI de las demas PRs de esa rama.
            for otra, estado in self.prs.items():
                if otra != pr and estado["abierta"] and estado["rama"] == rama:
                    estado["ci"] = "rojo"
        self.step_index += 1

    def spec(self) -> str:
        return (
            "PROCEDIMIENTO DE INTEGRACION CONTINUA\n"
            "\n"
            "Eres el controlador de integracion de un repositorio. Recibes un evento por\n"
            "paso y respondes con exactamente una accion.\n"
            "\n"
            "FORMATO DE EVENTO\n"
            "Registro de campos clave=valor separados por barras, empezando por el tipo.\n"
            "La mayoria de campos son metadatos operativos que NO afectan a tu accion\n"
            "(autor, equipo, revisores, duracion, cobertura, runner, etiqueta...). Lee\n"
            "primero el tipo y despues solo los campos que el procedimiento menciona.\n"
            "\n"
            "TIPOS DE EVENTO\n"
            "  pr_abierta      - una PR nueva. Campos portantes: pr, rama_destino.\n"
            "  ci_finalizado   - la CI de una PR termino con exito. Campo portante: pr.\n"
            "  solicitud_merge - alguien pide integrar una PR. Campo portante: pr.\n"
            "  telemetria      - lectura de estado. Ningun campo portante.\n"
            "\n"
            "ACCIONES\n"
            '  RunTests({"pr": "<PR>"})  - lanzar la CI de esa PR. Su estado pasa a\n'
            "      pendiente.\n"
            '  Approve({"pr": "<PR>"})   - registrar que la CI paso. Su estado pasa a\n'
            "      verde.\n"
            '  Merge({"pr": "<PR>"})     - integrar la PR. Solo es correcto si esa PR\n'
            "      tiene el CI EN VERDE en este momento.\n"
            '  Wait({})                  - el evento no requiere accion.\n'
            "\n"
            "PROCEDIMIENTO\n"
            "  1. En pr_abierta: RunTests sobre esa PR.\n"
            "  2. En ci_finalizado: Approve sobre esa PR.\n"
            "  3. En solicitud_merge: si esa PR esta en verde AHORA, Merge. Si no lo\n"
            "     esta — porque nunca lo estuvo o porque se invalido — RunTests para\n"
            "     volver a lanzarla.\n"
            "  4. En telemetria: Wait({}).\n"
            "\n"
            "LA REGLA QUE HACE ESTO DIFICIL\n"
            "**Integrar una PR invalida el CI de todas las demas PRs abiertas que apuntan\n"
            "a la misma rama de destino.** Sus estados pasan de verde a rojo, sin que\n"
            "llegue ningun evento avisandolo. Es decir: el estado verde de una PR puede\n"
            "dejar de ser cierto por una accion tuya sobre OTRA PR, y ningun evento\n"
            "posterior te lo recordara.\n"
            "\n"
            "Para decidir bien necesitas saber, en todo momento: que PRs siguen abiertas,\n"
            "a que rama apunta cada una, y cual tiene el CI en verde ahora. Nada de eso\n"
            "viene en el evento que estas leyendo.\n"
            "\n"
            "SALIDA\n"
            "Emite exactamente una accion por paso, con un objeto JSON como unico\n"
            "argumento. Manten tu razonamiento por debajo de 60 palabras: una respuesta\n"
            "larga se corta antes de escribir la accion, y un paso sin accion cuenta como\n"
            "accion incorrecta.\n"
        )

    def schema_fields(self) -> list[str]:
        return ["prs_abiertas", "ultimo_evento"]
