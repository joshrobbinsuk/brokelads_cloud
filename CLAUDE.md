# brokelads_cloud — backend

FastAPI + PostgreSQL backend for the BrokeLads sports-betting demo. Ingests football fixtures/odds from API-Football (RapidAPI), lets authenticated users place and settle bets, and deploys to **GCP** (Cloud Run + Neon Postgres) via Terraform; auth is **GCP Identity Platform (Firebase Auth)** — locally the **Firebase Auth emulator** (fake, seedable, no real emails). Frontend lives in the sibling `bl-fe` repo — see `../CLAUDE.md` for how they run together.

## Layout (`api/src/`)

Three feature packages, each a deep module with a thin surface:
- `client/` — public REST API (`/client/*`), Firebase-authed. `routes.py` is the surface; `queries.py` holds DB logic, `schemas.py` the Pydantic I/O, `utils/{firebase,user}.py` the auth dependencies (`firebase.py` verifies the id token via `firebase_admin`).
- `rapid_api/` — data ingestion + bet settlement jobs. `routes.py` exposes one cron-authed endpoint; `runner.py` orchestrates, `jobs.py` holds the `JOB_REGISTRY`, `external_calls.py` hits API-Football, `schemas/` parses its responses.
- `admin/` — SQLAdmin UI behind Google OIDC (`auth.py`; admin gate = token email equals `ADMIN_EMAIL` AND `email_verified`), model views (`admin_views.py`), manual job triggers (`rapid_api_admin.py`).

Shared: `main.py` (app + router wiring), `models.py` (all SQLAlchemy models), `database.py` (`BaseModel`, engine, `get_db`), `settings.py` (env + domain constants), `utils/logging.py` (loguru).

`dev/` is a **walled-off dev-only** package (the `python -m src.dev.seed` local seeder). It is NEVER imported by the running app — no wiring in `main.py`, no `if ENVIRONMENT == "dev"` in any production path. It only *calls into* the real functions from the outside, guarded by an internal prod-DB seatbelt. Keep it that way (a `src.dev` import from any non-test module is a bug).

## Data model (`models.py`)

`User` (`status` ACTIVE/DISABLED/INVITED) → `Bet` (choice HOME/AWAY/DRAW, `outcome` UNDECIDED/WON/LOST/VOIDED, NOT NULL `cup_entry_id`) → `Fixture` (kick-off, odds, goals, `outcome` property, nullable `league_id` FK, nullable `venue` — API-Football returns a null venue for unscheduled/international fixtures, so it must ingest). `League` carries `rapid_api_id`, `name`/`display_name`, `active`, plus metadata (`logo`, `country`, `type`). Money lives on `CupEntry` (the weekly account, starting stake granted at creation); `LedgerEntry` is its append-only ledger — signed `amount`, `balance_after`, `type` ENTRY_GRANT/BET_STAKE/BET_PAYOUT/BET_VOID_REFUND, nullable `bet_id`; invariant `entry.balance == sum(amounts)` (asserted in tests, never at runtime). The only credit not tied to a bet is the entry grant — the pot is sacrosanct, engagement rewards are status, never money. API-Football odds are **decimal odds** (the total return already includes the stake), so a bet's `returns = stake * odds` — do NOT add the stake back on top. Each `Bet` also stamps `odds_struck` at placement (the write-once decimal price it was struck at) — an internal fact, not on the wire, kept for future odds-mutability work. At settlement `settle_cup` stamps `CupEntry.final_rank` (competition ranking, co-winners share rank 1) and `Cup.final_entry_count`; settled-cup leaderboards serve these frozen values (user deletion leaves honest gaps), open cups rank live, and the wire's `is_winner` derives from `final_rank == 1`. **Streaks** (`client/streaks.py`) are computed on read (no storage, no caching): `participation_streak` = consecutive London civil weeks with a SETTLED cup entry, anchored at the most recent settled cup week overall (a missed settled week or a week with no cup breaks it; the open current week is ignored); `profit_streak` walks the same weeks but only while the entry's final balance beats its own ENTRY_GRANT ledger amount. Both ride every leaderboard row and `GET /client/me` as ints (additive; money stays strings). `Event` is an append-only, **observational** domain log (`USER_CREATED`/`CUP_ENTRY_CREATED`/`BET_PLACED`/`BET_SETTLED`/`CUP_SETTLED`), emitted inside each mutation's own transaction via `record_event`; it has a `seq` identity for total ordering and **no FK on `user_id`** (events survive user hard-delete, like frozen ranks). Nothing reads events yet. `JobControl` gates each ingestion/settlement job by `enabled` + `min_interval_seconds`. UUID string PKs, timezone-aware `created_at`/`updated_at` on `BaseModel`.

Leagues are auto-populated (all ~1100, all `active=False`) by the daily `fetch_leagues` job; the admin ticks the handful to make active. Fixture ingestion (`fetch_fixtures`) loops over *active* leagues, topping each up to `N_FIXTURES_PER_LEAGUE` (throttled by `JobControl.min_interval_seconds` + the below-target count gate). `upsert_leagues` refreshes metadata only — it never touches `active`, so admin toggles survive in-place deploys.

The leagues migration is **additive only — it does NOT wipe fixtures/bets** (a startup-gated `DELETE` against a live ingestion writer caused an App Runner deploy to hang on locks → health-check timeout → rollback). Instead, old fixtures keep `league_id IS NULL` and `save_new_fixtures` backfills it in place on the next ingestion of that league (one row per `rapid_api_id`, no duplicates); the client board query hides leagueless fixtures (`Fixture.league_id IS NOT NULL`) so they stay off the board until healed and age out otherwise.

Football status codes drive settlement — see the `*_STATUSES` lists in `settings.py`.

## Endpoints

- `GET /client/fixture` (optional `search`, `league_id`), `GET /client/league` (active leagues only), `POST /client/bet`, `GET /client/bet`, `GET /client/me` — all require a Firebase `idToken` Bearer (`verify_token` / `get_current_user`). `/client/me` exposes the Firebase uid as `auth_uid` (was `cognito_uuid`). `/client/fixture` returns a `FixtureResponse` schema nesting `league: {id, display_name, logo} | null`; money fields (odds) serialize as **strings**.
- `POST /rapid-api/run-jobs` — requires header `X-Cron-Auth-Key: $CRON_AUTH_KEY`; runs due jobs from `JOB_REGISTRY`.
- `GET /health`, `/admin` (Google OIDC), `GET /auth/callback` (OIDC callback). Admin access requires the token's email to match `ADMIN_EMAIL` **and** the `email_verified` claim to be true.

## Conventions

- Public-surface methods wrap their body in `try/except` that logs (`logger.error`/`logger.exception`) then converts to `HTTPException`; internal helpers stay clean. Match this for new endpoints. Domain validation failures raise `ClientSideError` (in `client/queries.py`) → mapped to 400.
- Reads via ORM; bulk ingestion via `insert()`/`update()` statements.
- Fully typed — mypy is strict (`disallow_untyped_defs`). Keep new code annotated.

## Commands

Local venv (Python 3.12, no Docker needed for tests/typecheck) lives at `api/.venv`:

```bash
cd api
uv venv --python 3.12 .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt   # first time
.venv/bin/mypy --config-file mypy.ini    # CI gate — clean
.venv/bin/pytest -q                       # CI gate — unit + integration suite (SQLite, no DB needed)
```

`uv` is a local convenience for the Python 3.12 interpreter; CI (`dev-pr-checks.yml`) uses plain `pip install` on 3.12 and runs the same `mypy`/`pytest`. Either works — the `.venv/bin/...` commands are identical.

Format/lint via pre-commit: black (line-length 88, `api/src/` only) + ruff `--fix`. Run `pre-commit run --all-files`.

Local seed (dev-only, mock data, drives the real ingestion + settlement path — needs a local DB, e.g. `docker-compose up`):

```bash
cd api
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/bl_dev ENVIRONMENT=dev \
  ADMIN_SESSION_SECRET=x .venv/bin/python -m src.dev.seed all
# subcommands: fixtures | bets [--email <addr>] | resolve | streaks [--email <addr>] | emulator-user | all
```

`all` seeds an active seed league + 6 mock fixtures (with odds), places a spread of bets as a synthetic user, writes mock results, runs settlement, seeds a 3-week history of PAST settled cups (participation streak 3, profit streak 1), and prints per-bet outcomes + the entry balance before/after (proves WIN/LOSE/VOID). Idempotent (reserved `rapid_api_id` range + past-week cups skipped if present); refuses to run against a non-local DB. `streaks --email <addr>` gives an existing (e.g. Cognito) user the same past-cup history so their `/client/me` streaks render. Use it to give a local stack real data for smoke/verify.

Full stack (DB + API + auto-migrate + hot reload) via Docker — see `LOCAL_DEV.md`:

```bash
docker-compose up        # API on :8000, Postgres on :5432 (bl_dev / postgres:postgres)
```

Needs `RAPID_API_KEY`, `CRON_AUTH_KEY`, `ADMIN_SESSION_SECRET` in the environment (no `.env.example` committed). Auth runs against the **Firebase Auth emulator** (compose service `firebase-auth`, project `demo-brokelads`, port `9099`); compose sets `GOOGLE_CLOUD_PROJECT=demo-brokelads` + `FIREBASE_AUTH_EMULATOR_HOST=firebase-auth:9099` so `firebase_admin` accepts the emulator's unsigned tokens — **never set the emulator host in the cloud**. `LOCAL_ADMIN_BYPASS` waves you into `/admin` locally; to exercise the real Google OIDC login supply `ADMIN_GOOGLE_CLIENT_ID`/`ADMIN_GOOGLE_CLIENT_SECRET`. `DATABASE_URL`, `ADMIN_SESSION_SECRET`, and `CORS_ORIGINS` (comma-separated allowed origins) are hard-required (app raises on missing) — compose sets `CORS_ORIGINS` for localhost, Terraform sets it in the cloud.

Seed the emulator's e2e test user with `python -m src.dev.seed emulator-user` (also folded into `seed all`): creates the user from `E2E_TEST_EMAIL` (default `joshrobbinsukdev+test@gmail.com`) + `E2E_TEST_PASSWORD` (from `bl-fe/.env.e2e`, never hardcoded), idempotently, and only when the emulator host is set.

## Migrations

```bash
docker-compose exec api alembic revision --autogenerate -m "description"
docker-compose exec api alembic upgrade head    # also runs automatically on container start
```

## Deploy & branches

Default branch is `dev`. Runs on **GCP** — Cloud Run + Neon Postgres, provisioned by Terraform in `terraform/gcp/`; auth is **GCP Identity Platform (Firebase Auth)**, provisioned by the `terraform/modules/identity-platform` module the GCP stack instantiates (Google IdP + email/password, one account per email). GitHub Actions: PR→`dev` runs mypy+pytest (`dev-pr-checks.yml`); push→`dev` builds the image, pushes to Artifact Registry, and Terraform-applies the GCP dev stack (`gcp-deploy.yml`, **keyless via Workload Identity Federation** — WIF/state bucket live in the `tf_bootstrap` repo). That deploy also sets the FE's Vercel env vars (`vercel.tf`, the three `NEXT_PUBLIC_FIREBASE_*`) + fires the rebuild hook, so a redeploy re-wires the frontend with no manual step. `prod` (`terraform/gcp/prod`) is scaffolded but not yet wired for deploy. Feature branches: `feature/<slug>`.

**Deploying the Firebase-auth squash onto an existing DB**: the squashed initial migration reuses revision id `72b152bf1095` with different content, so any DB stamped with the old lineage must be wiped in the same window the deploy lands — drop the schema **including `alembic_version`** on Neon dev (users are wiped by design), and `docker compose down -v` locally. A stale stamp either crash-loops startup ("Can't locate revision") or silently believes it's at head with the old schema.

The retired AWS App Runner + RDS stack is archived under `terraform/aws/` (reference only; tag `aws-baseline`), alongside the retired Cognito stacks (`terraform/aws/cognito`, `terraform/aws/local`, `terraform/aws/modules/cognito`) — tear them down with the manual `cognito-teardown.yml` workflow after cloud verification. Full migration record: `terraform/GCP_MIGRATION.md`.

## Tests

`src/tests/` runs against an in-memory SQLite engine (a fresh one per test, see `conftest.py`) — no Postgres needed. `factories.py` builds entities. `unit_tests/` covers model properties/validators; `integration_tests/` covers `create_bet` rules and settlement (`settle_bet`/`settle_voided_bet`/`run_settle_bets`). `test_seed.py` drives the dev seeder through the real fixture/odds/results **parse+write** path (schemas → `save_new_fixtures`/`update_fixtures`) plus the full bet→settlement loop, so the ingestion parse seam is now covered from `.model_validate` inward. `src/tests/client/` covers the client routes through the FastAPI app, and the auth dependencies have unit tests (`test_firebase_auth.py`, `test_admin_auth.py`). Still uncovered: the admin UI and the *live* RapidAPI HTTP layer (`external_calls.py` is unmocked — the seeder fakes the response, not the transport).

## Known gaps
- `ADMIN_EMAIL` is hardcoded (`settings.py`) — fine for a demo, not for reuse.
- `functions/agent/main.py` is a stub handler.
- **Hard-delete user** (`accounts.delete_user`, wired to the SQLAdmin user list's delete button) removes the Firebase Auth account (`firebase_admin.auth.delete_user`) then cascade-deletes their DB rows (transactions → bets → cup entries → pundit usage → user) in one transaction. Needs Firebase Auth admin on the Cloud Run runtime SA (`roles/firebaseauth.admin`, granted in `terraform/gcp/modules/app`); locally it hits the Auth emulator. An auth account that is already absent isn't fatal — the DB rows still go and the admin gets a warning alert.
- **Cup betting is not concurrency-hardened** (accepted for friends-scale v1): `create_bet`'s balance-check-then-`entry.debit` isn't row-locked, so two truly-simultaneous bets on the same `CupEntry` could overspend it; and the `get_or_create` of a cup/entry can lose a race on the unique constraint, surfacing a transient 500 (rolls back cleanly, self-heals on retry). Harden with `SELECT … FOR UPDATE` + an `IntegrityError` retry if real concurrent load appears.
