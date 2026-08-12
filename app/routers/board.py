import contextlib

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Invoice
from app.services import board_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/board")
def board_view(request: Request, db: Session = Depends(get_db)):
    columns = board_service.list_columns(db)
    invoices_by_column = {
        column.id: (
            db.query(Invoice)
            .filter(Invoice.board_column_id == column.id)
            .order_by(Invoice.board_position.asc())
            .all()
        )
        for column in columns
    }
    return templates.TemplateResponse(
        request,
        "board.html",
        {"columns": columns, "invoices_by_column": invoices_by_column},
    )


class MovePayload(BaseModel):
    invoice_id: int
    column_id: int
    position: int


@router.post("/board/move")
def move_card(payload: MovePayload, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, payload.invoice_id)
    if invoice is None:
        return {"ok": False, "error": "Rechnung nicht gefunden"}
    board_service.move_invoice(db, invoice, payload.column_id, payload.position)
    return {"ok": True}


@router.get("/board/columns")
def manage_columns(request: Request, db: Session = Depends(get_db)):
    columns = board_service.list_columns(db)
    return templates.TemplateResponse(request, "board_columns.html", {"columns": columns})


@router.post("/board/columns")
def add_column(name: str = Form(...), db: Session = Depends(get_db)):
    board_service.create_column(db, name)
    return RedirectResponse("/board/columns", status_code=303)


@router.post("/board/columns/{column_id}/rename")
def rename_column(column_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    board_service.rename_column(db, column_id, name)
    return RedirectResponse("/board/columns", status_code=303)


@router.post("/board/columns/{column_id}/delete")
def delete_column(column_id: int, db: Session = Depends(get_db)):
    with contextlib.suppress(board_service.LastColumnError):
        board_service.delete_column(db, column_id)
    return RedirectResponse("/board/columns", status_code=303)


@router.post("/board/columns/{column_id}/move")
def move_column(column_id: int, direction: str = Form(...), db: Session = Depends(get_db)):
    board_service.move_column(db, column_id, direction)
    return RedirectResponse("/board/columns", status_code=303)
