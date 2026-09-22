"""Las dos caches de Vertex, medidas y no supuestas (R3b del spec).

C1 -- que la cache invierte la contabilidad: 7,5x en tokens se quedan en 1,4x en
factura -- esta medida solo en Anthropic, y el spec dice que no es extrapolable porque
la cache de Gemini funciona distinto. Esto lo comprueba en vez de suponerlo.

Mide las dos por separado:

- **Implicita**: manda el mismo prefijo varias veces seguidas y mira si alguna lectura
  se descuenta. En Anthropic esto es lo que abarata a ReAct sin que nadie haga nada.
- **Explicita**: crea un objeto `cachedContents` con TTL, lo usa, y mide el descuento.

La diferencia importa para el paper: una cache automatica abarata el transcript sin
que el metodo haga nada, y una cache que hay que crear a mano NO sirve para un prefijo
que crece en cada paso -- habria que recrear el objeto cada turno, pagando la escritura,
para cachear algo que no se va a repetir.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from dr.llm import gcloud_access_token, post_json


def _relleno(n_tokens: int) -> str:
    return " ".join(f"item{n:05d} registro operativo sin efecto"
                    for n in range(n_tokens // 6))


def _url(proyecto: str, sufijo: str) -> str:
    return (f"https://aiplatform.googleapis.com/v1beta1/projects/{proyecto}"
            f"/locations/global/{sufijo}")


def implicita(proyecto: str, modelo: str, tokens: int, repeticiones: int) -> list[dict]:
    sistema = "You are a test harness. Ignore this reference table.\n" + _relleno(tokens)
    cabeceras = {"content-type": "application/json",
                 "Authorization": f"Bearer {gcloud_access_token()}",
                 "x-goog-user-project": proyecto}
    cuerpo = {"systemInstruction": {"parts": [{"text": sistema}]},
              "contents": [{"role": "user", "parts": [{"text": "Reply with: ok"}]}],
              "generationConfig": {"maxOutputTokens": 8, "temperature": 0}}
    url = _url(proyecto, f"publishers/google/models/{modelo}:generateContent")
    print(f"CACHE IMPLICITA ({repeticiones} llamadas identicas)")
    filas = []
    for i in range(1, repeticiones + 1):
        uso = post_json(url, cabeceras, cuerpo).get("usageMetadata", {})
        filas.append({"sonda": "identica", "llamada": i,
                      "prompt": uso.get("promptTokenCount"),
                      "cacheado": uso.get("cachedContentTokenCount", 0)})
        print(f"  llamada {i}: prompt={uso.get('promptTokenCount')} "
              f"cacheado={uso.get('cachedContentTokenCount', '(campo ausente)')}")
    return filas


def creciente(proyecto: str, modelo: str, tokens: int, pasos: int) -> list[dict]:
    """El patron REAL de un runtime que arrastra historia: el prefijo crece en cada
    llamada y el anterior es prefijo del siguiente.

    Existe porque la primera version de esta sonda midio el patron equivocado -- la
    misma peticion repetida -- concluyo "no hay cache implicita", y las rejillas de
    ReAct contradecian esa conclusion: 503.600 tokens leidos de cache en un solo
    episodio de T=200. Una medicion limpia de la cosa que no era.
    """
    cabeceras = {"content-type": "application/json",
                 "Authorization": f"Bearer {gcloud_access_token()}",
                 "x-goog-user-project": proyecto}
    url = _url(proyecto, f"publishers/google/models/{modelo}:generateContent")
    historia = "You are a test harness. Ignore this log.\n"
    filas = []
    print(f"CACHE IMPLICITA CON PREFIJO CRECIENTE ({pasos} llamadas)")
    for i in range(1, pasos + 1):
        historia += _relleno(tokens) + f"\n[step {i}]\n"
        uso = post_json(url, cabeceras, {
            "contents": [{"role": "user", "parts": [{"text": historia + "Reply: ok"}]}],
            "generationConfig": {"maxOutputTokens": 8, "temperature": 0}},
        ).get("usageMetadata", {})
        leido = uso.get("cachedContentTokenCount", 0)
        filas.append({"sonda": "creciente", "llamada": i,
                      "prompt": uso.get("promptTokenCount"), "cacheado": leido})
        print(f"  llamada {i}: prompt={uso.get('promptTokenCount'):>7} "
              f"cacheado={leido:>7} "
              f"({100 * leido / max(uso.get('promptTokenCount', 1), 1):.0f}%)")
    return filas


def explicita(proyecto: str, modelo: str, tokens: int) -> list[dict]:
    sistema = "You are a test harness. Ignore this reference table.\n" + _relleno(tokens)
    cabeceras = {"content-type": "application/json",
                 "Authorization": f"Bearer {gcloud_access_token()}",
                 "x-goog-user-project": proyecto}
    creado = post_json(_url(proyecto, "cachedContents"), cabeceras, {
        "model": (f"projects/{proyecto}/locations/global/publishers/google/"
                  f"models/{modelo}"),
        "systemInstruction": {"parts": [{"text": sistema}]},
        "ttl": "300s"})
    nombre = creado["name"]
    filas = [{"sonda": "explicita", "llamada": 0,
              "creado_con": creado.get("usageMetadata", {}).get("totalTokenCount")}]
    print(f"\nCACHE EXPLICITA: creado con "
          f"{creado.get('usageMetadata', {}).get('totalTokenCount')} tokens")
    url = _url(proyecto, f"publishers/google/models/{modelo}:generateContent")
    for i in (1, 2):
        uso = post_json(url, cabeceras, {
            "cachedContent": nombre,
            "contents": [{"role": "user", "parts": [{"text": "Reply with: ok"}]}],
            "generationConfig": {"maxOutputTokens": 8, "temperature": 0}},
        ).get("usageMetadata", {})
        filas.append({"sonda": "explicita", "llamada": i,
                      "prompt": uso.get("promptTokenCount"),
                      "cacheado": uso.get("cachedContentTokenCount", 0)})
        print(f"  llamada {i}: prompt={uso.get('promptTokenCount')} "
              f"cacheado={uso.get('cachedContentTokenCount', '(campo ausente)')}")
    # Un objeto de cache que se queda vivo sigue facturando almacenamiento.
    peticion = urllib.request.Request(
        f"https://aiplatform.googleapis.com/v1beta1/{nombre}",
        headers=cabeceras, method="DELETE")
    with urllib.request.urlopen(peticion, timeout=60):
        print("  objeto de cache borrado")
    return filas


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--proyecto", required=True)
    p.add_argument("--modelo", default="gemini-3-flash-preview")
    p.add_argument("--tokens", type=int, default=12000)
    p.add_argument("--repeticiones", type=int, default=4)
    p.add_argument("--out", default="results")
    p.add_argument("--pasos", type=int, default=8,
                   help="Llamadas del patron de prefijo creciente.")
    args = p.parse_args()
    # Una sonda que solo imprime no es auditable: sus cifras acaban en un documento
    # sin artefacto detras. Se persisten.
    filas = implicita(args.proyecto, args.modelo, args.tokens, args.repeticiones)
    print()
    filas += creciente(args.proyecto, args.modelo, args.tokens // 4, args.pasos)
    filas += explicita(args.proyecto, args.modelo, args.tokens)
    destino = Path(args.out) / f"probe_cache_vertex_{args.modelo}.json"
    destino.write_text(json.dumps(
        {"modelo": args.modelo, "proyecto": args.proyecto, "tokens": args.tokens,
         "pasos": args.pasos, "mediciones": filas}, indent=1, ensure_ascii=False))
    print(f"\nescrito {destino}")


if __name__ == "__main__":
    main()
