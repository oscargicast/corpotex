from datetime import date
from pathlib import Path

import pytest

from agent.persona.style import anonymize, load_template, parse_whatsapp_export, validate_style

FIXTURES = Path(__file__).resolve().parent.parent / "agent" / "persona" / "fixtures"
FIXTURE_SUPPLIERS = {
    "textiles-lima-norte.txt": ("Textiles Lima Norte S.A.C.", "Ramírez"),
    "hilados-del-bajio.txt": ("Hilados del Bajío", "Castañeda"),
}


def test_template_passes_validation():
    assert validate_style(load_template()) == []


def test_validate_rejects_phone_and_ruc():
    md = load_template() + "\nllámeme al 987 654 321 o al 51987654321, RUC 20123456789\n"
    errors = validate_style(md)
    assert any("teléfono" in e for e in errors)
    assert any("RUC" in e for e in errors)


def test_validate_rejects_amounts_and_supplier_names():
    md = load_template() + "\ncon Avíos Gamarra cerramos a S/ 12.50\n"
    errors = validate_style(md, supplier_names=("Avíos Gamarra",))
    assert any("monto" in e for e in errors)
    assert any("Avíos Gamarra" in e for e in errors)


def test_validate_rejects_manager_phrases_that_name_the_manager():
    md = (
        load_template()
        + '\n- "[G] lo del pago se lo confirma el Gerente"\n[G] eso lo ve el gerente\n'
    )
    errors = validate_style(md)
    assert sum("tercera persona" in e for e in errors) == 2
    # Descriptions may mention the manager; only his own phrases may not.
    assert validate_style(load_template() + "\nLos pagos los decide el Gerente.\n") == []
    # An anonymized name is a placeholder, not a third-person mention.
    assert validate_style(load_template() + '\n- "[G] hola, soy <GERENTE> de Corpotex"\n') == []


def test_validate_requires_sections_and_length():
    errors = validate_style("# Estilo del Gerente\n\n## Resumen\ncorto")
    assert any("## Ejemplos" in e for e in errors)
    assert any("corto" in e for e in errors)


@pytest.mark.parametrize("filename", sorted(FIXTURE_SUPPLIERS))
def test_fixtures_parse(filename):
    supplier_name, contact = FIXTURE_SUPPLIERS[filename]
    content = (FIXTURES / filename).read_text(encoding="utf-8")
    chat = parse_whatsapp_export(
        content, "Gerente", since=date(2026, 1, 1), supplier_name=supplier_name
    )

    assert len(chat["messages"]) >= 50
    assert {m["sender"] for m in chat["messages"]} == {"manager", "supplier"}
    joined = "\n".join(m["text"] for m in chat["messages"])
    for leaked in (contact, "20999999999", "999 999 999", "S/ 26.50", "USD 3.10"):
        assert leaked not in joined


def test_parse_export_handles_multiline_messages():
    content = (
        "02/10/26, 09:06 - Gerente: le paso el pedido del mes:\n"
        "- jersey 30/1 blanco 300 kilos\n"
        "al precio de siempre\n"
        "02/10/26, 10:40 - Sr. Ramírez: Conforme\n"
    )
    chat = parse_whatsapp_export(content, "Gerente", since=date(2026, 1, 1))
    assert [m["sender"] for m in chat["messages"]] == ["manager", "supplier"]
    assert chat["messages"][0]["text"].count("\n") == 2
    assert chat["contact_names"] == ["Sr. Ramírez"]


def test_parse_export_reads_ios_format_and_filters_since():
    content = (
        "[01/07/26, 9:00:12] Gerente: muy antiguo\n"
        "[14/10/26, 10:05:00] Gerente: buenos días\n"
        "[14/10/26, 10:06:00] Encargada: imagen omitida\n"
        "[14/10/26, 10:07:00] Encargada: Se eliminó este mensaje\n"
    )
    chat = parse_whatsapp_export(content, "Gerente", since=date(2026, 10, 10))
    assert [m["text"] for m in chat["messages"]] == ["buenos días", "[imagen]"]


def test_anonymize_removes_phones_ruc_and_names():
    text = (
        "Sr. Ramírez dice que Ramírez no está; Martín paga S/ 26.50 o USD 3.10. "
        "RUC 20999999999, cel 987 654 321, correo ventas@textiles.pe, "
        "https://textiles.pe. Textiles Lima Norte S.A.C. envía desde Lima"
    )
    result = anonymize(
        text,
        contact_names=["Sr. Ramírez"],
        supplier_names=["Textiles Lima Norte S.A.C."],
        manager_names=["Martín"],
    )
    for leaked in (
        "Ramírez",
        "Martín",
        "26.50",
        "3.10",
        "20999999999",
        "987 654 321",
        "ventas@",
        "https://",
    ):
        assert leaked not in result
    assert "<PROVEEDOR> envía desde Lima" in result  # the company name, not every "Lima"


def test_anonymize_is_idempotent():
    once = anonymize("Sr. Ramírez: S/ 12.50, cel 987654321", contact_names=["Sr. Ramírez"])
    assert anonymize(once, contact_names=["Sr. Ramírez"]) == once
