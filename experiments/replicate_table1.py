"""Replica la Tabla 1 de SKILL.state sobre Warehouse. Corridas en serie, a proposito."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import anthropic

from dr.config import load_env
from dr.envs.warehouse import Warehouse
from dr.llm import AnthropicClient
from dr.metrics import aggregate, score
from dr.runner import run_episode
from dr.runtimes.memory import MemoryRuntime
from dr.runtimes.react import ReActRuntime
from dr.runtimes.skillstate import SkillStateRuntime
from dr.runtimes.stateful import StatefulRuntime


def finite(value: float) -> float | None:
    """La sd de una sola seed es NaN; json.dumps lo escribiria como NaN, que no es JSON."""
    return value if math.isfinite(value) else None


RUNTIMES = {
    "react": lambda client, env: ReActRuntime(client, env.spec()),
    "memory": lambda client, env: MemoryRuntime(client, env.spec()),
    "stateful": lambda client, env: StatefulRuntime(client, env.spec(), env.schema_fields()),
    "skillstate": lambda client, env: SkillStateRuntime(client, env.spec(), env.schema_fields()),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--provider", default="auto", choices=["auto", "api", "foundry"])
    parser.add_argument("--max-tokens", type=int, default=600,
                        help="Tope de salida por llamada. Sus totales de la Tabla 1 "
                             "implican respuestas cortas; 2048 disparaba el coste "
                             "y, en los brazos con historia, la densidad.")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    load_env()

    client = AnthropicClient(model=args.model, provider=args.provider,
                             max_tokens=args.max_tokens)
    print(f"proveedor: {client.provider}  modelo: {args.model}", flush=True)
    Path(args.out).mkdir(exist_ok=True)
    table: dict[str, dict[str, object]] = {}

    # Checkpoint por episodio: una corrida larga que se cae por un fallo de red no
    # puede perder todo lo ya pagado. Al relanzar, los episodios ya hechos se saltan.
    stem = f"T{args.horizon}_{args.model}_{client.provider}"
    partial_path = Path(args.out) / f"partial_{stem}.json"
    done: dict[str, dict] = {}
    if partial_path.exists():
        done = json.loads(partial_path.read_text())
        print(f"reanudando: {len(done)} episodios ya completados", flush=True)

    for name, build in RUNTIMES.items():
        scores, prompts, totals = [], [], []
        overflowed: list[int] = []
        for seed in range(args.seeds):
            key = f"{name}:{seed}"
            if key in done:
                cached = done[key]
                if cached.get("overflowed"):
                    overflowed.append(seed)
                else:
                    scores.append(cached["score"])
                    prompts.append(cached["avg_prompt"])
                    totals.append(cached["total"])
                print(f"{name} seed={seed} (cacheado)", flush=True)
                continue
            env = Warehouse(horizon=args.horizon, seed=seed)
            try:
                results = run_episode(env, build(client, env))
            except anthropic.BadRequestError as error:
                if "prompt is too long" not in str(error).lower():
                    raise
                print(f"{name} seed={seed} DESBORDA la ventana de contexto", flush=True)
                overflowed.append(seed)
                done[key] = {"overflowed": True}
                partial_path.write_text(json.dumps(done, indent=2))
                continue
            truncs = sum(r.truncated for r in results)
            if truncs:
                print(f"  AVISO {name} seed={seed}: {truncs} respuestas truncadas "
                      f"por el tope de salida", flush=True)
            scores.append(score(results))
            prompts.append(sum(r.prompt_tokens for r in results) / len(results))
            totals.append(sum(r.prompt_tokens + r.output_tokens for r in results))
            done[key] = {
                "score": scores[-1],
                "avg_prompt": prompts[-1],
                "total": totals[-1],
                "overflowed": False,
            }
            partial_path.write_text(json.dumps(done, indent=2))
            print(f"{name} seed={seed} score={scores[-1]:.2f} tokens={totals[-1]}", flush=True)
        if scores:
            table[name] = {
                "score_mean": finite(aggregate(scores).mean),
                "score_sd": finite(aggregate(scores).sd),
                "avg_prompt_tokens": finite(aggregate(prompts).mean),
                "total_tokens": finite(aggregate(totals).mean),
                "overflowed_seeds": overflowed,
            }
        else:
            table[name] = {
                "score_mean": None,
                "score_sd": None,
                "avg_prompt_tokens": None,
                "total_tokens": None,
                "overflowed_seeds": overflowed,
            }

    table["_meta"] = {"provider": client.provider, "model": args.model,
                      "horizon": args.horizon, "seeds": args.seeds,
                      "max_tokens": args.max_tokens}
    path = Path(args.out) / f"table1_T{args.horizon}_{args.model}_{client.provider}.json"
    path.write_text(json.dumps(table, indent=2))
    print(f"escrito {path}", flush=True)


if __name__ == "__main__":
    main()
