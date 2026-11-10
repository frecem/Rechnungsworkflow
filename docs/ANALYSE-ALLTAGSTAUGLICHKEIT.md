# Analyse: Warum der Rechnungsworkflow im Alltag nicht funktioniert

Stand: 2026-11-10

## Ausgangslage

Das Projekt funktioniert technisch, wird aber im Alltag nicht genutzt:

- Zu umständlich: erst die Seite öffnen, einloggen, prüfen, freigeben, Girocode-Formular ausfüllen.
- Der Girocode war manchmal falsch.
- Einsatz: reiner Privatgebrauch (wenige Rechnungen pro Monat).

## Perspektiven

1. **Alltag:** Die App wartet darauf, dass man sie öffnet (Pull). Für wenige Rechnungen pro Monat hält keine Routine, die mehr als eine Minute dauert und nicht von selbst anstößt.
2. **Korrektheit des Girocodes:** Betrag (`amount_gross`), IBAN/BIC (`extraction.find_iban`/`find_bic`) und Empfänger (Fallback auf `sender_name`) sind OCR-Heuristiken, also geraten. Nur ein bereits aufgedruckter EPC-Code (`qr_scan.py`) ist verlässlich. Ein gelegentlich falscher Zahlungscode ist schlimmer als keiner.
3. **Technik/Aufwand:** ca. 3.100 Zeilen mit Kanban-Board, Statusmaschine, Passkeys, Statistik, Export und Backup. Hoher Pflegeaufwand für wenig Nutzen. Der Kern ist IMAP-Eingang, Dedup und Weiterleitung.
4. **Sicherheit/Betrieb:** Erreichbarer Server mit IMAP-/SMTP-Zugangsdaten ist für eine Einzelperson ein unverhältnismäßiges Risiko.

## Empfehlung

1. Push statt Pull: Beim Rechnungseingang eine Mail/Push mit Absender, Betrag, Fälligkeit und Girocode als Bild senden; Scan mit der Banking-App.
2. Girocode nur bei verlässlichen Daten (aufgedruckter EPC-Code oder abgeglichener Treffer). Sonst Warnung "bitte prüfen" ohne Code.
3. Letzte Kontrolle in der Banking-App (Empfänger/Betrag); Betrag in der Mail groß darstellen.
4. Abspecken: Kanban-Board, Statistik, Passkeys entfernen/deaktivieren; Status auf "neu → bezahlt/weitergeleitet" reduzieren.
5. Alternative: Paperless-ngx mit Mail-Eingang plus Banking-App-Scan, ganz ohne eigene App.

## Offene Fragen

- Welcher Wert war beim falschen Girocode falsch: Betrag, IBAN oder Empfänger?
- Vorsichtig nur Mail-Benachrichtigung ergänzen oder gleich deutlich abspecken?
