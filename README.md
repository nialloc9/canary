# Canary

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose

## Development

Copy the dev environment file and fill in any missing values:

```bash
cp .env.dev .env.dev.local   # optional — .env.dev has safe defaults for local dev
```

Start the stack (Postgres + backend with hot-reload):

```bash
docker compose up --build
```

| Service  | URL                     |
|----------|-------------------------|
| Backend  | http://localhost:8000   |
| Postgres | localhost:5432          |

The backend source is mounted as a volume so code changes reload automatically without rebuilding the image.

To stop and remove containers:

```bash
docker compose down
```

To also remove the Postgres volume (wipes all local DB data):

```bash
docker compose down -v
```

## Environment variables

`.env.dev` is read by Docker Compose at startup. Key variables:

| Variable              | Description                          |
|-----------------------|--------------------------------------|
| `POSTGRES_USER`       | Postgres username                    |
| `POSTGRES_PASSWORD`   | Postgres password                    |
| `POSTGRES_DB`         | Postgres database name               |
| `DATABASE_URL`        | Full async connection string         |
| `SECRET_KEY`          | JWT signing secret                   |
| `ANTHROPIC_API_KEY`   | Anthropic API key                    |
| `ANTHROPIC_MODEL`     | Claude model ID                      |
| `CORS_ORIGINS`        | Allowed frontend origins (JSON list) |

## Production

Production uses a second Compose override file. The backend image is built with code baked in (no volume mount), and Postgres is replaced by a managed database. The frontend is deployed to S3 separately.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Set production secrets in `.env.prod` before running. At minimum update:

- `DATABASE_URL` — point at your managed Postgres (e.g. RDS)
- `SECRET_KEY` — use a strong random value
- `ANTHROPIC_API_KEY` — production API key

## Frontend

The frontend is a Vite + React app under `frontend/`. In development it can be run locally:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

In production it is built and deployed to S3 (not run as a container).

## Init script

To seed a test account and connect integrations (GitHub, Snowflake), see [`scripts/init/README.md`](scripts/init/README.md).
