from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services import girocode, qr_scan


def _epc_payload():
    return girocode.build_epc_payload(
        recipient_name="Stadtwerke Musterstadt GmbH",
        iban="DE89370400440532013000",
        bic="COBADEFFXXX",
        amount=Decimal("102.34"),
        reference="SW-2026-118432",
    )


def _zbar_result(data: str):
    result = MagicMock()
    result.data = data.encode("utf-8")
    return result


def test_find_epc_payment_data_from_pdf_prefills_correctly():
    fake_image = object()
    with (
        patch("pdf2image.convert_from_bytes", return_value=[fake_image]),
        patch("pyzbar.pyzbar.decode", return_value=[_zbar_result(_epc_payload())]),
    ):
        result = qr_scan.find_epc_payment_data(b"%PDF-1.4 fake", "application/pdf")

    assert result == {
        "recipient_name": "Stadtwerke Musterstadt GmbH",
        "iban": "DE89370400440532013000",
        "bic": "COBADEFFXXX",
        "amount": Decimal("102.34"),
        "reference": "SW-2026-118432",
    }


def test_find_epc_payment_data_ignores_non_epc_qr_codes():
    fake_image = object()
    with (
        patch("pdf2image.convert_from_bytes", return_value=[fake_image]),
        patch("pyzbar.pyzbar.decode", return_value=[_zbar_result("https://example.com/tracking")]),
    ):
        result = qr_scan.find_epc_payment_data(b"%PDF-1.4 fake", "application/pdf")

    assert result is None


def test_find_epc_payment_data_no_qr_found_returns_none():
    fake_image = object()
    with (
        patch("pdf2image.convert_from_bytes", return_value=[fake_image]),
        patch("pyzbar.pyzbar.decode", return_value=[]),
    ):
        result = qr_scan.find_epc_payment_data(b"%PDF-1.4 fake", "application/pdf")

    assert result is None


def test_find_epc_payment_data_pdf_conversion_failure_returns_none():
    with patch("pdf2image.convert_from_bytes", side_effect=OSError("poppler missing")):
        result = qr_scan.find_epc_payment_data(b"%PDF-1.4 fake", "application/pdf")

    assert result is None


def test_find_epc_payment_data_unsupported_mime_type_returns_none():
    result = qr_scan.find_epc_payment_data(b"irrelevant", "text/plain")
    assert result is None


def test_find_epc_payment_data_zbar_decode_failure_returns_none():
    fake_image = object()
    with (
        patch("pdf2image.convert_from_bytes", return_value=[fake_image]),
        patch("pyzbar.pyzbar.decode", side_effect=RuntimeError("zbar not installed")),
    ):
        result = qr_scan.find_epc_payment_data(b"%PDF-1.4 fake", "application/pdf")

    assert result is None
