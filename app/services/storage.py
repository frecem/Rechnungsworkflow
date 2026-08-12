import hashlib
import mimetypes
import re
from datetime import date
from pathlib import Path

from app.config import settings

STORAGE_ROOT = Path(settings.storage_dir)

# Belegformate, die die App entgegennimmt. Bewusst eine Allowlist statt einer
# Blocklist und bewusst *ohne* aktive Formate (kein text/html, kein image/svg+xml):
# Belege werden in der Vorschau im selben Origin eingebettet, ein Dokument mit
# ausfuehrbarem Inhalt waere damit ein Stored-XSS-Vektor gegen die eigene Session.
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/tiff",
    "image/heic",
    "image/heif",
}

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class UnsupportedFileType(Exception):
    """Dateityp ist nicht in ALLOWED_MIME_TYPES."""


class StoredFileMissing(Exception):
    """Datei ist laut Datenbank vorhanden, liegt aber nicht (mehr) im Storage."""


def is_allowed_mime_type(mime_type: str | None) -> bool:
    return mime_type in ALLOWED_MIME_TYPES


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return _SAFE_NAME_RE.sub("", name) or "datei"


def guess_mime_type(filename: str) -> str | None:
    return mimetypes.guess_type(filename)[0]


def safe_download_name(filename: str) -> str:
    """Dateiname fuer den Content-Disposition-Header, ohne Anfuehrungszeichen/Zeilenumbrueche.

    Verhindert, dass ein praeparierter Originalname aus dem Header ausbricht und
    weitere Header einschleust (Header-Injection).
    """
    return _safe_filename(filename)


def save_file(content: bytes, original_filename: str, received_on: date | None = None) -> tuple[str, str]:
    """Speichert Dateiinhalt unter storage/invoices/YYYY/<hash>_<name>.

    Gibt (relativer_pfad, sha256_hash) zurueck. Der relative Pfad ist relativ zu STORAGE_ROOT.
    """
    received_on = received_on or date.today()
    file_hash = sha256_of(content)
    year_dir = STORAGE_ROOT / str(received_on.year)
    year_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(original_filename)
    stored_name = f"{file_hash[:16]}_{safe_name}"
    full_path = year_dir / stored_name
    if not full_path.exists():
        full_path.write_bytes(content)

    relative_path = f"{received_on.year}/{stored_name}"
    return relative_path, file_hash


def absolute_path(relative_path: str) -> Path:
    """Loest einen gespeicherten Pfad auf und stellt sicher, dass er unterhalb von
    STORAGE_ROOT bleibt.

    save_file() erzeugt ausschliesslich harmlose Pfade, die Pruefung ist Absicherung
    in der Tiefe: ein manipulierter DB-Eintrag (z.B. aus einem fremden Backup)
    koennte sonst ueber '../' beliebige Dateien des Servers ausliefern.
    """
    root = STORAGE_ROOT.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise StoredFileMissing(f"Pfad liegt ausserhalb des Storage: {relative_path}")
    return candidate


def read_file(relative_path: str) -> bytes:
    path = absolute_path(relative_path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise StoredFileMissing(f"Belegdatei fehlt: {relative_path}") from exc
