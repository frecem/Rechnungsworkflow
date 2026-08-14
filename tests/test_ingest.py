"""Vorbefuellung aus einem auf dem Beleg gefundenen EPC-Girocode.

Hintergrund: qr_scan.find_epc_payment_data() liefert zuverlaessigere Daten als
das Erraten per Texterkennung (siehe app/services/extraction.py). amount_gross
nutzte das bereits als Fallback; sender_name/invoice_number sollen aus dem
gleichen Grund vom Girocode-Empfaengernamen bzw. der Zahlungsreferenz
profitieren, wenn die Texterkennung dafuer nichts gefunden hat.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services import ocr, qr_scan, storage
from app.services.ingest import ingest_document


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


_EPC_PAYMENT = {
    "recipient_name": "Stadtwerke Musterstadt GmbH",
    "iban": "DE89370400440532013000",
    "bic": "COBADEFFXXX",
    "amount": Decimal("102.34"),
    "reference": "SW-2026-118432",
}


def test_ingest_uebernimmt_girocode_daten_wenn_ocr_nichts_findet(db, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)

    with (
        patch.object(ocr, "extract_text", return_value=""),
        patch.object(qr_scan, "find_epc_payment_data", return_value=_EPC_PAYMENT),
    ):
        invoice, is_new = ingest_document(
            db,
            content=b"%PDF-1.4 fake",
            original_filename="rechnung.pdf",
            mime_type="application/pdf",
            source_type="upload",
        )

    assert is_new is True
    assert invoice.sender_name == "Stadtwerke Musterstadt GmbH"
    assert invoice.invoice_number == "SW-2026-118432"
    assert invoice.amount_gross == Decimal("102.34")
    assert invoice.payment_recipient_name == "Stadtwerke Musterstadt GmbH"
    assert invoice.payment_iban == "DE89370400440532013000"


def test_ingest_bevorzugt_ocr_treffer_vor_girocode_daten(db, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)

    with (
        patch.object(
            ocr,
            "extract_text",
            return_value="Musterfirma AG\nRechnungsnummer: RE-2026-42\nGesamtbetrag 55,00",
        ),
        patch.object(qr_scan, "find_epc_payment_data", return_value=_EPC_PAYMENT),
    ):
        invoice, _ = ingest_document(
            db,
            content=b"%PDF-1.4 fake",
            original_filename="rechnung.pdf",
            mime_type="application/pdf",
            source_type="upload",
        )

    assert invoice.sender_name == "Musterfirma AG"
    assert invoice.invoice_number == "RE-2026-42"
    assert invoice.amount_gross == Decimal("55.00")


def test_ingest_ohne_girocode_bleibt_unveraendert(db, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)

    with (
        patch.object(ocr, "extract_text", return_value=""),
        patch.object(qr_scan, "find_epc_payment_data", return_value=None),
    ):
        invoice, _ = ingest_document(
            db,
            content=b"%PDF-1.4 fake",
            original_filename="rechnung.pdf",
            mime_type="application/pdf",
            source_type="upload",
        )

    assert invoice.sender_name is None
    assert invoice.invoice_number is None
    assert invoice.amount_gross is None
