from datetime import date
from decimal import Decimal

from app.services.extraction import extract_fields, parse_de_amount

SAMPLE_INVOICE_TEXT = """
Musterfirma GmbH
Musterstraße 1
12345 Musterstadt

Rechnung

Rechnungsnummer: RE-2026-00042
Rechnungsdatum: 03.08.2026

Leistung                          Betrag
Beratung                          100,00 EUR

Nettobetrag: 100,00 EUR
MwSt 19%: 19,00 EUR
Gesamtbetrag: 119,00 EUR
"""


def test_parse_de_amount_german_format():
    assert parse_de_amount("1.234,56") == Decimal("1234.56")


def test_parse_de_amount_plain_decimal():
    assert parse_de_amount("42,00") == Decimal("42.00")


def test_parse_de_amount_invalid_returns_none():
    assert parse_de_amount("nicht-numerisch") is None


def test_parse_de_amount_empty_returns_none():
    assert parse_de_amount("") is None


def test_extract_fields_empty_text():
    fields = extract_fields("")
    assert fields.amount_gross is None
    assert fields.invoice_number is None


def test_extract_fields_invoice_number():
    fields = extract_fields(SAMPLE_INVOICE_TEXT)
    assert fields.invoice_number == "RE-2026-00042"


def test_extract_fields_date():
    fields = extract_fields(SAMPLE_INVOICE_TEXT)
    assert fields.invoice_date == date(2026, 8, 3)


def test_extract_fields_gross_amount():
    fields = extract_fields(SAMPLE_INVOICE_TEXT)
    assert fields.amount_gross == Decimal("119.00")


def test_extract_fields_net_amount():
    fields = extract_fields(SAMPLE_INVOICE_TEXT)
    assert fields.amount_net == Decimal("100.00")


def test_extract_fields_vat_amount():
    fields = extract_fields(SAMPLE_INVOICE_TEXT)
    assert fields.vat_amount == Decimal("19.00")


def test_extract_fields_sender():
    fields = extract_fields(SAMPLE_INVOICE_TEXT)
    assert fields.sender_name == "Musterfirma GmbH"
