"""Vorbefuellung aus einem auf dem Beleg gefundenen EPC-Girocode.

Hintergrund: qr_scan.find_epc_payment_data() liefert zuverlaessigere,
strukturiert kodierte Daten als das Erraten per Texterkennung (siehe
app/services/extraction.py, insbesondere _extract_sender - "nimmt die erste
plausible Zeile an"). sender_name/invoice_number/amount_gross uebernehmen
deshalb bevorzugt die Girocode-Werte, wenn ein Girocode gefunden wurde, und
fallen nur auf die Texterkennung zurueck, wenn der Girocode dieses Feld nicht
enthaelt oder gar kein Girocode gefunden wurde.
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


def test_ingest_bevorzugt_girocode_daten_vor_geratenen_ocr_treffern(db, tmp_path, monkeypatch):
    """Die Texterkennung fuer sender_name ist reines Raten (erste plausible Zeile,

    siehe extraction._extract_sender) und liefert oft Muell (z.B. eine
    Marketing-Zeile statt des Firmennamens). Ein gefundener Girocode ist
    strukturiert und zuverlaessiger, muss also gewinnen statt nur als
    Fallback fuer leere Felder zu dienen.
    """
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)

    with (
        patch.object(
            ocr,
            "extract_text",
            return_value="Ihre Rechnung digital statt\nRechnungsnummer: RE-2026-42\nGesamtbetrag 55,00",
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

    assert invoice.sender_name == "Stadtwerke Musterstadt GmbH"
    assert invoice.invoice_number == "SW-2026-118432"
    assert invoice.amount_gross == Decimal("102.34")


def test_ingest_faellt_pro_feld_auf_ocr_zurueck_wenn_girocode_feld_fehlt(db, tmp_path, monkeypatch):
    """Ein Girocode ohne strukturierte Referenz darf die per Texterkennung

    gefundene Rechnungsnummer nicht loeschen - der Fallback greift pro Feld,
    nicht nur, wenn gar kein Girocode gefunden wurde.
    """
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    payment_ohne_referenz = {**_EPC_PAYMENT, "reference": None}

    with (
        patch.object(ocr, "extract_text", return_value="Rechnungsnummer: RE-2026-42"),
        patch.object(qr_scan, "find_epc_payment_data", return_value=payment_ohne_referenz),
    ):
        invoice, _ = ingest_document(
            db,
            content=b"%PDF-1.4 fake",
            original_filename="rechnung.pdf",
            mime_type="application/pdf",
            source_type="upload",
        )

    assert invoice.sender_name == "Stadtwerke Musterstadt GmbH"
    assert invoice.invoice_number == "RE-2026-42"


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
