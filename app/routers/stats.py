from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice
from app.services.stats import available_years, compute_yearly_stats

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/stats")
def stats_view(request: Request, year: int | None = None, db: Session = Depends(get_db)):
    invoices = db.query(Invoice).filter(Invoice.invoice_date.isnot(None)).all()
    years = available_years(invoices)
    selected_year = year or (years[0] if years else date.today().year)

    stats = compute_yearly_stats(invoices, selected_year)

    return templates.TemplateResponse(
        request,
        "stats.html",
        {"stats": stats, "years": years, "selected_year": selected_year},
    )
