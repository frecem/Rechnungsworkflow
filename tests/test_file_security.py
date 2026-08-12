"""Absicherung der Datei-Annahme und -Auslieferung.

Hintergrund: Belege werden in der Detailansicht im selben Origin eingebettet
(iframe/img). Ein Dokument mit ausfuehrbarem Inhalt (HTML/SVG) waere damit ein
Stored-XSS-Vektor gegen die eigene Session, deshalb die Allowlist.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services import storage
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


@pytest.mark.parametrize(
    "mime_type",
    ["application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"],
)
def test_belegformate_sind_erlaubt(mime_type):
    assert storage.is_allowed_mime_type(mime_type) is True


@pytest.mark.parametrize(
    "mime_type",
    [
        "text/html",
        "image/svg+xml",  # SVG kann <script> enthalten
        "application/xhtml+xml",
        "text/xml",
        "application/javascript",
        "application/octet-stream",
        None,
    ],
)
def test_aktive_und_unbekannte_formate_sind_gesperrt(mime_type):
    assert storage.is_allowed_mime_type(mime_type) is False


def test_ingest_lehnt_html_ab_und_speichert_nichts(db, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)

    with pytest.raises(storage.UnsupportedFileType):
        ingest_document(
            db,
            content=b"<script>alert(1)</script>",
            original_filename="boese.html",
            mime_type="text/html",
            source_type="upload",
        )

    # Weder Datei noch Datenbankeintrag duerfen entstanden sein.
    assert list(tmp_path.rglob("*")) == []


def test_ingest_lehnt_svg_ab(db, tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)

    with pytest.raises(storage.UnsupportedFileType):
        ingest_document(
            db,
            content=b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            original_filename="boese.svg",
            mime_type="image/svg+xml",
            source_type="upload",
        )


def test_absolute_path_blockt_ausbruch_aus_dem_storage():
    with pytest.raises(storage.StoredFileMissing):
        storage.absolute_path("../../../../../../etc/passwd")


def test_absolute_path_erlaubt_normalen_pfad(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    result = storage.absolute_path("2026/beleg.pdf")
    assert result == (tmp_path / "2026" / "beleg.pdf").resolve()


def test_read_file_meldet_fehlende_datei_sauber(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path)
    with pytest.raises(storage.StoredFileMissing):
        storage.read_file("2026/gibtesnicht.pdf")


def test_safe_download_name_entfernt_header_injection():
    boese = 'rechnung".pdf\r\nX-Injected: 1'
    sauber = storage.safe_download_name(boese)
    assert '"' not in sauber
    assert "\r" not in sauber
    assert "\n" not in sauber
