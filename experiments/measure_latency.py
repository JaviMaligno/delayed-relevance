"""Mide la latencia del despliegue segun el tamano de salida.

La rejilla de T=50 iba a 127 minutos por episodio. Antes de culpar al despliegue
hay que separar dos causas: leer un prompt grande, o generar una respuesta larga.
"""
from __future__ import annotations

import argparse
import time

from dr.config import load_env
from dr.llm import AnthropicClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-haiku-4-5")
    args = parser.parse_args()
    load_env()

    prompt_corto = "Reply with the single word: ready."
    prompt_largo = ("Background record, ignore it.\n" + "field=value | " * 1500) + (
        "\nReply with the single word: ready."
    )

    casos = [
        ("prompt corto, salida corta", prompt_corto, 32),
        ("prompt corto, salida larga", "Write a detailed 500-word essay about logistics.", 2048),
        ("prompt largo,  salida corta", prompt_largo, 32),
    ]
    for etiqueta, prompt, max_tokens in casos:
        client = AnthropicClient(model=args.model, max_tokens=max_tokens)
        inicio = time.monotonic()
        reply = client.complete(system="You are a warehouse controller.", user=prompt)
        segundos = time.monotonic() - inicio
        print(
            f"{etiqueta}: {segundos:6.1f}s  "
            f"(entrada {reply.prompt_tokens} tok, salida {reply.output_tokens} tok, "
            f"{reply.output_tokens / max(segundos, 0.01):.1f} tok/s)",
            flush=True,
        )


if __name__ == "__main__":
    main()
