# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> This repo also maintains `AGENTS.md` — a detailed agent guide covering the manager (gestionnaire) dashboard business rules in depth. Read it for anything related to `accounts/dashboards/`, salaries/honoraria, caisse, or monthly closures. The summary below covers commands and overall architecture.

## Project

**Django 6.0 / Python 3.14** monolith for ESFE (Mali), a school management system. French-language project (UI, templates, model field names, business terms).

## Commands

```powershell
# activate venv first
pip install -r requirements.txt
npm install
python manage.py migrate
npm run watch:css       # tailwind dev (output: static/public/css/main.css)
python manage.py runserver
```

| Task | Command |
|------|---------|
| Run tests (all) | `python manage.py test` |
| Run tests (single app) | `python manage.py test core` |
| Run tests (no Postgres/Redis) | `python manage.py test --settings=config.settings_test_local core` |
| Tailwind watch | `npm run watch:css` |
| Tailwind build | `npm run build:css` |
| Seed data | `python manage.py seed_<tab>` (see `seed_bundle/`) |

`--settings=config.settings_test_local` swaps to SQLite, MD5PasswordHasher, InMemoryChannelLayer, and a restricted URL conf (`config.urls_test_local`) — use it for fast local test runs without Postgres/Redis.

No pre-commit hooks, no lint/typecheck config, no pytest/CI — rely on Django's own checks (`python manage.py check`) and `manage.py test`.

## Architecture

- **ASGI primary** (`config.asgi`) — daphne/channels. HTTP wrapped in `ClientDisconnectSafeASGIApp` (swallows `CancelledError`). WebSocket via `communication.realtime.routing`.
- **WSGI fallback** (`config.wsgi`) — gunicorn + whitenoise for HTTP.
- **~20 Django apps**, monolithic layout:
  - `core` / `ui` — home, about, SEO, sitemap, django-components entry point (registered in `core/apps.py:CoreConfig.ready()`)
  - `accounts` / `portal` / `secretary` / `students` — user dashboards
  - `admissions` / `inscriptions` / `payments` / `academic_cycle` / `academics` — core school workflows
  - `shop`, `blog`, `news`, `community`, `formations`, `branches`, `superadmin`, `marketing`
  - `communication` — email (Brevo SMTP via `.env`), realtime/WebSocket, notifications
- **Access control**: `accounts/access.py` — `can_access()`, `get_user_scope()`. Full role/permission mapping in `accounts/ACCESS_MAPPING.md`.
- **Settings** (`config.settings`) loads `.env` from project root. Postgres + Redis in dev/prod, SQLite/InMemory in `settings_test_local`.
- **Channels layers**: Redis if `REDIS_URL` and `channels_redis` are available, else `InMemoryChannelLayer`.
- **Tailwind** via PostCSS — `static/src/css/input.css` → `static/public/css/main.css`.
- **Email**: custom `StableSMTPEmailBackend` in `core.mail_backends`; provider "brevo" via SMTP.
- **PDF**: weasyprint (legal pages), reportlab (elsewhere).
- **Rich text**: django-ckeditor-5. **HTMX**: `django_htmx.middleware.HtmxMiddleware`. **Admin theme**: django-jazzmin.

### URL layout

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

Full URL config: `config/urls.py` (includes `fallback_404` catch-all). Test URL conf: `config/urls_test_local.py` is a subset — some app URLs are excluded.

### Django components

Registered in `core/apps.py:CoreConfig.ready()` via explicit imports. All components live under `ui/components/`:

```python
import ui.components.<category>.<name>.<name>
```

### Template filter gotchas

- `{% load humanize %}` required in **every** template using `intcomma` (including HTMX partials) — Django does not propagate `{% load %}` from parent templates.
- `django.contrib.humanize` **is** in `INSTALLED_APPS` — if `intcomma` fails, the partial template is missing the load tag.
- Custom tag libraries: `accounts/templatetags/custom_filters.py`, `core/templatetags/extra_filters.py`.
- `accounts` dashboard partials under `accounts/templates/accounts/dashboard/partials/` are rendered via HTMX — each must independently load its required template tag libraries.

### Manager (gestionnaire) dashboard

Entrypoints in `accounts/dashboards/`:
- `manager_dashboard.py` — main dashboard views
- `htmx_manager.py` — HTMX actions (candidatures, inscriptions, payments, cash sessions, salaries, honoraria, expenses, donations, closures, reports)
- `htmx_caisse.py`, `htmx_candidatures.py`, `htmx_depenses.py`, `htmx_honoraires.py`, `htmx_inscriptions.py`, `htmx_paiements.py`, `htmx_salaires.py` — per-domain HTMX
- `htmx_admissions.py` / `htmx_finance.py` — legacy HTMX views
- `permissions.py` / `helpers.py` — `is_manager()`, `get_user_branch()`

**The single most critical rule: filtrage obligatoire par annexe.** All data must be filtered by the user's branch (`annexe`). No cross-branch visibility. See `AGENTS.md` for the full set of business rules (salaries, honoraria, reports, monthly closures, bank deposits).

## Testing

- Vanilla `unittest`/`django.test.TestCase` — no pytest.
- `tests.py` files live inside each app directory; additional test files exist in `accounts/` and `academic_cycle/tests/`.

## Constraints

- `.env` contains real secrets — never commit it or expose its contents.
- `media/` is gitignored — uploaded files are not in the repo.
- `staticfiles/` is gitignored — run `npm run build:css` before deploy.
