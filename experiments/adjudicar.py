"""Repite UN episodio con la traza puesta, para poder explicar sus fallos.

La rejilla guarda el score; esto guarda la respuesta. Existe porque un `correct=False`
no dice si el modelo perdio la cuenta del estado -- lo que el experimento mide -- o si
copio mal un campo del JSON de accion, que es una diferencia de nuestra
reimplementacion contra su accion posicional de dos campos (hueco 4 de I4).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dr.envs.warehouse import Warehouse
from dr.llm import build_client
from dr.metrics import score
from dr.runner import run_episode
from replicate_table1 import build_runtimes


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
    p.add_argument("--etiqueta", default="",
                   help="Sufijo del fichero de traza. Repetir la MISMA celda es\nla unica forma de medir el ruido de corrida a corrida, y sin etiqueta\ncada repeticion pisaria a la anterior.")
    p.add_argument("--out", default="results")
    args = p.parse_args()

    cliente = build_client(args.model, args.provider, args.max_tokens,
                           thinking_budget=args.thinking_budget)
    env = Warehouse(horizon=args.horizon, seed=args.seed, apendice_b=args.apendice_b,
                    sin_telemetria=args.sin_telemetria, ruido=args.ruido)
    runtime = build_runtimes(True, True)[args.runtime](cliente, env)
    sufijo = f"_{args.etiqueta}" if args.etiqueta else ""
    destino = Path(args.out) / (f"adj_T{args.horizon}_{args.model}_{args.runtime}"
                                f"_s{args.seed}{sufijo}.jsonl")
    destino.unlink(missing_ok=True)
    print(f"adjudicando {args.runtime} T={args.horizon} seed={args.seed} -> {destino}",
          flush=True)
    resultados = run_episode(env, runtime, traza=destino)
    print(f"score={score(resultados):.3f}  pasos={len(resultados)}  "
          f"fallos={sum(1 for r in resultados if r.actionable and not r.correct)}")


if __name__ == "__main__":
    main()
