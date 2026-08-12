# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Rechnungsworkflow is a **single-user, self-hosted** web app for processing incoming invoices (private/personal use, German UI). Invoices arrive via IMAP email or manual upload, get OCR'd, reviewed/corrected on a Kanban board, approved, and forwarded to a tax app and/or Paperless-ngx. On approval it also generates an EPC-QR code (Girocode) for paying the invoice. No cloud dependency, no multi-user support, no SPA framework — server-rendered Jinja2 + vanilla JS.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set SESSION_SECRET_KEY
alembic upgrade head

# Run
uvicorn app.main:app --reload --port 8000

# Tests (in-memory SQLite fixtures, no external deps required)
pytest tests/
pytest tests/test_reminders.py                      # single file
pytest tests/test_reminders.py::test_run_reminder_check_sends_digest_and_marks_invoices  # single test

# Lint (config in pyproject.toml)
ruff check app/ scripts/ tests/
ruff check app/ scripts/ tests/ --fix

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1   # always verify a new migration is reversible before committing
```

`tesseract-ocr`, `tesseract-ocr-deu`, and `poppler-utils` are required system packages for OCR fallback on scanned/photographed invoices — without them the app still runs, but PDFs without a text layer won't extract text. All extracted fields are always manually editable regardless.

Docker: `docker-compose.yml` + `Dockerfile` + `docker-entrypoint.sh` build a single app container (no bundled nginx/TLS — designed to sit behind an existing reverse proxy, see README "Docker-Betrieb"). Migrations run automatically on container start.

## Architecture

### Config vs. settings — two different layers, don't confuse them

- `app/config.py` (`Settings`, loaded from `.env`) holds **only bootstrap infrastructure**: `DATABASE_URL`, `STORAGE_DIR`, `SESSION_SECRET_KEY`. Nothing else belongs here.
- `app/models.py` (`AppSettings`, a **singleton DB row with `id=1`**) holds **everything else**: IMAP/SMTP credentials, forwarding addresses, reminder settings, categories, the admin username/password hash, WebAuthn state, backup timestamp. Always accessed via `app.services.settings_service.get_settings(db)`, which creates the row on first access if missing. This split exists so all user-configurable data can be managed through the web UI after first boot, without editing files on the server.

### Status workflow vs. board columns — two independent axes

`Invoice.status` follows a strict state machine (`app/services/status.py`, `ALLOWED_TRANSITIONS`): `new → extracted → reviewed → approved → forwarded`, with `rejected` reachable from `extracted`/`reviewed`/`approved` and reversible back to `reviewed`. All transitions go through `change_status()`, which also writes an `InvoiceStatusHistory` row — never set `invoice.status` directly.

Separately, `Invoice.board_column_id`/`board_position` place the invoice on a **user-defined, freely renameable Kanban board** (`app/services/board_service.py`) for personal organization (e.g. "Pay this week", "Later"). The board is orthogonal to `status` — moving a card between columns never changes status, and vice versa.

`Invoice.paid_at` is a third, independent flag (not part of the state machine) that only gates the due-date reminder loop.

### Ingestion pipeline is the single choke point for file safety

`app/services/ingest.py::ingest_document()` is called by **both** the upload router and the IMAP sync service — it is the only place that should enforce file-type validation (`storage.ALLOWED_MIME_TYPES` — PDF and image formats only, deliberately **not** HTML/SVG, since invoice files are later embedded in an `<iframe>`/`<img>` in the same origin and an executable format would be a stored-XSS vector). It also does hash-based dedup (`file_hash_sha256`) before OCR runs, so re-uploading/re-fetching the same file is a no-op. Any new ingestion path (e.g. a future second email account) must go through this function, not bypass it.

### Login/session model

- Session state lives in the signed cookie (Starlette `SessionMiddleware`), not server-side. `app/services/auth.py` (`start_session`/`session_is_valid`) implements a two-tier expiry stored *inside* the session payload: 12h default, 180d if "remember me" was checked (or always for passkey logins) — this is layered on top of the cookie's own `max_age`, which is set to the longer ceiling.
- **Middleware order matters and is intentionally commented in `app/main.py`**: Starlette's `add_middleware()` inserts at the front of the stack, so the *last*-registered middleware runs *first*. `SessionMiddleware` is added after `require_login` is defined (so it executes before it), and `security_headers` is added last (so it wraps everything, including redirects `require_login` issues). Do not reorder these without re-reading that comment block.
- `app/services/login_guard.py` is a simple in-memory (not per-IP, not persisted) lockout shared between password and passkey login attempts.
- Passkeys (`app/services/webauthn_service.py`, `app/routers/webauthn.py`) are additive, not a password replacement — there's always a CLI fallback (`scripts/reset_password.py`) for when both email-based reset and passkeys are unavailable. RP ID/origin are derived dynamically from the request URL rather than configured, so a passkey is bound to whatever hostname it was registered under.

### Scheduled jobs (`app/main.py` lifespan + `app/services/reminders.py`, `app/services/imap_client.py`)

APScheduler `AsyncIOScheduler` runs in-process (no external cron):
- Hourly IMAP sync
- Daily 07:00 due-date reminder digest (approved/forwarded invoices with an upcoming/overdue `due_date`, deduplicated via `due_reminder_sent_at` so each invoice is reminded once)
- Weekday 08:00 / weekend 09:00 "unprocessed invoices" digest (status `new`/`extracted`/`reviewed`) — **two separate cron jobs** because a single cron expression can't express different times per day-of-week; deliberately has no dedup flag, so it resurfaces daily until the invoice is approved/rejected
- IMAP failure alert fires once after 3 consecutive sync failures, resets on next success (`imap_consecutive_failures`/`imap_failure_notified_at` on `AppSettings`)

All of these reuse the same reminder-email address (`AppSettings.reminder_email`) and require SMTP to be configured; they degrade to a silent no-op (not a crash) when unconfigured or when SMTP is unreachable — every send site catches both `SmtpNotConfigured` and `(smtplib.SMTPException, OSError)`.

### Forwarding has per-destination email templates

`app/services/smtp_client.py` has `send_to_steuer()` (empty body — tax-scan apps OCR the attachment themselves) and `send_to_paperless()` (subject includes sender name + "aus dem Rechnungsworkflow" marker) as distinct functions rather than one generic sender — don't collapse them back into a shared function without re-checking the README rationale.

### CSP-driven frontend constraints

The app ships a strict CSP with **no `unsafe-inline`** (`app/main.py`, `security_headers` middleware). This means: no inline `<script>` blocks, no `onclick=`/`onchange=`/`onsubmit=` attributes, no `style="..."` attributes in any template. Interactivity is wired via `data-*` attributes picked up by `static/app.js` (generic: `data-confirm`, `data-href`, `data-autosubmit`, `data-print`, `data-noop`) or `static/passkey-ui.js` (passkey-specific). Adding a new interactive element must follow this pattern, not inline handlers — it will silently fail under CSP otherwise, and Playwright-based console-error checks are the way to catch that (see README "Code- und Sicherheitsprüfung"). There is no JS framework and no build step; htmx was removed after an audit found it was bundled but completely unused (zero `hx-*` attributes) and only served to violate the CSP.

### Storage layout

Files live under `STORAGE_DIR/<year>/<sha256[:16]>_<sanitized-original-name>`, tracked by `Invoice.file_path` (relative). `app/services/storage.py::absolute_path()` re-resolves and bounds-checks every stored path against `STORAGE_ROOT` before reading — defense in depth against a corrupted/malicious DB row pointing outside the storage tree (e.g. from a manually edited backup).

### Migrations

Every migration in `alembic/versions/` follows the same shape for altering existing tables with data: `with op.batch_alter_table('table_name') as batch_op:` (required for SQLite ALTER TABLE support), and new NOT-NULL columns get a `server_default` so existing rows don't break. Match this pattern; verify new migrations with `upgrade head` → `downgrade -1` → `upgrade head` before committing.

## Testing conventions

- Service-level unit tests use in-memory SQLite (`create_engine("sqlite:///:memory:")`) fixtures — see any `tests/test_*.py` for the pattern (a `db` fixture + a `make_invoice`/`_settings` helper).
- External I/O (SMTP, IMAP, WebAuthn crypto verification) is mocked via `unittest.mock.patch` at the point of use, not abstracted behind interfaces.
- There is no HTTP test client in the suite; router-level/end-to-end behavior is verified manually by running a live `uvicorn` instance and hitting it with `curl` (form data via `--data-urlencode` — plain `-d` mangles non-ASCII characters) or Playwright (for anything requiring a real browser: CSP violations, JS console errors, the WebAuthn passkey flow via Chromium's CDP virtual authenticator). If you add router-level behavior, verify it this way rather than assuming pytest coverage.
