"""Regenera el resumen de la sonda L1 v3 desde sus checkpoints, sin llamar a la API.

Por celda: episodios, materializados, aciertos (solo materializados), excluidos y sus
aciertos, tasa condicionada y tasa conjunta, y el desglose por seed. Reescribe el campo
`celda` de cada probeA_*.json, que antes promediaba el acierto de todos los episodios.
"""
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_a import resumen_celda

CONDICIONES = {"": "sin campo dedicado", "_hatch": "notes", "_oracle": "campo nombrado",
               "_reminder": "recordatorio"}

for parcial in sorted(glob.glob("results/partial_probeA_T50_*_estricto_v3.json")):
    datos = json.loads(Path(parcial).read_text())
    resumen_path = Path(parcial.replace("partial_probeA", "probeA"))
    tabla = json.loads(resumen_path.read_text()) if resumen_path.exists() else {}
    m = re.search(r"probeA_T50_(.+?)(_hatch|_oracle|_reminder)?_mt", parcial)
    modelo, cond = m.group(1), m.group(2) or ""
    for rt in ("react", "skillstate"):
        eps = {k: v for k, v in datos.items() if k.startswith(f"{rt}:k40:")}
        celda = resumen_celda(list(eps.values()))
        por_seed = {}
        for seed in sorted({k.split(":")[2] for k in eps}, key=int):
            por_seed[seed] = resumen_celda([v for k, v in eps.items() if k.split(":")[2] == seed])
        celda["por_seed"] = {s: f"{c['aciertos']}/{c['materializados']} (de {c['episodios']})"
                             for s, c in por_seed.items()}
        entrada = tabla.setdefault(f"{rt}:k40", {})
        # El campo viejo promediaba el acierto de TODOS los episodios (revision 8): se
        # renombra para que nadie lo lea como la metrica publicada.
        if "acierto_dependiente" in entrada:
            entrada["acierto_dependiente_sin_filtrar"] = entrada.pop("acierto_dependiente")
        entrada["celda"] = celda
        print(f"{modelo:24s} {CONDICIONES[cond]:18s} {rt:10s} condicionado "
              f"{celda['aciertos']}/{celda['materializados']}  conjunto "
              f"{celda['aciertos']}/{celda['episodios']}  excluidos {celda['excluidos']} "
              f"(aciertos {celda['aciertos_excluidos']})  seeds {celda['por_seed']}")
    resumen_path.write_text(json.dumps(tabla, indent=2))
