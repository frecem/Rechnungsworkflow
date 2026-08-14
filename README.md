# Rechnungsworkflow

Kleine lokale Web-App zum **Verarbeiten eingehender Rechnungen** (privat/persönlich):
Belege kommen per E-Mail (IMAP) oder als manueller Foto-/Scan-Upload rein, werden per
OCR ausgelesen, auf einem Kanban-Board organisiert, im Browser geprüft/korrigiert und
freigegeben. Nach der Freigabe lassen sich unabhängig voneinander ein Girocode
(EPC-QR-Code) zum Bezahlen versenden und die Rechnung an eine Steuer-App und/oder
Paperless-ngx weiterleiten.

Einzelnutzer-Tool mit einfachem Passwortschutz, läuft komplett lokal, keine
Cloud-Abhängigkeit.

## Status-Workflow

```
new → extracted → reviewed → approved → forwarded
                       ↳ rejected ↵ (zurück zu reviewed möglich)
```

Freigabe (`approved`) schaltet zwei unabhängige Aktionen frei: Girocode versenden
(ändert den Status nicht) und Weiterleiten an Steuer-App/Paperless-ngx (wechselt den
Status erst dabei zu `forwarded`) – beide können in beliebiger Reihenfolge oder auch
nur einzeln ausgeführt werden.

Unabhängig davon lässt sich jede Rechnung auf dem **Kanban-Board** frei zwischen
selbst angelegten Spalten verschieben (z.B. "Bezahlen bis diese Woche", "Später",
"Bezahlt") – das Board dient der eigenen Organisation und ist von den Status oben
unabhängig.

## Setup

### 1. Systempakete (für OCR + Girocode-Erkennung)

```bash
# Debian/Ubuntu
sudo apt install tesseract-ocr tesseract-ocr-deu poppler-utils libzbar0

# macOS (Homebrew)
brew install tesseract tesseract-lang poppler zbar
```

Ohne `tesseract-ocr`/`poppler-utils` funktioniert der Upload trotzdem – nur die
OCR-Fallback-Extraktion für gescannte/fotografierte Belege liefert dann keinen Text
(PDFs mit echtem Textlayer werden unabhängig davon korrekt gelesen). Ohne `libzbar0`
wird ein bereits auf dem Beleg aufgedruckter Girocode nicht automatisch erkannt (siehe
"Girocode / EPC-QR-Code" unten). Alle Felder sind ohnehin immer manuell nachbearbeitbar.

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

Bleibt `SESSION_SECRET_KEY` auf dem Platzhalter-Wert aus `.env.example` stehen, warnt
die App das beim Start deutlich im Log (leicht kompromittierbare Login-Session).

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
  normale Passwörter oft nicht per IMAP funktionieren) – Button "IMAP-Verbindung
  testen" prüft Login und Postfachzugriff sofort, auch mit gerade eingetippten, noch
  nicht gespeicherten Werten, ohne etwas zu importieren
- SMTP-Zugangsdaten (für Girocode-Versand und Weiterleitung) – mit "SMTP-Verbindung
  testen" sofort prüfbar, ohne eine echte Mail zu verschicken (nur Verbindung+Login).
  Für eine echte Zustellprüfung zusätzlich eine Adresse bei "Testmail an" eintragen
  und "Testmail senden" klicken – verschickt eine tatsächliche Testmail dorthin.
- **Steuer-App-Adresse**: Scan-E-Mail-Eingang deiner Steuer-Software (z.B. die
  [Buhl Steuer-Scan-App](https://www.buhl.de/steuer/steuer-scan-app/)). Die Mail
  dorthin ist bewusst textleer (nur der Anhang) – solche Apps werten die PDF selbst
  per OCR aus, zusätzlicher Text stört eher.
- **Paperless-ngx-Adresse**: [E-Mail-Eingang](https://docs.paperless-ngx.com/usage/#usage-email)
  deiner paperless-ngx-Instanz. Der Betreff enthält Absender + einen
  "aus dem Rechnungsworkflow"-Hinweis (z.B. `Musterfirma GmbH – Rechnung aus dem
  Rechnungsworkflow`), damit das Dokument in Paperless-ngx auch ohne geöffneten
  Anhang klar zuzuordnen ist.
- **Girocode-Empfänger-Adresse**: wohin der erzeugte Zahlungs-QR-Code (PNG) gesendet wird
- Standard-Weiterleitungsziel (Steuer / Paperless / beides) – vorbelegt bei jeder
  Freigabe, pro Rechnung änderbar
- **Fälligkeits-Erinnerung**: Erinnerungs-E-Mail-Adresse und Vorlaufzeit (Tage vor
  Fälligkeit) – ohne hinterlegte Adresse ist die Funktion inaktiv. Dieselbe Adresse
  wird auch für den IMAP-Fehler-Alarm und überfällige wiederkehrende Zahlungen genutzt
  (siehe unten)
- **Kategorien**: eigene Verwaltungstabelle (anlegen/umbenennen/löschen) statt
  Freitext. Umbenennen aktualisiert automatisch alle Rechnungen, die die Kategorie
  bereits tragen; Löschen entfernt sie nur aus der Auswahlliste, bestehende
  Rechnungen behalten ihren Wert (kein stiller Datenverlust)

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
- **Girocode-Prüfmaske** (nach Freigabe, auch nach Weiterleitung noch nutzbar):
  Zahlungsdaten (Empfänger, IBAN, BIC, Betrag, Verwendungszweck) werden aus dem
  Belegtext vorbefüllt (IBAN/BIC-Erkennung), müssen aber vor dem Absenden geprüft
  werden – die IBAN-Prüfsumme wird zusätzlich technisch validiert. Versendet nur den
  Girocode (EPC-QR-Code als PNG) an die Girocode-Adresse, ändert den Status nicht.
- **Weiterleiten-Maske** (nach Freigabe, unabhängig vom Girocode-Versand): Ziel wählen
  (Steuer-App/Paperless-ngx/beides), sendet die Original-Rechnung dorthin und wechselt
  den Status danach zu `forwarded`.
- **Auswertung** (`/stats`): Jahres-Übersicht als schneller Überblick vor der
  Steuererklärung – Gesamtsummen (Brutto/Netto/USt), Aufschlüsselung nach Kategorie
  und nach Monat, Jahr per Dropdown wählbar, zusätzlich per Kategorie filterbar
  (Klick auf eine Kategorie in der Tabelle oder über das Dropdown). Zählt alle
  Rechnungen außer abgelehnten mit (gruppiert nach Rechnungsdatum, nicht
  Fälligkeitsdatum). "Drucken / als PDF speichern" blendet Navigation und
  Formularsteuerung aus für einen sauberen Ausdruck über den Browser-Druckdialog
  (kein zusätzlicher PDF-Dependency nötig). Darunter eine separate, jahresunabhängige
  Übersicht aller **wiederkehrenden Zahlungen** (siehe unten).
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

**Erkennung bereits vorhandener Girocodes**: Viele Rechnungen (v.a. von Versorgern)
drucken schon einen eigenen Girocode ab. Beim Import (Upload wie IMAP) wird jede Seite
des Belegs auf einen solchen Code durchsucht (`app/services/qr_scan.py`, `pyzbar` +
Systempaket `libzbar0`); wird einer gefunden, werden Empfänger, IBAN, BIC und
Verwendungszweck direkt daraus übernommen – zuverlässiger als das Erraten per
Texterkennung, da die Zahlungsdaten strukturiert im Code stehen. Andere QR-Codes auf dem
Beleg (z.B. Tracking- oder Portal-Links) werden ignoriert, erkennbar am fehlenden
`BCD`-Kennzeichen des EPC-Formats. Fehlt `libzbar0` oder wird kein Code gefunden, bleiben
die Felder wie gehabt leer/aus der Texterkennung befüllt – kein Absturz.

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

## Unbearbeitete-Rechnungen-Erinnerung

Getrennt von der Fälligkeits-Erinnerung: erinnert an Rechnungen, die noch eine
Board-Aktion brauchen (Status `new`/`extracted`/`reviewed`, also noch nicht
freigegeben oder abgelehnt). Läuft **werktags um 8:00 Uhr** und **am Wochenende um
9:00 Uhr** (zwei separate Zeitpläne, da eine einzelne Cron-Angabe keine
unterschiedliche Uhrzeit je nach Wochentag ausdrücken kann) und listet alle
betroffenen Rechnungen einzeln in der Mail auf. Der automatische, stündliche
IMAP-Abruf läuft davon unabhängig weiter – neue Rechnungen lassen sich also jederzeit
sofort einzeln bearbeiten, ohne auf den nächsten Digest zu warten. Es gibt bewusst
kein "schon erinnert"-Flag: solange eine Rechnung unbearbeitet bleibt, taucht sie
jeden Tag erneut auf; sobald sie freigegeben/abgelehnt wird, verschwindet sie am
nächsten Tag automatisch aus der Mail. Manueller Test-Button auf der
Einstellungen-Seite, analog zur Fälligkeits-Erinnerung.

## Wiederkehrende Zahlungen

Für Abos, Miete o.ä.: auf der Detailseite einer Rechnung "Wiederkehrend" ankreuzen und
ein Intervall in Tagen angeben (z.B. 30 = monatlich, 365 = jährlich). Die Gruppierung
erfolgt über den Absendernamen. Auf `/stats` erscheint eine eigene, jahresunabhängige
Übersicht mit Summe, Anzahl, letzter Rechnung und erwartetem nächsten Termin je
Absender. Bleibt der erwartete nächste Beleg mehr als 7 Tage über das Intervall hinaus
aus, taucht das in der täglichen Erinnerungs-Mail auf (kein separater Job) – so lange,
bis entweder eine neue Rechnung dieser Serie eintrifft oder die Serie über "Als
beendet markieren" auf der Auswertungsseite abgeschlossen wird (z.B. bei einer
Kündigung). Eine beendete Serie bleibt in der Übersicht sichtbar, wird aber nie mehr
als überfällig gemeldet; "Wieder aktivieren" macht das rückgängig.

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

Der Zeitpunkt des letzten Downloads wird gespeichert und auf der Einstellungen-Seite
angezeigt. Liegt er mehr als 30 Tage zurück (oder wurde noch nie ein Backup
heruntergeladen), erscheint dort eine Warnung, und die tägliche
Fälligkeits-Erinnerungs-Mail (siehe oben) weist zusätzlich darauf hin.

## Passwort vergessen

Über **"Passwort vergessen?"** auf der Login-Seite lässt sich ein Reset-Link an die in
den Einstellungen hinterlegte Erinnerungs-Adresse schicken (SMTP muss konfiguriert
sein). Der Link ist 30 Minuten gültig; eine erneute Anfrage während ein gültiger Link
existiert, verschickt denselben Link erneut statt einen neuen Token zu erzeugen. Ist
SMTP nicht erreichbar oder keine Erinnerungs-Adresse hinterlegt, lässt sich das
Passwort stattdessen per CLI direkt auf dem Server zurücksetzen:

```bash
python -m scripts.reset_password
```

Fragt interaktiv (ohne Echo) nach dem neuen Passwort und setzt es direkt in der
Datenbank, unabhängig von SMTP oder einem laufenden Reset-Link.

## Login: Benutzername, "Angemeldet bleiben", Passkeys

Der Login besteht aus Benutzername + Passwort (Benutzername lässt sich unter
**Einstellungen → Zugangsdaten ändern** anpassen, Standard beim Ersteinrichten ist
`admin`). Eine Checkbox **"Angemeldet bleiben auf diesem Gerät"** verlängert die
Session von 12 Stunden auf 180 Tage – praktisch für ein privates Haupt-/Zweitgerät,
ohne dass man sich bei jedem Öffnen neu anmelden muss; ohne Checkbox bleibt es beim
kürzeren Standard, was auf einem geteilten/fremden Gerät sinnvoller ist.

Zusätzlich lassen sich **Passkeys** (FIDO2/WebAuthn – Geräte-PIN, Fingerabdruck oder
Gesichtserkennung) als weiterer Anmeldeweg registrieren, unter **Einstellungen →
Passkeys**. Ein Passkey ersetzt das Passwort nicht, sondern ergänzt es – Passwort und
CLI-Reset bleiben als Fallback bestehen, falls z.B. das Gerät mit dem Passkey nicht
zur Hand ist. Beim Login erscheint automatisch ein "Mit Passkey anmelden"-Button,
sobald mindestens ein Passkey registriert ist; da es nur einen Account gibt, muss dafür
kein Benutzername eingegeben werden.

Wichtige Einschränkungen von Passkeys (WebAuthn-Standard, keine App-Entscheidung):

- **Erfordert HTTPS** (oder `localhost`) – über eine reine `http://`-Adresse mit
  IP-Adresse funktionieren Passkeys nicht (der Browser lehnt das als "invalid domain"
  ab). Siehe Reverse-Proxy-Abschnitt unten für den HTTPS-Zugriff.
- Ein Passkey ist an den **Hostnamen** gebunden, unter dem er registriert wurde – bei
  Zugriff über einen anderen Domainnamen/eine andere Subdomain muss er neu registriert
  werden.
- Passkey-Logins gelten immer als "Angemeldet bleiben" (180 Tage), da der Passkey
  selbst bereits durch die Geräte-Sperre/Biometrie geschützt ist.

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

## Docker-Betrieb (docker compose)

Für einen Traefik-Setup mit dateibasiertem Provider (`dynamic.yaml`, Backend per
IP:Port statt Docker-Labels) bringt der mitgelieferte `docker-compose.yml` **nur**
den App-Container mit – kein eigenes nginx, kein eigenes Zertifikats-Handling, das
übernimmt der vorhandene Traefik.

### 1. Verzeichnis + Konfiguration anlegen

```bash
mkdir -p /var/docker/rechnungsworkflow
cat > /var/docker/rechnungsworkflow/.env <<'EOF'
SESSION_SECRET_KEY=<mit `python3 -c "import secrets; print(secrets.token_hex(32))"` erzeugen>
EOF
```

Das ist die **App-eigene** `.env` (nur `SESSION_SECRET_KEY` nötig – alle anderen
Zugangsdaten werden nach dem Start über die Weboberfläche gepflegt).

Danach im Projektverzeichnis (neben `docker-compose.yml`, **nicht** in `${DATA_PATH}`)
die **Compose-eigene** `.env` anlegen – das ist eine andere Datei mit demselben
Namen, sie steuert nur die `${...}`-Platzhalter in `docker-compose.yml`:

```bash
cp docker-compose.env.example .env
# DATA_PATH, APP_PORT, FORWARDED_ALLOW_IPS, TZ bei Bedarf anpassen
```

**Wichtig:** Die Datei muss exakt `.env` heißen. Wird sie z.B. als
`docker-compose.env` abgelegt (naheliegend, weil die Vorlage `docker-compose.env.example`
heißt), liest `docker compose` sie **nicht** automatisch ein – alle
`${...}`-Platzhalter fallen dann auf ihre Defaults zurück bzw. bleiben leer
(`${DATA_PATH}/storage` würde z.B. zu `/storage`). Mit `docker compose config`
lässt sich vorab prüfen, welche Werte tatsächlich eingesetzt werden.

### 2. Starten

```bash
docker compose up -d --build
docker compose logs -f
```

Migrationen laufen bei jedem Start automatisch (`docker-entrypoint.sh`), auch nach
einem späteren `git pull` + `docker compose up -d --build` – kein manuelles
`docker compose exec ... alembic upgrade head` nötig.

### 3. In Traefiks `dynamic.yaml` eintragen

```yaml
http:
  routers:
    rechnungsworkflow:
      rule: "Host(`rechnungen.example.de`)"
      service: rechnungsworkflow
      tls: {}   # Zertifikat/Resolver wie bei deinen anderen Routern

  services:
    rechnungsworkflow:
      loadBalancer:
        servers:
          - url: "http://<Docker-Host-IP>:8000"
```

`<Docker-Host-IP>` ist die Adresse, unter der Traefik den Docker-Host erreicht –
bei Traefik im selben Docker-Netz z.B. die Bridge-Gateway-IP (`docker network
inspect bridge | grep Gateway`, oft `172.17.0.1`), bei Traefik mit `network_mode:
host` oder auf einem anderen Host die tatsächliche LAN-IP. Der Port muss zum
`APP_PORT` aus der Compose-`.env` passen.

### 4. `FORWARDED_ALLOW_IPS` einschränken (empfohlen)

Der Standardwert `*` in `docker-compose.env.example` vertraut `X-Forwarded-*`-Headern
von jeder Quelle – für ein Heimnetz ohne direkten Zugriff auf den App-Port von außen
vertretbar, aber enger geht sicherer: `FORWARDED_ALLOW_IPS` in der Compose-`.env`
auf genau die IP setzen, mit der Traefik den Container erreicht (dieselbe wie in
Schritt 3 als `<Docker-Host-IP>` ermittelt).

### Persistenz

Ein einziger Bind-Mount unter `${DATA_PATH}/storage` deckt sowohl die SQLite-Datenbank
als auch alle Belegdateien ab (analog zum Nextcloud-DB-Mount-Muster) – ein
`docker compose down && docker compose up -d` (ohne `-v`) verliert nichts.
Regelmäßig trotzdem über **Einstellungen → Backup** ein ZIP ziehen (siehe oben) –
das schützt zusätzlich gegen einen kaputten Host, nicht nur gegen einen
neu erstellten Container.

Live getestet: Image baut, Migrationen laufen beim ersten Start automatisch durch,
`/setup` und Login funktionieren über den veröffentlichten Port, ein
Container-Neustart (`docker restart`) behält sowohl die Datenbank (Bind-Mount) als
auch die angemeldete Session (gleicher `SESSION_SECRET_KEY` aus der gemounteten
`.env`).

## Sicherheit

Die App ist für den **lokalen** Einsatz durch eine einzelne Person gedacht. Der
Passwortschutz verhindert beiläufigen Zugriff. Zugangsdaten (IMAP/SMTP) liegen
Klartext-äquivalent in der lokalen SQLite-Datenbank (`storage/db.sqlite3`, gitignored).
Wird die App über den Reverse Proxy auch von außerhalb des eigenen Netzes erreichbar
gemacht, zusätzlich eine Firewall-/IP-Beschränkung auf dem Proxy in Betracht ziehen.

Der Login sperrt sich nach 5 falschen Passwortversuchen für 15 Minuten (global, nicht
pro IP – In-Memory, geht bei einem Neustart der App verloren; für dieses private
Einzelnutzer-Tool ein akzeptabler Kompromiss gegenüber einer dauerhaften Sperre). Die
Sperre gilt gemeinsam für Passwort- und Passkey-Login.

**Upgrade-Hinweis für bestehende Installationen:** Vor Einführung des Benutzernamens
gab es nur ein Passwort. Bestandsinstallationen ohne gesetzten Benutzernamen fallen
beim Login automatisch auf `admin` zurück – nach dem Update also `admin` +
bestehendes Passwort eingeben, danach den Benutzernamen bei Bedarf unter
Einstellungen anpassen.

### Belege: Allowlist statt Blocklist

Angenommen werden ausschließlich PDF- und Bild-Formate (siehe
`storage.ALLOWED_MIME_TYPES`), **nicht** aber Formate mit ausführbarem Inhalt wie
HTML oder SVG. Grund: Belege werden in der Detailansicht per `iframe`/`img` im
selben Origin eingebettet – ein Dokument mit eingebettetem `<script>` könnte sonst
im Kontext der eigenen Sitzung laufen und z.B. einen fremden Passkey registrieren.
Die Prüfung sitzt zentral in `ingest_document()` und gilt damit automatisch für
jeden Eingangsweg (Upload wie IMAP). Beim Ausliefern greifen zusätzlich
`X-Content-Type-Options: nosniff` und ein auf die Allowlist begrenzter
Content-Type, damit auch Altbestände nicht als aktiver Inhalt interpretiert werden.

### Content-Security-Policy

Die App liefert eine strikte CSP **ohne** `unsafe-inline` aus – möglich, weil
sämtliches JavaScript in `static/*.js` liegt und alle Styles in `style.css`; im
HTML gibt es weder `<script>`-Blöcke noch `onclick=`/`style=`-Attribute
(Interaktionen laufen über `data-`-Attribute, siehe `static/app.js`). Ein
eingeschleustes Skript würde damit gar nicht erst ausgeführt. Ergänzt um
`nosniff`, `Referrer-Policy: no-referrer`, eine restriktive `Permissions-Policy`
und `frame-ancestors 'self'` (Clickjacking-Schutz, erlaubt aber weiterhin die
eigene Beleg-Vorschau im iframe).

### CSV-Export

Felder wie der Absendername stammen aus der OCR fremder Rechnungen. Zellen, die mit
`=`, `+`, `-` oder `@` beginnen, bekommen beim Export ein führendes `'`, damit
Excel/LibreOffice sie als Text und nicht als Formel auswertet (CSV-/Formel-Injection).

### Bewusst offene Punkte

- **Kein CSRF-Token.** Schutz beruht auf `SameSite=Lax` beim Session-Cookie, das
  fremde Seiten daran hindert, Formulare mit gültigem Cookie abzuschicken. Für ein
  privates Einzelnutzer-Tool ein vertretbarer Kompromiss; bei Bedarf nachrüstbar.
- **Kein `Secure`-Flag am Cookie**, damit die App auch über reines HTTP hinter dem
  Reverse Proxy erreichbar bleibt. Wer ausschließlich HTTPS nutzt, sollte in
  `app/main.py` bei der `SessionMiddleware` `https_only=True` setzen.

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
Gruppierung/Überfälligkeitserkennung wiederkehrender Zahlungen (inkl. "beendet"-Flag),
das IMAP-Fehler-Alarm-Tracking (Zähler, einmaliger Alarm ab Schwellwert, Reset bei
Erfolg), die Kategorie-Verwaltung (Anlegen/Umbenennen mit Kaskade auf bestehende
Rechnungen/Löschen ohne Datenverlust), die IMAP-/SMTP-Verbindungstests (Erfolg,
Auth-Fehler, Verbindungsfehler, jeweils gemockt), die Backup-Überfälligkeitserkennung,
den Passwort-Reset (Token-Erzeugung/-Wiederverwendung/-Ablauf, Versandfehler,
gültiger/ungültiger/abgelaufener Token beim Abschluss), die Session-Logik für
"Angemeldet bleiben" (kurze vs. lange Gültigkeit, Ablauf-Erkennung inkl. eines
gefundenen Bugs mit `expires_at == 0`), den Passkey-Service (Registrierung inkl.
Ausschluss bereits registrierter Credentials, Login inkl. Sign-Count-Update, jeweils
mit gemockter WebAuthn-Kryptoverifikation), die Unbearbeitete-Rechnungen-Erinnerung
(korrekte Status-Filterung, Digest-Inhalt, kein Versand bei fehlender Konfiguration,
Verhalten bei SMTP-Verbindungsfehlern) sowie die zielspezifischen Weiterleitungs-Mails
(leerer Body an die Steuer-App, Betreff mit Absender + Workflow-Hinweis an
Paperless-ngx) und die SMTP-Testmail-Funktion, die Datei-Allowlist (PDF/Bilder
erlaubt, HTML/SVG/unbekannt abgelehnt, ohne dass etwas gespeichert wird), den
Ausbruchsschutz beim Pfad-Auflösen, die saubere Fehlermeldung bei fehlender
Belegdatei sowie die CSV-Formel-Entschärfung – ohne Abhängigkeit von
Tesseract/Poppler oder einem echten Postfach, läuft daher überall.

Zusätzlich sind Linting und Import-Reihenfolge über `ruff` festgelegt
(Konfiguration in `pyproject.toml`, inklusive FastAPI-gerechter Ausnahme für
`Depends()`/`Form()` in Default-Argumenten):

```bash
ruff check app/ scripts/ tests/
```

## Manuelle Verifikation (bereits durchgeführt)

Der komplette Ablauf wurde lokal end-to-end getestet: Ersteinrichtung/Login,
PDF-Upload → automatische Extraktion → Board-Karte in Startspalte → Freigabe →
Girocode-Prüfmaske (inkl. IBAN-Validierung) → Girocode-PNG-Versand (unabhängig, ändert
den Status nicht) → separate Weiterleitung an zwei Ziele gleichzeitig → Status
`forwarded`. Der tatsächliche Mail-Versand wurde dabei
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

Passwort-Reset und Backup-Erinnerung live über HTTP getestet: Reset-Anfrage ohne
konfigurierte Erinnerungs-Adresse/SMTP liefert eine klare Fehlermeldung statt eines
Absturzes; bei konfiguriertem, aber unerreichbarem SMTP-Host wird der Token trotzdem
erzeugt (CLI-Fallback bleibt nutzbar) und der Versandfehler abgefangen; ein gültiger
Reset-Link setzt das Passwort erfolgreich (altes Passwort danach abgelehnt, neues
akzeptiert), ein manipulierter Token wird als ungültig erkannt, und der Token wird nach
Gebrauch aus der Datenbank entfernt. `python -m scripts.reset_password` erfolgreich als
CLI-Fallback getestet (Passwort direkt in der DB gesetzt, per Login verifiziert).
Backup-Bereich zeigt vor dem ersten Download korrekt "noch kein Backup" plus
Überfälligkeits-Warnung, nach dem Download das aktuelle Datum ohne Warnung.

Bei diesem Test wurde außerdem ein echter Bug gefunden und behoben: der manuelle
Fälligkeits-Check stürzte mit HTTP 500 ab, wenn SMTP zwar konfiguriert, der Host aber
nicht erreichbar war (`run_reminder_check` fing bislang nur `SmtpNotConfigured` ab,
nicht aber `smtplib`-/Verbindungsfehler wie `socket.gaierror`) – jetzt wird das wie an
allen anderen Versandstellen der App abgefangen und sauber mit Rückgabewert `0`
behandelt; Regressionstest ergänzt.

"Serie als beendet markieren" live getestet: markierte Serie wird in der Auswertung
nicht mehr als überfällig angezeigt, "Wieder aktivieren" macht es rückgängig.
Kategorie-Verwaltung live getestet: Anlegen/Umbenennen/Löschen über die neue
Tabellen-UI funktioniert, Rechnungen mit gelöschter Kategorie zeigen sie weiterhin
korrekt in ihrem Formular an (mit Hinweis "gelöscht") statt sie beim nächsten
Speichern stillschweigend zu verlieren. IMAP-/SMTP-Verbindungstest live gegen einen
absichtlich nicht auflösbaren Host getestet: klare Fehlermeldung im UI, eingegebene
Werte bleiben im Formular sichtbar, es wird nichts in die Datenbank geschrieben
(direkt per SQLite-Abfrage nach dem Test verifiziert). SESSION_SECRET_KEY-Warnung
live mit Platzhalter-Wert (Warnung im Log) und mit eigenem Wert (keine Warnung)
gegengetestet.

Benutzername/"Angemeldet bleiben"/Passkeys live end-to-end getestet: Login mit
falschem Benutzernamen wird abgelehnt (auch bei korrektem Passwort), Session-Cookie
enthält nach Login ohne Häkchen eine ~12h-, mit Häkchen eine ~180-Tage-Ablaufzeit
(verifiziert durch Dekodieren des Cookie-Payloads). Passkey-Flow komplett über einen
von Chromium per CDP bereitgestellten virtuellen Authenticator getestet (kein Zugriff
auf echte Hardware nötig): Registrierung aus den Einstellungen heraus, Anzeige in der
Passkey-Liste, danach Logout und erfolgreicher Login ausschließlich per Passkey ohne
Passworteingabe, redirect zum Board.

Bei diesem Test wurden zwei echte Bugs gefunden und behoben: (1) Die
Passkey-Options-Endpunkte gaben das Ergebnis von `options_to_json()` (das bereits ein
JSON-*String* ist) nochmal in `JSONResponse()` verpackt zurück und haben es damit
doppelt kodiert – der Browser erhielt einen String statt eines Objekts und scheiterte
mit "Cannot read properties of undefined". (2) `session_is_valid()` prüfte den
Session-Ablauf mit `if expires_at and ...` statt `if expires_at is not None and ...`
– bei einem (im echten Betrieb zwar unrealistischen, aber von einem Unit-Test
aufgedeckten) Ablaufzeitpunkt von exakt `0` wertete Python das als "falsy" und
übersprang die Ablaufprüfung komplett. Beide Stellen sind gefixt, Regressionstests
ergänzt.

SMTP-Testmail, Unbearbeitete-Rechnungen-Erinnerung und zielspezifische
Weiterleitungs-Mails live über HTTP getestet: "Testmail senden" ohne Empfänger-Adresse
liefert eine klare Validierungsmeldung statt eines Absturzes, mit Adresse aber
unerreichbarem SMTP-Host einen sauberen Fehlertext (eingegebene Empfänger-Adresse
bleibt im Formular erhalten); der manuelle Unbearbeitete-Rechnungen-Check läuft ohne
500er auch bei nicht erreichbarem SMTP; der Girocode+Weiterleitungs-Flow mit
`forward_target=both` und absichtlich unerreichbarem SMTP-Host bricht sauber mit
Fehlermeldung ab statt mit unbehandelter Exception. Die unterschiedlichen
Mail-Inhalte pro Ziel (leerer Body an Steuer, Betreff mit Absender + Workflow-Hinweis
an Paperless-ngx) sind zusätzlich per Unit-Test auf den exakten Inhalt geprüft.

## Code- und Sicherheitsprüfung (durchgeführt)

Alle Routen wurden live gegen einen laufenden Server geprüft – unauthentifiziert
(jede geschützte Route leitet auf `/login` um, öffentlich sind nur Login,
Passwort-vergessen/-zurücksetzen und die beiden Passkey-Login-Endpunkte),
authentifiziert (kein einziger 500er über alle GET-Seiten, Upload-, Rechnungs-,
Board-, Einstellungs- und Export-Routen) sowie auf tote Links (jedes `href`/`action`
aus allen Templates aufgelöst – keine 404). Die Oberfläche wurde zusätzlich per
Playwright auf CSP-Verstöße und JavaScript-Fehler geprüft, inklusive der
interaktiven Elemente (Zeilen-Klick, Auto-Submit in der Auswertung,
Bestätigungsdialoge, Board-Dropdown, Beleg-Vorschau) und des kompletten
Passkey-Flows gegen einen virtuellen WebAuthn-Authenticator.

Dabei gefunden und behoben:

1. **Stored XSS über den Upload (schwerwiegend).** Der Upload nahm jeden Dateityp an
   und `/invoices/<id>/file` lieferte ihn mit dem gespeicherten Content-Type wieder
   aus. Eine hochgeladene HTML- oder SVG-Datei wurde damit als aktiver Inhalt im
   eigenen Origin ausgeführt – live reproduziert (`alert(document.domain)` lief).
   Da die Vorschau im selben Origin eingebettet ist, hätte ein solches Skript u.a.
   einen fremden Passkey registrieren und damit dauerhaften Zugang schaffen können.
   Auffällig war die Inkonsistenz: der IMAP-Weg filterte bereits per Allowlist, der
   Upload nicht. Behoben durch eine zentrale Allowlist in `ingest_document()` (gilt
   damit für alle Eingangswege) plus gehärtete Auslieferung.
2. **CSV-/Formel-Injection im Export.** Ein aus einer fremden Rechnung geOCRter
   Absendername wie `=cmd|' /C calc'!A1` landete unverändert im CSV und wäre beim
   Öffnen in Excel als Formel ausgewertet worden.
3. **HTTP 500 statt 404 bei fehlender Belegdatei.** Trat realistisch nach einem
   unvollständig wiederhergestellten Backup auf (DB zurückgespielt, `storage/`
   nicht).
4. **Fehlende Security-Header.** Es gab weder CSP noch `nosniff`, `Referrer-Policy`
   oder `Permissions-Policy`.
5. **Kein Ausbruchsschutz beim Pfad-Auflösen.** `read_file()` hängte den
   DB-Pfad ungeprüft an das Storage-Verzeichnis an – als Absicherung in der Tiefe
   jetzt auf das Storage-Verzeichnis begrenzt.
6. **Unbegrenzter Mailversand über `/forgot-password`.** Der Endpunkt ist
   notwendigerweise ohne Login erreichbar; wiederholtes Absenden verschickte
   beliebig viele Mails. Jetzt mit 5-Minuten-Cooldown.

Beim Absichern per CSP fielen zwei weitere Punkte auf, die der Browser-Test
aufdeckte: `frame-ancestors 'none'` hätte die **eigene** Beleg-Vorschau blockiert
(jetzt `'self'`), und **htmx war zwar eingebunden, wurde aber nirgends verwendet**
(kein einziges `hx-*`-Attribut) – es injizierte lediglich ein Inline-`<style>`,
das die CSP verletzte. Die 50 KB wurden ersatzlos entfernt.
