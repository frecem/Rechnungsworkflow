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
async def upload_files(request: Request, files: list[UploadFile], db: Session = Depends(get_db)):
    results = []
    rejected: list[str] = []
    for file in files:
        content = await file.read()
        # Der vom Browser gemeldete Content-Type ist manipulierbar; guess_mime_type()
        # als Fallback nutzt nur die Dateiendung. Verlaesslich ist erst die Allowlist
        # in ingest_document(), die beide Angaben gegenpruefen laesst.
        mime_type = file.content_type or storage.guess_mime_type(file.filename or "")

        try:
            invoice, is_new = ingest_document(
                db,
                content=content,
                original_filename=file.filename or "beleg",
                mime_type=mime_type,
                source_type="upload",
                source_detail=file.filename,
            )
        except storage.UnsupportedFileType:
            rejected.append(file.filename or "unbenannt")
            continue
        results.append((invoice, is_new))

    if rejected and not results:
        return templates.TemplateResponse(
            request, "upload.html", {"rejected": rejected}, status_code=400
        )

    if len(results) == 1 and not rejected:
        invoice, is_new = results[0]
        if not is_new:
            return templates.TemplateResponse(request, "upload.html", {"duplicate_invoice": invoice})
        return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)

    new_count = sum(1 for _, is_new in results if is_new)
    duplicate_count = len(results) - new_count
    return RedirectResponse(
        f"/board?upload_new={new_count}&upload_dup={duplicate_count}&upload_rejected={len(rejected)}",
        status_code=303,
    )
