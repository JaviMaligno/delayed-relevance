"""Repite UN episodio con la traza puesta, para poder explicar sus fallos.

La rejilla guarda el score; esto guarda la respuesta. Existe porque un `correct=False`
no dice si el modelo perdio la cuenta del estado -- lo que el experimento mide -- o si
copio mal un campo del JSON de accion, que es una diferencia de nuestra
reimplementacion contra su accion posicional de dos campos (hueco 4 de I4).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dr.envs.warehouse import Warehouse
from dr.llm import build_client
from dr.metrics import score
from dr.runner import run_episode


def episodio_ya_hecho(destino, horizonte: int) -> bool:
    """True si esa traza corresponde a un episodio COMPLETO y legible.

    Relanzar una cadena que se cayo -- por caducidad de sesion o por cuota -- no puede
    re-pagar lo ya medido. Pero una traza a medias no vale: su score seria el de un
    episodio que nunca termino, y un fichero cortado a mitad de linea, que es como
    queda si el proceso muere escribiendo, tampoco. La cabecera de condiciones no
    es un paso: contarla desplazaba el total y hacia re-pagar episodios enteros."""
    destino = Path(destino)
    if not destino.exists():
        return False
    try:
        filas = [json.loads(l) for l in destino.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
    except json.JSONDecodeError:
        return False
    pasos = [f for f in filas if f.get("kind") != "run_header"]
    return len(pasos) == horizonte



def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--horizon", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--runtime", required=True)
    p.add_argument("--model", default="gemini-3-flash-preview")
    p.add_argument("--provider", default="vertex")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--thinking-budget", type=int, default=None)
    p.add_argument("--apendice-b", action="store_true")
    p.add_argument("--sin-telemetria", action="store_true")
    p.add_argument("--ruido", type=int, default=0)
    p.add_argument("--summary-max-tokens", type=int, default=None,
                   help="Tope del resumidor de Memory. Sin la bandera, el de serie.")
    p.add_argument("--stateful-orden", default="estado_primero",
                   choices=["estado_primero", "historia_primero"])
    p.add_argument("--stateful-cache", action="store_true",
                   help="Marca la historia de Stateful como prefijo cacheable.")
    p.add_argument("--etiqueta", default="",
                   help="Sufijo del fichero de traza. Repetir la MISMA celda es\nla unica forma de medir el ruido de corrida a corrida, y sin etiqueta\ncada repeticion pisaria a la anterior.")
    p.add_argument("--out", default="results")
    args = p.parse_args()

    sufijo = f"_{args.etiqueta}" if args.etiqueta else ""
    destino = Path(args.out) / (f"adj_T{args.horizon}_{args.model}_{args.runtime}"
                                f"_s{args.seed}{sufijo}.jsonl")
    # Antes de construir el cliente: el de Vertex pide proyecto y token a gcloud, que
    # con el portatil cargado tarda minutos, y saltar lo ya hecho no puede costar eso.
    if episodio_ya_hecho(destino, args.horizon):
        print(f"ya hecho, se salta: {destino}", flush=True)
        return
    from replicate_table1 import build_runtimes

    cliente = build_client(args.model, args.provider, args.max_tokens,
                           thinking_budget=args.thinking_budget)
    env = Warehouse(horizon=args.horizon, seed=args.seed, apendice_b=args.apendice_b,
                    sin_telemetria=args.sin_telemetria, ruido=args.ruido)
    runtime = build_runtimes(True, True, args.summary_max_tokens, args.stateful_orden,
                             args.stateful_cache)[args.runtime](cliente, env)
    destino.unlink(missing_ok=True)
    print(f"adjudicando {args.runtime} T={args.horizon} seed={args.seed} -> {destino}",
          flush=True)
    resultados = run_episode(env, runtime, traza=destino, condiciones={
        "model": args.model, "provider": cliente.provider,
        "max_tokens": args.max_tokens, "thinking_budget": args.thinking_budget,
        "horizon": args.horizon, "seed": args.seed, "runtime": args.runtime,
        "apendice_b": args.apendice_b, "sin_telemetria": args.sin_telemetria,
        "ruido": args.ruido,
        "summary_max_tokens": getattr(runtime, "summary_max_tokens", None),
        "stateful_parser": (__import__("dr.runtimes.stateful", fromlist=["x"]).PARSER_VERSION
                            if args.runtime == "stateful" else None),
        "stateful_orden": args.stateful_orden if args.runtime == "stateful" else None,
        "stateful_cache": args.stateful_cache if args.runtime == "stateful" else None,
    })
    print(f"score={score(resultados):.3f}  pasos={len(resultados)}  "
          f"fallos={sum(1 for r in resultados if r.actionable and not r.correct)}")


if __name__ == "__main__":
    main()
