from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

STATUSES = ("new", "extracted", "reviewed", "approved", "rejected", "forwarded")
FORWARD_TARGETS = ("steuer", "paperless", "both")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Quelle
    source_type: Mapped[str]  # "email" | "upload"
    source_detail: Mapped[str | None]  # z.B. IMAP message-id oder Original-Dateiname
    email_from: Mapped[str | None]

    # Dateiablage
    file_path: Mapped[str]
    file_original_name: Mapped[str | None]
    file_mime_type: Mapped[str | None]
    file_hash_sha256: Mapped[str] = mapped_column(unique=True)

    # Extrahierte Felder (immer manuell editierbar)
    sender_name: Mapped[str | None]
    invoice_number: Mapped[str | None]
    invoice_date: Mapped[date | None]
    due_date: Mapped[date | None]
    amount_gross: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    amount_net: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    currency: Mapped[str] = mapped_column(default="EUR")
    category: Mapped[str | None]

    raw_extracted_text: Mapped[str | None]

    # Lifecycle
    status: Mapped[str] = mapped_column(default="new")
    forwarded_to: Mapped[str | None]
    forwarded_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Girocode / SEPA-Zahlungsdaten (aus der Pruefmaske vor der Freigabe)
    payment_recipient_name: Mapped[str | None]
    payment_iban: Mapped[str | None]
    payment_bic: Mapped[str | None]
    payment_reference: Mapped[str | None]
    girocode_sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Bezahlt-Markierung (orthogonal zum Status-Workflow) und Fälligkeits-Erinnerung
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    due_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Wiederkehrende Zahlungen (z.B. Miete, Abos) - Gruppierung ueber sender_name.
    # recurring_ended gilt fuer die gesamte Serie, sobald es auf der jeweils
    # aktuellsten Rechnung der Gruppe gesetzt ist (siehe app/services/stats.py).
    is_recurring: Mapped[bool] = mapped_column(default=False)
    recurrence_interval_days: Mapped[int | None]
    recurring_ended: Mapped[bool] = mapped_column(default=False)

    # Kanban-Board-Zuordnung
    board_column_id: Mapped[int | None] = mapped_column(ForeignKey("board_columns.id"))
    board_position: Mapped[int] = mapped_column(default=0)

    notes: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class InvoiceStatusHistory(Base):
    __tablename__ = "invoice_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    old_status: Mapped[str | None]
    new_status: Mapped[str]
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None]


class SyncState(Base):
    """Trackt den letzten verarbeiteten IMAP-UID pro Postfach, um doppelten Abruf zu vermeiden."""

    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox: Mapped[str] = mapped_column(unique=True)
    last_uid: Mapped[int] = mapped_column(default=0)


class BoardColumn(Base):
    """Frei benennbare Kanban-Spalte, vom Nutzer selbst angelegt/umbenannt/sortiert."""

    __tablename__ = "board_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    position: Mapped[int] = mapped_column(default=0)


class AppSettings(Base):
    """Singleton-Zeile (id=1) mit allen ueber die Einstellungen-Seite verwalteten Zugangsdaten."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)

    admin_password_hash: Mapped[str | None]

    imap_host: Mapped[str | None]
    imap_port: Mapped[int] = mapped_column(default=993)
    imap_user: Mapped[str | None]
    imap_app_password: Mapped[str | None]
    imap_mailbox: Mapped[str] = mapped_column(default="INBOX")

    smtp_host: Mapped[str | None]
    smtp_port: Mapped[int] = mapped_column(default=587)
    smtp_user: Mapped[str | None]
    smtp_password: Mapped[str | None]

    steuer_email: Mapped[str | None]
    paperless_email: Mapped[str | None]
    girocode_email: Mapped[str | None]
    default_forward_target: Mapped[str] = mapped_column(default="steuer")

    reminder_email: Mapped[str | None]
    reminder_days_before: Mapped[int] = mapped_column(default=3)

    imap_consecutive_failures: Mapped[int] = mapped_column(default=0)
    imap_failure_notified_at: Mapped[datetime | None] = mapped_column(DateTime)

    password_reset_token: Mapped[str | None]
    password_reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    last_backup_at: Mapped[datetime | None] = mapped_column(DateTime)

    categories: Mapped[str] = mapped_column(default="Büro,Software,Reise,Sonstiges")

    @property
    def category_list(self) -> list[str]:
        return [c.strip() for c in self.categories.split(",") if c.strip()]

    @property
    def imap_configured(self) -> bool:
        return bool(self.imap_host and self.imap_user and self.imap_app_password)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def password_set(self) -> bool:
        return bool(self.admin_password_hash)
