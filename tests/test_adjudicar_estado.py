"""El adjudicador de estado: los tres defectos de la revision adversarial 3."""
from experiments.adjudicar_estado import _aplicar_stateful, _coincide, _creencia


def test_un_sku_suelto_es_una_estanteria_ocupada_no_vacia():
    # Gemini escribe a veces `"0": "SKU-B"`. Leerlo como vacia marcaba siete episodios
    # como corrompidos sin que lo estuvieran.
    assert _creencia({"shelf_contents": {"0": "SKU-B"}}) == {0: ("SKU-B", None, None)}
    assert _coincide({0: ("SKU-B", None, None)}, {0: ("SKU-B", 14, "L-1")})


def test_las_unidades_cuentan():
    # Comparar solo SKU y lote dejaba fuera dos parches con la cantidad mal.
    assert not _coincide({0: ("SKU-B", 15, "L-1")}, {0: ("SKU-B", 17, "L-1")})


def test_stateful_se_reconstruye_con_el_parser_de_su_version():
    # Con el v1 un parche anidado no se aplicaba nunca; reconstruirlo con el actual
    # inventa un estado que el modelo no vio.
    texto = 'StateUpdate: {"shelf_contents": {"0": {"sku": "SKU-A", "units": 3, "lot": "L"}}}'
    campos = {"shelf_contents", "last_event"}
    assert _aplicar_stateful(1, {}, texto, campos) == {}
    assert _aplicar_stateful(3, {}, texto, campos)["shelf_contents"]["0"]["sku"] == "SKU-A"
    markdown = '**StateUpdate:**\n{"last_event": "x"}'
    assert _aplicar_stateful(2, {}, markdown, campos) == {}
    assert _aplicar_stateful(3, {}, markdown, campos) == {"last_event": "x"}


def test_las_unidades_se_leen_aunque_vengan_como_texto_o_decimal():
    # Revision 4: "999" se leia como `sin especificar` y 14.9 se truncaba a 14.
    assert _creencia({"shelf_contents": {"0": {"sku": "A", "units": "999", "lot": "L"}}}) == {0: ("A", 999, "L")}
    assert not _coincide(_creencia({"shelf_contents": {"0": {"sku": "A", "units": 14.9, "lot": "L"}}}),
                         {0: ("A", 14, "L")})


def test_unas_unidades_mal_formadas_son_discrepancia_no_comodin():
    # Revision 4, hallazgo nuevo 2: "WRONG" se leia como `sin especificar` y no contaba.
    creida = _creencia({"shelf_contents": {"0": {"sku": "A", "units": "WRONG", "lot": "L"}}})
    assert not _coincide(creida, {0: ("A", 14, "L")})
    # Ausente sigue siendo comodin: el modelo no lo escribio.
    assert _coincide(_creencia({"shelf_contents": {"0": {"sku": "A", "lot": "L"}}}), {0: ("A", 14, "L")})
