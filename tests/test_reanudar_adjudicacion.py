"""Relanzar una cadena de adjudicaciones no puede re-pagar lo ya medido.

Cada adjudicacion escribe su propio fichero de traza, asi que al relanzar una cadena
que se cayo a mitad -- por caducidad de sesion o por cuota -- los episodios completos
tienen que saltarse. Un episodio a medias, en cambio, NO vale: su traza esta truncada
y su score seria de un episodio que nunca termino.
"""
import json

from experiments.adjudicar import episodio_ya_hecho


def _escribir(path, filas):
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(filas):
            fh.write(json.dumps({"step": i, "http": 200, "correct": True,
                                 "raw": {"respuestas": ["x"]}}) + "\n")


def test_un_episodio_completo_se_salta(tmp_path):
    f = tmp_path / "traza.jsonl"
    _escribir(f, 200)
    assert episodio_ya_hecho(f, horizonte=200) is True


def test_un_episodio_a_medias_no_cuenta(tmp_path):
    # Es el caso de la caida: la traza existe pero el episodio no termino.
    f = tmp_path / "traza.jsonl"
    _escribir(f, 137)
    assert episodio_ya_hecho(f, horizonte=200) is False


def test_un_fichero_que_no_existe_no_cuenta(tmp_path):
    assert episodio_ya_hecho(tmp_path / "no-existe.jsonl", horizonte=200) is False


def test_una_traza_corrupta_no_cuenta(tmp_path):
    # Un JSON cortado a mitad de linea, que es como queda si el proceso muere
    # escribiendo. Vale mas re-medir que dar por bueno un fichero ilegible.
    f = tmp_path / "traza.jsonl"
    _escribir(f, 200)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write('{"step": 200, "raw": {"respu')
    assert episodio_ya_hecho(f, horizonte=200) is False


def test_la_cabecera_de_condiciones_no_cuenta_como_paso(tmp_path):
    # La traza lleva una primera fila con las condiciones de la corrida. Contarla
    # como un paso mas desplazaba el total en uno: ningun episodio cuadraba con su
    # horizonte y la cadena volvia a pagar episodios ya medidos.
    f = tmp_path / "traza.jsonl"
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "run_header",
                             "condiciones": {"horizon": 200}}) + "\n")
        for i in range(200):
            fh.write(json.dumps({"step": i, "http": 200, "correct": True}) + "\n")
    assert episodio_ya_hecho(f, horizonte=200) is True
