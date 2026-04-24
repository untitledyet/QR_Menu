<div align="center">

# Tably — Universal Product Documentation

**Multi-tenant QR Menu & Reservations SaaS · Source-of-Truth Technical Reference**

| Field              | Value                                                          |
|--------------------|----------------------------------------------------------------|
| Product            | Tably (QR Menu + Reservations)                                 |
| Runtime            | Python 3.12 · Flask 3.1 · PostgreSQL · Gunicorn                |
| LLM layer          | OpenAI Responses API · Embeddings · Images                     |
| Deployment         | Railway (Nixpacks) · Cloudflare R2 storage                     |
| UI language        | Georgian (primary) / English (secondary, auto-translated)      |
| Auth               | Password + SMS/Email 2FA · Google OAuth (customers)            |
| Document purpose   | Source-of-truth ops manual — update BEFORE touching code       |

</div>

---

## 📖 Table of Contents

1. [Introduction & Product Context](#1-introduction--product-context)
2. [High-Level Architecture](#2-high-level-architecture)
3. [File Tree & Module Map](#3-file-tree--module-map)
4. [Boot & Runtime Lifecycle](#4-boot--runtime-lifecycle)
5. [Environment Variables (Configuration Contract)](#5-environment-variables-configuration-contract)
6. [Database Schema (Complete)](#6-database-schema-complete)
7. [Endpoint Catalogue (Every Route)](#7-endpoint-catalogue-every-route)
8. [AI / LLM Layer — Models, Prompts, Schemas](#8-ai--llm-layer--models-prompts-schemas)
9. [Scraper Pipeline](#9-scraper-pipeline)
10. [Translation Service (Background)](#10-translation-service-background)
11. [Cloudflare R2 Storage](#11-cloudflare-r2-storage)
12. [Authentication & Security](#12-authentication--security)
13. [Rate Limiting Matrix](#13-rate-limiting-matrix)
14. [External Integrations](#14-external-integrations)
15. [Payments (Adapter Pattern)](#15-payments-adapter-pattern)
16. [Reservations Subsystem](#16-reservations-subsystem)
17. [Notifications](#17-notifications)
18. [Observability (Sentry, Structlog, Health)](#18-observability-sentry-structlog-health)
19. [Background Jobs (RQ + Thread Fallback)](#19-background-jobs-rq--thread-fallback)
20. [Frontend Behaviour](#20-frontend-behaviour)
21. [Business Flows (Diagrammed)](#21-business-flows-diagrammed)
22. [Deployment](#22-deployment)
23. [Zero-to-Running Setup](#23-zero-to-running-setup)
24. [Known Debt & Risks](#24-known-debt--risks)
25. [Change Control Protocol](#25-change-control-protocol)
26. [Quick Reference — What Lives Where](#26-quick-reference--what-lives-where)

---

## 1. Introduction & Product Context

**Tably** is a multi-tenant SaaS that replaces paper restaurant menus with QR-code-driven digital menus, and layers table reservations on top. Each customer ("venue") signs up self-service, gets a unique slug, and their guests access the menu by scanning a per-table QR code:

```
https://<host>/<venue-slug>/table/<table-number>
```

**What it does beyond a menu:**

- **AI-driven menu import** — on registration, a background job scrapes Google Maps / Glovo and extracts the menu via OpenAI vision, so the venue admin sees a pre-filled draft instead of a blank screen.
- **Bilingual auto-translation** — menu items written in Georgian get English translations automatically; English items get Georgian. Performed asynchronously after each save.
- **Plan-gated features** — `free`/`basic`/`premium` unlock subsequent features (promotions, cart, payments, ratings, analytics, reservations).
- **Chain / group system** — owner venue shares a central menu with branch venues; branches may override prices if the owner allows it.
- **Reservations** — customer registers, picks a slot, (optionally) pays a deposit via Stripe, gets a cancellation link.
- **Super-admin panel** — platform-level control (venue management, feature overrides, global product library, scraper diagnostics).

This document is the operational **Source-of-Truth**. Any change to a prompt, provider, env var, or feature **must** be reflected here before the code change lands. See §[25. Change Control Protocol](#25-change-control-protocol).

---

## 2. High-Level Architecture

### 2.1 Tech Stack

| Layer               | Technology                                                              |
|---------------------|-------------------------------------------------------------------------|
| Web framework       | Flask 3.1 + blueprints                                                  |
| ORM                 | SQLAlchemy 3.1 (via Flask-SQLAlchemy) + Flask-Migrate                   |
| Database            | PostgreSQL (prod, Railway) · SQLite (local fallback)                    |
| Auth                | Werkzeug password hashing · custom 2FA · Authlib (Google OAuth)         |
| LLM / Vision        | OpenAI **Responses API** (`gpt-5.4`) + Embeddings (`text-embedding-3-large`) + Images (`gpt-image-1`) |
| Browser automation  | Playwright (Chromium, headless)                                         |
| Object storage      | Cloudflare R2 (S3-compatible, content-addressable keys)                 |
| SMS                 | smsoffice.ge (`http://smsoffice.ge/api/v2/send`)                        |
| Email               | Resend API (primary) · SMTP (fallback)                                  |
| Payments            | Stripe adapter · MockPaymentGateway (default)                           |
| Background jobs     | RQ + Redis (when `REDIS_URL` set) · in-process thread (fallback)        |
| Rate limiting       | Flask-Limiter (in-memory → Redis when configured)                       |
| Error monitoring    | Sentry (`sentry-sdk[flask]`) with Flask + SQLAlchemy integrations       |
| Logging             | structlog JSON (`LOG_JSON=1`) · plain text + rotating file (default)    |
| Process manager     | Gunicorn (`gthread` workers)                                            |
| Build / deploy      | Nixpacks · Railway (release phase + runtime)                            |

### 2.2 Application Layers

```
┌─────────────────────────────────────────────────────────────────┐
│  Flask app (create_app)                                         │
│                                                                 │
│  ┌─ Blueprints ─────────────────────────────────────────────┐   │
│  │ landing_bp   public: /, /login, /register, /api/...      │   │
│  │ menu_bp      customer menu: /<slug>/table/<id>           │   │
│  │ api_bp       public API:     /api/<slug>/items           │   │
│  │ bo_bp        backoffice:     /backoffice/*               │   │
│  │ res_api_bp   reservations:   /api/<slug>/reservations/*  │   │
│  │ lib_bp       global library: /backoffice/library/*       │   │
│  │ group_bp     chain/group:    /backoffice/group/*         │   │
│  │ _health      /health, /health/ready                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Services ───────────────────────────────────────────────┐   │
│  │ registration_service · reservation_service · payment_    │   │
│  │ service · notification_service · translation_service ·   │   │
│  │ r2_storage                                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Scraper pipeline ───────────────────────────────────────┐   │
│  │ job_runner → queue (RQ|thread) → google_menu / google_   │   │
│  │ photos / glovo_menu → image_preprocessor → ai_analyzer   │   │
│  │ → embeddings → merger → r2_storage                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Utils ──────────────────────────────────────────────────┐   │
│  │ logging · observability (Sentry + Limiter) · feature_    │   │
│  │ flags                                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. File Tree & Module Map

```
QR_Menu-Refactored-/
├── Procfile                         # web / worker / release entries
├── gunicorn.conf.py                 # workers, threads, timeouts, logging
├── railway.toml                     # Railway deploy config + healthcheck
├── nixpacks.toml                    # Playwright chromium install
├── runtime.txt                      # Python version pin
├── manage.py                        # Flask entrypoint + runtime migrations
├── seed.py                          # Initial super-admin + demo seed
├── migrate_to_library.py            # One-time Global Library backfill
├── translate_existing.py            # Bulk translate existing rows
├── requirements.txt                 # Python deps (see §5.4)
│
├── docs/
│   └── UNIVERSAL_PRODUCT_DOCUMENTATION.md   ← this file
│
├── app/
│   ├── __init__.py                  # create_app: blueprints, sentry, limiter, health
│   ├── config.py                    # Config class (env → Flask config)
│   ├── models.py                    # All SQLAlchemy models + constants
│   │
│   ├── routes/
│   │   ├── landing_routes.py        # Public: register/login/2FA/reset
│   │   ├── menu_routes.py           # Customer menu pages + category JSON
│   │   ├── api_routes.py            # GET /api/<slug>/items
│   │   ├── backoffice_routes.py     # Venue admin + super admin
│   │   ├── reservation_api_routes.py# Customer auth + booking + OAuth
│   │   ├── global_library_routes.py # Platform catalog CRUD
│   │   └── group_routes.py          # Chain/group management
│   │
│   ├── services/
│   │   ├── registration_service.py  # SMS · email · Places · password helpers
│   │   ├── reservation_service.py   # Availability · auto-assign · expire
│   │   ├── payment_service.py       # PaymentGateway ABC + Stripe/Mock
│   │   ├── notification_service.py  # Booking emails (ka/en templates)
│   │   ├── translation_service.py   # Async auto-translate (gpt-4o-mini)
│   │   └── r2_storage.py            # Content-addressable R2 uploads
│   │
│   ├── scraper/
│   │   ├── config.py                # Model tiers, timeouts, headless
│   │   ├── job_runner.py            # Pipeline orchestrator + PipelineLog
│   │   ├── queue.py                 # RQ dispatch + thread fallback
│   │   ├── worker.py                # `python -m app.scraper.worker`
│   │   ├── google_menu.py           # Playwright: Google Maps text menu
│   │   ├── google_photos.py         # Playwright: menu photo URLs
│   │   ├── glovo_menu.py            # Playwright: Glovo link + menu
│   │   ├── ai_analyzer.py           # All vision/parse/classify LLM calls
│   │   ├── embeddings.py            # Cosine dedup + library match
│   │   ├── image_preprocessor.py    # EXIF/autocontrast/downscale/webp
│   │   ├── merger.py                # Priority-based source merge
│   │   ├── saver.py                 # Local-disk photo/json save (legacy)
│   │   └── extract_menu.py          # Standalone CLI (not wired to Flask)
│   │
│   ├── utils/
│   │   ├── logging.py               # Plain + structlog JSON
│   │   ├── observability.py         # init_sentry · init_rate_limiter · @rate_limit
│   │   └── feature_flags.py         # Jinja context processor
│   │
│   ├── templates/                   # Jinja2 templates (ka primary)
│   ├── static/
│   │   ├── css/                     # app.css · landing.css · backoffice.css
│   │   └── js/                      # i18n.js · menu · cart · backoffice
│   └── tests/                       # unittest (legacy — see §24)
│
└── logs/                            # rotating app logs (10 MB × 10)
```

---

## 4. Boot & Runtime Lifecycle

### 4.1 `create_app(config_class=Config)` step-by-step

| Step | Action                                                  | File                              |
|------|---------------------------------------------------------|-----------------------------------|
| 1    | `app.config.from_object(Config)` — env → Flask config   | `app/config.py`                   |
| 2    | `init_sentry(app)` — if `SENTRY_DSN` is set             | `app/utils/observability.py`      |
| 3    | `db.init_app(app)` + `migrate.init_app(app, db)`        | `app/__init__.py`                 |
| 4    | `setup_logging(app)` — JSON when `LOG_JSON=1` else plain| `app/utils/logging.py`            |
| 5    | `init_rate_limiter(app)` — Redis if `REDIS_URL`, memory otherwise | `app/utils/observability.py` |
| 6    | Register 7 blueprints (landing, menu, api, bo, res_api, lib, group) | `app/__init__.py`     |
| 7    | `init_feature_flags(app)` — Jinja `feature_flags` context | `app/utils/feature_flags.py`    |
| 8    | Mount `/health` and `/health/ready` endpoints           | `app/__init__.py`                 |

### 4.2 Production Release & Runtime (Railway)

```bash
# release phase — runs once per deploy
python -c 'from manage import run_migrations; run_migrations()'   # schema + indexes
python seed.py                                                    # super-admin + demo
python migrate_to_library.py                                      # global library backfill

# runtime — always-on web service
gunicorn manage:app --config gunicorn.conf.py
```

**Optional RQ worker** (separate Railway service when `REDIS_URL` set):

```bash
python -m app.scraper.worker
```

### 4.3 Health Endpoints

| Path             | Returns                                               |
|------------------|-------------------------------------------------------|
| `GET /health`    | `{"status":"ok"}` — always 200 (for load balancer)    |
| `GET /health/ready` | DB `SELECT 1` — 200 on success, 503 on DB failure  |

Railway is wired to `/health` (see `railway.toml:healthcheckPath`).

---

## 5. Environment Variables (Configuration Contract)

### 5.1 Required in Production

| Variable                  | Purpose                                                |
|---------------------------|--------------------------------------------------------|
| `SECRET_KEY`              | Flask session signing                                  |
| `DATABASE_URL`            | PostgreSQL URL (`postgres://` auto-converted)          |
| `BASE_URL`                | Public base (used in email links)                      |
| `OPENAI_API_KEY`          | Translation, scraper, vision, embeddings, image gen    |

### 5.2 Provider Integrations

| Variable                                              | Used By                              |
|-------------------------------------------------------|--------------------------------------|
| `SMS_API_KEY`, `SMS_SENDER`                           | `registration_service.send_sms_code` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | SMTP fallback for outbound mail  |
| `RESEND_API_KEY`                                      | Primary email sender                 |
| `GOOGLE_PLACES_API_KEY`                               | Venue lookup during registration     |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`            | Google OAuth (reservation customers) |
| `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_URL` | Cloudflare R2 photo storage |
| `STRIPE_SECRET_KEY`                                   | Stripe adapter (wire manually; mock by default) |

### 5.3 LLM / Scraper Tunables

| Variable                      | Default                     | Effect                                        |
|-------------------------------|-----------------------------|-----------------------------------------------|
| `OPENAI_MODEL_VISION`         | `gpt-5.4`                   | OCR + photo extraction                        |
| `OPENAI_MODEL_REASON`         | `gpt-5.4`                   | Hierarchical parsing of raw OCR               |
| `OPENAI_MODEL_FAST`           | `gpt-5.4`                   | Classify / translate / enrich / categorize    |
| `OPENAI_MODEL_EMBED`          | `text-embedding-3-large`    | Dedup + library matching                      |
| `OPENAI_MODEL_IMAGE_GEN`      | `gpt-image-1`               | `generate_dish_photo`                         |
| `SCRAPER_HEADLESS`            | `1` (True)                  | Headless chromium                             |
| `SCRAPER_SLOW_MO`             | `0`                         | ms delay between Playwright actions           |
| `LLM_TIMEOUT_CONNECT`         | `10`                        | seconds                                       |
| `LLM_TIMEOUT_READ`            | `240`                       | seconds (vision can be slow)                  |
| `LLM_TIMEOUT_WRITE`           | `60`                        | seconds                                       |
| `LLM_TIMEOUT_POOL`            | `10`                        | seconds                                       |
| `VISION_MAX_PX`               | `2000`                      | Downscale threshold before base64 to vision   |
| `LLM_MAX_RETRIES`             | `2`                         | Retries on transient error                    |

### 5.4 Observability & Background Jobs

| Variable                           | Default                          | Effect                                           |
|------------------------------------|----------------------------------|--------------------------------------------------|
| `SENTRY_DSN`                       | —                                | Enables Sentry init when set                     |
| `SENTRY_ENV`                       | `production`/`development`       | Tag for Sentry events                            |
| `SENTRY_RELEASE`                   | `$RAILWAY_GIT_COMMIT_SHA`        | Release tag                                      |
| `SENTRY_TRACES_SAMPLE_RATE`        | `0.1`                            | Traces sample rate                               |
| `SENTRY_PROFILES_SAMPLE_RATE`      | `0.0`                            | Profiling sample rate                            |
| `LOG_JSON`                         | `0`                              | `1` → structlog JSON stdout                      |
| `LOG_TO_STDOUT`                    | `1`                              | Plain formatter → stdout (dev default)           |
| `REDIS_URL`                        | —                                | RQ queue + Flask-Limiter (optional)              |
| `RATELIMIT_STORAGE_URI`            | falls back to `REDIS_URL` / memory | Dedicated Limiter storage                      |

### 5.5 Gunicorn Tuning

| Variable                           | Default            | Effect                                |
|------------------------------------|--------------------|---------------------------------------|
| `WEB_CONCURRENCY`                  | `max(2, nproc)`    | Worker count                          |
| `GUNICORN_WORKER_CLASS`            | `gthread`          | Worker class                          |
| `GUNICORN_THREADS`                 | `4`                | Threads per worker                    |
| `GUNICORN_TIMEOUT`                 | `120`              | Request timeout                       |
| `GUNICORN_GRACEFUL_TIMEOUT`        | `30`               | Graceful shutdown                     |
| `GUNICORN_KEEPALIVE`               | `5`                | Keep-alive seconds                    |
| `GUNICORN_MAX_REQUESTS`            | `1000`             | Recycle worker after N requests       |
| `GUNICORN_MAX_REQUESTS_JITTER`     | `100`              | Jitter on recycle                     |
| `GUNICORN_PRELOAD`                 | `0`                | Preload app before fork               |
| `GUNICORN_LOG_LEVEL`               | `info`             | Gunicorn log level                    |

### 5.6 Flask Debug & Session

| Variable          | Default | Effect                                        |
|-------------------|---------|-----------------------------------------------|
| `FLASK_DEBUG`     | `0`     | When `1`: disables Secure cookie flag         |
| `SESSION_COOKIE_SAMESITE` | `Strict` (hardcoded) | CSRF mitigation                  |
| `SESSION_COOKIE_HTTPONLY` | `True` (hardcoded)   | JS can't read session cookie     |

### 5.7 Configuration Rules

- `DATABASE_URL` starting with `postgres://` is auto-rewritten to `postgresql://` in `app/config.py`.
- Missing `OPENAI_API_KEY` silently disables translation + scraper AI features.
- Missing `SMS_API_KEY` → `send_sms_code` logs the OTP to stdout (dev mode).
- Missing R2 credentials → all storage helpers return `None` instead of uploading.
- Missing `REDIS_URL` → RQ queue falls back to in-process thread execution.
- Missing `SENTRY_DSN` → no-op init.

---

## 6. Database Schema (Complete)

Primary DB: **PostgreSQL** (production). SQLite works locally but some migrations use `ALTER TABLE` syntax assuming PG.

### 6.1 Multi-Tenant Core

#### `AdminUser` (`AdminUsers`)

| Column                      | Type         | Notes                             |
|-----------------------------|--------------|-----------------------------------|
| `id`                        | Integer PK   |                                   |
| `username`                  | VARCHAR(80) unique | Legacy (super-admin compat) |
| `email`                     | VARCHAR(150) unique |                             |
| `phone`                     | VARCHAR(20), **indexed** | Normalized `995XXXXXXXXX` |
| `password_hash`             | VARCHAR(256) | `werkzeug.generate_password_hash` |
| `role`                      | VARCHAR(20) default `venue` | `venue` \| `super`  |
| `venue_id`                  | FK Venues.id **indexed** |                       |
| `email_verified`            | Boolean      |                                   |
| `email_token`               | VARCHAR(64)  | SHA-256 hash of raw token         |
| `email_token_expires`       | DateTime     | 24h TTL                           |
| `phone_verified`            | Boolean      |                                   |
| `sms_code_hash`             | VARCHAR(256) | werkzeug hash of OTP              |
| `sms_code_expires`          | DateTime     | 2 min TTL                         |
| `sms_attempts`              | Integer      | 0-5 before lockout                |
| `is_active`                 | Boolean      |                                   |
| `reset_token`               | VARCHAR(64)  | SHA-256 hash                      |
| `reset_token_expires`       | DateTime     | 1h TTL                            |
| `failed_login_attempts`     | Integer      | 5 → lockout                       |
| `locked_until`              | DateTime     | 15-min lock window                |
| `two_fa_enabled`            | Boolean      |                                   |
| `two_fa_method`             | VARCHAR(10)  | `sms` \| `email` \| NULL          |
| `lang`                      | VARCHAR(5)   | `ka` \| `en`                      |
| `created_at`                | DateTime     |                                   |

#### `Venue` (`Venues`)

| Column              | Type         | Notes                                      |
|---------------------|--------------|--------------------------------------------|
| `id`                | Integer PK   |                                            |
| `name`              | VARCHAR(100) |                                            |
| `slug`              | VARCHAR(100) unique | Used in `/<slug>/...` URLs          |
| `venue_code`        | VARCHAR(12) unique  | `TB-XXXXXX` (backfilled on add)     |
| `plan`              | VARCHAR(20) default `free` | `free` \| `basic` \| `premium` |
| `total_tables`      | Integer default 0 |                                       |
| `address`           | VARCHAR(300) |                                            |
| `google_place_id`   | VARCHAR(100) |                                            |
| `is_active`         | Boolean      |                                            |
| `group_id`          | FK VenueGroups.id **indexed** | Chain membership (nullable)|
| `created_at`        | DateTime     |                                            |

Helper methods on `Venue`:

- `has_feature(feature_key)` — override → plan default
- `get_all_features()` — returns dict of every feature for this venue
- `plan_display` — capitalized string
- `item_count()` — join FoodItem → Category filter

#### `VenueFeatureOverride` (`VenueFeatureOverrides`)

| Column        | Type                        |
|---------------|-----------------------------|
| `id`          | Integer PK                  |
| `venue_id`    | FK Venues.id **indexed**    |
| `feature_key` | VARCHAR(50)                 |
| `enabled`     | Boolean                     |
| UNIQUE        | (venue_id, feature_key)     |

#### Plan Matrix

| Feature                     | free | basic | premium |
|-----------------------------|:----:|:-----:|:-------:|
| menu                        |  ✓   |   ✓   |    ✓    |
| categories                  |  ✓   |   ✓   |    ✓    |
| subcategories               |  ✓   |   ✓   |    ✓    |
| ingredient_customization    |  ✗   |   ✓   |    ✓    |
| promotions                  |  ✗   |   ✓   |    ✓    |
| cart                        |  ✗   |   ✓   |    ✓    |
| payments                    |  ✗   |   ✗   |    ✓    |
| ratings                     |  ✗   |   ✗   |    ✓    |
| analytics                   |  ✗   |   ✗   |    ✓    |
| reservations                |  ✗   |   ✗   |    ✓    |

### 6.2 Menu

#### `Category` (`Categories`)

| Column              | Type           | Notes                                  |
|---------------------|----------------|----------------------------------------|
| `CategoryID`        | Integer PK     |                                        |
| `CategoryName`      | VARCHAR(50)    |                                        |
| `CategoryName_en`   | VARCHAR(50)    | Auto-translated                        |
| `Description`       | VARCHAR(200)   |                                        |
| `Description_en`    | VARCHAR(200)   |                                        |
| `CategoryIcon`      | VARCHAR(100)   |                                        |
| `venue_id`          | FK Venues.id **indexed** | Venue-local category         |
| `group_id`          | FK VenueGroups.id **indexed** | Shared chain category   |

Exactly one of `venue_id` / `group_id` is non-NULL per row.

#### `Subcategory` (`Subcategories`)

| Column                  | Type                              |
|-------------------------|-----------------------------------|
| `SubcategoryID`         | Integer PK                        |
| `SubcategoryName`       | VARCHAR(50)                       |
| `SubcategoryName_en`    | VARCHAR(50)                       |
| `CategoryID`            | FK Categories.CategoryID **indexed** |

#### `FoodItem` (`FoodItems`)

| Column                  | Type                              |
|-------------------------|-----------------------------------|
| `FoodItemID`            | Integer PK                        |
| `FoodName`              | VARCHAR(50)                       |
| `FoodName_en`           | VARCHAR(50)                       |
| `Description`           | VARCHAR(200)                      |
| `Description_en`        | VARCHAR(200)                      |
| `Ingredients`           | VARCHAR(200)                      |
| `Ingredients_en`        | VARCHAR(200)                      |
| `Price`                 | Float                             |
| `ImageFilename`         | VARCHAR(100)                      |
| `CategoryID`            | FK Categories **indexed**         |
| `SubcategoryID`         | FK Subcategories **indexed**      |
| `allow_customization`   | Boolean default True              |
| `is_active`             | Boolean default True              |

`FoodItem.to_dict()` exposes bilingual fields + image + allow_customization for JSON API consumers.

#### `Promotion` (`Promotions`)

| Column                | Type                     |
|-----------------------|--------------------------|
| `PromotionID`         | Integer PK               |
| `PromotionName`       | VARCHAR(100)             |
| `Description`         | VARCHAR(255)             |
| `Discount`            | Float                    |
| `StartDate`           | Date                     |
| `EndDate`             | Date                     |
| `BackgroundImage`     | VARCHAR(255)             |
| `is_active`           | Boolean                  |
| `venue_id`            | FK Venues.id **indexed** |

#### `Order` (`Orders`) — legacy placeholder

| Column     | Type                               |
|------------|------------------------------------|
| `OrderID`  | Integer PK                         |
| `TableID`  | FK Users.id **indexed**            |
| `Items`    | Text (JSON-encoded)                |
| `Status`   | VARCHAR(50) default Pending **indexed** |
| `CreatedAt`| DateTime                           |
| `venue_id` | FK Venues.id **indexed**           |

> `Orders.TableID` references a legacy `Users` table that predates the refactor. The current placeholder endpoint `POST /<slug>/order` does not actually persist here — see §24.

### 6.3 Global Library

#### `GlobalCategory` (`GlobalCategories`)

- `id`, `name`, `name_en`, `description`, `description_en`, `icon`, `sort_order`, `is_active`, `created_at`
- 1:N `items` → `GlobalItem`

#### `GlobalSubcategory` (`GlobalSubcategories`)

- `id`, `category_id` **indexed**, `name`, `name_en`, `is_active`

#### `GlobalItem` (`GlobalItems`)

- `id`, `category_id` **indexed**, `subcategory_id` **indexed**, `name`, `name_en`, `description`, `description_en`, `ingredients`, `ingredients_en`, `image_filename`, `is_active`, `created_at`
- `to_dict()` returns bilingual JSON payload used by `/backoffice/library/api/items`.

### 6.4 Reservations

#### `ReservationCustomer` (`ReservationCustomers`)

- `id`, `name`, `email` unique, `phone`, `password_hash`, `preferred_language`, `created_at`

#### `RestaurantTable` (`RestaurantTables`)

| Column      | Type                          |
|-------------|-------------------------------|
| `id`        | Integer PK                    |
| `venue_id`  | FK Venues.id **indexed**      |
| `label`     | VARCHAR(20) (e.g. "T-12")     |
| `shape`     | VARCHAR(20) default `circle`  |
| `capacity`  | Integer default 4             |
| `pos_x` / `pos_y` | Float (floor layout)    |
| `width` / `height`| Float (floor layout)    |
| `is_active` | Boolean                       |

#### `Booking` (`Bookings`)

| Column                 | Type                                      |
|------------------------|-------------------------------------------|
| `id`                   | Integer PK                                |
| `venue_id`             | FK Venues.id **indexed**                  |
| `table_id`             | FK RestaurantTables.id **indexed**        |
| `customer_id`          | FK ReservationCustomers.id **indexed**    |
| `booking_date`         | Date **indexed**                          |
| `time_slot`            | Time                                      |
| `guest_count`          | Integer                                   |
| `guest_name`           | VARCHAR(100)                              |
| `guest_email`          | VARCHAR(150)                              |
| `guest_phone`          | VARCHAR(20)                               |
| `comment`              | Text                                      |
| `status`               | VARCHAR(20) **indexed**                   |
| `language`             | VARCHAR(5)                                |
| `cancellation_token`   | VARCHAR(64) unique                        |
| `payment_intent_id`    | VARCHAR(100)                              |
| `deposit_amount`       | Float                                     |
| `created_at`, `updated_at` | DateTime                              |

**Status values:** `pending_payment`, `confirmed`, `cancelled`, `expired`, `completed`.  
**Booking duration constant:** `BOOKING_DURATION = 3 hours` (used in overlap detection).

#### `ReservationSettings` (`ReservationSettings`)

| Column                | Type                                  |
|-----------------------|---------------------------------------|
| `id`                  | Integer PK                            |
| `venue_id`            | FK Venues.id **unique**               |
| `deposit_amount`      | Float default 0.0                     |
| `time_slots`          | JSON array of `"HH:MM"` strings       |
| `max_advance_days`    | Integer default 30                    |
| `floor_layout`        | JSON (arbitrary editor state)         |
| `updated_at`          | DateTime                              |

### 6.5 Chain / Group

- `VenueGroup` — `id`, `name`, `owner_venue_id` **indexed**, `allow_price_override` bool, `created_at`.  
  Relationships: `owner_venue`, `branches` (dynamic), `invites`, `categories`.
- `VenueGroupInvite` — `id`, `group_id` **indexed**, `invite_code` unique (`TB-INV-XXXXXX`), `invited_by` **indexed**, `target_venue_id` **indexed**, `status` **indexed** (`pending`/`accepted`/`expired`), `expires_at` (24 h TTL), `created_at`.
- `VenueItemPriceOverride` — `id`, `venue_id` **indexed**, `food_item_id` **indexed**, `price`. Unique `(venue_id, food_item_id)`.

### 6.6 Scraper Runtime

#### `ScraperJob` (`ScraperJobs`)

| Column              | Type                                          |
|---------------------|-----------------------------------------------|
| `id`                | Integer PK                                    |
| `venue_id`          | FK Venues.id **unique**                       |
| `status`            | `pending` \| `running` \| `done` \| `failed` \| `dismissed` |
| `result_json`       | JSONB — full pipeline output + `_log` entries |
| `sources_found`     | JSONB — `{google_text, google_photos, glovo}` |
| `error_message`     | Text — last 2000 chars of traceback           |
| `created_at`        | DateTime                                      |
| `finished_at`       | DateTime                                      |

### 6.7 OTP

#### `PhoneOtp` (`PhoneOtps`)

| Column        | Type                                |
|---------------|-------------------------------------|
| `id`          | Integer PK                          |
| `phone`       | VARCHAR(20) **indexed**             |
| `code_hash`   | VARCHAR(256) — werkzeug hash of OTP |
| `expires`     | DateTime — 2 min TTL                |
| `attempts`    | Integer                             |
| `ip`          | VARCHAR(45) — IPv4/IPv6             |
| `created_at`  | DateTime                            |

### 6.8 Indexes

`manage.py:_ensure_indexes()` creates the following on every deploy (idempotent `CREATE INDEX IF NOT EXISTS`):

```
AdminUsers.venue_id, AdminUsers.phone
Venues.group_id
VenueGroups.owner_venue_id
VenueGroupInvites.{group_id, invited_by, target_venue_id, status}
VenueFeatureOverrides.venue_id
Categories.{venue_id, group_id}
Subcategories.CategoryID
FoodItems.{CategoryID, SubcategoryID}
Promotions.venue_id
Orders.{TableID, Status, venue_id}
GlobalSubcategories.category_id
GlobalItems.{category_id, subcategory_id}
RestaurantTables.venue_id
Bookings.{venue_id, table_id, customer_id, booking_date, status}
VenueItemPriceOverrides.{venue_id, food_item_id}
```

Primary keys and `UNIQUE` constraints already create their own indexes and are not listed separately.

---

## 7. Endpoint Catalogue (Every Route)

**Auth legend:**
- `public` — no session check
- `admin` — `login_required`
- `super` — `super_required`
- `owner` — group owner role
- `customer` — reservation customer session

Rate limits are applied via `@rate_limit(...)` from `app.utils.observability`; see §[13. Rate Limiting Matrix](#13-rate-limiting-matrix) for the table.

### 7.1 `landing_bp` — Public Auth & Registration

Base: `/`

| Method | Path                                | Auth   | Description                                    |
|--------|-------------------------------------|--------|------------------------------------------------|
| GET    | `/`                                 | public | Marketing landing page                         |
| GET    | `/login`                            | public | Venue login modal                              |
| GET    | `/admin`                            | public | Super-admin login page                         |
| GET    | `/api/places/search`                | public | Google Places venue lookup                     |
| GET    | `/api/suggest-password`             | public | Strong password suggestion (16 chars)          |
| POST   | `/api/check-availability`           | public | Email uniqueness pre-check                     |
| POST   | `/api/send-phone-otp`               | public | Send pre-registration SMS OTP                  |
| POST   | `/api/verify-phone-otp`             | public | Verify pre-registration SMS OTP                |
| POST   | `/register`                         | public | Create venue + admin + (optional scraper job)  |
| GET    | `/verify-email/<token>`             | public | Mark email as verified                         |
| POST   | `/resend-email-verification`        | public | Re-issue verification email                    |
| POST   | `/login-venue`                      | public | Credentials + optional 2FA step                |
| POST   | `/forgot-password`                  | public | Start reset via SMS / email                    |
| POST   | `/verify-reset-sms`                 | public | Verify reset OTP                               |
| POST   | `/resend-reset-sms`                 | public | Re-issue reset OTP                             |
| GET    | `/reset-password/<token>`           | public | Reset form (token validity check)              |
| POST   | `/reset-password/<token>`           | public | Set new password                               |

### 7.2 `menu_bp` — Customer-Facing Menu

| Method | Path                                                   | Auth   | Description                               |
|--------|--------------------------------------------------------|--------|-------------------------------------------|
| GET    | `/<slug>/table/<int:table_id>`                         | public | Main QR menu home                         |
| GET    | `/<slug>/table/<int:table_id>/cart`                    | public | Cart page (feature-gated)                 |
| GET    | `/<slug>/category/<int:category_id>`                   | public | Items + subcategories JSON                |
| GET    | `/<slug>/subcategory/<int:subcategory_id>`             | public | Items for a subcategory                   |
| GET    | `/<slug>/promotion/<int:promotion_id>`                 | public | Promo detail page                         |
| POST   | `/<slug>/order`                                        | public | Placeholder order response (see §24)      |
| GET    | `/<slug>/reservations`                                 | public | Reservation page (feature-gated)          |

### 7.3 `api_bp` — Minimal Public API

| Method | Path                    | Auth   | Description                |
|--------|-------------------------|--------|----------------------------|
| GET    | `/api/<slug>/items`     | public | Raw list of active items   |

### 7.4 `res_api_bp` — Reservation Customer API

| Method | Path                                                     | Auth     |
|--------|----------------------------------------------------------|----------|
| POST   | `/api/<slug>/customers/register`                         | public   |
| POST   | `/api/<slug>/customers/login`                            | public   |
| GET    | `/api/<slug>/reservations/availability`                  | public   |
| POST   | `/api/<slug>/reservations`                               | customer |
| POST   | `/api/<slug>/reservations/<int:booking_id>/pay`          | customer |
| GET    | `/api/<slug>/reservations/my`                            | customer |
| POST   | `/api/<slug>/reservations/<int:booking_id>/cancel`       | customer |
| GET    | `/api/<slug>/reservations/cancel/<token>`                | public   |
| GET    | `/auth/google/login`                                     | public   |
| GET    | `/auth/google/callback`                                  | public   |

### 7.5 `bo_bp` — Backoffice (Venue + Super)

Base: `/backoffice`

**Auth / Profile**

| Method | Path                              | Auth  |
|--------|-----------------------------------|-------|
| POST   | `/backoffice/login`               | public|
| GET/POST | `/backoffice/change-password`   | admin |
| GET    | `/backoffice/logout`              | admin |
| GET/POST | `/backoffice/profile`           | admin |
| GET    | `/backoffice/`                    | admin |

**Super — Scraper Diagnostics**

| Method | Path                                           | Auth  |
|--------|------------------------------------------------|-------|
| GET    | `/backoffice/super/scraper-test`               | super |
| POST   | `/backoffice/super/scraper-test/trigger`       | super |
| POST   | `/backoffice/super/scraper-test/reset`         | super |
| GET    | `/backoffice/super/scraper-test/status`        | super |
| POST   | `/backoffice/super/scraper-test/test-r2`       | super |
| POST   | `/backoffice/super/scraper-test/test-openai`   | super |
| GET    | `/backoffice/super/scraper-test/detail`        | super |

**Super — Venue Management**

| Method | Path                                                    | Auth  |
|--------|---------------------------------------------------------|-------|
| GET    | `/backoffice/venues`                                    | super |
| GET/POST | `/backoffice/venues/<int:venue_id>/features`          | super |
| POST   | `/backoffice/venues/<int:venue_id>/toggle-active`       | super |
| POST   | `/backoffice/venues/<int:venue_id>/delete`              | super |
| GET/POST | `/backoffice/venues/add`                              | super |

**Menu Management (venue admin)**

| Method | Path                                                         | Auth  |
|--------|--------------------------------------------------------------|-------|
| GET    | `/backoffice/menu`                                           | admin |
| GET    | `/backoffice/menu/import-photos`                             | admin |
| POST   | `/backoffice/menu/analyze-photos`                            | admin |
| GET    | `/backoffice/menu/analyze-status/<job_id>`                   | admin |
| GET    | `/backoffice/menu/analyze-events/<job_id>`                   | admin |
| POST   | `/backoffice/menu/import-analyzed`                           | admin |
| POST   | `/backoffice/menu/toggle-customization/<int:item_id>`        | admin |
| POST   | `/backoffice/menu/toggle-active/<int:item_id>`               | admin |
| GET/POST | `/backoffice/menu/add`                                     | admin |
| GET/POST | `/backoffice/menu/edit/<int:item_id>`                      | admin |
| POST   | `/backoffice/menu/delete/<int:item_id>`                      | admin |
| POST   | `/backoffice/menu/delete-category-items/<int:cat_id>`        | admin |
| POST   | `/backoffice/menu/delete-all-items`                          | admin |
| POST   | `/backoffice/menu/copy/<int:item_id>`                        | admin |

**Promotions & Stats**

| Method | Path                                              | Auth  |
|--------|---------------------------------------------------|-------|
| GET    | `/backoffice/promotions`                          | admin |
| POST   | `/backoffice/promotions/toggle/<int:promo_id>`    | admin |
| GET    | `/backoffice/api/stats`                           | admin |
| GET    | `/backoffice/api/subcategories/<int:category_id>` | admin |

**Categories**

| Method | Path                                                      | Auth  |
|--------|-----------------------------------------------------------|-------|
| GET    | `/backoffice/categories`                                  | admin |
| GET/POST | `/backoffice/categories/add`                            | admin |
| GET/POST | `/backoffice/categories/edit/<int:cat_id>`              | admin |
| POST   | `/backoffice/categories/delete/<int:cat_id>`              | admin |
| POST   | `/backoffice/categories/<int:cat_id>/subcategories/add`   | admin |
| POST   | `/backoffice/subcategories/delete/<int:sub_id>`           | admin |
| POST   | `/backoffice/categories/add-json`                         | admin |
| POST   | `/backoffice/categories/edit-json/<int:cat_id>`           | admin |
| POST   | `/backoffice/categories/delete-json/<int:cat_id>`         | admin |
| POST   | `/backoffice/categories/<int:cat_id>/subcategories/add-json` | admin |
| POST   | `/backoffice/subcategories/delete-json/<int:sub_id>`      | admin |

**Reservation Admin**

| Method | Path                                                     | Auth  |
|--------|----------------------------------------------------------|-------|
| GET    | `/backoffice/reservations`                               | admin |
| POST   | `/backoffice/reservations/<int:booking_id>/cancel`       | admin |
| GET    | `/backoffice/reservations/layout`                        | admin |
| GET    | `/backoffice/api/reservations/layout`                    | admin |
| PUT    | `/backoffice/api/reservations/layout`                    | admin |
| GET/POST | `/backoffice/reservations/settings`                    | admin |
| GET/POST | `/backoffice/settings`                                 | admin |

### 7.6 `lib_bp` — Global Library (Platform Catalog)

Base: `/backoffice/library`

| Method | Path                                              | Auth  |
|--------|---------------------------------------------------|-------|
| GET    | `/backoffice/library/`                            | super |
| POST   | `/backoffice/library/categories/add`              | super |
| POST   | `/backoffice/library/categories/<int:cat_id>/delete` | super |
| POST   | `/backoffice/library/subcategories/add`           | super |
| POST   | `/backoffice/library/subcategories/<int:sub_id>/delete` | super |
| POST   | `/backoffice/library/items/add`                   | super |
| POST   | `/backoffice/library/items/<int:item_id>/delete`  | super |
| GET    | `/backoffice/library/browse`                      | admin |
| POST   | `/backoffice/library/import`                      | admin |
| POST   | `/backoffice/library/create-category`             | admin |
| GET    | `/backoffice/library/api/items`                   | admin |

### 7.7 `group_bp` — Chain / Group

Base: `/backoffice/group`

| Method | Path                                                | Auth  |
|--------|-----------------------------------------------------|-------|
| GET    | `/backoffice/group/`                                | admin |
| GET/POST | `/backoffice/group/create`                        | admin |
| GET/POST | `/backoffice/group/join`                          | admin |
| POST   | `/backoffice/group/invite/generate`                 | owner |
| POST   | `/backoffice/group/invite/<int:invite_id>/expire`   | owner |
| GET/POST | `/backoffice/group/branch/add`                    | owner |
| POST   | `/backoffice/group/branch/<int:venue_id>/remove`    | owner |
| POST   | `/backoffice/group/leave`                           | admin |
| POST   | `/backoffice/group/dissolve`                        | owner |
| POST   | `/backoffice/group/settings`                        | owner |
| GET    | `/backoffice/group/menu`                            | owner |
| POST   | `/backoffice/group/menu/category/add`               | owner |
| POST   | `/backoffice/group/menu/category/<int:cat_id>/delete` | owner |
| POST   | `/backoffice/group/menu/item/add`                   | owner |
| POST   | `/backoffice/group/menu/item/<int:item_id>/edit`    | owner |
| POST   | `/backoffice/group/menu/item/<int:item_id>/delete`  | owner |
| POST   | `/backoffice/group/menu/subcategory/add`            | owner |
| GET    | `/backoffice/group/price-overrides`                 | admin |
| POST   | `/backoffice/group/price-overrides/set`             | admin |

### 7.8 Health

| Method | Path              | Auth   | Returns                            |
|--------|-------------------|--------|------------------------------------|
| GET    | `/health`         | public | `{"status":"ok"}` always 200       |
| GET    | `/health/ready`   | public | DB `SELECT 1` — 200 / 503          |

---

## 8. AI / LLM Layer — Models, Prompts, Schemas

### 8.1 Model Registry

All model names come from `app/scraper/config.py` and are env-overridable:

| Constant                   | Default                  | Use case                                      |
|----------------------------|--------------------------|-----------------------------------------------|
| `OPENAI_MODEL_VISION`      | `gpt-5.4`                | Vision OCR + photo extraction                 |
| `OPENAI_MODEL_REASON`      | `gpt-5.4`                | Hierarchical parse of raw OCR text            |
| `OPENAI_MODEL_FAST`        | `gpt-5.4`                | Classify / translate / enrich / categorize    |
| `OPENAI_MODEL_EMBED`       | `text-embedding-3-large` | Dedup + library photo matching                |
| `OPENAI_MODEL_IMAGE_GEN`   | `gpt-image-1`            | Dish photo generation                         |
| `OPENAI_MODEL` (alias)     | = `OPENAI_MODEL_VISION`  | Back-compat for legacy callers                |
| `OPENAI_MODEL_MINI` (alias)| = `OPENAI_MODEL_FAST`    | Back-compat for legacy callers                |

The **translation service** (`app/services/translation_service.py`) uses its own constant `OPENAI_MODEL = 'gpt-4o-mini'` and hits the **Chat Completions API** (`POST https://api.openai.com/v1/chat/completions`) with `response_format={"type":"json_object"}`, `temperature=0.1`, `max_tokens=1024`, `timeout=20s`. This is a standalone background-translation path, unrelated to the scraper.

### 8.2 API Surface & Response Contract

Every structured LLM call in `ai_analyzer.py` goes through:

```python
client.responses.create(
    model=<tier>,
    input=[{"role":"user", "content":[...]}],
    text={"format": {"type":"json_schema", "name":<name>, "schema":<schema>, "strict": True}},
    # optional per-task:
    # text["verbosity"] = "high"
    # reasoning = {"effort": "minimal" | "low" | ...}
)
```

**Key guarantees:**

- `json_schema` + `strict=True` means the parser never sees markdown fences — `resp.output_text` is always a valid JSON instance of the schema.
- `verbosity="high"` is used **only** for OCR transcription (encourages literal rendering).
- `reasoning.effort="minimal"` is used for cheap classifications where depth-of-thought isn't needed (category map, categorization, simple ingredients).
- Vision calls send `data:<mime>;base64,<...>` URLs with `detail="auto"` by default, or `detail="original"` for OCR transcription where pixel-level fidelity matters.
- Retries use exponential backoff (max `LLM_MAX_RETRIES`, starts at 2s, cap 8s) on timeout / 429 / 5xx / "overloaded".

### 8.3 Prompt Registry (Exact Text)

The following prompts are the **exact current text** in code. Any edit here must land in the referenced source file.

---

**P1. `translation_service._SYSTEM_PROMPT`**
```
You are a professional culinary translator specialising in restaurant menus and gastronomy. Translate accurately using precise culinary and gastronomic terminology. Preserve empty strings as empty strings. Return ONLY a valid JSON object with the exact same keys as the input. No markdown, no explanation.
```

**P2. `translation_service._USER_PROMPT` template**
```
Translate the following restaurant menu JSON from {source} to {target}:

{content}
```

---

**P3. `ai_analyzer._vision_ocr_text` OCR transcription**
```
Transcribe every piece of text visible in this image exactly as it appears. Preserve layout cues (line breaks, columns, bullets) with plain ASCII (newlines, ' - ', indentation). Do not summarize, explain, or add commentary.
```
- Model: `OPENAI_MODEL_VISION`
- Parameters: `detail="original"`, `verbosity="high"`

---

**P4. `ai_analyzer._VISION_EXTRACT_PROMPT` — single-photo flat extraction**
```
You extract structured menu data from restaurant photos.

# Task
Return every dish or drink visible in the image.

# Per-item schema
- name: the dish name only (e.g. "ხინკალი", "Caesar Salad")
- price: numeric string only (e.g. "15.00") or "" when no price is shown
- description: ingredients or subtitle text if shown, otherwise ""
- category: the section header this item sits under (e.g. "სალათები", "Pizza")

# What counts as an item
INCLUDE:
  • any dish or drink with a name, even if the price is missing
  • each variant of a dish (e.g. "Small"/"Large") as its own item — append the
    variant to the name: "Pizza Margherita (Small)"

EXCLUDE:
  • standalone prices, page numbers, addresses, phone numbers
  • pure category headers without a dish
  • decorative slogans or promotional text

# Examples
"ხინკალი ხორცის — 2.00" under the header "ხინკალი"
  → {"name":"ხინკალი ხორცის","price":"2.00","description":"","category":"ხინკალი"}

"Caesar Salad · Romaine, parmesan, croutons · 25 ₾" under "Salads"
  → {"name":"Caesar Salad","price":"25","description":"Romaine, parmesan, croutons","category":"Salads"}

"Pizza Margherita  S 12  L 18"
  → two items: "Pizza Margherita (S)" price 12, "Pizza Margherita (L)" price 18

If the photo is unreadable or contains no menu, return {"items": []}.
```
- Model: `OPENAI_MODEL_VISION`
- Parameters: `detail="auto"`, `verbosity="high"`
- Schema: `_SCHEMA_VISION_ITEMS`

---

**P5. `ai_analyzer._PARSE_SYSTEM_RULES` — hierarchical parse of raw OCR text**
```
You convert raw OCR text from a restaurant menu into a clean, hierarchical JSON structure.

# Output shape (strict)
{
  "categories": [
    {
      "name": "<category>",
      "subcategories": [
        {"name": "<sub>", "items": [ <item>, ... ]}
      ],
      "items": [ <item>, ... ]
    }
  ]
}
where <item> is:
  {
    "name":        "<dish name>",
    "price":       "<numeric string>" | null,
    "description": "<ingredients/subtitle>" | "",
    "variants":    [{"name": "<label>", "price": "<numeric string>" | null}]
  }

# Handling messy input
1. Plain lists, nested categories, handwritten text, typos — all fair game
2. Price formats ("10", "10₾", "GEL 10", "$5") → extract numeric string only
3. Variant lines (Small/Large/XL, 0.33L/0.5L) → fill `variants`, leave top-level price empty
4. If no explicit categories exist, infer sensible ones (Drinks, Mains, Desserts…)
5. When uncertain about placement, use "Other"
6. De-duplicate items that appear multiple times
7. Ignore addresses, phone numbers, slogans, service-charge lines

# Hard rules
- Never hallucinate dishes the OCR text does not reference.
- Never invent prices — missing price = null.
- Fix obvious typos but preserve culturally-specific names (do not translate).
- Keep subcategories=[] when none exist; keep items=[] when a category only has sub-items.
- variants=[] when there are no size/option variants.

# Raw OCR text follows below.
```
- Model: `OPENAI_MODEL_REASON`
- Schema: `_SCHEMA_HIERARCHICAL`

---

**P6. `ai_analyzer._CATEGORY_MAP_PROMPT` — classify into Global taxonomy**
```
You classify restaurant menu items into a fixed global taxonomy.

For each input name, pick the SINGLE best-fitting category from the allowed list.
If nothing fits well, pick the most general applicable category from the list — never
invent a new category.

Return a mapping array where each entry has:
  - "input":   the original input string
  - "matched": the exact category name from the allowed list (case-sensitive)
```
- Model: `OPENAI_MODEL_FAST`
- `reasoning.effort="minimal"`
- Schema: `_SCHEMA_CATEGORY_MAP`

---

**P7. `ai_analyzer._ENRICH_PROMPT` — extracted + inferred ingredients with confidence**
```
You add ingredient data to restaurant menu items.

For each item:
  * extracted:  ingredients the description explicitly states
  * inferred:   ingredients a knowledgeable chef would expect for that dish,
                when not explicitly stated
  * confidence: high | medium | low

Rules:
  * Drinks (juices, sodas, cocktails, beer, wine, coffee, tea): return extracted=[] and inferred=[]
  * Do not hallucinate exotic ingredients a typical recipe would not use
  * Use the dish's native culinary vocabulary
  * Output one result object per input index, in the same order, always keyed by "i"
```
- Model: `OPENAI_MODEL_FAST`
- `reasoning.effort="low"`
- Schema: `_SCHEMA_INGREDIENTS`

---

**P8. `ai_analyzer._BILINGUAL_PROMPT` — normalize + translate ka↔en**
```
You normalize and translate restaurant menu items into Georgian (ka) AND English (en).

For every input, produce BOTH translations regardless of the source language.

# Hard rules
1. Food-industry STANDARD translations, not literal:
     ხაჭაპური ↔ Khachapuri      (NOT "cheese bread")
     ხინკალი ↔ Khinkali         (NOT "dumplings")
     შაურმა ↔ Shawarma
     ცეზარი ↔ Caesar Salad
2. International dishes keep their canonical name: Pizza, Burger, Pasta, Tiramisu.
3. Local/traditional dishes: transliterate into English, do not over-explain.
4. Generic names translate meaningfully ("ქათმის სალათი" → "Chicken Salad").
5. Descriptions: natural paraphrase, not word-by-word.
6. Ingredients: standard culinary terms ("ყველი" → "cheese", "საქონლის ხორცი" → "beef").
7. Keep capitalization: English Title Case for names; Georgian natural.
8. Fix obvious typos before translating.
9. Do not invent new dishes or change meaning.
10. Keep the SAME index for each output (i) as in the input.

# Output
Return a results array — one object per input item, each with:
  i, name_ka, name_en, category_ka, category_en,
  description_ka, description_en, ingredients_ka, ingredients_en
```
- Model: `OPENAI_MODEL_FAST`
- Schema: `_SCHEMA_BILINGUAL`

---

**P9. `ai_analyzer._CATEGORIZE_PROMPT` — bucket flat items when no categories exist**
```
Group Georgian restaurant menu items into logical sections.

Typical categories: სალათები, ცხელი კერძები, წვნიანები, ცომეული, სასმელი,
სადილი, დესერტი, საუზმე — but infer the best fit for each input.

Output buckets: each bucket has a "category" name and an "items" array containing
exact item names from the input. Every input name must appear in exactly one bucket.
```
- Model: `OPENAI_MODEL_FAST`
- `reasoning.effort="minimal"`
- Schema: `_SCHEMA_CATEGORIZE`

---

**P10. `ai_analyzer._SIMPLE_INGR_PROMPT` — dish-name → ingredients string**
```
You produce typical ingredient strings for restaurant dishes.

For each dish name, output ingredients as a short Georgian comma-separated string
(3-6 items). If the item is a drink or you are unsure, return an empty string.
Return one result object per input, preserving the input name exactly.
```
- Model: `OPENAI_MODEL_FAST`
- `reasoning.effort="minimal"`
- Schema: `_SCHEMA_DISH_INGREDIENTS`

---

**P11. `ai_analyzer.generate_dish_photo` — dish photo generation template**
```
Professional food photography of {dish_name}, Georgian restaurant dish, top-down 45-degree angle on a matte white plate, clean neutral background, soft studio lighting, shallow depth of field, crisp focus on the food, appetizing, editorial magazine quality.
```
- Model: `OPENAI_MODEL_IMAGE_GEN` (`gpt-image-1`)
- Size: `1024x1024`, `n=1`

---

**P12. `backoffice_routes` — OpenAI connectivity smoke test**
```
Reply with just: OK
```

### 8.4 JSON Schemas

All located in `app/scraper/ai_analyzer.py`:

| Schema                      | Prompt that uses it | Shape summary                                                          |
|-----------------------------|---------------------|-------------------------------------------------------------------------|
| `_SCHEMA_VISION_ITEMS`      | P4                  | `{items:[{name, price, description, category}]}`                       |
| `_SCHEMA_HIERARCHICAL`      | P5                  | `{categories:[{name, subcategories:[{name, items:[item]}], items:[item]}]}` where item has `name, price, description, variants` |
| `_SCHEMA_CATEGORY_MAP`      | P6                  | `{mapping:[{input, matched}]}`                                         |
| `_SCHEMA_INGREDIENTS`       | P7                  | `{results:[{i, extracted, inferred, confidence}]}`                      |
| `_SCHEMA_BILINGUAL`         | P8                  | `{results:[{i, name_ka, name_en, ...}]}` (9 fields per result)         |
| `_SCHEMA_DISH_INGREDIENTS`  | P10                 | `{results:[{name, ingredients}]}`                                       |
| `_SCHEMA_CATEGORIZE`        | P9                  | `{buckets:[{category, items:[string]}]}`                                |

All schemas use `additionalProperties:false` and list every property in `required`, matching OpenAI's strict-mode requirements.

### 8.5 Embedding-Based Decisions (`app/scraper/embeddings.py`)

| Function                      | Threshold | Model                   | Purpose                                    |
|-------------------------------|-----------|-------------------------|--------------------------------------------|
| `dedupe_items`                | `≥ 0.88`  | `text-embedding-3-large`| Cluster near-identical menu items          |
| `dedupe_categories`           | `≥ 0.88`  | same                    | Same, respecting category buckets          |
| `match_library_photos`        | `≥ 0.82`, assign only at `≥ 0.90` | same   | Menu item → GlobalItem photo       |

**Normalization applied before embedding**: lowercase, remove parenthetical sizing, drop filler stopwords (`classic`, `homemade`, `special`, `best`, `style`, `house`, `fresh`, `new`, `signature`, `original`, `traditional`, `large`, `small`, `medium`, `xl`, `xxl`, `mini`, `big`).

Cosine similarity uses NumPy when present (fast vectorised path) and falls back to pure-Python pairwise computation otherwise.

### 8.6 Retry Policy

```
attempt 1 — immediate
attempt 2 — sleep min(2^1, 8) + 0.25 = ~2.25s  on timeout/429/5xx/overloaded
attempt 3 — sleep min(2^2, 8) + 0.5  = ~4.5s   same condition
…
fail — returns empty list/dict, pipeline continues with partial data
```

---

## 9. Scraper Pipeline

### 9.1 Pipeline Diagram

```
                   ┌──────────────────────┐
registration / ──► │ trigger_scraper_job  │
super-panel POST   └──────────┬───────────┘
                              │
                              ▼
                   ┌──────────────────────┐        REDIS_URL set?
                   │ enqueue_scraper_job  │────┬──► yes → RQ ('scraper' queue)
                   └──────────────────────┘    └──► no  → threading.Thread
                              │
                              ▼
                   ┌──────────────────────┐
                   │       _worker        │  with app.app_context()
                   └──────────┬───────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             _run_pipeline                                   │
│                                                                             │
│  1. Playwright launch (headless, viewport 1280x900, Chrome UA)              │
│                                                                             │
│  2. Google Maps text menu   ── google_menu.extract_google_text_menu         │
│                                                                             │
│  3. Debug screenshot        ── r2_storage.upload_from_path(no_compress=True)│
│                                                                             │
│  4. Google Maps photos      ── google_photos.extract_google_menu_photos     │
│                                                                             │
│  5. Glovo discovery         ── glovo_menu.find_glovo_url                    │
│         (fallback)          ──  find_glovo_url_direct  (Glovo.com search)   │
│     Glovo menu              ──  extract_glovo_menu                          │
│                                                                             │
│  6. Download photos (requests, +=w2000 HD suffix, min 5 KB)                 │
│                                                                             │
│  7. Upload Glovo images to R2 (compressed, CA key)                          │
│                                                                             │
│  8. AI photo analysis       ── ai_analyzer.analyze_menu_photo (per photo)   │
│     Fallback categorization ──  ai_analyzer.categorize_items                │
│                                                                             │
│  9. Upload downloaded menu photos to R2                                     │
│                                                                             │
│  10. Merge sources          ── merger.merge_menu  (see §9.3 priority)       │
│                                                                             │
│  11. Embedding dedup        ── ai_analyzer.ai_deduplicate                   │
│      (if items > max(text_count×1.3, 20))                                   │
│                                                                             │
│  12. Ingredient enrichment  ── ai_analyzer.enrich_ingredients               │
│                                                                             │
│  13. Second-pass categorize ── ai_analyzer.categorize_items (only if flat)  │
│                                                                             │
│  14. Persist result_json to ScraperJob                                      │
│                                                                             │
│  15. Library photo match    ── _match_library_photos (embedding, ≥ 0.90)    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Module Surface

| Module                              | Public functions                                                      |
|-------------------------------------|-----------------------------------------------------------------------|
| `scraper/job_runner.py`             | `trigger_scraper_job`, `_worker`, `_run_pipeline`, `_match_library_photos`, `PipelineLog` |
| `scraper/queue.py`                  | `enqueue_scraper_job`, `run_scraper_job` (RQ entry), `_run_in_thread` |
| `scraper/worker.py`                 | `main` (`python -m app.scraper.worker`)                               |
| `scraper/google_menu.py`            | `extract_google_text_menu(page, place_url)` → `{cat: [items]}` \| `None` |
| `scraper/google_photos.py`          | `extract_google_menu_photos(page, place_url, output_dir=None)` → `[base_url, ...]` |
| `scraper/glovo_menu.py`             | `find_glovo_url(page, place_url)`, `find_glovo_url_direct(page, venue_name)`, `extract_glovo_menu(page, glovo_url)` |
| `scraper/image_preprocessor.py`     | `prepare_for_vision(path)` → `(bytes, mime)`; `prepare_bytes_for_storage(data, max_px, quality)` → `(bytes, ext)` |
| `scraper/ai_analyzer.py`            | See §9.4                                                              |
| `scraper/embeddings.py`             | `embed_texts`, `dedupe_items`, `dedupe_categories`, `match_library_photos` |
| `scraper/merger.py`                 | `merge_menu(google_text, google_photos_ai, glovo_data, glovo_photo_map)`, `normalize_price` |
| `scraper/saver.py`                  | `save_menu_json`, `save_photo`, `save_glovo_photos`, `save_google_photos` (legacy local-disk saves) |

### 9.3 Merge Priority Rules (`merger.py`)

```
Prices:        google_text > google_photos_ai        (Glovo prices NEVER used)
Categories:    google_text > glovo > photos_ai > AI categorization
Items:         google_text > glovo > photos_ai
Descriptions:  google_text > glovo > photos_ai > AI enrichment
Photos:        glovo images > AI web search (library match)
```

If the text source produced ≥ 15 items, it is treated as **authoritative** — photo-AI items that don't appear in the text-menu are *filtered out*, not merged. This prevents hallucinations from disproportionately growing the final menu.

### 9.4 `ai_analyzer` Public Surface

| Function                                   | Called From                    | Purpose                                      |
|--------------------------------------------|---------------------------------|----------------------------------------------|
| `analyze_menu_photo(path)`                 | job_runner (step 8)             | Flat extract from a single menu photo        |
| `analyze_menu_photo_structured(path, cb)`  | `backoffice/menu/analyze-photos`| Two-step OCR + hierarchical parse            |
| `assign_global_categories(items, cats, subs)` | library import flow          | Map extracted → GlobalCategory/Subcategory   |
| `enrich_missing_ingredients(items)`        | photo-import finalization       | Fill `ingredients` with extracted+inferred   |
| `enrich_ingredients(items)`                | job_runner (step 12)            | Simple name-only ingredient enrichment       |
| `translate_items_bilingual(items)`         | photo-import finalization       | Add `name_ka/en`, `ingredients_ka/en`, etc.  |
| `categorize_items(items)`                  | job_runner (steps 8 / 13)       | Bucket flat items into categories            |
| `ai_deduplicate(categories)`               | job_runner (step 11)            | Delegates to embeddings cosine dedup         |
| `match_library_photos_ai(menu, library)`   | job_runner (step 15)            | Delegates to embeddings match                |
| `generate_dish_photo(name, output_dir)`    | admin tools                     | `gpt-image-1` editorial photo                |

### 9.5 Task Queue (RQ + Thread Fallback)

| Mode    | Trigger                               | Execution                                                   |
|---------|---------------------------------------|-------------------------------------------------------------|
| **RQ**  | `REDIS_URL` set + reachable           | `enqueue()` on `Queue('scraper')` with `job_timeout=900s`, `result_ttl=24h`, `failure_ttl=7d`. Worker: `python -m app.scraper.worker` rebuilds its own `create_app()` context per job. |
| **Thread** | REDIS_URL unset or Redis ping fails | `threading.Thread(target=_run_in_thread, daemon=True)` inside the current web worker. Same function body, just different context construction. |

Both modes end at the same `_worker()` call, so the pipeline behaves identically.

---

## 10. Translation Service (Background)

**File:** `app/services/translation_service.py`  
**Model:** `gpt-4o-mini` (hardcoded constant `OPENAI_MODEL`)  
**Endpoint:** `POST https://api.openai.com/v1/chat/completions`  
**Parameters:** `temperature=0.1`, `max_tokens=1024`, `response_format={"type":"json_object"}`, `timeout=20s`

### 10.1 Public API

| Function                                                               | Called When                                  |
|------------------------------------------------------------------------|----------------------------------------------|
| `translate_item_async(item_id, fields, source_lang, target_lang, app)` | After `FoodItem` insert/update in backoffice |
| `translate_category_async(cat_id, fields, source_lang, target_lang, app)` | After `Category` insert/update            |
| `translate_global_item_async(item_id, fields, source_lang, target_lang, app)` | After `GlobalItem` insert/update      |
| `needs_translation(primary, secondary)`                                | Gate — primary filled, secondary empty        |

Each `translate_*_async` spawns a `daemon=True` thread, calls OpenAI, then updates the row inside `with app.app_context():`. Errors are logged, never raised.

### 10.2 Prompts

See §8.3 / P1 (system) and P2 (user template).

### 10.3 Bulk Backfill

`translate_existing.py` is a one-off CLI that iterates every row with `needs_translation()=True` and calls the same async function synchronously.

---

## 11. Cloudflare R2 Storage

**File:** `app/services/r2_storage.py`  
**Protocol:** S3-compatible (boto3 → `endpoint_url=R2_ENDPOINT`, `region_name='auto'`)

### 11.1 Key Behaviour

- **Content-addressable keys**: `{prefix}/{sha256(body)[:24]}.{ext}` — identical bytes always produce the identical key, so dedup is automatic.
- **Compression path**: Pillow resizes to ≤ 1600 px long side, encodes WebP q=85 (falls back to JPEG q=85). Delegates to `image_preprocessor.prepare_bytes_for_storage`.
- **HEAD check before PUT**: avoids paid Class A writes when the object already exists.
- **`Cache-Control: public, max-age=31536000, immutable`** — safe because keys are content-addressed.
- **Minimum size guard**: anything below 5 KB is refused (tracking pixels / HTTP error bodies).
- **`no_compress=True`**: passthrough for full-fidelity uploads (debug screenshots, PNGs).

### 11.2 Public API

| Function                                      | Returns            |
|-----------------------------------------------|--------------------|
| `upload_from_url(url, prefix='photos', **kw)` | Public URL or None |
| `upload_from_path(path, prefix='photos', **kw)` | Public URL or None |
| `upload_bytes(data, prefix='photos', **kw)`   | Public URL or None |

Extra kwargs: `no_compress: bool`, `max_px: int=1600`, `quality: int=85`, `content_type: str|None`.

### 11.3 Failure Modes

- Missing credentials → `_get_client()` returns `None`, every call returns `None`. Pipeline continues; photos stay local-only.
- boto3 not installed → warning log, returns `None`.

---

## 12. Authentication & Security

### 12.1 Password Hashing

- **Library:** `werkzeug.security.generate_password_hash` / `check_password_hash`
- **Algorithm:** PBKDF2-SHA256 (werkzeug default)
- **Applied on:** `AdminUser.password_hash`, `ReservationCustomer.password_hash`, `AdminUser.sms_code_hash`

### 12.2 OTP Generation

`app/services/registration_service._generate_otp_code(length=6)`:
```python
''.join(secrets.choice(string.digits) for _ in range(length))
```
Uses `secrets` (crypto-safe) — never `random`. Used by `send_sms_code` (landing OTP + reset), and by email 2FA paths in `backoffice_routes` and `landing_routes`.

### 12.3 Password Validation

`validate_password(pw)` in `registration_service.py`:

- length ≥ 8
- ≥ 1 uppercase
- ≥ 1 lowercase
- ≥ 1 digit

### 12.4 Tokens

| Token             | Random source        | Storage        | TTL     |
|-------------------|----------------------|----------------|---------|
| Email verification| `secrets.token_urlsafe(32)` | SHA-256 in DB | 24 h    |
| Password reset    | `secrets.token_urlsafe(32)` | SHA-256 in DB | 1 h     |
| Cancellation      | `secrets.token_urlsafe(32)` | Raw in DB     | lifetime of booking |
| Venue code        | `TB-` + 6 chars (upper + digits) | raw     | —       |
| Invite code       | `TB-INV-` + 6 chars  | raw            | 24 h    |

Token `_hash_token(raw)` = SHA-256 hex — the raw value is emailed/SMS'd, the hash lives in DB (email/reset). This prevents DB dump → account takeover.

### 12.5 2FA

`AdminUser.two_fa_method ∈ { None, 'sms', 'email' }`.

- **SMS 2FA**: `send_sms_code` generates 6-digit → werkzeug-hashed → `sms_code_expires` = now + 2 min.
- **Email 2FA**: `_generate_otp_code` → `send_2fa_email` template (`ka`/`en`).
- Max 5 attempts per code (increments `sms_attempts`).
- On success: `sms_code_hash = None`, session key `admin_id` set.

### 12.6 Brute-Force Lockout

`AdminUser.record_failed_login()`: increments `failed_login_attempts`; at 5 → `locked_until = now + 15 min`. `is_locked` property short-circuits `/login` before password check.

### 12.7 OTP Rate Limits (app-level)

- **Per-phone**: resend blocked if > 60 s remaining on previous OTP.
- **Per-IP**: max 10 pre-registration OTPs per hour (via `PhoneOtp.ip`).
- **Per-endpoint**: Flask-Limiter — see §13.

### 12.8 Session Cookie Hardening

| Flag                     | Value                               |
|--------------------------|-------------------------------------|
| `SESSION_COOKIE_SECURE`  | True in production (off if FLASK_DEBUG=1) |
| `SESSION_COOKIE_HTTPONLY`| True                                |
| `SESSION_COOKIE_SAMESITE`| `Strict`                            |
| `REMEMBER_COOKIE_SECURE` | matches `SESSION_COOKIE_SECURE`     |

### 12.9 Tenant Isolation

- Every write endpoint in `backoffice_routes.py` calls `verify_item_ownership(item_id)` / filters by `admin.venue_id` before mutating.
- Menu rendering (`menu_routes.py`) filters categories by `venue_id` and (if group) adds `group_id=… AND venue_id IS NULL`.
- Group routes (`group_routes.py`) check `owner_venue_id == admin.venue_id` for destructive operations via `@owner_required`.

---

## 13. Rate Limiting Matrix

`@rate_limit(*exprs)` wraps endpoints via `app.utils.observability.rate_limit`. When `flask-limiter` is not installed, the decorator is a no-op (graceful degradation). Storage: in-memory default, Redis when `RATELIMIT_STORAGE_URI` or `REDIS_URL` is set.

| Endpoint                                   | Limit(s)              |
|--------------------------------------------|-----------------------|
| `POST /api/send-phone-otp`                 | `30/hour`, `3/minute` |
| `POST /api/verify-phone-otp`               | `30/hour`, `10/minute`|
| `POST /register`                           | `10/hour`             |
| `POST /login-venue`                        | `20/hour`, `5/minute` |
| `POST /forgot-password`                    | `10/hour`, `3/minute` |
| `POST /verify-reset-sms`                   | `30/hour`, `10/minute`|
| `POST /resend-reset-sms`                   | `10/hour`, `3/minute` |
| `POST /reset-password/<token>`             | `10/hour`             |
| `POST /resend-email-verification`          | `5/hour`              |
| `POST /backoffice/login`                   | `20/hour`, `5/minute` |

Key function: `get_remote_address` (Flask-Limiter default). `forwarded_allow_ips='*'` in Gunicorn config so Railway edge forwards the real client IP.

---

## 14. External Integrations

### 14.1 SMS — smsoffice.ge

| Field          | Value                                         |
|----------------|-----------------------------------------------|
| Endpoint       | `http://smsoffice.ge/api/v2/send`             |
| Method         | `GET` (legacy)                                |
| Query params   | `key`, `destination`, `sender`, `content`     |
| Timeout        | 10 s                                          |
| Function       | `registration_service.send_sms_code(phone, lang='ka', purpose='otp')` |
| Returns        | `(code: str, error_message: str | None)`      |
| Dev mode       | If `SMS_API_KEY` unset → writes code to `app.logger.warning` and returns success |

**Message templates** (Georgian default, English when `lang='en'`):

- OTP: `Tably: დამადასტურებელი კოდი: {code}. მოქმედებს 2 წუთი.`
- Reset: `Tably: პაროლის აღდგენის კოდი: {code}. მოქმედებს 5 წუთი.`

### 14.2 Email

- **Primary**: Resend API (`POST https://api.resend.com/emails`, bearer `RESEND_API_KEY`, from `Tably <info@tably.ge>`, 15 s timeout).
- **Fallback**: SMTP (tries configured `SMTP_PORT` first, then swaps 465 ↔ 587). Certifi-backed SSL context.
- **Sender**: `_send_email_smtp(to, subject, html, ...)` — fire-and-forget on a daemon thread so Gunicorn workers don't block.

Three senders wrap the HTML template:

- `send_verification_email(email, token, venue_name, base_url, lang)`
- `send_password_reset_email(email, token, base_url, lang)`
- `send_2fa_email(email, code, lang)`

### 14.3 Google Places

| Field     | Value                                                    |
|-----------|----------------------------------------------------------|
| Endpoint  | `POST https://places.googleapis.com/v1/places:searchText`|
| Header    | `X-Goog-Api-Key`, `X-Goog-FieldMask: places.displayName,places.formattedAddress,places.id` |
| Location bias | Tbilisi center `41.7151, 44.8271`, radius 50 km      |
| Function  | `search_google_place(name, address)` → list of max 5 `{name, address, place_id, maps_url}` |

### 14.4 Google OAuth (Reservation Customers)

- Library: `Authlib`
- OIDC discovery: `https://accounts.google.com/.well-known/openid-configuration`
- Flow: `/auth/google/login` → redirect → `/auth/google/callback` → match or create `ReservationCustomer` by email.
- Session: same `customer_id` key as password login.

### 14.5 Cloudflare R2

See §[11. Cloudflare R2 Storage](#11-cloudflare-r2-storage).

### 14.6 OpenAI

Two API surfaces are used:

- **Responses API** (`client.responses.create`) — scraper, via `app/scraper/ai_analyzer.py`.
- **Chat Completions API** (`POST /v1/chat/completions`) — auto-translate, via `app/services/translation_service.py`.
- **Embeddings API** (`client.embeddings.create`) — `app/scraper/embeddings.py`.
- **Images API** (`client.images.generate`) — `generate_dish_photo`.

See §[8. AI / LLM Layer](#8-ai--llm-layer--models-prompts-schemas) for complete prompts, schemas, parameters.

### 14.7 Playwright

- Browser: Chromium
- Launch options: `headless=SCRAPER_HEADLESS`, `slow_mo=SCRAPER_SLOW_MO`
- Context: viewport `1280×900`, locale `en-US`, timezone `America/New_York`, desktop Chrome UA
- Install: `playwright install --with-deps chromium` in `nixpacks.toml` build step
- Usage sites: Google Maps text menu, Google Maps photos, Glovo discovery + menu extraction

---

## 15. Payments (Adapter Pattern)

**File:** `app/services/payment_service.py`

### 15.1 Components

```
PaymentGateway (ABC)
  ├─ create_payment_intent(amount, currency, metadata) → PaymentResult
  └─ verify_payment(payment_id) → PaymentResult

StripeAdapter(secret_key)        — real integration (needs stripe package)
MockPaymentGateway               — dev default, always succeeds

PaymentService(gateway=None)
  ├─ process_deposit(booking)        # 0 → auto-confirm; else create intent
  ├─ confirm_payment(booking)        # check status and commit
  └─ handle_webhook(payload)         # Stripe event → booking.status
```

### 15.2 Current Defaults

- `PaymentService()` without arg uses `MockPaymentGateway`.
- Currency hardcoded `gel` in `process_deposit`.
- Amount converted to cents (`int(amount * 100)`).
- Webhook **does not** verify the `Stripe-Signature` header — open for wiring (see §24).
- Idempotency keys are **not** passed to `stripe.PaymentIntent.create` — wiring pending.

### 15.3 `PaymentResult` dataclass

```python
@dataclass
class PaymentResult:
    success: bool
    payment_id: str = ''
    error: str = ''
    client_secret: str = ''
```

---

## 16. Reservations Subsystem

**File:** `app/services/reservation_service.py`

### 16.1 Constants

- `BOOKING_DURATION = timedelta(hours=3)` — used for overlap detection on both sides of the requested slot.
- `BOOKING_STATUSES = { pending_payment, confirmed, cancelled, expired, completed }`.
- Pending expiry window = 15 minutes (see `expire_pending_bookings`).

### 16.2 Public API

| Function                                                   | Behaviour                                          |
|------------------------------------------------------------|----------------------------------------------------|
| `check_overlap(table_id, date, start, for_update=False)`   | Uses half-open interval `[start, start+3h)`; with `for_update=True` selects with row lock (only during creation) |
| `get_available_tables(venue_id, date, time, guests)`       | Filters active tables with `capacity >= guests` and no overlap |
| `auto_assign_table(venue_id, date, time, guests)`          | Picks the smallest-capacity fit; returns None if none match |
| `create_booking(venue_id, data)`                           | Validates fields, assigns table (auto or specified), checks overlap, sets `deposit_amount`, status `pending_payment` |
| `cancel_booking(booking_id, cancelled_by='customer')`      | Customer cancellation blocked < 2 h before slot; admin can always cancel |
| `get_bookings_for_venue(venue_id, filters=None)`           | Supports `date` / `status` / `table_id` filters    |
| `get_customer_bookings(customer_id)`                       | Newest first                                        |
| `expire_pending_bookings()`                                | Sets `status='expired'` on rows created > 15 min ago still in `pending_payment` |

### 16.3 Booking Flow

1. Customer registers or logs in (`/api/<slug>/customers/...`) or completes Google OAuth.
2. Frontend calls `/api/<slug>/reservations/availability` with date + guests.
3. `POST /api/<slug>/reservations` creates a row (`pending_payment`, token, deposit derived from `ReservationSettings`).
4. If `deposit_amount > 0` → `POST /api/<slug>/reservations/<id>/pay` calls `PaymentService.process_deposit`, returns `client_secret` for Stripe.js.
5. On successful webhook → status becomes `confirmed`, `NotificationService.send_booking_confirmation` is called.
6. Customer can cancel (≥ 2 h before slot) via authenticated endpoint OR via the `/cancel/<token>` token link.

---

## 17. Notifications

**File:** `app/services/notification_service.py`

### 17.1 Templates (inline `TEMPLATES` dict)

Keys: `confirmation`, `cancellation`, `reminder` × `ka`, `en`. Each entry has `subject` and `body` templates rendered with context dict `{venue_name, date, time_slot, table_label, guest_count, cancel_url}`.

### 17.2 Public API

| Method                                         | Purpose                                               |
|------------------------------------------------|-------------------------------------------------------|
| `generate_cancellation_token(booking_id)`      | `secrets.token_urlsafe(32)` written to `Booking.cancellation_token` |
| `verify_cancellation_token(token)`             | Returns booking id if still cancellable, else None    |
| `send_booking_confirmation(booking)`           | Generates token if missing, renders + sends            |
| `send_booking_cancellation(booking)`           | Cancellation email                                     |
| `send_booking_reminder(booking)`               | 24h-before reminder (call site: cron/manual)           |

### 17.3 Delivery Path

`_send_email(to, subject, html)` tries Flask-Mail if attached to `current_app.extensions['mail']`, otherwise logs. This is a less robust path than `registration_service._send_email_smtp` — see §24.

---

## 18. Observability (Sentry, Structlog, Health)

### 18.1 Sentry

**File:** `app/utils/observability.py:init_sentry`

- Gated by `SENTRY_DSN`. If unset → no-op.
- Integrations: `FlaskIntegration`, `SqlalchemyIntegration`, `LoggingIntegration(level=INFO, event_level=ERROR)`.
- Traces sample rate: `SENTRY_TRACES_SAMPLE_RATE=0.1` default.
- Release tag: `SENTRY_RELEASE` or `RAILWAY_GIT_COMMIT_SHA`.
- Environment: `SENTRY_ENV` or `production`/`development` based on `app.debug`.
- `send_default_pii=False`, `attach_stacktrace=True`.

### 18.2 Structured Logging

**File:** `app/utils/logging.py`

- **Plain mode** (default): `RotatingFileHandler('logs/menu_app.log', 10MB × 10)` plus stdout when `LOG_TO_STDOUT=1`. Format: `%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]`.
- **JSON mode** (`LOG_JSON=1`): structlog processors = `merge_contextvars + add_log_level + iso TimeStamper(utc) + StackInfoRenderer + format_exc_info + JSONRenderer`. Stdlib `logging` is rerouted through structlog so `app.logger.info("msg")` also emits JSON.

`get_logger(name)` helper returns a structlog logger when JSON mode is on, else `logging.getLogger`. Both accept kwargs:

```python
log.info("scraper_job_started", venue_id=42, source="google")
```

### 18.3 Health Endpoints

See §4.3.

### 18.4 Sampling Rates

| Setting                          | Default | Override                            |
|----------------------------------|---------|-------------------------------------|
| Sentry traces                    | 0.1     | `SENTRY_TRACES_SAMPLE_RATE`         |
| Sentry profiling                 | 0.0     | `SENTRY_PROFILES_SAMPLE_RATE`       |

---

## 19. Background Jobs (RQ + Thread Fallback)

### 19.1 Queue Architecture

```
 Producers                        Queue ('scraper')                Consumers
 ─────────                        ─────────────────                ─────────
 landing:/register     ─┐
 bo:/super/scraper/    ─┤─► enqueue_scraper_job()  ┬─► RQ (Redis)  ─► python -m app.scraper.worker
                         │                          │                  (separate Railway service)
                         └─► REDIS_URL unset        └─► threading.Thread (in-process)
```

### 19.2 RQ Config

- Queue name: `scraper`
- `job_timeout = 900 s`
- `result_ttl  = 86400 s`  (1 day retention)
- `failure_ttl = 604800 s` (7 days retention for failed jobs)

### 19.3 Worker Entry

```python
# app/scraper/worker.py
python -m app.scraper.worker
# → connects to REDIS_URL, listens on queue 'scraper', no scheduler
```

Each job rebuilds its own `create_app()` context so the worker doesn't share state with the web process.

### 19.4 Public API

| Function                                   | Context           | Returns                                 |
|--------------------------------------------|-------------------|-----------------------------------------|
| `trigger_scraper_job(app, venue_id, place_id, venue_name)` | web request      | handle string (RQ job id or thread name)|
| `enqueue_scraper_job(app, venue_id, place_id, venue_name)` | web request      | same                                    |
| `run_scraper_job(venue_id, place_id, venue_name)`          | RQ worker        | —                                       |
| `_worker(app, venue_id, place_id, venue_name)`             | internal         | —                                       |

---

## 20. Frontend Behaviour

### 20.1 Templating

- Engine: Jinja2 (Flask built-in).
- Primary locale: Georgian, secondary: English (toggled client-side via `i18n.js`).
- Template root: `app/templates/` — landing, admin, menu, cart, reservation, library, group variants.
- Global context injection: `FeatureFlags` instance via `@app.context_processor`.

### 20.2 Static Assets

- CSS: `app/static/css/app.css`, `landing.css`, `backoffice.css`.
- JS: `app/static/js/` — `i18n.js` (locale strings), menu rendering, cart logic, backoffice scripts.
- No JS bundler; assets are served by Flask static view.

### 20.3 Client-Side State

- **Cart**: `localStorage` key `cart_<slug>_<table>` holds current line items.
- **Language**: `localStorage` holds `lang=ka|en`.
- **Theme**: `localStorage` holds `theme=light|dark`.
- **Session**: server-side Flask signed cookie (`admin_id`, `customer_id`, `table_id`, etc.).

### 20.4 Public UX Rules

- Scanning a QR at a table writes `session['table_id']` and `session['venue_slug']`.
- Category/subcategory contents are fetched via XHR (`/<slug>/category/<id>`, `/<slug>/subcategory/<id>`) so the menu is single-page.
- Cart feature is gated by `features.cart`; hitting the cart URL on a `free` plan redirects home with flash.

---

## 21. Business Flows (Diagrammed)

### 21.1 Venue Registration

```
1.  user types phone ───► POST /api/send-phone-otp
                          (rate-limit 30/h, 3/min; SMS sent)
2.  user types OTP  ───► POST /api/verify-phone-otp
                          session['verified_phone'] = phone
3.  user fills form ───► POST /register
                          (rate-limit 10/h)
                          - validate_password
                          - Venue.create + slug + venue_code
                          - AdminUser.create (email_verified=False)
                          - email verification email (async)
                          - trigger_scraper_job() in background
                          - session['admin_id'] set
4.  redirect       ───► /backoffice
5.  later          ───► GET /verify-email/<token> (24h TTL)
```

**Testuser backdoor**: venue name ending in `-testuser` (e.g. `paulaner-testuser`) skips OTP and Places validation; useful for scenario testing only.

### 21.2 Venue Login + 2FA

```
POST /login-venue {identifier, password}
  │
  ├─ is_locked?          ── yes → 429/403 lockout msg
  ├─ record_failed_login ── if password wrong
  │
  ├─ two_fa_method==None → session['admin_id']; 200 OK
  │
  ├─ two_fa_method=='sms'
  │   ├─ send_sms_code
  │   ├─ set_sms_code(hash)
  │   ├─ session['login_admin_id']
  │   └─ return {step:'sms_2fa'}
  │
  └─ two_fa_method=='email'
      ├─ _generate_otp_code
      ├─ send_2fa_email
      ├─ session['login_admin_id']
      └─ return {step:'sms_2fa'}   (UI is the same)

POST /login-venue/verify-2fa {code}
  │
  ├─ check_sms_code
  ├─ sms_attempts < 5
  ├─ not expired
  └─ session['admin_id']; 200 OK
```

### 21.3 Reservation Booking (Deposit > 0)

```
customer register/login (or Google OAuth)
  │
  ▼
GET /api/<slug>/reservations/availability?date=..&guests=..
  │ returns tables[] + time_slots[]
  ▼
POST /api/<slug>/reservations
  ReservationService.create_booking
    → Booking(status=pending_payment, deposit_amount=N)
    → NotificationService.generate_cancellation_token
  │
  ▼
POST /api/<slug>/reservations/<id>/pay
  PaymentService.process_deposit
    deposit==0 → status=confirmed, no intent
    deposit>0  → stripe.PaymentIntent.create (or mock)
                 booking.payment_intent_id = intent.id
  returns {client_secret}
  │
  ▼
[frontend] confirmCardPayment via Stripe.js
  │
  ▼ (Stripe webhook)
PaymentService.handle_webhook
  payment_intent.succeeded → booking.status = confirmed
                             NotificationService.send_booking_confirmation
```

Pending bookings older than 15 min get `status='expired'` by `expire_pending_bookings()` (call site: periodic task / admin action).

### 21.4 Scraper Auto-Import

See §9.1 diagram.

### 21.5 Chain Creation & Branch Onboarding

```
Owner venue → POST /backoffice/group/create
                VenueGroup(owner_venue_id=v.id)
                Venue.group_id = group.id
                Existing Category rows: venue-local remain; new shared rows use group_id

Owner → POST /backoffice/group/invite/generate
          VenueGroupInvite(invite_code=TB-INV-XXXXXX, expires_at=+24h)

Branch → POST /backoffice/group/join {invite_code}
           verify invite.status=='pending' and not expired
           Branch Venue.group_id = invite.group_id
           invite.status = 'accepted'

Customer menu on branch (menu_bp.home) merges:
  local categories (venue_id=branch) + group categories (group_id=group, venue_id IS NULL)
  VenueItemPriceOverride(venue_id=branch, food_item_id=…) overrides Price in to_dict
```

---

## 22. Deployment

### 22.1 Railway (`railway.toml`)

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python -c 'from manage import run_migrations; run_migrations()' && python seed.py && python migrate_to_library.py && gunicorn manage:app --config gunicorn.conf.py"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
healthcheckPath = "/health"
healthcheckTimeout = 10
```

### 22.2 Nixpacks (`nixpacks.toml`)

Adds `playwright install --with-deps chromium` to the build phase so the chromium binary and its system deps (libnss, etc.) are available at runtime.

### 22.3 Procfile

```
web:     gunicorn manage:app --config gunicorn.conf.py
worker:  python -m app.scraper.worker
release: python -c "from manage import run_migrations; run_migrations()"
```

### 22.4 Gunicorn (`gunicorn.conf.py`)

| Setting                | Value / Env override                  |
|------------------------|---------------------------------------|
| `bind`                 | `0.0.0.0:$PORT` (default 5001)        |
| `worker_class`         | `gthread` (override: `GUNICORN_WORKER_CLASS`) |
| `workers`              | `WEB_CONCURRENCY` (default: `max(2, nproc)`) |
| `threads`              | `GUNICORN_THREADS` (default 4)        |
| `timeout`              | `GUNICORN_TIMEOUT` (default 120 s)    |
| `graceful_timeout`     | `GUNICORN_GRACEFUL_TIMEOUT` (default 30 s) |
| `keepalive`            | `GUNICORN_KEEPALIVE` (default 5 s)    |
| `max_requests`         | 1000 with 100 jitter (worker recycling) |
| `forwarded_allow_ips`  | `*` (Railway edge)                    |
| `accesslog` / `errorlog`| `-` (stdout)                         |

### 22.5 Version Pin (`runtime.txt`)

```
python-3.12.x
```

### 22.6 Dependencies (`requirements.txt`)

```
Flask==3.1.3
Flask-Migrate==4.1.0
Flask-SQLAlchemy==3.1.1
python-dotenv==1.2.2
gunicorn==23.0.0
psycopg2-binary==2.9.10
Authlib==1.3.2
requests==2.32.3
boto3==1.35.0
openai>=1.57.0
httpx>=0.27.0
playwright==1.48.0
certifi
Pillow>=10.0.0

# Observability
sentry-sdk[flask]>=2.18.0
structlog>=24.4.0

# Rate limiting
Flask-Limiter>=3.8.0

# Background jobs (activated when REDIS_URL is set)
rq>=1.16.0
redis>=5.0.0

# Embeddings / numerical (cosine-similarity acceleration)
numpy>=1.26.0
```

---

## 23. Zero-to-Running Setup

```bash
# 1. Clone and set up a Python 3.12 venv
git clone <repo> && cd QR_Menu-Refactored-
python3.12 -m venv venv && source venv/bin/activate

# 2. Install dependencies + Playwright browser
pip install -r requirements.txt
playwright install --with-deps chromium

# 3. Create .env with at minimum:
cat > .env <<'EOF'
SECRET_KEY=<random 32+ chars>
DATABASE_URL=postgresql://user:pass@host/db      # or sqlite:///dev.db
BASE_URL=http://localhost:5001
OPENAI_API_KEY=sk-...
EOF

# 4. Run migrations + seed
python -c "from manage import run_migrations; run_migrations()"
python seed.py
python migrate_to_library.py   # idempotent — safe to rerun

# 5. Run the web server
gunicorn manage:app --config gunicorn.conf.py
# or for dev hot-reload:
FLASK_DEBUG=1 python manage.py

# 6. Smoke checks
curl http://localhost:5001/health
curl http://localhost:5001/health/ready
open http://localhost:5001/
open http://localhost:5001/login
```

**Optional extras:**
- For background jobs on Redis: set `REDIS_URL=redis://…` and run `python -m app.scraper.worker` in a second terminal.
- For JSON logs: `LOG_JSON=1`.
- For Sentry: `SENTRY_DSN=https://…@sentry.io/…`.

---

## 24. Known Debt & Risks

1. **Legacy tests**. `app/tests/` uses an old API (`create_app('testing')`, fields that no longer exist). Not integrated with CI; rewrite blocked on fixture work.
2. **`Orders.TableID` → legacy `Users` table**. `place_order` endpoint is a placeholder (`return jsonify('Order placed')`) — nothing actually persists here yet.
3. **`user_service.py`** (if present) references a `User` model that has been dropped. Dead code residue.
4. **Stripe not wired**. `PaymentService()` defaults to `MockPaymentGateway`. Two pending items before real use:
   - `handle_webhook` does not verify `Stripe-Signature`.
   - `create_payment_intent` does not pass `idempotency_key=f"booking-{id}"`.
5. **`NotificationService._send_email`** only uses Flask-Mail if an extension is explicitly registered; otherwise logs. Less robust than the SMTP path in `registration_service`.
6. **SMS API key in query string**. `send_sms_code` performs `requests.get(SMS_URL, params={key: …})` — key ends up in any upstream access log. Deliberate (smsoffice.ge's contract), kept as-is.
7. **Background thread fallback**. When REDIS_URL isn't set, scrapers run in the web worker's thread pool. Fine for single-worker local dev; for production with > 1 worker use RQ.
8. **`extract_menu.py`** is a standalone CLI that lives in `app/scraper/` but is not wired through Flask. Its behaviour may drift from `job_runner.py` (duplicates the orchestration).
9. **CSRF**. Flask's built-in WTF-CSRF is not enabled globally. Backoffice POSTs rely on same-origin + `SESSION_COOKIE_SAMESITE=Strict` for mitigation.
10. **Worker restart + scraper**. If an RQ worker dies mid-scrape, the current job becomes "failed"; no automatic retry. Jobs have `failure_ttl=7d` so the error is preserved.

---

## 25. Change Control Protocol

Any change in one of the categories below MUST update this document first:

### 25.1 AI prompt / model changes

| You want to change…                 | Touch                                        |
|-------------------------------------|----------------------------------------------|
| Translation prompt or model          | `app/services/translation_service.py` — `OPENAI_MODEL`, `_SYSTEM_PROMPT`, `_USER_PROMPT`; reflect in §8.3 P1-P2 |
| Scraper prompts                      | `app/scraper/ai_analyzer.py` — `_VISION_EXTRACT_PROMPT`, `_PARSE_SYSTEM_RULES`, `_CATEGORY_MAP_PROMPT`, `_ENRICH_PROMPT`, `_BILINGUAL_PROMPT`, `_CATEGORIZE_PROMPT`, `_SIMPLE_INGR_PROMPT`, `generate_dish_photo` template; reflect in §8.3 P3-P11 |
| Model tier defaults                  | `app/scraper/config.py` — `OPENAI_MODEL_*`; reflect in §5.3 + §8.1 |
| Structured-output schemas            | `_SCHEMA_*` in `ai_analyzer.py`; reflect in §8.4 |
| Embedding thresholds                 | `dedupe_items` / `match_library_photos` in `embeddings.py`; reflect in §8.5 |

### 25.2 SMS / email provider changes

| You want to change…                 | Touch                                        |
|-------------------------------------|----------------------------------------------|
| SMS provider URL / payload          | `registration_service.SMS_URL`, `send_sms_code`; preserve `(code, error)` return shape; reflect in §14.1 |
| Primary email provider               | `registration_service._send_via_resend` / add branch in `_send_email_smtp`; reflect in §14.2 |
| Reservation email delivery           | `notification_service._send_email`; reflect in §17.3 |

### 25.3 Payment provider

- `app/services/payment_service.py` — implement a new `PaymentGateway` subclass; `PaymentService(gateway=NewGateway(...))` wiring at call sites.
- Preserve `PaymentResult` contract.
- Reflect in §15.

### 25.4 New endpoint

1. Add route in the appropriate blueprint (`app/routes/*`).
2. Add `@rate_limit(...)` if it's an auth/mutation endpoint.
3. Add row to §7 table.
4. Update §13 if rate-limited.

### 25.5 New environment variable

1. Read it inside its module.
2. Add to §5 (table + default).
3. If it's mandatory for a feature, note in §5.7 as a rule.

### 25.6 New DB column or table

1. Add to `app/models.py`.
2. Add safe `ALTER TABLE IF NOT EXISTS` (or `CREATE TABLE IF NOT EXISTS`) in `manage.py:run_migrations`.
3. Add FK index entry to `_INDEXES_TO_ENSURE` if there's a foreign key.
4. Update §6.

### 25.7 UI / design

- Public styles: `app/static/css/app.css`, `landing.css`.
- Backoffice: `app/static/css/backoffice.css`.
- Templates: `app/templates/*`.
- JS: `app/static/js/*.js`.
- Reflect in §20.

### 25.8 Suggested commit message format

```
docs+code: <domain> — <short change>

<details>
```

Examples:
- `docs+code: scraper — switch vision model to gpt-5.5`
- `docs+code: auth — raise lockout threshold from 5 to 10`
- `docs+code: r2 — enable immutable cache headers`

---

## 26. Quick Reference — What Lives Where

| Need to find…                            | Go to                                          |
|------------------------------------------|------------------------------------------------|
| App factory / blueprint registration     | `app/__init__.py`                              |
| Flask config                             | `app/config.py`                                |
| All DB models + constants                | `app/models.py`                                |
| Customer menu pages                      | `app/routes/menu_routes.py`                    |
| Registration / login flows               | `app/routes/landing_routes.py`                 |
| Public items API                         | `app/routes/api_routes.py`                     |
| Venue + super backoffice                 | `app/routes/backoffice_routes.py`              |
| Reservation customer API + Google OAuth  | `app/routes/reservation_api_routes.py`         |
| Global library CRUD                      | `app/routes/global_library_routes.py`          |
| Chain / group                            | `app/routes/group_routes.py`                   |
| SMS / email / Places / password helpers  | `app/services/registration_service.py`         |
| Booking / availability logic             | `app/services/reservation_service.py`          |
| Payment adapter                          | `app/services/payment_service.py`              |
| Reservation emails                       | `app/services/notification_service.py`         |
| Menu auto-translate                      | `app/services/translation_service.py`          |
| R2 upload / compression                  | `app/services/r2_storage.py`                   |
| Scraper orchestrator                     | `app/scraper/job_runner.py`                    |
| Task queue (RQ / thread)                 | `app/scraper/queue.py`, `worker.py`            |
| All LLM prompts + schemas                | `app/scraper/ai_analyzer.py`                   |
| Embeddings (dedup, library match)        | `app/scraper/embeddings.py`                    |
| Image preprocessing                      | `app/scraper/image_preprocessor.py`            |
| Source merger                            | `app/scraper/merger.py`                        |
| Google Maps text menu                    | `app/scraper/google_menu.py`                   |
| Google Maps menu photos                  | `app/scraper/google_photos.py`                 |
| Glovo link + menu                        | `app/scraper/glovo_menu.py`                    |
| Scraper config + model tiers             | `app/scraper/config.py`                        |
| Logging (plain + JSON)                   | `app/utils/logging.py`                         |
| Sentry + rate limiter                    | `app/utils/observability.py`                   |
| Feature flag injection                   | `app/utils/feature_flags.py`                   |
| Runtime migrations + index creation      | `manage.py`                                    |
| Super-admin seed                         | `seed.py`                                      |
| Library backfill                         | `migrate_to_library.py`                        |
| Bulk re-translate                        | `translate_existing.py`                        |
| Gunicorn config                          | `gunicorn.conf.py`                             |
| Deploy manifests                         | `Procfile`, `railway.toml`, `nixpacks.toml`    |

---

<div align="center">

**Document version 2.0 — synchronised with post-refactor codebase (April 2026).**  
Source-of-Truth: update this file FIRST, then the code.

</div>
