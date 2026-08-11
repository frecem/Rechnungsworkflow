from decimal import Decimal

import pytest

from app.services.girocode import InvalidPaymentData, build_epc_payload, normalize_iban, validate_iban

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
