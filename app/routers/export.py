from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice
from app.services.export_csv import build_csv

router = APIRouter()


@router.get("/export/csv")
def export_csv(
    status: str | None = None,
    category: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    if category:
        query = query.filter(Invoice.category == category)
    if date_from:
        query = query.filter(Invoice.invoice_date >= date_from)
    if date_to:
        query = query.filter(Invoice.invoice_date <= date_to)

    invoices = query.order_by(Invoice.invoice_date.asc()).all()
    csv_content = build_csv(invoices)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rechnungen_export.csv"},
    )
