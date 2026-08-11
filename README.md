# Rechnungsworkflow

Kleine lokale Web-App zum **Verarbeiten eingehender Rechnungen** (privat/persönlich):
Belege kommen per E-Mail (IMAP) oder als manueller Foto-/Scan-Upload rein, werden per
OCR ausgelesen, auf einem Kanban-Board organisiert, im Browser geprüft/korrigiert und
freigegeben. Bei der Freigabe wird ein Girocode (EPC-QR-Code) zum Bezahlen erzeugt und
die Rechnung automatisch an eine Steuer-App und/oder Paperless-ngx weitergeleitet.

Einzelnutzer-Tool mit einfachem Passwortschutz, läuft komplett lokal, keine
Cloud-Abhängigkeit.

## Status-Workflow

```
new → extracted → reviewed → approved → forwarded
                       ↳ rejected ↵ (zurück zu reviewed möglich)
```

Freigabe (`approved`) führt zur Girocode-Prüfmaske; nach erfolgreichem Versand von
Girocode und Weiterleitung wechselt der Status zu `forwarded`.

Unabhängig davon lässt sich jede Rechnung auf dem **Kanban-Board** frei zwischen
selbst angelegten Spalten verschieben (z.B. "Bezahlen bis diese Woche", "Später",
"Bezahlt") – das Board dient der eigenen Organisation und ist von den Status oben
unabhängig.

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

### 3. Bootstrap-Konfiguration

```bash
cp .env.example .env
```

`.env` enthält nur Infrastruktur (DB-Pfad, Storage-Pfad, `SESSION_SECRET_KEY`).
Ein zufälliges Session-Secret erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Alle Benutzerdaten** (IMAP, SMTP, Weiterleitungs-Adressen, Kategorien) werden
**nicht** in `.env` gepflegt, sondern nach dem Start über die Weboberfläche.

### 4. Datenbank

```bash
alembic upgrade head
```

### 5. Starten

```bash
uvicorn app.main:app --reload --port 8000
```

Öffnen: http://localhost:8000 – beim ersten Start wirst du zur Ersteinrichtung
(`/setup`) weitergeleitet und legst dort ein Passwort fest.

### 6. Einstellungen ausfüllen

Nach dem Login unter **Einstellungen** (`/settings`) hinterlegen:
- IMAP-Zugangsdaten (für automatischen E-Mail-Abruf, z.B. Gmail-App-Passwort, da
  normale Passwörter oft nicht per IMAP funktionieren)
- SMTP-Zugangsdaten (für Girocode-Versand und Weiterleitung)
- **Steuer-App-Adresse**: Scan-E-Mail-Eingang deiner Steuer-Software (z.B. die
  [Buhl Steuer-Scan-App](https://www.buhl.de/steuer/steuer-scan-app/))
- **Paperless-ngx-Adresse**: [E-Mail-Eingang](https://docs.paperless-ngx.com/usage/#usage-email)
  deiner paperless-ngx-Instanz
- **Girocode-Empfänger-Adresse**: wohin der erzeugte Zahlungs-QR-Code (PNG) gesendet wird
- Standard-Weiterleitungsziel (Steuer / Paperless / beides) – vorbelegt bei jeder
  Freigabe, pro Rechnung änderbar
- Kategorien-Liste

Die App startet auch ohne vollständig ausgefüllte Einstellungen; die jeweiligen
Funktionen (Sync-Button, Girocode-Formular) zeigen dann einen Hinweis statt eines
Fehlers.

## Bedienung

- **Board** (`/board`, Startseite): Kanban-Ansicht aller Rechnungen. Direkt oben eine
  Drag&Drop-Upload-Zone (PDF/Foto/Scan per Ziehen oder Klick), ohne extra auf
  `/upload` navigieren zu müssen. Spalten frei anlegen/umbenennen/löschen/sortieren
  unter "Spalten verwalten". Karten per Drag&Drop zwischen Spalten verschieben. Neue
  Rechnungen landen automatisch in der ersten Spalte.
- **Hochladen** (`/upload`): PDF oder Foto/Scan (JPG/PNG) einer Rechnung hochladen.
  Die App liest zuerst den PDF-Textlayer, falls vorhanden; sonst OCR über Tesseract.
  Ergebnis landet im Status `extracted`, alle erkannten Felder sind sofort editierbar.
- **E-Mails synchronisieren** (Button oben rechts): holt neue Anhänge (PDF/JPG/PNG)
  aus dem konfigurierten IMAP-Postfach ab (read-only, verändert nichts im Postfach).
- **Übersicht** (`/invoices`): tabellarische Liste, filterbar nach Status, durchsuchbar
  nach Absender/Rechnungsnummer.
- **Detailansicht**: Dateivorschau links, editierbares Formular rechts. Absender ist
  das am wenigsten zuverlässige Feld und wird entsprechend markiert. Aktionen:
  Speichern, Freigeben, Ablehnen.
- **Girocode-Prüfmaske** (nach Freigabe): Zahlungsdaten (Empfänger, IBAN, BIC, Betrag,
  Verwendungszweck) werden aus dem Belegtext vorbefüllt (IBAN/BIC-Erkennung), müssen
  aber vor dem Absenden geprüft werden – die IBAN-Prüfsumme wird zusätzlich technisch
  validiert. Nach Bestätigen: Girocode (EPC-QR-Code) wird als PNG an die
  Girocode-Adresse gesendet, danach die Original-Rechnung an das gewählte Ziel
  (Steuer/Paperless/beides) weitergeleitet. Erst wenn beides erfolgreich war, wechselt
  der Status zu `forwarded`.
- **CSV-Export** (`/export/csv`, optional mit `?status=&category=&date_from=&date_to=`):
  lädt eine `;`-getrennte CSV mit deutschem Dezimalformat (Komma statt Punkt). Netto/USt/Brutto
  sind getrennte Spalten, damit sich später bei Bedarf ein DATEV-Export ergänzen lässt, ohne
  das Datenmodell zu ändern.

## Girocode / EPC-QR-Code

Der erzeugte QR-Code folgt dem [EPC-QR-Code-Standard](https://de.wikipedia.org/wiki/EPC-QR-Code)
(Version 002, UTF-8, SEPA Credit Transfer) und lässt sich mit jeder Banking-App scannen,
die Girocodes unterstützt, um die Rechnung direkt zu bezahlen. Kodiert werden Empfänger,
IBAN, optional BIC, Betrag und Verwendungszweck – also die Zahlungsdaten des
**Rechnungsstellers**, nicht deine eigenen.

## Duplikaterkennung

Jede Datei wird beim Speichern per SHA-256 gehasht. Ein erneuter Upload (oder E-Mail-Anhang)
mit identischem Inhalt wird erkannt und nicht doppelt angelegt.

## Sicherheit

Die App ist für den **lokalen** Einsatz durch eine einzelne Person gedacht. Der
Passwortschutz verhindert beiläufigen Zugriff, ersetzt aber keine Absicherung, wenn du
den Port ins Netz exponierst (z.B. per Reverse Proxy) – dann zusätzlich HTTPS und
ggf. eine Firewall-Beschränkung einrichten. Zugangsdaten (IMAP/SMTP) liegen
Klartext-äquivalent in der lokalen SQLite-Datenbank (`storage/db.sqlite3`, gitignored).

## Tests

```bash
pytest tests/
```

Deckt ab: Extraktions-Heuristiken (inkl. IBAN/BIC-Erkennung), Datei-Speicherlogik und
den EPC-Girocode-Payload-Aufbau inkl. IBAN-Prüfsummenvalidierung – ohne Abhängigkeit
von Tesseract/Poppler oder einem echten Postfach, läuft daher überall.

## Manuelle Verifikation (bereits durchgeführt)

Der komplette Ablauf wurde lokal end-to-end getestet: Ersteinrichtung/Login,
PDF-Upload → automatische Extraktion → Board-Karte in Startspalte → Freigabe →
Girocode-Prüfmaske (inkl. IBAN-Validierung) → Girocode-PNG-Versand → Weiterleitung an
zwei Ziele gleichzeitig → Status `forwarded`. Der tatsächliche Mail-Versand wurde dabei
mit einem gemockten SMTP-Client verifiziert (Nachrichteninhalt, Anhänge, Empfänger
korrekt); mit einem unerreichbaren SMTP-Host wurde zusätzlich der Fehlerpfad geprüft
(klare Fehlermeldung statt Absturz, Status bleibt unverändert). E-Mail-Sync (IMAP) ist
implementiert, aber mangels echtem Postfach in dieser Umgebung nicht live getestet –
bitte nach dem Ausfüllen der Einstellungen einmal mit einer echten Test-Mail prüfen.
