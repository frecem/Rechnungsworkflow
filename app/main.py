from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routers import email_sync, export, invoices, upload

app = FastAPI(title="Rechnungsworkflow")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(invoices.router)
app.include_router(upload.router)
app.include_router(email_sync.router)
app.include_router(export.router)


@app.get("/")
def root():
    return RedirectResponse("/invoices")
