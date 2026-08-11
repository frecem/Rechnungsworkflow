from datetime import date

from app.services.storage import absolute_path, read_file, save_file, sha256_of


def test_sha256_of_is_deterministic():
    content = b"hello world"
    assert sha256_of(content) == sha256_of(content)


def test_save_file_roundtrip(tmp_path, monkeypatch):
    import app.services.storage as storage_module

    monkeypatch.setattr(storage_module, "STORAGE_ROOT", tmp_path)

    content = b"%PDF-1.4 fake content"
    relative_path, file_hash = save_file(content, "Rechnung Müller.pdf", received_on=date(2026, 8, 11))

    assert relative_path.startswith("2026/")
    assert file_hash == sha256_of(content)
    assert read_file(relative_path) == content
    assert absolute_path(relative_path).exists()


def test_save_file_is_idempotent_for_same_content(tmp_path, monkeypatch):
    import app.services.storage as storage_module

    monkeypatch.setattr(storage_module, "STORAGE_ROOT", tmp_path)

    content = b"same content"
    path1, hash1 = save_file(content, "a.pdf", received_on=date(2026, 1, 1))
    path2, hash2 = save_file(content, "a.pdf", received_on=date(2026, 1, 1))

    assert path1 == path2
    assert hash1 == hash2
