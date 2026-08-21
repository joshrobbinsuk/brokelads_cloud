# brokelads_cloud

Backend for **BrokeLads**, a sports-betting demo app built around a weekly play-money cup.
A FastAPI service ingests football fixtures, odds and results from API-Football (RapidAPI),
lets authenticated users stake a £1000 weekly pot on match outcomes, settles those bets from
live match statuses, and ranks everyone on a leaderboard. It runs on GCP (Cloud Run + Neon
Postgres) and is provisioned entirely by Terraform.

The frontend is a separate repo: **[joshrobbinsuk/bl-fe](https://github.com/joshrobbinsuk/bl-fe)**
(Next.js on Vercel). The two are independent checkouts that run and deploy together.

## Architecture

```mermaid
flowchart TB
    FE["Next.js frontend (bl-fe)<br/>built and served by Vercel"]
    GHA["GitHub Actions — push to dev<br/>build image, terraform apply<br/>keyless via Workload Identity Federation"]

    subgraph gcp["GCP project — europe-west2"]
        AR["Artifact Registry<br/>api image"]
        SM["Secret Manager<br/>DATABASE_URL, API keys, session secret"]
        API["Cloud Run<br/>FastAPI, this repo<br/>min 0 / max 2 instances"]
        IDP["Identity Platform (Firebase Auth)<br/>email+password and Google IdP"]
        SCHED["Cloud Scheduler<br/>every minute, 12:00-22:59 Europe/London"]
    end

    NEON[("Neon Postgres<br/>serverless, autosuspends")]
    RAPID["API-Football via RapidAPI"]
    OPENAI["OpenAI Responses API"]

    FE -->|"sign in, mint idToken"| IDP
    FE -->|"REST, Authorization: Bearer idToken"| API
    API -->|"verify_id_token"| IDP
    API -->|"SQLAlchemy, pooled connection"| NEON
    SCHED -->|"POST /rapid-api/run-jobs<br/>X-Cron-Auth-Key"| API
    API -->|"fixtures, odds, results"| RAPID
    API -->|"Ask the Pundit, streamed"| OPENAI
    AR -.->|"container image"| API
    SM -.->|"env from secret refs"| API

    GHA -->|"docker push"| AR
    GHA -->|"terraform apply<br/>Cloud Run, Neon, Scheduler, Secret Manager, Identity Platform"| API
    GHA -->|"sets NEXT_PUBLIC_* env vars, fires rebuild hook"| FE
```

The frontend never holds backend configuration of its own in the cloud: the Terraform apply in
this repo writes the frontend's `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_FIREBASE_*` variables into
the Vercel project and then triggers a Vercel deploy hook, so a backend redeploy re-wires and
rebuilds the frontend with no manual step.

## Repository layout

```
api/                    FastAPI service
  src/                  application code (see below)
  alembic/              migrations
  templates/            admin panel templates
  Dockerfile            image built by CI
docker/                 firebase-emulator image used by docker-compose
functions/              stub serverless handler, not wired to anything
terraform/
  gcp/dev               LIVE root: Cloud Run, Neon, Scheduler, Secret Manager, monitoring, Vercel wiring
  gcp/prod              scaffolded, never applied
  modules/app           the app stack module instantiated by gcp/dev
  modules/identity-platform   Firebase Auth config (Google IdP + email/password)
  aws/                  archived AWS stacks, reference only
.github/workflows/      dev-pr-checks.yml (mypy + pytest), gcp-deploy.yml (build + apply)
docker-compose.yml      local stack: Postgres, API, Firebase Auth emulator
```

### Modules (`api/src/`)

Three feature packages, each a deep module with a thin public surface:

- **`client/`** — the public REST API under `/client/*`, Firebase-authed. `routes.py` is the
  surface; `queries.py` holds the DB logic, `cup.py` the weekly cup and leaderboard,
  `streaks.py` the streak computation, `pundit.py` the OpenAI streaming chat, `schemas.py` the
  Pydantic I/O, and `utils/{firebase,user}.py` the auth dependencies.
- **`rapid_api/`** — ingestion and settlement jobs. `routes.py` exposes one cron-authed
  endpoint, `runner.py` orchestrates, `jobs.py` holds the `JOB_REGISTRY`, `external_calls.py`
  hits API-Football, `internal_queries.py` does the writes, `schemas/` parses the responses.
- **`admin/`** — a SQLAdmin UI behind Google OIDC. `auth.py` is the gate, `admin_views.py` the
  model views, `rapid_api_admin.py` the manual job triggers.

Shared: `main.py` (app and router wiring), `models.py` (all SQLAlchemy models), `database.py`
(`BaseModel`, engine, `get_db`), `settings.py` (env plus domain constants), `accounts.py`
(hard-delete of a user across Firebase Auth and the DB), `utils/weeks.py` (civil-week maths),
`utils/logging.py` (loguru).

`dev/` is a walled-off dev-only package holding the local seeder. It is never imported by the
running app — there is no wiring in `main.py` and no `if ENVIRONMENT == "dev"` branch in any
production path. It calls the real functions from the outside, behind a seatbelt that refuses to
run against a non-local database. A `src.dev` import from any non-test module is a bug.

## Data model

All models live in `api/src/models.py`. String UUID primary keys, timezone-aware `created_at` /
`updated_at` on `BaseModel`.

- **`User`** (`status` ACTIVE / DISABLED / INVITED, `auth_uid` from the Firebase token,
  `username` set once at first run) → **`Bet`** (`choice` HOME / AWAY / DRAW, `outcome`
  UNDECIDED / WON / LOST / VOIDED, NOT NULL `cup_entry_id`) → **`Fixture`** (kick-off, odds,
  goals, an `outcome` property, nullable `league_id`, nullable `venue` — API-Football returns a
  null venue for unscheduled fixtures, so it has to ingest).
- **`League`** carries `rapid_api_id`, `name` / `display_name`, `active` and metadata (`logo`,
  `country`, `type`).
- **Money** lives on **`CupEntry`** — a user's account in one week's **`Cup`**, credited with
  `CUP_STARTING_STAKE` (£1000) at creation. **`LedgerEntry`** is its append-only ledger: signed
  `amount`, `balance_after`, `type` ENTRY_GRANT / BET_STAKE / BET_PAYOUT / BET_VOID_REFUND, and
  a nullable `bet_id`. The invariant `entry.balance == sum(amounts)` is asserted in tests, never
  at runtime. The only credit not tied to a bet is the entry grant: the pot is fixed, and
  engagement rewards are status rather than money.
- **Odds are decimal odds** — the total return already includes the stake, so a bet's
  `returns = stake * odds`; do not add the stake back on top. Each `Bet` also stamps
  `odds_struck` at placement, an internal write-once record of the price it was struck at.
- A cup runs Monday 00:00 to the next Monday 00:00, computed in **Europe/London** civil terms
  (`utils/weeks.py`) so DST weeks resolve to the right UTC span. At settlement `settle_cup`
  freezes `CupEntry.final_rank` (competition ranking, co-winners share rank 1) and
  `Cup.final_entry_count`. Settled-cup leaderboards serve those frozen values — user deletion
  leaves honest gaps — while open cups rank live, and the wire's `is_winner` derives from
  `final_rank == 1`.
- **Streaks** (`client/streaks.py`) are computed on read, with no storage and no caching.
  `participation_streak` counts consecutive London civil weeks with a settled cup entry,
  anchored at the most recent settled cup week overall; a missed week or a week with no cup
  breaks it, and the open current week is ignored. `profit_streak` walks the same weeks but only
  while an entry's final balance beat its own ENTRY_GRANT amount. Both ride every leaderboard row
  and `GET /client/me` as integers.
- **`Event`** is an append-only, purely observational domain log (USER_CREATED,
  CUP_ENTRY_CREATED, BET_PLACED, BET_SETTLED, CUP_SETTLED) written inside each mutation's own
  transaction via `record_event`. It has a `seq` identity column for total ordering and
  deliberately no foreign key on `user_id`, so events survive a user hard-delete. Nothing reads
  it yet.
- **`PunditUsage`** is the per-user, per-day counter behind the pundit's daily cap.
  **`JobControl`** gates each ingestion/settlement job on `enabled` plus `min_interval_seconds`.

**Money crosses the wire as strings.** Backend `Decimal` columns serialize to JSON strings, and
the frontend keeps them as strings end to end.

## Endpoints

| Endpoint | Auth | Notes |
| --- | --- | --- |
| `GET /client/fixture` | Firebase idToken | optional `search`, `league_id`; nests `league: {id, display_name, logo} \| null`; odds as strings; hides fixtures with no league |
| `GET /client/league` | Firebase idToken | active leagues only |
| `POST /client/bet` | Firebase idToken | 201; validates fixture, odds, kick-off, cup week and balance |
| `GET /client/bet` | Firebase idToken | optional `outcome`, `search` |
| `GET /client/me` | Firebase idToken | user, cup balance, `cups_won`, both streaks; exposes the Firebase uid as `auth_uid` |
| `PUT /client/me/username` | Firebase idToken | 409 if taken, 422 if malformed |
| `GET /client/cup/current` | Firebase idToken | current cup, your balance and rank, live leaderboard |
| `GET /client/cup/{cup_id}` | Firebase idToken | one cup plus its leaderboard |
| `GET /client/cups` | Firebase idToken | cups for the week selector |
| `POST /client/pundit` | Firebase idToken | Server-Sent Events stream; 429 once the daily cap is hit |
| `POST /rapid-api/run-jobs` | `X-Cron-Auth-Key` header | runs every due job in `JOB_REGISTRY` |
| `GET /health` | none | liveness, also the target of the GCP uptime check |
| `/admin`, `GET /auth/callback` | Google OIDC | SQLAdmin UI and its OIDC callback |

Client auth is a `HTTPBearer` dependency: `verify_token` calls
`firebase_admin.auth.verify_id_token`, then `get_current_user` provisions the DB user on first
sight of an `auth_uid`. Admin access requires the token's email to equal `ADMIN_EMAIL` (a
constant in `settings.py`) **and** the `email_verified` claim to be true.

## Ingestion and settlement

`POST /rapid-api/run-jobs` runs whatever is due. The jobs in `JOB_REGISTRY` are:

| Job | Does |
| --- | --- |
| `fetch_leagues` | upserts all API-Football leagues (metadata only — never touches `active`, so admin toggles survive deploys) |
| `fetch_fixtures` | for each **active** league, tops it up to `N_FIXTURES_PER_LEAGUE` upcoming fixtures |
| `fetch_odds` | fetches odds for stored fixtures that have none |
| `fetch_fixture_updates` | refreshes status and goals for non-finished fixtures |
| `settle_bets` | wins/losses for fixtures that reached a result status |
| `settle_voided_bets` | refunds bets on postponed, cancelled, abandoned or awarded fixtures |
| `close_cups` | settles a finished week: resolves what it can, force-voids bets whose fixture kicked off over `CUP_BET_MAX_AGE_HOURS` ago and never resolved, then crowns winners once no bets are still undecided |

Each job self-gates on its `JobControl` row, so the cron cadence is only a floor. Cloud Scheduler
fires every minute, but only between 12:00 and 22:59 Europe/London — the window brackets UK
kick-offs, from the earliest lunchtime games to the latest 20:00/20:15 kick-offs finishing by
~22:10. The tick rate is what costs Neon compute-hours (each tick opens a session and Neon needs
~5 idle minutes to autosuspend), so Neon stays awake for the whole window (~84 of the 100 free
CU-h/month) and sleeps outside it; user requests still wake it on demand at any hour. Settlement
lands within a minute or so of full-time.

Leagues are auto-populated (all ~1100, all `active=False`) by `fetch_leagues`; an admin ticks the
handful that should be active. Every job can also be triggered by hand from the `/admin`
RapidAPI page. Which football status codes count as not-started, finished, result-bearing or
voided is defined by the `*_STATUSES` lists in `settings.py`.

Fixtures ingested before leagues existed keep `league_id IS NULL`; `save_new_fixtures` backfills
it in place on the next ingestion of that league, and the client board query filters
`Fixture.league_id IS NOT NULL` so those rows stay off the board until healed.

## Local development

The full stack runs in Docker: Postgres 16, the API with hot reload and auto-migration, and the
Firebase Auth emulator.

```bash
docker-compose up        # API on :8000, Postgres on :5432 (bl_dev / postgres:postgres)
```

`RAPID_API_KEY`, `OPENAI_API_KEY`, `CRON_AUTH_KEY` and `ADMIN_SESSION_SECRET` are read from your
shell environment; no `.env.example` is committed. `DATABASE_URL`, `ADMIN_SESSION_SECRET` and
`CORS_ORIGINS` are hard-required — the app raises on startup without them. Compose sets all three
for localhost; Terraform sets them in the cloud.

Auth runs against the **Firebase Auth emulator** (compose service `firebase-auth`, project
`demo-brokelads`, port 9099). Compose sets `GOOGLE_CLOUD_PROJECT=demo-brokelads` and
`FIREBASE_AUTH_EMULATOR_HOST=firebase-auth:9099`, which `firebase_admin` honours natively so it
accepts the emulator's unsigned tokens. Never set the emulator host in the cloud. `LOCAL_ADMIN_BYPASS`
waves you into `/admin` without the OIDC dance; supply `ADMIN_GOOGLE_CLIENT_ID` /
`ADMIN_GOOGLE_CLIENT_SECRET` instead to exercise the real Google login locally.

Type checking and tests need no Docker. A Python 3.12 venv at `api/.venv`:

```bash
cd api
uv venv --python 3.12 .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt   # first time
.venv/bin/mypy --config-file mypy.ini    # CI gate
.venv/bin/pytest -q                      # CI gate
```

`uv` is only a convenience for getting a 3.12 interpreter; CI uses plain `pip install` and runs
the same two commands. Formatting and linting go through pre-commit (black at line length 88 over
`api/src/`, plus `ruff --fix`): `pre-commit run --all-files`.

### Seeding local data

The dev seeder drives the real ingestion and settlement code paths with mock API responses, so a
local stack gets realistic data without touching RapidAPI. It needs a running database.

```bash
cd api
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/bl_dev ENVIRONMENT=dev \
  ADMIN_SESSION_SECRET=x .venv/bin/python -m src.dev.seed all
```

Subcommands:

| Subcommand | Does |
| --- | --- |
| `fixtures` | seeds an active seed league and six mock fixtures with odds |
| `bets [--email <addr>]` | places a spread of bets, as a synthetic user or an existing one |
| `resolve` | writes mock results and runs settlement |
| `streaks [--email <addr>]` | seeds three weeks of past settled cups so streaks render |
| `emulator-user` | creates the e2e test user in the Auth emulator from `E2E_TEST_EMAIL` / `E2E_TEST_PASSWORD` |
| `all` | all of the above in order, printing per-bet outcomes and the entry balance before and after |

`all` is idempotent (it reserves a `rapid_api_id` range and skips past-week cups that already
exist) and refuses to run against anything but a local database.

### Migrations

```bash
docker-compose exec api alembic revision --autogenerate -m "description"
docker-compose exec api alembic upgrade head    # also runs automatically on container start
```

## Tests and gates

Both gates must be green, and both run on every PR into `dev` (`dev-pr-checks.yml`):

- `mypy` is **strict** (`disallow_untyped_defs`) across the service.
- `pytest` runs the whole suite against a fresh in-memory SQLite engine per test
  (`src/tests/conftest.py`), so no Postgres is needed. `factories.py` builds entities.

The suite splits into `unit_tests/` (model properties and validators, schema parsing, CORS
wiring, admin and Firebase auth dependencies, civil-week maths), `integration_tests/` (bet
creation rules, settlement, ledger invariants, cup close, streaks, leagues, ingestion, events,
user delete, pundit limits, and the dev seeder end to end) and `client/` (fixture, league, cup,
username and pundit routes through the FastAPI app).

Not covered: the admin UI, and the live RapidAPI HTTP transport — `external_calls.py` is
unmocked, and the seeder fakes the response bodies rather than the transport.

## Deploy

Default branch is **`dev`**; feature branches are `feature/<slug>`.

Pushing to `dev` runs `gcp-deploy.yml`, which authenticates to GCP **keyless via Workload
Identity Federation** (the WIF pool and Terraform state bucket are bootstrapped once in a
separate `tf_bootstrap` repo), then:

1. Applies Artifact Registry and the enabled API services first, targeted, so the repository
   exists before the push.
2. Builds `api/Dockerfile` and pushes it tagged with the commit SHA.
3. Runs a full `terraform plan` and `apply` over `terraform/gcp/dev` — Cloud Run, Neon (project,
   branch, role, database, pooled endpoint), Cloud Scheduler, Secret Manager, the uptime check
   and email alert policy, Identity Platform, and the Vercel environment variables.
4. Fires the Vercel deploy hook so the frontend rebuilds against the new API URL and Firebase
   config.

Repo secrets required, all one-time: `RAPID_API_KEY`, `OPENAI_API_KEY`, `ADMIN_SESSION_SECRET`,
`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` (one Google OAuth web client backs both
the end-user Google IdP and the admin OIDC login), `NEON_API_KEY`, `VERCEL_API_TOKEN`,
`VERCEL_PROJECT_ID`, `VERCEL_DEPLOY_HOOK_URL`. The Neon credentials and the cron auth key are
generated by Terraform and delivered to Cloud Run through Secret Manager. The Vercel project is
referenced by ID and never created or destroyed by Terraform.

`terraform/gcp/prod` is scaffolded but has never been applied.

## Running cost

Roughly **£0/month** for the GCP side. Cloud Run has `min_instance_count = 0` so it is billed per
request, and `max_instance_count = 2` caps what a hammered public URL can spend. Neon is
serverless and autosuspends, and the 12:00-22:59 ingestion window keeps its compute inside the
free tier's monthly allowance. Cloud Scheduler runs a single job, and Identity Platform sign-ins
sit well inside the free tier. Third-party usage (RapidAPI, OpenAI) is billed separately.

## Conventions

- Public-surface methods wrap their body in `try/except` that logs (`logger.error` /
  `logger.exception`) and then converts to an `HTTPException`; internal helpers stay clean.
  Domain validation failures raise `ClientSideError` (`client/queries.py`), mapped to 400.
- Reads go through the ORM; bulk ingestion uses `insert()` / `update()` statements.
- Everything is annotated — mypy strict is a gate, so keep new code typed.

## Known limitations

- `ADMIN_EMAIL` is a hardcoded constant in `settings.py`.
- `functions/agent/main.py` is a stub.
- Cup betting is not concurrency-hardened, which is accepted at friends scale. `create_bet`
  checks the balance and debits without a row lock, so two truly simultaneous bets on one
  `CupEntry` could overspend it; and the get-or-create of a cup or entry can lose a race on the
  unique constraint, surfacing a transient 500 that rolls back cleanly and self-heals on retry.
  `SELECT … FOR UPDATE` plus an `IntegrityError` retry would close both.
