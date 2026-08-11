from sqlalchemy.orm import Session

from app.models import AppSettings, Invoice

SETTINGS_ID = 1


def get_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, SETTINGS_ID)
    if settings is None:
        settings = AppSettings(id=SETTINGS_ID)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _save_category_list(db: Session, settings: AppSettings, categories: list[str]) -> None:
    settings.categories = ",".join(categories)
    db.commit()


def add_category(db: Session, name: str) -> None:
    settings = get_settings(db)
    name = name.strip()
    if not name:
        return
    categories = settings.category_list
    if name not in categories:
        categories.append(name)
        _save_category_list(db, settings, categories)


def rename_category(db: Session, old_name: str, new_name: str) -> None:
    """Benennt eine Kategorie um und aktualisiert alle Rechnungen, die sie verwenden,

    damit keine Rechnung durch die Umbenennung verwaist (auf eine nicht mehr in der
    Liste vorhandene Kategorie zeigt).
    """
    new_name = new_name.strip()
    if not new_name or old_name == new_name:
        return

    settings = get_settings(db)
    categories = settings.category_list
    if old_name not in categories:
        return

    categories = [new_name if c == old_name else c for c in categories]
    _save_category_list(db, settings, categories)

    db.query(Invoice).filter(Invoice.category == old_name).update({"category": new_name})
    db.commit()


def delete_category(db: Session, name: str) -> None:
    """Entfernt eine Kategorie aus der Auswahlliste.

    Rechnungen, die diese Kategorie bereits tragen, behalten ihren Wert (keine
    stille Datenverfälschung) - sie taucht in deren Formular dann als zusätzliche,
    weiterhin ausgewählte Option auf, ist aber für neue Zuordnungen nicht mehr wählbar.
    """
    settings = get_settings(db)
    categories = [c for c in settings.category_list if c != name]
    _save_category_list(db, settings, categories)
