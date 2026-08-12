import csv
import io
from decimal import Decimal

import pytest

from app.models import Invoice
from app.services.export_csv import CSV_COLUMNS, build_csv


def parse_row(csv_text: str, index: int = 0) -> dict[str, str]:
    """Liest den Export so, wie eine Tabellenkalkulation es tun wuerde.

    Wichtig fuer die Escaping-Tests: der csv-Writer verdoppelt Anfuehrungszeichen
    im Feld, ein Substring-Vergleich auf der Rohzeile wuerde daran scheitern.
    """
    rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))
    return rows[index]


def make_invoice(**overrides):
    defaults = {
        "id": 1,
        "source_type": "upload",
        "file_path": "2026/beleg.pdf",
        "file_hash_sha256": "hash",
        "status": "approved",
        "currency": "EUR",
        "sender_name": "Musterfirma GmbH",
        "invoice_number": "RE-1",
        "amount_gross": Decimal("99.50"),
    }
    defaults.update(overrides)
    return Invoice(**defaults)


def test_csv_enthaelt_kopfzeile_und_werte():
    csv_text = build_csv([make_invoice()])

    assert csv_text.splitlines()[0] == ";".join(CSV_COLUMNS)
    row = parse_row(csv_text)
    assert row["sender_name"] == "Musterfirma GmbH"
    # Deutsches Dezimaltrennzeichen
    assert row["amount_gross"] == "99,50"


@pytest.mark.parametrize("gefaehrlich", ["=1+1", "+1", "-1", "@SUM(A1)", '=cmd|" /C calc"!A1'])
def test_formelzellen_werden_entschaerft(gefaehrlich):
    """Absendernamen stammen aus der OCR fremder Rechnungen.

    Ohne Entschaerfung wuerde Excel/LibreOffice eine so praeparierte Zelle beim
    Oeffnen des Exports als Formel auswerten (CSV-/Formel-Injection).
    """
    csv_text = build_csv([make_invoice(sender_name=gefaehrlich)])
    zelle = parse_row(csv_text)["sender_name"]

    # Fuehrendes ' -> Tabellenkalkulation wertet die Zelle als Text aus,
    # der urspruengliche Inhalt bleibt dahinter unveraendert lesbar.
    assert zelle == f"'{gefaehrlich}"


def test_harmlose_werte_bleiben_unveraendert():
    csv_text = build_csv([make_invoice(sender_name="Musterfirma GmbH")])
    assert parse_row(csv_text)["sender_name"] == "Musterfirma GmbH"


def test_leere_felder_erzeugen_keinen_fehler():
    csv_text = build_csv([make_invoice(sender_name=None, invoice_number=None, category=None)])
    assert len(csv_text.splitlines()) == 2
