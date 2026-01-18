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

Run mypy inside the running container:
```bash
docker exec -w /app -it bl-api mypy --config-file /app/mypy.ini src
```

Run pytest locally (from `bl/api` on your host machine):
```bash
pytest
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

- `GET /` - Root endpoint
- `GET /health` - Health check endpoint
