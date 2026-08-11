# Rechnungsworkflow

Kleine lokale Web-App zum **Verarbeiten eingehender Rechnungen** (privat/persönlich):
Belege kommen per E-Mail (IMAP) oder als manueller Foto-/Scan-Upload rein, werden per
OCR ausgelesen, im Browser geprüft/korrigiert, freigegeben und optional per E-Mail
weitergeleitet (z.B. an eine Steuerberatung). Ein CSV-Export bereitet die Daten für
Steuer/Buchhaltung auf.

Einzelnutzer-Tool, läuft komplett lokal, kein Login, keine Cloud-Abhängigkeit.

## Status-Workflow

```
new → extracted → reviewed → approved → forwarded
                       ↳ rejected ↵ (zurück zu reviewed möglich)
```

## Setup

### 1. Systempakete (für OCR)

```bash
# Debian/Ubuntu
sudo apt install tesseract-ocr tesseract-ocr-deu poppler-utils

# macOS (Homebrew)
brew install tesseract tesseract-lang poppler
```

Ohne diese Pakete funktioniert der Upload trotzdem – nur die OCR-Fallback-Extraktion
für gescannte/fotografierte Belege liefert dann keinen Text (PDFs mit echtem
Textlayer werden unabhängig davon korrekt gelesen). Alle Felder sind ohnehin immer
manuell nachbearbeitbar.

### 2. Python-Umgebung

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Konfiguration

```bash
cp .env.example .env
```

`.env` ausfüllen:
- `IMAP_*` – nur nötig für den E-Mail-Sync (z.B. Gmail-App-Passwort verwenden, da normale Passwörter oft nicht per IMAP funktionieren)
- `SMTP_*` / `FORWARD_DEFAULT_RECIPIENT` – nur nötig für die Weiterleitungsfunktion
- `CATEGORIES` – Komma-getrennte Liste eigener Kategorien

Die App startet auch ohne IMAP/SMTP-Konfiguration; die jeweiligen Funktionen (Sync-Button,
Weiterleiten-Formular) zeigen dann einen Hinweis statt eines Fehlers.

### 4. Datenbank

```bash
alembic upgrade head
```

### 5. Starten

```bash
uvicorn app.main:app --reload --port 8000
```

Öffnen: http://localhost:8000

## Bedienung

- **Hochladen** (`/upload`): PDF oder Foto/Scan (JPG/PNG) einer Rechnung hochladen. Die App
  liest zuerst den PDF-Textlayer, falls vorhanden; sonst OCR über Tesseract. Ergebnis landet
  im Status `extracted`, alle erkannten Felder sind sofort editierbar.
- **E-Mails synchronisieren** (Button oben rechts): holt neue Anhänge (PDF/JPG/PNG) aus dem
  konfigurierten IMAP-Postfach ab (read-only, verändert nichts im Postfach). Bereits verarbeitete
  Nachrichten werden über die letzte gesehene IMAP-UID nicht erneut abgerufen.
- **Übersicht** (`/invoices`): Liste aller Rechnungen, filterbar nach Status und durchsuchbar
  nach Absender/Rechnungsnummer.
- **Detailansicht**: Dateivorschau links, editierbares Formular rechts. Absender ist das am
  wenigsten zuverlässige Feld und wird entsprechend markiert. Aktionen: Speichern, Freigeben,
  Ablehnen; nach Freigabe zusätzlich Weiterleiten per E-Mail.
- **CSV-Export** (`/export/csv`, optional mit `?status=&category=&date_from=&date_to=`):
  lädt eine `;`-getrennte CSV mit deutschem Dezimalformat (Komma statt Punkt). Netto/USt/Brutto
  sind getrennte Spalten, damit sich später bei Bedarf ein DATEV-Export ergänzen lässt, ohne
  das Datenmodell zu ändern.

## Duplikaterkennung

Jede Datei wird beim Speichern per SHA-256 gehasht. Ein erneuter Upload (oder E-Mail-Anhang)
mit identischem Inhalt wird erkannt und nicht doppelt angelegt.

## Tests

```bash
pytest tests/
```

Deckt die Extraktions-Heuristiken (`app/services/extraction.py`) und die
Datei-Speicherlogik (`app/services/storage.py`) ab – ohne Abhängigkeit von Tesseract/Poppler,
läuft daher überall.

## Manuelle Verifikation (bereits durchgeführt)

Der komplette Kernablauf wurde lokal end-to-end getestet: PDF-Upload → automatische
Extraktion (Absender/Rechnungsnr./Datum/Netto/USt/Brutto) → Speichern → Freigeben →
CSV-Export mit korrekten Werten. Duplikat-Upload und Dateivorschau (`/invoices/{id}/file`)
wurden ebenfalls verifiziert. E-Mail-Sync und SMTP-Weiterleitung sind implementiert, aber
mangels echtem Postfach/SMTP-Zugang in dieser Umgebung nicht live getestet – bitte nach dem
Ausfüllen von `.env` einmal mit einer echten Test-Mail bzw. einer Test-Weiterleitung prüfen.
