import io
import sqlite3
import zipfile
from datetime import date, datetime, timedelta

from app.models import AppSettings
from app.services.backup import BACKUP_REMINDER_DAYS, backup_filename, build_backup_zip, is_backup_overdue


def test_backup_filename_has_zip_extension():
    assert backup_filename().endswith(".zip")
    assert backup_filename().startswith("rechnungsworkflow_backup_")


def test_build_backup_zip_contains_valid_sqlite_db():
    content = build_backup_zip()
    zf = zipfile.ZipFile(io.BytesIO(content))

    assert "db.sqlite3" in zf.namelist()

    db_bytes = zf.read("db.sqlite3")
    assert db_bytes.startswith(b"SQLite format 3")

    # Sicherstellen, dass die kopierte DB tatsaechlich abfragbar ist
    with zipfile.ZipFile(io.BytesIO(content)) as zf2:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as tmp:
            tmp.write(zf2.read("db.sqlite3"))
            tmp.flush()
            con = sqlite3.connect(tmp.name)
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            con.close()

    assert "invoices" in tables
    assert "app_settings" in tables


def test_build_backup_zip_includes_invoice_files(tmp_path, monkeypatch):
    import app.services.backup as backup_module

    fake_storage = tmp_path / "invoices"
    (fake_storage / "2026").mkdir(parents=True)
    (fake_storage / "2026" / "test.pdf").write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(backup_module, "STORAGE_ROOT", fake_storage)

    content = build_backup_zip()
    zf = zipfile.ZipFile(io.BytesIO(content))

    assert "invoices/2026/test.pdf" in zf.namelist()
    assert zf.read("invoices/2026/test.pdf") == b"%PDF-1.4 fake"


def test_is_backup_overdue_when_never_backed_up():
    settings = AppSettings(id=1, last_backup_at=None)
    assert is_backup_overdue(settings) is True


def test_is_backup_overdue_false_shortly_after_backup():
    settings = AppSettings(id=1, last_backup_at=datetime.utcnow())
    assert is_backup_overdue(settings, today=date.today()) is False


def test_is_backup_overdue_true_after_threshold():
    today = date.today()
    settings = AppSettings(
        id=1, last_backup_at=datetime.combine(today - timedelta(days=BACKUP_REMINDER_DAYS), datetime.min.time())
    )
    assert is_backup_overdue(settings, today=today) is True


def test_is_backup_overdue_false_just_below_threshold():
    today = date.today()
    settings = AppSettings(
        id=1,
        last_backup_at=datetime.combine(today - timedelta(days=BACKUP_REMINDER_DAYS - 1), datetime.min.time()),
    )
    assert is_backup_overdue(settings, today=today) is False
