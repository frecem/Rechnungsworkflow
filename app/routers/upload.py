from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import storage
from app.services.ingest import ingest_document

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/upload")
def upload_form(request: Request):
    return templates.TemplateResponse(request, "upload.html", {})


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile, db: Session = Depends(get_db)):
    content = await file.read()
    mime_type = file.content_type or storage.guess_mime_type(file.filename or "")

    invoice, is_new = ingest_document(
        db,
        content=content,
        original_filename=file.filename or "beleg",
        mime_type=mime_type,
        source_type="upload",
        source_detail=file.filename,
    )

    if not is_new:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {"duplicate_invoice": invoice},
        )

    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
