"""Erstellt ein ZIP-Backup aus Datenbank und Belegdateien zum Download.

Die Datenbank wird ueber die SQLite-Backup-API konsistent kopiert (nicht per
einfachem Dateikopieren), damit ein gleichzeitiger Schreibzugriff der laufenden
App das Backup nicht beschaedigen kann.
"""

import io
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.storage import STORAGE_ROOT

_DB_PATH = Path(settings.database_url.removeprefix("sqlite:///"))


def _snapshot_database() -> bytes:
    """Kopiert die DB ueber die SQLite-Backup-API in eine temporaere Datei und liest sie ein.

    Robuster als ein einfaches Dateikopieren, da die Backup-API auch bei
    gleichzeitigem Schreibzugriff der laufenden App einen konsistenten Snapshot liefert.
    """
    source = sqlite3.connect(str(_DB_PATH))
    try:
        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as tmp:
            dest = sqlite3.connect(tmp.name)
            try:
                source.backup(dest)
            finally:
                dest.close()
            tmp.seek(0)
            return tmp.read()
    finally:
        source.close()


def build_backup_zip() -> bytes:
    """Baut ein ZIP mit einer konsistenten DB-Kopie und allen Belegdateien."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("db.sqlite3", _snapshot_database())

        if STORAGE_ROOT.exists():
            for file_path in STORAGE_ROOT.rglob("*"):
                if file_path.is_file():
                    arcname = f"invoices/{file_path.relative_to(STORAGE_ROOT)}"
                    zf.write(file_path, arcname)

    return buffer.getvalue()


def backup_filename() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"rechnungsworkflow_backup_{timestamp}.zip"
