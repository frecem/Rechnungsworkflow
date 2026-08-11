from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceStatusHistory

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"extracted"},
    "extracted": {"reviewed", "rejected"},
    "reviewed": {"approved", "rejected", "extracted"},
    "approved": {"forwarded", "rejected"},
    "rejected": {"reviewed"},
    "forwarded": set(),
}


class InvalidStatusTransition(Exception):
    pass


def change_status(db: Session, invoice: Invoice, new_status: str, note: str | None = None) -> Invoice:
    allowed = ALLOWED_TRANSITIONS.get(invoice.status, set())
    if new_status not in allowed:
        raise InvalidStatusTransition(
            f"Wechsel von '{invoice.status}' zu '{new_status}' ist nicht erlaubt."
        )

    old_status = invoice.status
    invoice.status = new_status
    db.add(InvoiceStatusHistory(invoice_id=invoice.id, old_status=old_status, new_status=new_status, note=note))
    db.commit()
    db.refresh(invoice)
    return invoice
