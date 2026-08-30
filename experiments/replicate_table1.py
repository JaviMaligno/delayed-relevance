"""Replica la Tabla 1 de SKILL.state sobre Warehouse. Corridas en serie, a proposito."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import anthropic

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
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    client = AnthropicClient(model=args.model)
    Path(args.out).mkdir(exist_ok=True)
    table: dict[str, dict[str, object]] = {}

    for name, build in RUNTIMES.items():
        scores, prompts, totals = [], [], []
        overflowed: list[int] = []
        for seed in range(args.seeds):
            env = Warehouse(horizon=args.horizon, seed=seed)
            try:
                results = run_episode(env, build(client, env))
            except anthropic.BadRequestError as error:
                if "prompt is too long" not in str(error).lower():
                    raise
                print(f"{name} seed={seed} DESBORDA la ventana de contexto")
                overflowed.append(seed)
                continue
            scores.append(score(results))
            prompts.append(sum(r.prompt_tokens for r in results) / len(results))
            totals.append(sum(r.prompt_tokens + r.output_tokens for r in results))
            print(f"{name} seed={seed} score={scores[-1]:.2f} tokens={totals[-1]}")
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

    path = Path(args.out) / f"table1_T{args.horizon}_{args.model}.json"
    path.write_text(json.dumps(table, indent=2))
    print(f"escrito {path}")


if __name__ == "__main__":
    main()
