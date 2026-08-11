import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSettings, Invoice
from app.services.settings_service import add_category, delete_category, get_settings, rename_category


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _settings(db, categories="Büro,Software"):
    settings = AppSettings(id=1, categories=categories)
    db.add(settings)
    db.commit()
    return settings


def _invoice(db, *, hash_suffix, category=None):
    invoice = Invoice(
        source_type="upload",
        file_path=f"x/{hash_suffix}",
        file_hash_sha256=f"hash-{hash_suffix}",
        category=category,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def test_add_category_appends_new_name(db):
    _settings(db)
    add_category(db, "Reise")
    settings = get_settings(db)
    assert settings.category_list == ["Büro", "Software", "Reise"]


def test_add_category_ignores_duplicate(db):
    _settings(db)
    add_category(db, "Büro")
    settings = get_settings(db)
    assert settings.category_list == ["Büro", "Software"]


def test_add_category_ignores_blank(db):
    _settings(db)
    add_category(db, "   ")
    settings = get_settings(db)
    assert settings.category_list == ["Büro", "Software"]


def test_rename_category_updates_list(db):
    _settings(db)
    rename_category(db, "Büro", "Office")
    settings = get_settings(db)
    assert settings.category_list == ["Office", "Software"]


def test_rename_category_cascades_to_invoices(db):
    _settings(db)
    inv = _invoice(db, hash_suffix="a", category="Büro")
    other = _invoice(db, hash_suffix="b", category="Software")

    rename_category(db, "Büro", "Office")

    db.refresh(inv)
    db.refresh(other)
    assert inv.category == "Office"
    assert other.category == "Software"


def test_rename_category_unknown_name_is_noop(db):
    _settings(db)
    rename_category(db, "Unbekannt", "Neu")
    settings = get_settings(db)
    assert settings.category_list == ["Büro", "Software"]


def test_delete_category_removes_from_list(db):
    _settings(db)
    delete_category(db, "Büro")
    settings = get_settings(db)
    assert settings.category_list == ["Software"]


def test_delete_category_does_not_touch_existing_invoices(db):
    _settings(db)
    inv = _invoice(db, hash_suffix="a", category="Büro")

    delete_category(db, "Büro")

    db.refresh(inv)
    settings = get_settings(db)
    assert "Büro" not in settings.category_list
    assert inv.category == "Büro"
