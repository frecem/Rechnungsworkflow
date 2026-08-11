import smtplib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import STATUSES, Invoice
from app.services import storage
from app.services.smtp_client import SmtpNotConfigured, send_invoice
from app.services.status import InvalidStatusTransition, change_status

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw or not raw.strip():
        return None
    try:
        return Decimal(raw.strip().replace(",", "."))
    except InvalidOperation:
        return None


def _parse_date(raw: str | None) -> date | None:
    if not raw or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Rechnung nicht gefunden")
    return invoice


@router.get("/invoices")
def list_invoices(request: Request, status: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Invoice.sender_name.ilike(like)) | (Invoice.invoice_number.ilike(like))
        )
    invoices = query.order_by(Invoice.created_at.desc()).all()

    return templates.TemplateResponse(
        request,
        "invoice_list.html",
        {
            "invoices": invoices,
            "statuses": STATUSES,
            "current_status": status or "",
            "q": q or "",
        },
    )


@router.get("/invoices/{invoice_id}")
def invoice_detail(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    return templates.TemplateResponse(
        request,
        "invoice_detail.html",
        {
            "invoice": invoice,
            "categories": settings.category_list,
            "default_recipient": settings.forward_default_recipient,
            "smtp_configured": settings.smtp_configured,
        },
    )


@router.get("/invoices/{invoice_id}/file")
def invoice_file(invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    content = storage.read_file(invoice.file_path)
    media_type = invoice.file_mime_type or "application/octet-stream"
    return Response(content=content, media_type=media_type)


@router.post("/invoices/{invoice_id}/save")
def save_invoice(
    invoice_id: int,
    sender_name: str = Form(""),
    invoice_number: str = Form(""),
    invoice_date: str = Form(""),
    due_date: str = Form(""),
    amount_gross: str = Form(""),
    amount_net: str = Form(""),
    vat_amount: str = Form(""),
    vat_rate: str = Form(""),
    currency: str = Form("EUR"),
    category: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)

    invoice.sender_name = sender_name or None
    invoice.invoice_number = invoice_number or None
    invoice.invoice_date = _parse_date(invoice_date)
    invoice.due_date = _parse_date(due_date)
    invoice.amount_gross = _parse_decimal(amount_gross)
    invoice.amount_net = _parse_decimal(amount_net)
    invoice.vat_amount = _parse_decimal(vat_amount)
    invoice.vat_rate = _parse_decimal(vat_rate)
    invoice.currency = currency or "EUR"
    invoice.category = category or None
    invoice.notes = notes or None
    db.commit()

    if invoice.status in ("extracted", "rejected"):
        change_status(db, invoice, "reviewed", note="Felder geprueft/bearbeitet")

    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    try:
        change_status(db, invoice, "approved")
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: int, note: str = Form(""), db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    try:
        change_status(db, invoice, "rejected", note=note or None)
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/forward")
def forward_invoice(invoice_id: int, recipient: str = Form(...), db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)

    try:
        send_invoice(invoice, recipient)
    except SmtpNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"Versand fehlgeschlagen: {exc}") from exc

    invoice.forwarded_to = recipient
    invoice.forwarded_at = datetime.utcnow()
    db.commit()

    try:
        change_status(db, invoice, "forwarded")
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)
