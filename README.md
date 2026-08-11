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

Für den Betrieb hinter einem Reverse Proxy (HTTP **und** HTTPS erreichbar, siehe
unten) läuft die App produktiv eher so:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="<Proxy-IP>"
```

- `--host 0.0.0.0`, damit der Proxy die App überhaupt erreicht (statt nur `127.0.0.1`)
- `--proxy-headers --forwarded-allow-ips=...`: die App vertraut den `X-Forwarded-*`-Headern
  **nur** von der angegebenen Proxy-IP (z.B. `127.0.0.1` bei gleichem Host, oder die
  Docker-Netzwerk-IP des Proxy-Containers) – wichtig, damit niemand von außen diese
  Header fälschen kann. Mehrere IPs kommagetrennt, `"*"` vertraut allen (nur sinnvoll,
  wenn die App ohnehin nicht direkt von außen erreichbar ist).

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
- **Fälligkeits-Erinnerung**: Erinnerungs-E-Mail-Adresse und Vorlaufzeit (Tage vor
  Fälligkeit) – ohne hinterlegte Adresse ist die Funktion inaktiv. Dieselbe Adresse
  wird auch für den IMAP-Fehler-Alarm und überfällige wiederkehrende Zahlungen genutzt
  (siehe unten)
- Kategorien-Liste

Die App startet auch ohne vollständig ausgefüllte Einstellungen; die jeweiligen
Funktionen (Sync-Button, Girocode-Formular) zeigen dann einen Hinweis statt eines
Fehlers.

## Bedienung

- **Board** (`/board`, Startseite): Kanban-Ansicht aller Rechnungen. Direkt oben eine
  Drag&Drop-Upload-Zone (PDF/Foto/Scan, auch mehrere Dateien auf einmal, per Ziehen
  oder Klick), ohne extra auf `/upload` navigieren zu müssen. Spalten frei
  anlegen/umbenennen/löschen/sortieren unter "Spalten verwalten". Karten per Drag&Drop
  zwischen Spalten verschieben – auf Touchscreens (Handy/Tablet, wo Drag&Drop nicht
  funktioniert) alternativ per Dropdown-Auswahl auf der Karte. Neue Rechnungen landen
  automatisch in der ersten Spalte. Voll bedienbar auf Handy/Tablet (responsive
  Layout, keine horizontalen Überläufe).
- **Hochladen** (`/upload`): PDF oder Foto/Scan (JPG/PNG) einer oder mehrerer
  Rechnungen gleichzeitig hochladen. Die App liest zuerst den PDF-Textlayer, falls
  vorhanden; sonst OCR über Tesseract. Bei genau einer Datei geht es direkt zur
  Detailansicht zur Prüfung; bei mehreren landen alle im Status `extracted` auf dem
  Board, mit einer Zusammenfassung (neu/bereits bekannt).
- **E-Mails synchronisieren** (Button oben rechts): holt neue Anhänge (PDF/JPG/PNG)
  aus dem konfigurierten IMAP-Postfach ab (read-only, verändert nichts im Postfach).
  Läuft zusätzlich automatisch stündlich im Hintergrund (kein manueller Klick nötig,
  sobald IMAP konfiguriert ist).
- **Übersicht** (`/invoices`): tabellarische Liste, filterbar nach Status, durchsuchbar
  nach Absender/Rechnungsnummer.
- **Detailansicht**: Dateivorschau links, editierbares Formular rechts. Absender ist
  das am wenigsten zuverlässige Feld und wird entsprechend markiert. "Wiederkehrend"
  ankreuzbar mit Intervall in Tagen (siehe unten). Aktionen: Speichern, Freigeben,
  Ablehnen. Nach Freigabe zusätzlich "Als bezahlt markieren" (stoppt künftige
  Fälligkeits-Erinnerungen für diese Rechnung). Unten ein aufklappbarer Verlauf aller
  Statuswechsel mit Zeitstempel.
- **Girocode-Prüfmaske** (nach Freigabe): Zahlungsdaten (Empfänger, IBAN, BIC, Betrag,
  Verwendungszweck) werden aus dem Belegtext vorbefüllt (IBAN/BIC-Erkennung), müssen
  aber vor dem Absenden geprüft werden – die IBAN-Prüfsumme wird zusätzlich technisch
  validiert. Nach Bestätigen: Girocode (EPC-QR-Code) wird als PNG an die
  Girocode-Adresse gesendet, danach die Original-Rechnung an das gewählte Ziel
  (Steuer/Paperless/beides) weitergeleitet. Erst wenn beides erfolgreich war, wechselt
  der Status zu `forwarded`.
- **Auswertung** (`/stats`): Jahres-Übersicht als schneller Überblick vor der
  Steuererklärung – Gesamtsummen (Brutto/Netto/USt), Aufschlüsselung nach Kategorie
  und nach Monat, Jahr per Dropdown wählbar, zusätzlich per Kategorie filterbar
  (Klick auf eine Kategorie in der Tabelle oder über das Dropdown). Zählt alle
  Rechnungen außer abgelehnten mit (gruppiert nach Rechnungsdatum, nicht
  Fälligkeitsdatum). Darunter eine separate, jahresunabhängige Übersicht aller
  **wiederkehrenden Zahlungen** (siehe unten).
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

## Fälligkeits-Erinnerung

Läuft automatisch einmal täglich um 07:00 Uhr im laufenden App-Prozess (kein externer
Cronjob nötig). Prüft alle freigegebenen/weitergeleiteten, noch nicht bezahlten
Rechnungen mit Fälligkeitsdatum und verschickt bei Bedarf **eine** Sammel-E-Mail
(Digest, keine Einzel-Mail pro Rechnung) an die in den Einstellungen hinterlegte
Erinnerungs-Adresse – sowohl für bald fällige als auch bereits überfällige Posten.
Jede Rechnung wird nur einmal erinnert; "Als bezahlt markieren" oder ein manueller
Check über den Button auf der Einstellungen-Seite (nützlich zum Testen der
Konfiguration, ohne auf 7 Uhr zu warten) sind die beiden Wege, den Kreislauf zu
beenden. Überfällige wiederkehrende Zahlungen (siehe unten) fließen in dieselbe
Sammel-Mail ein.

## Wiederkehrende Zahlungen

Für Abos, Miete o.ä.: auf der Detailseite einer Rechnung "Wiederkehrend" ankreuzen und
ein Intervall in Tagen angeben (z.B. 30 = monatlich, 365 = jährlich). Die Gruppierung
erfolgt über den Absendernamen. Auf `/stats` erscheint eine eigene, jahresunabhängige
Übersicht mit Summe, Anzahl, letzter Rechnung und erwartetem nächsten Termin je
Absender. Bleibt der erwartete nächste Beleg mehr als 7 Tage über das Intervall hinaus
aus, taucht das in der täglichen Erinnerungs-Mail auf (kein separater Job) – so lange,
bis entweder eine neue Rechnung dieser Serie eintrifft oder die Markierung entfernt
wird.

## IMAP-Fehler-Alarm

Schlägt der automatische stündliche E-Mail-Abruf 3 Mal in Folge fehl (z.B. abgelaufenes
App-Passwort, falscher Host), wird **einmalig** eine Warn-Mail an die
Erinnerungs-Adresse verschickt – keine Wiederholung bei jedem weiteren stündlichen
Versuch, solange der Fehler anhält. Nach dem nächsten erfolgreichen Abruf wird der
Zähler zurückgesetzt.

## Duplikaterkennung

Jede Datei wird beim Speichern per SHA-256 gehasht. Ein erneuter Upload (oder E-Mail-Anhang)
mit identischem Inhalt wird erkannt und nicht doppelt angelegt.

## Backup

Unter **Einstellungen → Backup** lädt sich ein ZIP mit einer konsistenten Kopie der
Datenbank (über die SQLite-Backup-API, sicher auch bei laufendem Betrieb) und allen
Belegdateien herunter. Zum Wiederherstellen: `storage/db.sqlite3` und
`storage/invoices/` durch den Inhalt des ZIPs ersetzen. Da alles ausschließlich lokal
liegt, gibt es keine automatische Cloud-Sicherung – regelmäßig manuell exportieren.

## Als App installieren (PWA)

Die App liefert ein Web-App-Manifest samt Icons mit. Auf dem Smartphone/Tablet über
"Zum Home-Bildschirm hinzufügen" (iOS Safari) bzw. "App installieren" (Android Chrome)
lässt sie sich wie eine native App vom Homescreen starten (eigenes Icon, ohne
Browser-Adressleiste). Es gibt bewusst **keinen Offline-Modus** (kein Service Worker) –
die App braucht für OCR/Versand ohnehin eine Verbindung zum Server, ein Cache wäre hier
nur zusätzliche Komplexität ohne echten Nutzen.

## Betrieb hinter einem Reverse Proxy (HTTP + HTTPS)

Die App selbst spricht nur HTTP (Uvicorn ohne eigenes Zertifikat). Für den Zugriff
über `http://` **und** `https://` läuft davor ein Reverse Proxy, der die
TLS-Terminierung übernimmt und intern per HTTP an die App weiterreicht. Die App ist
darauf ausgelegt: keine erzwungene HTTPS-Weiterleitung, keine "secure-only"-Cookies –
sie funktioniert unter beiden Schemas identisch, solange der Proxy die Header korrekt
weiterreicht.

Wichtig auf App-Seite:
- Mit `--host 0.0.0.0` starten, sonst erreicht der Proxy die App nicht (siehe oben).
- `--proxy-headers --forwarded-allow-ips="<Proxy-IP>"` setzen, damit `X-Forwarded-Proto`/
  `X-Forwarded-For` korrekt ausgewertet werden – aber **nur** von der echten Proxy-IP
  vertraut wird (sonst könnte ein Client diese Header selbst gegenüber der App fälschen,
  falls sie doch direkt erreichbar wäre).

Beispiel-Konfiguration auf Proxy-Seite (nginx, HTTP + HTTPS parallel, kein Redirect):

```nginx
server {
    listen 80;
    listen 443 ssl;
    server_name rechnungen.example.local;

    ssl_certificate     /pfad/zum/fullchain.pem;
    ssl_certificate_key /pfad/zum/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Bei Caddy übernimmt ein einfaches `rechnungen.example.local { reverse_proxy 127.0.0.1:8000 }`
automatisches HTTPS inkl. Zertifikat; für reines IP:Port ohne Domain (self-signed)
oder Traefik gilt das gleiche Prinzip – Host/X-Forwarded-*-Header weiterreichen, TLS
im Proxy terminieren.

## Sicherheit

Die App ist für den **lokalen** Einsatz durch eine einzelne Person gedacht. Der
Passwortschutz verhindert beiläufigen Zugriff. Zugangsdaten (IMAP/SMTP) liegen
Klartext-äquivalent in der lokalen SQLite-Datenbank (`storage/db.sqlite3`, gitignored).
Wird die App über den Reverse Proxy auch von außerhalb des eigenen Netzes erreichbar
gemacht, zusätzlich eine Firewall-/IP-Beschränkung auf dem Proxy in Betracht ziehen.

Der Login sperrt sich nach 5 falschen Passwortversuchen für 15 Minuten (global, nicht
pro IP – In-Memory, geht bei einem Neustart der App verloren; für dieses private
Einzelnutzer-Tool ein akzeptabler Kompromiss gegenüber einer dauerhaften Sperre).

## Tests

```bash
pytest tests/
```

Deckt ab: Extraktions-Heuristiken (inkl. IBAN/BIC-Erkennung), Datei-Speicherlogik, den
EPC-Girocode-Payload-Aufbau inkl. IBAN-Prüfsummenvalidierung, die
Fälligkeits-Erinnerungslogik (welche Rechnungen qualifizieren, Digest-Versand,
Markieren als erinnert, Verhalten bei SMTP-Verbindungsfehlern), die Login-Sperre, den
Backup-Export (gültige, konsistente SQLite-Kopie inkl. aller Tabellen, Belegdateien im
ZIP enthalten), die Jahres-/Kategorie-Auswertung (Summenbildung, Ausschluss
abgelehnter Rechnungen, Gruppierung nach Kategorie/Monat, Kategorie-Filter), die
Gruppierung/Überfälligkeitserkennung wiederkehrender Zahlungen und das
IMAP-Fehler-Alarm-Tracking (Zähler, einmaliger Alarm ab Schwellwert, Reset bei
Erfolg) – ohne Abhängigkeit von Tesseract/Poppler oder einem echten Postfach, läuft
daher überall.

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

Zusätzlich end-to-end verifiziert: manueller Fälligkeits-Check versendet korrekt
formatierten Digest (gemocktes SMTP) und markiert Rechnungen als erinnert; "Als
bezahlt markieren" stoppt einen erneuten Check zuverlässig; Status-Historie zeigt alle
Übergänge korrekt; Login sperrt sich nach 5 Fehlversuchen (HTTP 429) und lässt sich
nach Reset wieder normal nutzen; APScheduler-Jobs sind korrekt registriert (Erinnerung
täglich 07:00 Uhr, IMAP-Sync stündlich). Mobile-/Tablet-Tauglichkeit wurde per
Playwright bei 375×667 und 768×1024 Viewport-Größen geprüft (Board, Übersicht,
Detailansicht): keine horizontalen Layout-Überläufe, Topbar bricht korrekt um, und das
Verschieben von Karten zwischen Spalten funktioniert nachweislich auch ohne Drag&Drop
über das Dropdown-Menü auf jeder Karte.

Backup-Download live über HTTP getestet: Manifest, alle Icons und Favicon werden mit
korrekten Content-Types ausgeliefert, `/settings/backup` liefert ein gültiges ZIP mit
funktionsfähiger SQLite-Kopie.

Mehrfach-Upload (3 Dateien gleichzeitig) und Jahres-Auswertung live über HTTP
getestet: alle drei Rechnungen korrekt angelegt und auf dem Board sichtbar,
Zusammenfassungs-Banner zeigt korrekte Anzahl; Einzel-Upload (inkl.
Duplikaterkennung) funktioniert unverändert weiter; Auswertung berechnet Summen nach
Kategorie und Monat korrekt aus echten, unterschiedlich datierten/kategorisierten
Testrechnungen; Kategorie-Filter (inkl. Umlaute) liefert die korrekt gefilterte
Teilmenge.

Wiederkehrende Zahlungen live getestet: Markierung inkl. Intervall wird korrekt
gespeichert und in der Detailansicht vorbelegt angezeigt, Auswertungsseite zeigt die
Gruppe mit korrekter Summe und markiert sie als überfällig, sobald Intervall +
Kulanzfrist verstrichen sind.

Bei diesem Test wurde außerdem ein echter Bug gefunden und behoben: der manuelle
Fälligkeits-Check stürzte mit HTTP 500 ab, wenn SMTP zwar konfiguriert, der Host aber
nicht erreichbar war (`run_reminder_check` fing bislang nur `SmtpNotConfigured` ab,
nicht aber `smtplib`-/Verbindungsfehler wie `socket.gaierror`) – jetzt wird das wie an
allen anderen Versandstellen der App abgefangen und sauber mit Rückgabewert `0`
behandelt; Regressionstest ergänzt.
