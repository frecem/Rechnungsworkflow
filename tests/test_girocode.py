from decimal import Decimal

import pytest

from app.services.girocode import (
    InvalidPaymentData,
    build_epc_payload,
    normalize_iban,
    parse_epc_payload,
    validate_iban,
)

# Bekannte gültige Beispiel-IBAN der Bundesbank
VALID_IBAN = "DE89 3704 0044 0532 0130 00"


def test_normalize_iban_strips_spaces_and_uppercases():
    assert normalize_iban("de89 3704 0044 0532 0130 00") == "DE89370400440532013000"


def test_validate_iban_accepts_known_valid_iban():
    assert validate_iban(VALID_IBAN) is True


def test_validate_iban_rejects_wrong_checksum():
    assert validate_iban("DE00370400440532013000") is False


def test_validate_iban_rejects_malformed_input():
    assert validate_iban("not an iban") is False


def test_build_epc_payload_valid():
    payload = build_epc_payload(
        recipient_name="Testfirma GmbH",
        iban=VALID_IBAN,
        bic="COBADEFFXXX",
        amount=Decimal("119.50"),
        reference="Rechnung RE-2026-001",
    )
    lines = payload.split("\n")
    assert lines[0] == "BCD"
    assert lines[1] == "002"
    assert lines[3] == "SCT"
    assert lines[4] == "COBADEFFXXX"
    assert lines[5] == "Testfirma GmbH"
    assert lines[6] == "DE89370400440532013000"
    assert lines[7] == "EUR119.50"
    assert lines[10] == "Rechnung RE-2026-001"


def test_build_epc_payload_rejects_invalid_iban():
    with pytest.raises(InvalidPaymentData):
        build_epc_payload("Testfirma", "DE00000000000000000000", None, Decimal("10.00"), "x")


def test_build_epc_payload_rejects_zero_amount():
    with pytest.raises(InvalidPaymentData):
        build_epc_payload("Testfirma", VALID_IBAN, None, Decimal("0"), "x")


def test_build_epc_payload_bic_optional():
    payload = build_epc_payload("Testfirma", VALID_IBAN, None, Decimal("10.00"), "x")
    lines = payload.split("\n")
    assert lines[4] == ""


def test_parse_epc_payload_round_trip():
    payload = build_epc_payload(
        recipient_name="Testfirma GmbH",
        iban=VALID_IBAN,
        bic="COBADEFFXXX",
        amount=Decimal("119.50"),
        reference="Rechnung RE-2026-001",
    )
    parsed = parse_epc_payload(payload)
    assert parsed == {
        "recipient_name": "Testfirma GmbH",
        "iban": "DE89370400440532013000",
        "bic": "COBADEFFXXX",
        "amount": Decimal("119.50"),
        "reference": "Rechnung RE-2026-001",
    }


def test_parse_epc_payload_bic_optional_becomes_none():
    payload = build_epc_payload("Testfirma", VALID_IBAN, None, Decimal("10.00"), "x")
    parsed = parse_epc_payload(payload)
    assert parsed["bic"] is None


def test_parse_epc_payload_rejects_non_epc_qr_content():
    assert parse_epc_payload("https://example.com/some-tracking-link") is None


def test_parse_epc_payload_rejects_invalid_iban():
    payload = "BCD\n002\n1\nSCT\n\nTestfirma\nDE00000000000000000000\nEUR10.00\n\n\nx"
    assert parse_epc_payload(payload) is None


def test_parse_epc_payload_handles_crlf_line_endings():
    payload = build_epc_payload("Testfirma", VALID_IBAN, None, Decimal("10.00"), "x").replace("\n", "\r\n")
    parsed = parse_epc_payload(payload)
    assert parsed["iban"] == "DE89370400440532013000"
