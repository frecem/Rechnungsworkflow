FROM python:3.11-slim

# tesseract-ocr + Sprachpaket + poppler-utils: fuer die OCR-Fallback-Extraktion
# gescannter/fotografierter Belege (siehe app/services/ocr.py). PDFs mit echtem
# Textlayer werden unabhaengig davon per pypdf/pdfplumber gelesen.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-deu \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
