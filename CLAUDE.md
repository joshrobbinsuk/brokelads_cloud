# brokelads_cloud — backend

FastAPI + PostgreSQL backend for the BrokeLads sports-betting demo. Ingests football fixtures/odds from API-Football (RapidAPI), lets authenticated users place and settle bets, and ships to AWS via Terraform. Frontend lives in the sibling `bl-fe` repo — see `../CLAUDE.md` for how they run together.

## Layout (`api/src/`)

Three feature packages, each a deep module with a thin surface:
- `client/` — public REST API (`/client/*`), Cognito-authed. `routes.py` is the surface; `queries.py` holds DB logic, `schemas.py` the Pydantic I/O, `utils/{cognito,user}.py` the auth dependencies.
- `rapid_api/` — data ingestion + bet settlement jobs. `routes.py` exposes one cron-authed endpoint; `runner.py` orchestrates, `jobs.py` holds the `JOB_REGISTRY`, `external_calls.py` hits API-Football, `schemas/` parses its responses.
- `admin/` — SQLAdmin UI behind Google OAuth (`auth.py`), model views (`admin_views.py`), manual job triggers (`rapid_api_admin.py`).

Shared: `main.py` (app + router wiring), `models.py` (all SQLAlchemy models), `database.py` (`BaseModel`, engine, `get_db`), `settings.py` (env + domain constants), `utils/logging.py` (loguru).

## Data model (`models.py`)

`User` (balance defaults 100.00, `status` ACTIVE/DISABLED/INVITED) → `Bet` (choice HOME/AWAY/DRAW, `outcome` UNDECIDED/WON/LOST/VOIDED) → `Fixture` (kick-off, odds, goals, `outcome` property). `TransactionRecord` audits balance changes; `JobControl` gates each ingestion/settlement job by `enabled` + `min_interval_seconds`. UUID string PKs, timezone-aware `created_at`/`updated_at` on `BaseModel`.

Football status codes drive settlement — see the `*_STATUSES` lists in `settings.py`.

## Endpoints

- `GET /client/fixture`, `POST /client/bet`, `GET /client/bet`, `GET /client/me` — all require a Cognito `idToken` Bearer (`verify_token` / `get_current_user`).
- `POST /rapid-api/run-jobs` — requires header `X-Cron-Auth-Key: $CRON_AUTH_KEY`; runs due jobs from `JOB_REGISTRY`.
- `GET /health`, `/admin` (Google OAuth), `GET /auth/google` (OAuth callback).

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

Full stack (DB + API + auto-migrate + hot reload) via Docker — see `LOCAL_DEV.md`:

```bash
docker-compose up        # API on :8000, Postgres on :5432 (bl_dev / postgres:postgres)
```

Needs `RAPID_API_KEY`, `CRON_AUTH_KEY`, `ADMIN_SESSION_SECRET`, `GOOGLE_CLIENT_*` in the environment (no `.env.example` committed). `DATABASE_URL` and `ADMIN_SESSION_SECRET` are hard-required (app raises on missing).

## Migrations

```bash
docker-compose exec api alembic revision --autogenerate -m "description"
docker-compose exec api alembic upgrade head    # also runs automatically on container start
```

## Deploy & branches

Default branch is `dev`. GitHub Actions: PR→`dev` runs mypy+pytest (`dev-pr-checks.yml`); push→`dev` builds the image and Terraform-applies to the dev AWS env (`dev.yml`); merge→`main` → prod. Feature branches: `feature/<slug>`.

## Tests

`src/tests/` runs against an in-memory SQLite engine (a fresh one per test, see `conftest.py`) — no Postgres needed. `factories.py` builds entities. `unit_tests/` covers model properties/validators; `integration_tests/` covers `create_bet` rules and settlement (`settle_bet`/`settle_voided_bet`/`run_settle_bets`). Still uncovered: the FastAPI routes/auth dependencies, the admin UI, and the RapidAPI ingestion path (`external_calls.py` is unmocked).

## Known gaps
- `ADMIN_EMAIL` and the Cognito client/pool IDs are hardcoded (`settings.py`, `docker-compose.yml`) — fine for a demo, not for reuse.
- `functions/agent/main.py` is a stub handler.
