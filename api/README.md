# BL API

FastAPI backend for BL project.

## Local Development

### Prerequisites
- Python 3.12+
- PostgreSQL database

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variable:
```bash
export DATABASE_URL="postgresql://username:password@localhost:5432/bl_dev"
```

3. Run migrations:
```bash
alembic upgrade head
```

4. Start the server:
```bash
uvicorn src.main:app --reload
```

API will be available at `http://localhost:8000`

## Project Structure

- `src/` application code
- `alembic/` database migrations
- `templates/` admin templates

## Type Checking and Tests

Tests run against in-memory SQLite (no Postgres needed). `src/tests/` has
`unit_tests/` (model properties and validators) and `integration_tests/`
(bet creation and settlement). Run from `api/` in a Python 3.12 env with
`requirements.txt` installed:

```bash
pytest                            # full suite
mypy --config-file mypy.ini       # type check
```

CI uses pip on 3.12; mypy can also run inside the container:
```bash
docker exec -w /app -it bl-api mypy --config-file /app/mypy.ini src
```

## Database Migrations

Create a new migration:
```bash
alembic revision --autogenerate -m "description"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback last migration:
```bash
alembic downgrade -1
```

## Docker

Build the image:
```bash
docker build -t bl-api .
```

Run the container:
```bash
docker run -p 8000:8000 -e DATABASE_URL="postgresql://..." bl-api
```

## API Endpoints

- `GET /health` - Health check
- `GET /client/fixture`, `POST /client/bet`, `GET /client/bet`, `GET /client/me` - client API (Cognito-authed)
- `POST /rapid-api/run-jobs` - runs due ingestion/settlement jobs (requires `X-Cron-Auth-Key`)
- `/admin` - SQLAdmin UI (Google OAuth); `GET /auth/google` is the OAuth callback
