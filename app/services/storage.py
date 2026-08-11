import hashlib
import mimetypes
import re
from datetime import date
from pathlib import Path

from app.config import settings

STORAGE_ROOT = Path(settings.storage_dir)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sha256_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return _SAFE_NAME_RE.sub("", name) or "datei"


def guess_mime_type(filename: str) -> str | None:
    return mimetypes.guess_type(filename)[0]


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


def read_file(relative_path: str) -> bytes:
    return (STORAGE_ROOT / relative_path).read_bytes()


def absolute_path(relative_path: str) -> Path:
    return STORAGE_ROOT / relative_path
