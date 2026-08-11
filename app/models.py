from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

STATUSES = ("new", "extracted", "reviewed", "approved", "rejected", "forwarded")


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
