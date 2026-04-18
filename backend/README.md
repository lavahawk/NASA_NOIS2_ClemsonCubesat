# Backend Setup

This backend contains:

- a background worker that polls NASA FIRMS, normalizes hotspot rows, and writes them into PostGIS
- a FastAPI service that reads hotspot rows from `public.points` and serves `GET /v1/points`

## Docker Compose

The repository root contains a `docker-compose.yml` with three services:

- `db`: PostgreSQL 17 with PostGIS 3.5
- `worker`: the Python background worker from this backend
- `api`: the FastAPI read-only service for hotspot point queries

### Prerequisites

- Docker Desktop installed and running
- A valid NASA FIRMS map key

### Start The Stack

From the repository root:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and set `FIRMS_MAP_KEY`, then run:

```powershell
docker compose up --build
```

To run the stack in the background:

```powershell
docker compose up --build -d
```

The worker uses this internal database connection string:

```text
postgresql://fireuser:firepass@db:5432/firedb
```

You can override the default database settings with environment variables before running `docker compose up`:

```powershell
Copy-Item .env.example .env
notepad .env
```

### What Happens On Startup

When the worker starts, it automatically:

1. Connects to the PostGIS database.
2. Applies SQL migrations from `backend/migrations`.
3. Creates `public.schema_migrations` if needed.
4. Creates `public.points` and required indexes if they do not exist.
5. Begins polling FIRMS on the configured interval.

You do not need to manually create the schema before starting the stack.

### Useful Commands

Start only the database:

```powershell
docker compose up -d db
```

Start the database, worker, and API:

```powershell
docker compose up --build db worker api
```

View logs:

```powershell
docker compose logs -f worker
docker compose logs -f db
docker compose logs -f api
```

Stop the stack:

```powershell
docker compose down
```

Stop the stack and remove the database volume:

```powershell
docker compose down -v
```
