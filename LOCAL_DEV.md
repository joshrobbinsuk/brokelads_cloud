# Local Development with Docker Compose

## Quick Start

1. **Start everything:**

   ```bash
   docker-compose up
   ```

2. **API will be available at:** `http://localhost:8000`

3. **Database connection:** `postgresql://postgres:postgres@localhost:5432/bl_dev`

## Creating Migrations

The API container volume-mounts your code, so you can create migrations from inside the container:

```bash
# Enter the API container
docker-compose exec api bash

# Create a migration
alembic revision --autogenerate -m "description"

# Exit
exit
```

---

docker-compose exec api alembic revision --autogenerate -m "initial migration"

The migration file will appear in `api/alembic/versions/` on your host machine.

## Useful Commands

**Stop everything:**

```bash
docker-compose down
```

**Rebuild API after code changes:**

```bash
docker-compose up --build
```

**View logs:**

```bash
docker-compose logs -f api
docker-compose logs -f db
```

**Access PostgreSQL directly:**

```bash
docker-compose exec db psql -U postgres -d bl_dev
```

**Reset database (WARNING: destroys data):**

```bash
docker-compose down -v
docker-compose up
```

## Environment

- PostgreSQL 16
- Database: `bl_dev`
- User: `postgres`
- Password: `postgres`
- API runs with `--reload` for hot reloading

## First Time Setup

1. Start services: `docker-compose up`
2. Wait for health check to pass
3. Migrations run automatically
4. Visit `http://localhost:8000` to see API

## Troubleshooting

**"Port 5432 already in use"**

- You have PostgreSQL running locally
- Stop it: `brew services stop postgresql` (macOS) or `sudo systemctl stop postgresql` (Linux)

**"Database connection failed"**

- Wait for health check to complete
- Check logs: `docker-compose logs db`

**API not reloading on code changes**

- The volume mount should handle this
- If not, rebuild: `docker-compose up --build`
