from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./storage/db.sqlite3"
    storage_dir: str = "./storage/invoices"

    imap_host: str | None = None
    imap_port: int = 993
    imap_user: str | None = None
    imap_app_password: str | None = None
    imap_mailbox: str = "INBOX"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    forward_default_recipient: str | None = None

    categories: str = "Büro,Software,Reise,Sonstiges"

    @property
    def category_list(self) -> list[str]:
        return [c.strip() for c in self.categories.split(",") if c.strip()]

    @property
    def imap_configured(self) -> bool:
        return bool(self.imap_host and self.imap_user and self.imap_app_password)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


settings = Settings()
