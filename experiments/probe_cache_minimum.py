"""Cual es el prefijo minimo cacheable, medido y no supuesto.

En la tabla de coste (§3) todos los brazos que comprimen ahorran 0% y solo ReAct
cachea. La explicacion candidata es que la especificacion del entorno (~1.300 tokens)
queda por debajo del minimo cacheable del modelo, asi que el bloque de sistema —que
si lleva punto de corte en todos los brazos— nunca llega a cachear. Si es eso, el 0%
no es una propiedad del metodo sino de la longitud de ESTE prompt, y hay que decirlo.

Manda el mismo bloque de sistema dos veces y mira si la segunda lee de cache, para
varias longitudes de relleno.
"""
from __future__ import annotations

import argparse

from dr.config import load_env
from dr.llm import AnthropicClient


def prueba(cliente, tokens_objetivo: int) -> tuple[int, int]:
    # ~4 caracteres por token; el relleno es texto plano, no repetido, para que no
    # se comprima de forma rara al tokenizar.
    relleno = " ".join(f"item{n:05d} registro operativo sin efecto" for n in range(tokens_objetivo // 6))
    sistema = f"You are a test harness. Ignore this reference table.\n{relleno}"
    primera = cliente.complete(system=sistema, user="Reply with the single word: ok")
    segunda = cliente.complete(system=sistema, user="Reply with the single word: ok")
    return segunda.cache_read, primera.prompt_tokens + primera.cache_write


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-4-5")
    p.add_argument("--longitudes", nargs="*", type=int, default=[1300, 2500])
    args = p.parse_args()
    load_env()
    cliente = AnthropicClient(model=args.model, max_tokens=16)
    print(f"modelo {args.model}")
    for objetivo in args.longitudes:
        leidos, enviados = prueba(cliente, objetivo)
        print(f"  sistema ~{enviados:5} tokens -> segunda llamada lee de cache: {leidos}"
              f"   {'CACHEA' if leidos else 'NO CACHEA'}")


if __name__ == "__main__":
    main()
