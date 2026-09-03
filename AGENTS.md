# ESFE CORE — MASTER AGENT GUIDE

> Permanent engineering and execution contract for AI coding agents working on ESFE Core.
>
> This document is authoritative for repository-level implementation behavior.
> It applies to every task unless the user explicitly overrides a rule for a specific mission.
>
> Project language: French.
> Codebase: Django 6.0 / Python 3.14.
> Product: ESFE (Mali) school management platform.

---

# 0. PRIMARY DIRECTIVE — EXECUTE, DO NOT ONLY ADVISE

When the user asks to:

- implement;
- create;
- build;
- integrate;
- fix;
- refactor;
- connect;
- migrate;
- complete;
- repair;
- improve;
- replace;
- redesign;
- make functional;
- finish;

the request is an **EXECUTION TASK**.

You are expected to work directly on the repository.

A repository audit, explanation, implementation plan, architectural proposal,
TODO list, or recommendations are NOT considered completion of an execution task.

For implementation tasks, the default workflow is:

**INSPECT → UNDERSTAND → TRACE → REUSE → IMPLEMENT → MIGRATE → INTEGRATE → TEST → VERIFY → REPORT**

Do not stop after INSPECT, UNDERSTAND, TRACE, or PLAN unless a genuine blocking decision requires user input.

If the task can be safely completed from repository evidence, continue autonomously.

The final response must describe work that was actually performed, not work that could be performed.

---

# 1. CORE EXECUTION CONTRACT

## 1.1 Inspect before editing

Before implementing a substantial feature or modifying an existing workflow:

1. inspect the relevant models;
2. inspect related services;
3. inspect forms;
4. inspect views/endpoints;
5. inspect URLs;
6. inspect templates and HTMX fragments;
7. inspect permissions/access control;
8. inspect signals;
9. inspect existing tests;
10. inspect migrations when data structure is involved;
11. inspect existing UI components;
12. inspect neighboring workflows that may already solve part of the problem.

Do not infer architecture solely from filenames.

Read the actual implementation.

---

## 1.2 Existing architecture first

ESFE Core is a mature monolithic application.

The default rule is:

> **Reuse and extend the existing architecture before creating new architecture.**

Before creating any:

- Django model;
- database table;
- service;
- helper;
- manager;
- signal;
- form;
- template;
- component;
- dashboard shell;
- permission system;
- notification engine;
- payment mechanism;
- document mechanism;
- academic structure;
- workflow state machine;

search for the equivalent concept in the repository.

If an existing implementation already represents the domain concept, reuse it.

If it is incomplete, extend it.

If it needs refactoring, refactor it carefully.

Create a new abstraction only when the existing architecture genuinely cannot represent the required responsibility.

Do NOT create parallel systems merely because doing so is easier.

---

## 1.3 No duplicate business architecture

Never introduce a second implementation of a business concept that already has an authoritative implementation.

Examples:

- Do not create another payment engine if `payments` already owns payment logic.
- Do not create another academic year model if an authoritative academic year model exists.
- Do not create another student identity model because a new workflow needs student data.
- Do not create another notification system instead of `notifier`.
- Do not create a role-specific dashboard shell when the certified shell can support the role.
- Do not create a second access-control framework instead of `accounts/access.py`.
- Do not create duplicated class/programme/branch structures for a feature-specific shortcut.

One business concept should have one authoritative source of truth whenever possible.

---

# 2. REPOSITORY TRUTH OVERRIDES ASSUMPTIONS

The repository is the primary technical source of truth.

Task descriptions express the desired business outcome.

The codebase expresses the current implementation.

Your responsibility is to reconcile the desired outcome with the existing implementation.

Never invent:

- model names;
- field names;
- relations;
- status values;
- URLs;
- service interfaces;
- permission names;
- branch relationships;
- payment rules;
- academic rules;

without checking the repository.

If documentation and code disagree, investigate the discrepancy before changing behavior.

Do not silently replace an existing convention with an assumed convention.

---

# 3. DO NOT STOP AT ANALYSIS

For execution tasks, internal analysis exists to enable implementation.

It is not the deliverable.

Bad behavior:

1. inspect repository;
2. identify files;
3. write a long explanation;
4. stop.

Correct behavior:

1. inspect repository;
2. identify files;
3. determine dependencies;
4. implement;
5. run validations;
6. fix discovered issues;
7. verify the workflow;
8. report what was actually changed.

Do not ask:

> "Would you like me to implement this?"

when implementation was already requested.

Do not ask:

> "Should I continue?"

when the requested scope is already clear and the next operation is safe.

Continue.

---

# 4. WHEN TO ASK THE USER

User clarification is justified only when repository inspection cannot resolve a decision and proceeding would create significant risk.

Examples:

- two contradictory business rules are equally plausible;
- a destructive data migration may be required;
- production data could be irreversibly changed;
- a requested behavior conflicts with another explicit business rule;
- a security-sensitive choice requires product-owner approval;
- the task would require expanding scope far beyond the original mission;
- credentials or external resources are genuinely required.

Do NOT interrupt execution for ordinary implementation choices that can be derived from existing architecture.

---

# 5. DATA SAFETY — ABSOLUTE RULES

ESFE Core contains real institutional data.

Treat data integrity as critical.

Never:

- drop production tables casually;
- flush the database;
- delete real records to simplify implementation;
- recreate the database to solve migration problems;
- reset historical data;
- replace real data with fixtures;
- modify `.env` destructively;
- expose secrets;
- log credentials;
- commit secrets;
- remove historical records because a new workflow needs a cleaner structure;
- write destructive migrations without explicit necessity and careful review.

Prefer:

- additive migrations;
- nullable transitional fields when appropriate;
- deterministic data migrations;
- backwards-compatible schema evolution;
- staged migrations for complex changes;
- explicit uniqueness constraints;
- transactional business operations.

Historical institutional data must remain recoverable and coherent.

---

# 6. DATABASE MIGRATION POLICY

When model changes are required:

1. inspect existing migrations;
2. understand current database relationships;
3. determine whether existing rows need migration;
4. create the smallest safe schema change;
5. create deterministic data migrations if necessary;
6. preserve existing primary identities;
7. preserve historical records;
8. add constraints only when existing data can satisfy them;
9. run migration validation;
10. run targeted tests afterward.

Never solve migration conflicts by deleting migrations or resetting the database unless the user explicitly authorizes a controlled development-only reset.

Do not edit historical migrations that may already have been applied unless there is an exceptional repository-specific reason.

Prefer new migrations.

---

# 7. BUSINESS LOGIC MUST LIVE IN THE CORRECT LAYER

Do not place substantial domain logic directly inside templates.

Avoid duplicating complex domain logic across views.

Prefer the architecture already established by the relevant app.

Depending on existing conventions, business behavior may belong in:

- services;
- model methods;
- managers/querysets;
- forms;
- domain helpers;
- signals where event-driven behavior is appropriate.

Do not introduce a new architectural pattern just because it is personally preferred.

Follow the local architecture.

---

# 8. UI IS NOT THE FEATURE

A page rendering successfully does NOT prove that a feature is implemented.

For every interactive business feature, trace the full path:

**UI**
→ **request / HTMX / form**
→ **view or endpoint**
→ **permission**
→ **validation**
→ **business service**
→ **model/database**
→ **result**
→ **UI feedback**
→ **tests**

A button without backend behavior is unfinished.

A modal without persistence is unfinished.

A dashboard card backed by hardcoded values is unfinished.

A filter that visually changes but does not alter the queryset is unfinished.

A form that submits but bypasses domain rules is unfinished.

A feature is complete only when the real workflow works.

---

# 9. NO FAKE IMPLEMENTATIONS

Never use fake implementation as a substitute for requested functionality.

Forbidden unless explicitly requested for prototyping:

- hardcoded KPI values;
- hardcoded students;
- hardcoded payments;
- fake database results;
- fake success responses;
- placeholder workflow logic;
- TODO-only implementations;
- buttons with no backend;
- forms that do not persist;
- mocked production behavior;
- static dashboard numbers pretending to be real metrics;
- duplicated temporary models intended to imitate existing models.

Fixtures and mocks are acceptable inside tests where appropriate.

They are not acceptable as production functionality.

---

# 10. REAL DATA BY DEFAULT

Dashboards and operational workflows must use real database-backed data.

When displaying:

- counts;
- totals;
- financial values;
- student lists;
- academic information;
- schedules;
- notifications;
- documents;
- payment status;
- staff information;
- branch statistics;

derive them from authoritative models/querysets/services.

Do not fabricate values to make an interface look complete.

---

# 11. PRESERVE EXISTING FUNCTIONALITY

Before modifying shared infrastructure, determine what else depends on it.

Be especially careful with:

- authentication;
- access control;
- branch scoping;
- student identity;
- enrollment/registration;
- academic years;
- payments;
- notifications;
- dashboard shell;
- HTMX dispatch;
- academic structure;
- signals;
- document generation.

A fix for one dashboard must not silently break another dashboard.

A new workflow must not bypass established business rules.

When modifying shared code, run relevant regression tests.

---

# 12. SCOPE DISCIPLINE

Implement the requested feature completely.

Do not opportunistically rewrite unrelated parts of the repository.

Avoid broad cleanup unless:

- necessary for the requested feature;
- required to remove a conflicting legacy implementation;
- needed to prevent a concrete regression.

When unrelated technical debt is discovered:

- leave it untouched if safe;
- mention it briefly in the final report if materially relevant.

Do not turn a focused mission into a repository-wide rewrite.

---

# 13. LEGACY CODE POLICY

Legacy code is not automatically wrong.

Before removing or replacing legacy code:

1. identify its callers;
2. identify its URLs;
3. identify template dependencies;
4. identify JavaScript dependencies;
5. identify tests;
6. determine whether it still serves a live workflow.

If a new implementation supersedes old code, remove or deprecate the obsolete path only when safe.

Avoid leaving two competing implementations active.

---

# 14. AUTHORIZATION AND ACCESS CONTROL

Access control is a backend responsibility.

Never rely exclusively on:

- hidden buttons;
- disabled controls;
- frontend conditions;
- JavaScript;
- CSS;

to enforce authorization.

Server-side authorization must remain authoritative.

Existing access system:

`accounts/access.py`

Primary functions include:

- `can_access()`
- `get_user_scope()`

Full mapping:

`accounts/ACCESS_MAPPING.md`

Reuse this system.

Do not create a parallel permission framework without a compelling architectural requirement.

---

# 15. CRITICAL RULE — BRANCH / ANNEXE SCOPING

**All scoped operational data MUST respect the user's branch (`annexe`).**

This applies to reads AND writes.

No accidental cross-branch visibility.

No accidental cross-branch mutation.

No client-supplied branch ID should be trusted without validating that the current user is allowed to operate on that branch.

This is one of the most critical security and business rules in ESFE Core.

For every new operational workflow, verify:

- list querysets;
- detail access;
- create operations;
- update operations;
- delete/archive operations;
- exports;
- reports;
- HTMX endpoints;
- AJAX endpoints;
- dashboard KPIs;
- autocomplete/search endpoints.

All must enforce appropriate scope.

Higher-level roles with legitimate multi-branch visibility must use the established scope/permission system, not bypass filtering ad hoc.

---

# 16. TRANSACTIONAL INTEGRITY

Use database transactions for workflows that perform multiple dependent writes when partial completion would create inconsistent state.

Examples may include:

- registration;
- re-enrollment;
- payment validation;
- account activation;
- transfers;
- publication workflows;
- document issuance;
- financial closure.

Do not leave half-created business objects after an exception when atomic execution is expected.

Use `transaction.atomic()` or the repository's established equivalent where appropriate.

---

# 17. IDEMPOTENCY AND DUPLICATE PREVENTION

Critical workflows must resist accidental repeated submissions.

Consider:

- database uniqueness constraints;
- `get_or_create()` where semantically correct;
- explicit state checks;
- transactional locking where concurrency matters;
- idempotent service behavior;
- duplicate request protection.

Do not rely solely on disabling a frontend button.

Examples requiring particular attention:

- re-enrollment;
- payment validation;
- receipt generation;
- publication;
- payroll preparation;
- honorarium preparation;
- notifications.

---

# 18. CONCURRENCY

For workflows where two users/processes may update the same critical record, evaluate concurrency risk.

Financial and enrollment workflows deserve special care.

Use established locking/transaction strategies where required.

Do not introduce unnecessary locking, but do not ignore obvious race conditions.

---

# 19. AUDITABILITY

Institutional operations should remain auditable.

When the existing system records:

- actor;
- timestamps;
- status transitions;
- payment references;
- notification deliveries;
- validation actions;
- archival events;

preserve that behavior.

New workflows should integrate with existing audit mechanisms when appropriate.

Do not remove traceability to simplify code.

---

# 20. STATUS TRANSITIONS

When domain models use statuses, inspect existing status values and transitions.

Do not invent new status strings before checking existing choices/constants.

Validate transitions server-side.

Avoid impossible transitions.

Examples:

- pending → validated;
- validated → paid;
- draft → published;
- submitted → reviewed;
- enrollment states;
- academic publication states.

If a transition has side effects, centralize them according to existing architecture.

---

# 21. NOTIFICATION SYSTEM

The repository contains:

- `notifier` — notification engine;
- `notification_center` — user-facing notification interface.

`notifier` supports:

- in-app notifications;
- email via Brevo;
- WebSocket delivery;
- delivery auditing.

When a feature requires notifications, inspect and reuse this system.

Do not create a second notification table/engine merely for one dashboard.

Notification side effects must not compromise the primary transaction.

---

# 22. ASYNC / REALTIME

Primary server architecture:

- ASGI via `config.asgi`;
- daphne/channels;
- WebSocket routing via `notifier.realtime.routing`.

HTTP is wrapped in `ClientDisconnectSafeASGIApp`.

WebSockets can be disabled with:

`ENABLE_WEBSOCKETS=False`

WSGI fallback:

`config.wsgi`

used with gunicorn + whitenoise for HTTP.

Channels layer:

- Redis when `REDIS_URL` and `channels_redis` are available;
- otherwise InMemory.

Do not assume Redis is always available during local isolated tests.

---

# 23. PROJECT ARCHITECTURE

ESFE Core is a Django monolith with approximately 20 apps.

Important groups:

### Core / UI

- `core`
- `ui`

Responsibilities include:

- public pages;
- SEO;
- sitemap;
- component registration.

Django components are explicitly registered from:

`core/apps.py:CoreConfig.ready()`

Components live under:

`ui/components/`

Typical import:

```python
import ui.components.<category>.<name>.<name>
```

### Accounts / dashboards

- `accounts`
- `portal`
- `secretary`
- `students`

### School workflows

- `admissions`
- `inscriptions`
- `payments`
- `academic_cycle`
- `academics`

### Other applications

- `shop`
- `blog`
- `news`
- `community`
- `formations`
- `branches`
- `superadmin`
- `marketing`

### Notifications

- `notifier`
- `notification_center`

Do not create a new app simply because a feature is substantial.

First determine which existing domain app owns the responsibility.

---

# 24. CERTIFIED MANAGEMENT DASHBOARD SHELL

Canonical management dashboard template:

`templates/portal/staff/director_dashboard.html`

This is the certified shell for ESFE management dashboards.

New management roles MUST use:

`portal.services.certified_dashboard_shell.build_certified_dashboard_shell()`

and render the certified template.

Do not create another role-specific management shell.

Role-specific:

- services;
- workspace fragments;
- adapters;
- JavaScript behavior;

are allowed.

But:

- navigation;
- title;
- workspace;
- overlays;
- capabilities;

must be supplied through `dashboard_shell`.

Scoped roles must preserve server-side branch filtering on reads and writes.

The following already inherit this contract:

- Director of Studies;
- Academic Supervisor;
- annex manager;
- finance;
- admissions;
- secretary;
- executive;
- IT;
- marketing;
- superadmin landing dashboards.

Preserve this inheritance.

---

# 25. UI / DESIGN SYSTEM POLICY

Before creating custom markup for a reusable interface element:

1. inspect `ui/components/`;
2. inspect existing dashboard components;
3. inspect similar screens;
4. reuse certified patterns.

Do not create visual inconsistency by implementing a feature-specific design system.

Preserve existing:

- spacing;
- typography;
- cards;
- buttons;
- modals;
- drawers;
- tables;
- badges;
- empty states;
- filters;
- forms;
- feedback patterns.

Extend shared components when appropriate instead of copying them into feature templates.

---

# 26. HTMX POLICY

The project uses HTMX heavily for dashboards.

When working in an HTMX workflow:

- preserve partial rendering conventions;
- return the correct fragment;
- preserve server-side authorization;
- preserve branch scoping;
- return meaningful error states;
- avoid full-page reloads unless intentional;
- ensure direct endpoint access remains protected.

Do not make correctness depend on HTMX headers alone.

Backend endpoints must remain secure independently of the frontend.

---

# 27. TEMPLATE FILTER GOTCHAS

`{% load humanize %}` is required in **every template** using `intcomma`.

This includes HTMX partials.

Django does not propagate `{% load %}` from parent templates.

`django.contrib.humanize` is already in `INSTALLED_APPS`.

If `intcomma` fails, check the partial.

Custom tag libraries:

- `accounts/templatetags/custom_filters.py`
- `core/templatetags/extra_filters.py`

Accounts dashboard partials:

`accounts/templates/accounts/dashboard/partials/`

Each partial must independently load the libraries it uses.

---

# 28. MANAGER DASHBOARD

Entrypoints:

`accounts/dashboards/manager_dashboard.py`

Main dashboard views.

`accounts/dashboards/htmx_manager.py`

Central HTMX dispatch for:

- candidatures;
- inscriptions;
- payments;
- cash sessions;
- salaries;
- honoraria;
- expenses;
- donations;
- closures;
- reports.

Domain-specific HTMX modules:

- `htmx_caisse.py`
- `htmx_candidatures.py`
- `htmx_depenses.py`
- `htmx_honoraires.py`
- `htmx_inscriptions.py`
- `htmx_paiements.py`
- `htmx_salaires.py`

Shared helpers:

- `htmx_global.py`
- `htmx_utils.py`
- `htmx_widgets.py`

Exports/query helpers:

- `exports.py`
- `querysets.py`

Permissions/helpers:

- `permissions.py`
- `helpers.py`

Important functions include:

- `is_manager()`
- `get_user_branch()`

---

# 29. PARALLEL MANAGEMENT DASHBOARDS

These are separate dashboards:

- `executive_dashboard.py`
- `finance_dashboard.py`
- `admissions_dashboard.py`

with their respective HTMX views such as:

- `htmx_admissions.py`
- `htmx_finance.py`

They are NOT part of the gestionnaire dashboard.

Do not incorrectly route their logic through:

- `manager_dashboard.html`;
- gestionnaire-specific `htmx_*` modules;

unless the architecture explicitly requires shared behavior.

Shared services may be extracted where appropriate.

---

# 30. FINANCIAL DOMAIN — PRESERVE AUTHORITATIVE WORKFLOWS

Financial logic is high-risk.

Before modifying financial behavior inspect:

- `payments`;
- manager finance workflows;
- cash sessions;
- receipts;
- salary/honorarium generation;
- reports;
- closures;
- donations;
- shop integration where applicable.

Do not implement financial calculations independently in templates or dashboards.

Use authoritative backend calculations.

Money must not be represented with floating-point arithmetic when existing code uses decimal-safe types.

Preserve transaction traceability.

---

# 31. STAFF SALARIES

Staff salaries are auto-generated by:

`accounts/signals.py:auto_prepare_payroll_on_salary_change`

when a staff Profile has:

`salary_base > 0`

Staff roles include:

- informaticien;
- surveillant;
- directeur_etudes;
- secretaire;
- secretaire_adjointe;
- gestionnaire;
- gardien.

Do not ask the gestionnaire to manually create salary records when the automatic workflow owns this responsibility.

Expected workflow:

**verify → correct → validate → pay**

Preserve this behavior.

---

# 32. TEACHER HONORARIA

Teacher honoraria must NEVER be mixed with staff salaries.

Auto-generation:

`accounts/signals.py:auto_prepare_honorarium_on_rate_change`

when:

`teacher_hourly_rate > 0`

Expected model:

validated teaching hours × hourly rate
→ automatically prepared payment sheet.

Do not collapse salary and honorarium workflows into a single generic payment concept if that destroys their business distinction.

---

# 33. REPORTS

Reports may be:

- daily;
- weekly;
- monthly;
- custom.

Excel implementation:

`accounts/services/excel_reports.py`

Reports include:

- admissions;
- inscriptions;
- payments;
- donations;
- shop sales;
- expenses;
- salaries;
- honoraria;
- net result.

When extending reporting, reuse authoritative calculations.

Do not recalculate the same metric differently in multiple dashboards.

---

# 34. MONTHLY CLOSURE

Monthly closure must NEVER delete historical data.

Closure creates consultable archives.

Indicators may reset for the new period.

History remains preserved.

Do not implement "reset" by deleting transactional records.

---

# 35. BANK DEPOSITS

Bank deposits include:

- banque;
- référence;
- date;
- montant;
- justificatif;
- commentaire.

The DG must be able to see deposits by branch according to permissions.

Preserve branch ownership and auditability.

---

# 36. ACADEMIC DATA PRINCIPLE

Academic data is historical by nature.

Do not model current state in a way that destroys previous academic state.

When modifying:

- academic years;
- classes;
- enrollment;
- evaluations;
- grades;
- schedules;
- bulletins;
- progression;
- re-enrollment;

explicitly consider historical context.

An operation for a new academic year must not silently overwrite the previous year's academic record unless the domain model explicitly represents mutable shared identity rather than yearly state.

---

# 37. STUDENT IDENTITY VS YEARLY STATE

When implementing student lifecycle features, distinguish:

**permanent student identity**

from

**year-specific academic state**.

Do not duplicate the student's permanent identity simply because a new academic year begins.

Year-specific information should be associated with the appropriate enrollment/academic context according to the existing model architecture.

Before changing this architecture, inspect:

- `students`;
- `inscriptions`;
- `admissions`;
- `academic_cycle`;
- `academics`;
- `payments`.

This distinction is especially critical for re-enrollment.

---

# 38. RE-ENROLLMENT GENERAL PRINCIPLE

Re-enrollment must integrate with existing student, enrollment, academic, branch, and financial architecture.

Do NOT build re-enrollment as an isolated mini-application.

Before implementing re-enrollment, inspect:

- student identity model;
- existing enrollment model(s);
- academic year model;
- class/group model;
- programme/formation;
- branch;
- progression rules;
- payment linkage;
- account activation;
- dashboards;
- historical academic records;
- relevant tests.

Re-enrollment should preserve historical years.

Duplicate re-enrollment for the same student and target academic context must be prevented.

The exact implementation must follow repository evidence and the mission requirements.

---

# 39. YEAR CONTEXT

Where the product requires historical multi-year consultation, avoid globally assuming that "current enrollment" represents all student data.

Queries must use the appropriate academic-year context.

Do not accidentally show:

- current class for an old year;
- current payment state for an old year;
- current schedule for an old year;
- current academic status for an old year;

when historical data is expected.

The exact source of year context must follow existing architecture.

---

# 40. ADMISSIONS / INSCRIPTIONS / PAYMENTS INTEGRATION

These domains form a connected workflow.

Before changing one, trace dependencies into the others.

Do not create an enrollment that bypasses mandatory financial or admission rules unless the business workflow explicitly allows it.

Do not create duplicate user/student identities when an existing identity should be reused.

Do not couple unrelated historical payment records to a new academic year.

---

# 41. SIGNALS — USE CAREFULLY

The project already uses Django signals for certain automatic workflows.

Before adding a signal:

1. search existing signals;
2. determine whether explicit service logic would be clearer;
3. verify idempotency;
4. verify transaction behavior;
5. ensure the signal cannot create duplicate records;
6. ensure tests cover side effects.

Do not hide critical business workflows inside new signals without strong justification.

---

# 42. FORMS AND VALIDATION

Frontend validation improves UX.

Backend validation guarantees correctness.

Always validate critical business constraints server-side.

Use:

- Django forms;
- model validation;
- service validation;
- database constraints;

according to existing architecture.

Never trust:

- hidden inputs;
- client-provided prices;
- client-provided branch IDs;
- client-provided statuses;
- client-calculated totals;

without server validation.

---

# 43. SECURITY

Maintain Django security guarantees.

Be cautious with:

- CSRF;
- authorization;
- object-level access;
- file uploads;
- redirects;
- user-controlled URLs;
- HTML rendering;
- secrets;
- personally identifiable student/staff data.

Do not use `mark_safe` on untrusted content.

Do not weaken CSRF or permission checks to make an HTMX request work.

Fix the integration properly.

---

# 44. FILE UPLOADS

`media/` is gitignored.

Uploaded files are not repository assets.

Do not assume media files are committed.

When changing upload behavior:

- preserve storage abstraction;
- validate files according to existing rules;
- avoid hardcoded local filesystem assumptions if storage is abstracted.

---

# 45. SECRETS

`.env` contains real secrets.

Never:

- commit `.env`;
- print its contents;
- paste secrets into source files;
- expose secrets in test output;
- include credentials in final reports.

If configuration is required, refer to environment variable names.

---

# 46. EMAIL

Email backend:

`core.mail_backends.StableSMTPEmailBackend`

Provider `"brevo"` uses SMTP.

Relevant environment variables include:

- `EMAIL_HOST`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`

Reuse existing email infrastructure.

Do not hardcode provider credentials.

---

# 47. PDF GENERATION

Current project usage:

- WeasyPrint for legal pages;
- ReportLab elsewhere.

Before introducing a PDF library or mechanism, inspect the relevant existing document workflow.

Reuse existing generation patterns when suitable.

---

# 48. TAILWIND

Tailwind uses standalone CLI.

Not a PostCSS runner.

Input:

`static/src/css/input.css`

Output:

`static/public/css/main.css`

Commands:

```powershell
npm run watch:css
npm run build:css
```

`staticfiles/` is gitignored.

Run the appropriate build before deployment when CSS changes require it.

Do not replace the Tailwind toolchain casually.

---

# 49. QUICK START

```powershell
pip install -r requirements.txt; if ($?) { npm install }
python manage.py migrate
npm run watch:css
python manage.py runserver
```

Do not run installation commands unnecessarily if dependencies are already installed.

---

# 50. CRITICAL COMMANDS

| Task | Command |
|---|---|
| Tests (all) | `python manage.py test` |
| Tests (single app) | `python manage.py test core` |
| Tests (no Postgres/Redis) | `python manage.py test --settings=config.settings_test_local core` |
| Django checks | `python manage.py check` |
| Tailwind watch | `npm run watch:css` |
| Tailwind build | `npm run build:css` |
| Seed data | `python manage.py seed_<tab>` — see `seed_bundle/` |

For isolated testing:

```powershell
--settings=config.settings_test_local
```

This uses:

- SQLite;
- `test_db.sqlite3`;
- MD5PasswordHasher;
- InMemoryChannelLayer;
- restricted URL conf `config.urls_test_local`.

Do not mistake isolated-test behavior for full production configuration.

---

# 51. TESTING POLICY

Testing is part of implementation.

It is not optional cleanup.

Current testing conventions:

- vanilla `unittest`;
- Django `TestCase`;
- no pytest;
- no CI configuration currently assumed.

Tests exist in app-level `tests.py`.

Important suites include:

`accounts/test_manager_workflows.py`

and:

`academic_cycle/tests/`

Use existing test style.

Do not introduce pytest for a single feature unless the project intentionally adopts it.

---

# 52. TEST WHAT YOU CHANGE

For each substantial feature:

1. run targeted tests first;
2. add/update tests for changed behavior;
3. run Django checks;
4. run broader relevant tests;
5. fix failures caused by your changes.

Tests should cover business behavior, not merely HTTP 200 responses.

For workflows, test:

- successful path;
- permission denial;
- branch scoping;
- invalid transition;
- duplicate prevention;
- historical integrity;
- important validation errors.

---

# 53. DO NOT FAKE TEST SUCCESS

Never claim:

- "tests pass";
- "migration works";
- "Django check succeeds";
- "workflow verified";

unless the corresponding command/check was actually executed.

If a command could not run, state exactly why.

Distinguish:

- PASS;
- FAIL;
- NOT RUN;
- BLOCKED.

Do not describe NOT RUN as PASS.

---

# 54. TEST FAILURES

When tests fail:

1. determine whether failure existed before your changes or was introduced by them;
2. investigate relevant failure;
3. fix regressions caused by the task;
4. rerun targeted tests.

Do not blindly modify unrelated code to make a failing assertion green.

Do not weaken valid tests simply because implementation fails them.

---

# 55. DJANGO CHECKS

At minimum, after meaningful backend changes, run:

```powershell
python manage.py check
```

When model changes occur, also verify migration state using appropriate Django migration commands.

Do not declare model work complete while obvious migration drift remains unresolved.

---

# 56. CSS / FRONTEND VALIDATION

When UI changes affect Tailwind classes or source CSS, run the relevant Tailwind build when practical.

Verify:

- template syntax;
- HTMX targets;
- IDs;
- form endpoints;
- CSRF behavior;
- component registration where applicable.

Do not treat visually plausible markup as validated integration.

---

# 57. IMPORTS AND DEAD CODE

After refactoring:

- remove imports made obsolete by your change;
- remove superseded private helpers when safe;
- do not leave duplicate implementations active;
- do not delete public/shared helpers without tracing callers.

Avoid adding dead code "for future use".

---

# 58. COMMENTS

Comments should explain non-obvious reasoning, invariants, or business constraints.

Do not narrate obvious code.

Avoid large AI-style explanatory comment blocks inside production code.

Prefer readable implementation.

---

# 59. NAMING

Follow existing repository naming conventions.

The product/domain is French-language.

Do not arbitrarily translate existing domain concepts into new English alternatives if that creates duplicated terminology.

Consistency with existing model/service vocabulary is more important than personal naming preference.

---

# 60. PERFORMANCE

Avoid obvious N+1 query regressions in dashboards and lists.

Inspect opportunities for:

- `select_related`;
- `prefetch_related`;
- aggregation;
- annotations;
- bulk operations;

where appropriate.

Do not prematurely optimize trivial paths.

But dashboards operating over thousands of students must not perform avoidable per-row queries.

---

# 61. PAGINATION

Large operational lists should not load unlimited rows into the browser.

Reuse existing pagination/table patterns.

Do not solve performance problems by arbitrarily truncating results without communicating the limit.

---

# 62. EXPORTS

Exports must obey the same:

- permissions;
- branch scoping;
- filters;
- academic-year context;

as the screen from which they originate.

An export endpoint must not expose data that the corresponding dashboard cannot access.

---

# 63. SEARCH / FILTERS

Filters must affect authoritative backend queries.

Do not implement cosmetic filters that only hide already-loaded rows when the dataset should be server-filtered.

Preserve:

- branch scope;
- role scope;
- academic year;
- relevant domain constraints.

---

# 64. EMPTY STATES AND ERRORS

Operational UI should distinguish:

- no data;
- loading;
- permission denied;
- validation failure;
- server failure.

Do not show fake zero values to hide query errors.

Do not swallow backend exceptions and present misleading success states.

---

# 65. ERROR HANDLING

Catch exceptions only when you can:

- recover;
- translate them into a domain/user-facing error;
- add meaningful context;
- preserve integrity.

Do not use broad `except Exception: pass`.

Do not suppress errors merely to keep the UI rendering.

---

# 66. LOGGING

Logs must help diagnose problems without exposing sensitive information.

Do not log:

- passwords;
- tokens;
- secret keys;
- full `.env`;
- unnecessary personal documents.

Use appropriate log levels.

---

# 67. DESTRUCTIVE OPERATIONS

Before performing a destructive operation that could affect meaningful data, obtain explicit user approval unless the operation is unquestionably confined to disposable test data.

Examples:

- deleting production-like records;
- dropping tables;
- resetting database;
- removing migrations;
- mass deletion;
- destructive data migration.

Routine source-code edits do not require repeated approval when write permission has already been granted.

---

# 68. SOURCE CONTROL DISCIPLINE

Do not revert unrelated user changes.

Do not overwrite files simply because they differ from expected style.

Assume the working tree may contain intentional ongoing work.

Before large edits, inspect relevant current state.

If unexpected concurrent changes materially conflict with the task, preserve them where possible.

---

# 69. DO NOT MASS-REWRITE WITHOUT NEED

Avoid rewriting entire large files when a focused change is sufficient.

Focused changes reduce regression risk.

Large refactors are acceptable when the current architecture genuinely requires them for correctness, but they must remain within task scope.

---

# 70. USER'S EXISTING IMPLEMENTATION IS NOT DISPOSABLE

Do not treat existing code as a prototype to be replaced wholesale.

The project contains accumulated business decisions.

Understand why code exists before replacing it.

Prefer evolutionary changes over unnecessary reconstruction.

---

# 71. FEATURE COMPLETION DEFINITION

A feature is NOT complete because:

- a model exists;
- a migration exists;
- a URL exists;
- a template exists;
- a button exists;
- a service exists;
- tests were written.

A feature is complete when the requested business outcome works end-to-end.

Completion requires appropriate evidence across:

1. persistence;
2. business rules;
3. authorization;
4. scoping;
5. backend;
6. frontend;
7. historical integrity;
8. error handling;
9. tests;
10. regression validation.

Not every feature touches all ten dimensions, but all relevant dimensions must be verified.

---

# 72. DEFINITION OF DONE — BACKEND

Backend work is done only when applicable items are satisfied:

- authoritative models identified;
- schema updated safely;
- migrations created;
- data migration handled if needed;
- domain logic implemented;
- permissions enforced;
- branch scoping enforced;
- transactions considered;
- duplicate protection considered;
- URLs connected;
- views/endpoints connected;
- tests added/updated;
- Django checks run.

---

# 73. DEFINITION OF DONE — UI

UI work is done only when:

- real backend data is used;
- actions call real endpoints;
- forms persist correctly;
- errors are surfaced;
- permissions are respected;
- branch scope is respected;
- loading/empty states are coherent;
- existing design system is respected;
- no fake data remains;
- relevant interactions are tested.

---

# 74. DEFINITION OF DONE — WORKFLOW

For a workflow:

1. identify entry condition;
2. perform real operation;
3. persist authoritative state;
4. execute required side effects;
5. return correct user feedback;
6. expose updated state;
7. preserve history;
8. prevent invalid repetition;
9. verify permissions;
10. test important paths.

---

# 75. FINAL VERIFICATION LOOP

Before reporting completion:

### Step 1 — Re-read the task

Compare the original requested outcome against the implementation.

### Step 2 — Trace the implementation

Follow the actual path from UI/API entry point to persisted result.

### Step 3 — Look for placeholders

Search changed code for:

- TODO;
- FIXME;
- placeholder;
- temporary;
- hardcoded;
- mock;
- fake;

when relevant.

### Step 4 — Run validations

Run applicable:

- Django checks;
- targeted tests;
- broader regression tests;
- migration checks;
- frontend build.

### Step 5 — Fix

Fix problems caused by the implementation.

### Step 6 — Re-run

Re-run failed validations after fixes.

### Step 7 — Report

Only then provide the final implementation report.

---

# 76. PROOF-OF-EXECUTION RULE

When the user requested implementation, the final report must provide evidence of execution.

Report:

### Modified files

List files actually modified.

### Added files

List files actually created.

### Database

State:

- whether models changed;
- migration names;
- whether data migration was required.

### Backend

Summarize real:

- services;
- views;
- forms;
- endpoints;
- permissions;
- queries;
- signals;

that changed.

### Frontend

Summarize real:

- templates;
- components;
- HTMX;
- JavaScript;
- styles;

that changed.

### Validation

State commands actually executed and their results.

### Remaining issues

Only list genuine remaining issues.

Do not include hypothetical work as if it were completed.

---

# 77. NO "PLAN AS COMPLETION"

The following response is unacceptable after an implementation request:

> "I analyzed the project and recommend the following steps..."

unless a genuine blocker prevents implementation.

If you have enough information to produce the plan, and the plan does not require user decisions, continue and implement it.

---

# 78. NO HALF-IMPLEMENTATION

Do not intentionally stop after:

- backend only when UI integration was requested;
- UI only when backend functionality was requested;
- model creation without migrations;
- endpoint creation without permissions;
- form creation without persistence;
- service creation without wiring it;
- test creation without running it.

Follow the requested workflow to its functional boundary.

---

# 79. NO FALSE COMPLETION LANGUAGE

Do not say:

- "fully implemented";
- "production ready";
- "complete";
- "everything works";

unless evidence supports that statement.

Use precise language.

If one part remains blocked, say exactly which part.

---

# 80. AUTONOMY RULE

Once a clear execution task has been given, continue through ordinary engineering steps without requesting permission after every action.

You may:

- inspect files;
- edit repository files;
- create appropriate files;
- run non-destructive development commands;
- generate migrations;
- run tests;
- run Django checks;
- run frontend builds;
- fix regressions caused by your work;

when repository permissions allow it.

Ask before materially destructive or externally consequential actions.

---

# 81. REASONING PRIORITY

When choosing between:

**fast but isolated implementation**

and

**slower but correctly integrated implementation**

choose correct integration.

When choosing between:

**new duplicate architecture**

and

**careful extension of existing architecture**

choose careful extension.

When choosing between:

**pretty UI with fake data**

and

**plain but correct real workflow**

choose the real workflow first, then complete the UI.

---

# 82. BUSINESS RULES BEAT CONVENIENCE

Do not weaken domain rules to make implementation easier.

Examples:

- branch isolation;
- academic history;
- payment traceability;
- role permissions;
- salary/honorarium separation;
- historical closure;
- student identity continuity.

Implementation must adapt to business rules.

Business rules must not be discarded to accommodate implementation shortcuts.

---

# 83. KEEP HISTORICAL CONTEXT

ESFE Core is a longitudinal institutional system.

Data from previous:

- academic years;
- classes;
- enrollments;
- payments;
- evaluations;
- publications;
- closures;

may have legal, financial, administrative, or academic value.

Design new workflows accordingly.

"Current state" must not erase "historical state."

---

# 84. CROSS-DOMAIN IMPACT CHECK

For substantial changes, ask internally:

- Does this affect admissions?
- Does this affect enrollment?
- Does this affect payments?
- Does this affect student dashboard?
- Does this affect academic year?
- Does this affect class membership?
- Does this affect reports?
- Does this affect notifications?
- Does this affect permissions?
- Does this affect branch isolation?
- Does this affect exports?
- Does this affect historical data?

Inspect only relevant dependencies, but do not ignore obvious cross-domain consequences.

---

# 85. DASHBOARD KPI RULE

Every KPI must have an authoritative definition.

Before displaying a KPI:

1. identify the source model(s);
2. define filters;
3. define branch scope;
4. define academic-year scope;
5. define status inclusion/exclusion;
6. calculate server-side.

Do not use approximate or fabricated values.

Where multiple dashboards display the same KPI, prefer shared authoritative calculation services.

---

# 86. DASHBOARD FLUIDITY

The management dashboard architecture should remain fluid and natural.

Do not introduce unnecessary full-page reloads where the existing HTMX architecture supports workspace updates.

However:

**correctness > animation**

Do not compromise data consistency or accessibility for perceived fluidity.

Avoid global spinners that unnecessarily block unrelated dashboard interactions unless the existing certified shell intentionally requires them.

---

# 87. COMPONENT REUSE

When a reusable component exists:

- use it;
- extend it if necessary;
- improve the shared component if the improvement benefits all legitimate callers.

Do not copy-paste the component into a feature-specific template and create divergence.

Check component API before modifying it to avoid regressions.

---

# 88. ROLE-SPECIFIC RESPONSIBILITY

Do not move business responsibility to a role merely because its dashboard has room for the feature.

Respect institutional responsibility encoded by existing workflows.

Examples:

- financial validation belongs to appropriate financial roles;
- academic publication belongs to authorized academic roles;
- teachers should not receive administrative capabilities unless explicitly required;
- DG visibility does not automatically imply DG performs every operational action.

Inspect existing access mappings.

---

# 89. BACKEND-FIRST FOR CRITICAL OPERATIONS

For critical workflows, establish correct backend/domain behavior before polishing UI.

Recommended order:

1. domain understanding;
2. persistence;
3. service;
4. authorization;
5. tests;
6. endpoint;
7. UI integration;
8. UX polish.

Do not spend most of the mission polishing a screen while core persistence remains incomplete.

---

# 90. EXISTING TESTS ARE SPECIFICATION EVIDENCE

Existing tests may encode important business rules.

Read relevant tests before changing critical workflows.

Do not assume a failing existing test is obsolete.

Determine what behavior it protects.

Update tests only when the desired business behavior genuinely changed.

---

# 91. MODEL CONSTRAINTS ARE BUSINESS PROTECTION

Where a business invariant can safely be guaranteed at database level, consider appropriate constraints.

Examples:

- uniqueness;
- conditional uniqueness;
- non-null relationships;
- check constraints.

Do not rely exclusively on forms for invariants that must hold across all code paths.

Before adding constraints, verify existing data compatibility.

---

# 92. QUERYSET SCOPING

Centralize repeated sensitive filters where existing architecture permits.

Avoid scattered patterns where one endpoint remembers branch filtering and another forgets it.

Use existing managers/querysets/services where available.

Do not bypass scoped query helpers without reason.

---

# 93. DELETE VS ARCHIVE

Institutional records should often be archived/deactivated rather than physically deleted.

Before implementing delete behavior, inspect existing domain policy.

For:

- students;
- enrollments;
- financial transactions;
- academic results;
- official documents;
- closures;

physical deletion may be inappropriate.

Do not add destructive delete buttons casually.

---

# 94. USER ACCOUNT CONTINUITY

When workflows concern an existing person, determine whether the existing account/profile/student identity should be reused.

Do not create duplicate accounts because a new administrative process begins.

Account identity and domain records may have different lifecycles.

Respect that distinction.

---

# 95. IMPORT / EXPORT SAFETY

When implementing Excel or bulk imports:

- validate rows;
- report errors clearly;
- preserve atomicity where appropriate;
- prevent duplicates;
- respect branch scope;
- do not partially corrupt data because one row fails.

When exporting:

- respect permissions;
- respect active filters;
- respect academic-year context.

---

# 96. SEED DATA

Seed commands follow:

```powershell
python manage.py seed_<tab>
```

See:

`seed_bundle/`

Do not run seed commands against meaningful data merely to make a feature appear populated.

Seed data is not a substitute for correct queries.

---

# 97. LOCAL TEST SETTINGS

For quick isolated tests:

```powershell
python manage.py test --settings=config.settings_test_local <app>
```

This environment intentionally differs from full Postgres/Redis runtime.

Use it for speed where appropriate.

If behavior depends on PostgreSQL-specific features, do not claim full verification solely from SQLite tests.

---

# 98. URL TEST LIMITATION

`config.urls_test_local` is a restricted URL configuration.

Some application URLs are excluded.

If a test fails because a URL is intentionally absent from the restricted config, determine whether:

- a different test setup is needed;
- the URL should legitimately be included.

Do not distort production routing merely to satisfy the isolated test configuration.

---

# 99. ENVIRONMENT-AWARE VALIDATION

Do not assume every external service is available.

Potential dependencies include:

- PostgreSQL;
- Redis;
- SMTP/Brevo;
- external storage.

Tests should isolate external dependencies where existing architecture supports it.

A temporary external-service outage should not lead to destructive code changes.

---

# 100. COMMAND SAFETY

Before running a command, understand its effect.

Safe ordinary commands include typical:

- read/search;
- Django checks;
- tests;
- migration generation;
- frontend builds.

Be cautious with commands involving:

- flush;
- database reset;
- destructive SQL;
- force deletion;
- repository cleanup;
- production deployment.

Do not run destructive commands merely because they are convenient.

---

# 101. COMPLETION CHECKLIST

Before marking a substantial implementation complete, verify:

- [ ] I inspected the existing implementation.
- [ ] I reused existing architecture where possible.
- [ ] I did not create an unnecessary parallel system.
- [ ] I preserved historical data.
- [ ] I respected branch scoping.
- [ ] I respected permissions.
- [ ] I used real database-backed data.
- [ ] I did not leave fake UI behavior.
- [ ] I connected UI to backend.
- [ ] I considered transactions.
- [ ] I considered duplicate submissions.
- [ ] I created safe migrations where necessary.
- [ ] I added or updated meaningful tests.
- [ ] I actually ran applicable tests.
- [ ] I ran Django checks.
- [ ] I fixed regressions caused by my changes.
- [ ] I did not expose secrets.
- [ ] I did not destroy unrelated user work.
- [ ] I re-read the original task.
- [ ] The requested business outcome actually works.

If a relevant item is false, the task may not be complete.

---

# 102. FINAL RESPONSE FORMAT FOR IMPLEMENTATION TASKS

Keep the final response concise and factual.

Use this structure when useful:

## Implemented

What now actually works.

## Main changes

Important files/components changed.

## Database

Migrations/schema/data migration.

## Validation

Commands actually executed and results.

## Remaining

Only genuine blockers, risks, or follow-up work.

Do not replace execution evidence with a long architectural essay.

---

# 103. FINAL PRINCIPLE

ESFE Core must evolve as **one coherent institutional platform**.

Every new feature must integrate with the system already present.

The objective is not to produce the largest amount of code.

The objective is to produce the smallest coherent change that completely satisfies the business requirement without compromising:

- existing functionality;
- data integrity;
- security;
- branch isolation;
- academic history;
- financial traceability;
- UI consistency;
- maintainability.

When asked to implement:

**do the real work.**

When existing architecture already solves part of the problem:

**reuse it.**

When data already exists:

**use it.**

When history matters:

**preserve it.**

When a workflow is visible in the UI:

**connect it to the real backend.**

When tests can verify the work:

**run them.**

When something fails because of your changes:

**fix it before declaring completion.**

And when the mission is complete:

**report what was actually done — not what could be done.**