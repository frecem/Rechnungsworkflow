import imaplib

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.imap_client import ImapNotConfigured, sync_new_invoices

router = APIRouter()


@router.post("/email-sync")
def email_sync(db: Session = Depends(get_db)):
    try:
        result = sync_new_invoices(db)
    except ImapNotConfigured:
        return RedirectResponse("/invoices?sync_error=not_configured", status_code=303)
    except (imaplib.IMAP4.error, OSError):
        return RedirectResponse("/invoices?sync_error=connection", status_code=303)

    return RedirectResponse(
        f"/invoices?sync_new={result.get('new_invoices', 0)}&sync_dup={result.get('duplicates', 0)}",
        status_code=303,
    )
