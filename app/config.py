from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Nur Bootstrap-Infrastruktur (DB-Pfad, Storage-Pfad, Session-Secret).

    Alle Benutzerdaten (IMAP/SMTP/Weiterleitungs-Adressen/Kategorien/Login-Passwort)
    liegen in der Datenbank (app.models.AppSettings) und werden ueber die
    Login-geschuetzte Einstellungen-Seite verwaltet.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./storage/db.sqlite3"
    storage_dir: str = "./storage/invoices"
    session_secret_key: str = "change-me-please-a-long-random-string"


settings = Settings()
