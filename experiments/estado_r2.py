"""Una linea con el estado de R2: completos|en curso|trazas de error|RateLimit.

Lo lee el monitor de la tanda. Vive en el repo y no en un directorio de sesion para
que sobreviva a que se reinicie quien lo vigila."""
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
PATRON = re.compile(r"adj_T(50|200)_claude-haiku-4-5_(\w+)_s(\d)_h(\d)\.jsonl$")

completos = parciales = 0
for f in (RAIZ / "results").glob("adj_T*_claude-haiku-4-5_*_h?.jsonl"):
    m = PATRON.search(f.name)
    if not m:
        continue
    pasos = 0
    for linea in f.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            break
        if fila.get("kind") != "run_header":
            pasos += 1
    if pasos == int(m.group(1)):
        completos += 1
    elif pasos > 0:
        parciales += 1

log = RAIZ / "logs" / "r2_haiku.log"
texto = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
fallos = len(re.findall(r"^Traceback", texto, flags=re.M))
limites = texto.count("RateLimitError")
print(f"{completos}|{parciales}|{fallos}|{limites}")
