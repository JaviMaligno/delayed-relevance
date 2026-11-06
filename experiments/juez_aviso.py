"""Juez ciego: en el paso del aviso de la sonda C, ¿el agente ACEPTO la correccion?

Haiku 5.5 descartaba a veces el `correction_notice` («not a defined event type, I can't
verify its claim»). Si el agente no acepta el aviso cuando lo recibe, sus fallos
posteriores no dicen nada de la compactacion: el aviso y la decision de ignorarlo caen
antes de compactar. Este juez separa los dos casos para recontar la sonda.

Ciego: ve el aviso y la respuesta del agente en ese paso, nunca el brazo, el modelo ni el
resultado. Un juez de otro modelo (Sonnet 5.5) que el evaluado, por suscripcion.

Uso:
    PYTHONPATH="src;." python experiments/juez_aviso.py results/compaction/C-haiku55 ...
Escribe `<dir>/juez_aviso.json` (cache: lo ya juzgado no se repite).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from dr.llm import build_client

MODELO_JUEZ = "claude-sonnet-5-5"
SISTEMA = (
    "You audit the log of a warehouse agent. The agent tracks which shelves are occupied. "
    "At this step it received a correction notice saying an earlier put-away never "
    "happened and a shelf is actually empty. Decide whether the agent ACCEPTED the "
    "correction, i.e. it now treats that shelf as empty for future decisions, or REJECTED "
    "it, i.e. it keeps treating the shelf as occupied (for example it calls the notice "
    "unverifiable, flags a discrepancy without updating, or says it will not change "
    "occupancy). If the reply gives no way to tell, answer UNCLEAR. The action itself is "
    "Wait in every case and tells you nothing. Reply with JSON only: "
    '{"verdict": "ACCEPTED" | "REJECTED" | "UNCLEAR", "evidence": "<short quote>"}'
)


def casos(directorio: Path):
    for f in sorted((directorio / "trazas").glob("*.jsonl")):
        m = re.search(r"_(summary|fresh_lookup|hybrid_lookup|summary_lookup|react|skillstate)"
                      r"_s(\d+)_r(\d+)\.jsonl$", f.name)
        if not m:
            continue
        for linea in open(f, encoding="utf-8"):
            p = json.loads(linea)
            obs = p.get("observation") or ""
            if obs.startswith("EVENT correction_notice"):
                resp = ((p.get("raw") or {}).get("respuestas") or [""])[-1]
                # Codex no escribe razonamiento visible; su resumen va aparte. Se le pasa
                # al juez como parte de la respuesta, sin decirle de que modelo viene.
                razon = ((p.get("razonamiento") or [""]) or [""])[-1]
                if razon:
                    resp = f"[internal reasoning summary]\n{razon}\n\n[visible reply]\n{resp}"
                yield f.name, f"{m.group(1)}:s{m.group(2)}:r{m.group(3)}", obs.split("\n")[0], resp
                break


def main() -> None:
    juez = build_client(MODELO_JUEZ, "claude-cli", 2048)
    for d in map(Path, sys.argv[1:]):
        salida = d / "juez_aviso.json"
        hecho = json.loads(salida.read_text(encoding="utf-8")) if salida.exists() else {}
        for fichero, clave, aviso, resp in casos(d):
            if fichero in hecho:
                continue
            c = juez.complete(SISTEMA, f"Correction notice:\n{aviso}\n\nAgent reply:\n{resp}")
            m = re.search(r"\{.*\}", c.text, re.S)
            try:
                v = json.loads(m.group(0)) if m else {}
            except json.JSONDecodeError:
                v = {}
            hecho[fichero] = {"clave": clave, "verdict": v.get("verdict", "ERROR"),
                              "evidence": v.get("evidence", c.text[:200])}
            salida.write_text(json.dumps(hecho, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{d.name} {clave}: {hecho[fichero]['verdict']}", flush=True)


if __name__ == "__main__":
    main()
