# ESFE Core — Agent Guide

**Django 6.0 / Python 3.14** monolith for ESFE (Mali) school management. French-language project.

## Quick start

```powershell
# activate venv first
pip install -r requirements.txt
npm install
python manage.py migrate
npm run watch:css       # tailwind dev (output: static/public/css/main.css)
python manage.py runserver
```

## Critical commands

| Task | Command |
|------|---------|
| Run tests (all) | `python manage.py test` |
| Run tests (single app) | `python manage.py test core` |
| Run tests (no Postgres/Redis) | `python manage.py test --settings=config.settings_test_local core` |
| Tailwind watch | `npm run watch:css` |
| Tailwind build | `npm run build:css` |
| Seed data | `python manage.py seed_<tab>` (see `seed_bundle/`) |

Use `--settings=config.settings_test_local` for isolated testing — swaps to SQLite, MD5PasswordHasher, InMemoryChannelLayer, restricted URL conf (`config.urls_test_local`).

## Architecture

- **ASGI primary** (`config.asgi`) — daphne/channels. HTTP wrapped in `ClientDisconnectSafeASGIApp` (swallows `CancelledError`). WebSocket via `communication.realtime.routing`
- **WSGI fallback** (`config.wsgi`) — gunicorn + whitenoise for HTTP
- **~20 Django apps** — monolithic layout:
  - `core` / `ui` — home, about, SEO, sitemap, django-components entry (registered in `core/apps.py:CoreConfig.ready()`)
  - `accounts` / `portal` / `secretary` / `students` — user dashboards
  - `admissions` / `inscriptions` / `payments` / `academic_cycle` / `academics` — core school workflows
  - `shop`, `blog`, `news`, `community`, `formations`, `branches`, `superadmin`, `marketing`
  - `communication` — email (Brevo SMTP via `.env`), realtime/WebSocket, notifications
- **Access system** in `accounts/access.py` — `can_access()`, `get_user_scope()`. Full mapping at `accounts/ACCESS_MAPPING.md`
- **Settings** (`config.settings`) loads `.env` at project root. Postgres in dev/prod, SQLite in `settings_test_local`
- **Channels layers**: Redis if `REDIS_URL` + `channels_redis` available, else InMemory
- **Tailwind** via PostCSS — `static/src/css/input.css` → `static/public/css/main.css`
- **Email**: custom `StableSMTPEmailBackend` in `core.mail_backends`; provider "brevo" via SMTP
- **PDF**: weasyprint (legal pages), reportlab (elsewhere)
- **Rich text**: django-ckeditor-5. **HTMX**: `django_htmx.middleware.HtmxMiddleware`. **Admin theme**: django-jazzmin

## URL layout

```
/                           core:home
/admin/                     Django admin
/accounts/                  auth + accounts
/portal/                    accounts_portal namespace
/portal/student-dashboard/  student portal
/secretary/                 secretary dashboard
/admissions/, /inscriptions/, /payments/, /academic-cycle/
/formations/, /students/, /academics/
/blog/, /actualites/        news namespace
/shop/                      shop namespace
/community/, /communication/ communication namespace
/marketing/                 marketing namespace
/superadmin/, /surveillance/general/
```

Full URL config: `config/urls.py` (includes `fallback_404` catch-all). Test URL conf: `config/urls_test_local.py` (subset, some app URLs excluded).

## Django components

Registered in `core/apps.py:CoreConfig.ready()` via explicit imports. All components under `ui/components/`:

```python
import ui.components.<category>.<name>.<name>
```

## Template filter gotchas

- `{% load humanize %}` required in **every** template using `intcomma` (including HTMX partials) — Django does not propagate `{% load %}` from parents.
- `django.contrib.humanize` **is** in `INSTALLED_APPS` — if `intcomma` fails, the partial template lacks the load.
- Custom tag libraries: `accounts/templatetags/custom_filters.py`, `core/templatetags/extra_filters.py`.
- `accounts` dashboard partials under `accounts/templates/accounts/dashboard/partials/` are rendered via HTMX — each must independently load its required libraries.

## Manager (gestionnaire) dashboard

Entrypoints in `accounts/dashboards/`:
- `manager_dashboard.py` — main dashboard views
- `htmx_manager.py` — HTMX actions (candidatures, inscriptions, payments, cash sessions, salaries, honoraria, expenses, donations, closures, reports)
- `htmx_caisse.py`, `htmx_candidatures.py`, `htmx_depenses.py`, `htmx_honoraires.py`, `htmx_inscriptions.py`, `htmx_paiements.py`, `htmx_salaires.py` — per-domain HTMX
- `htmx_admissions.py` / `htmx_finance.py` — legacy HTMX views
- `permissions.py` / `helpers.py` — `is_manager()`, `get_user_branch()`

### Critical business rules

**Filtrage obligatoire par annexe** — All data MUST be filtered by the user's branch (`annexe`). No cross-branch visibility. This is the single most critical rule.

**Salaires staff** — Auto-generate payslips when STAFF user is created (informaticien, surveillant, directeur_etudes, secretaire, secretaire_adjointe, gestionnaire, gardien). Staff model must have `salaire`. Never ask the gestionnaire to create them manually. Workflow: verify → correct → validate → pay.

**Honoraires enseignants** — Never mix with staff salaries. Teacher model must have `tarif_horaire`. System: fetch validated hours × tarif → auto-generate payment sheet.

**Rapports** — Daily, weekly, monthly, custom. Excel format (`accounts/services/excel_reports.py`). Include: admissions, inscriptions, payments, donations, shop sales, expenses, salaries, honoraria, net result.

**Clôture mensuelle** — Never delete data. Create consultable archives. Indicators reset to zero for new period; history preserved.

**Versements bancaires** — Fields: banque, référence, date, montant, justificatif, commentaire. DG must see deposits by branch.

## Testing

- Vanilla `unittest`/`TestCase` — no pytest, no CI config
- `settings_test_local` bypasses Postgres/Redis — use for quick smoke tests
- Test URL conf (`urls_test_local.py`) is a subset — some app URLs not included
- `tests.py` files live inside each app directory. Additional test files exist in `accounts/` and `academic_cycle/tests/`

## Constraints

- **`.env` contains real secrets** — do not commit, do not expose in logs
- `media/` is gitignored — uploaded files not in repo
- `staticfiles/` is gitignored — run `build:css` before deploy
- No pre-commit hooks, no lint/typecheck config — rely on Django's own checks
