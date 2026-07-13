# Bristol Regional Food Network - DESD Resit

This repository contains the combined resit implementation of the Bristol Regional Food Network digital marketplace. It merges the broad marketplace functionality from `DESD-BRFN` with the Docker, Nginx, and Django REST Framework ideas from `g10-bristol-food-network-main`.

The system supports producers, individual customers, community groups, restaurants, and administrators. It includes product management, multi-vendor checkout, order tracking, recurring orders, surplus discounts, traceability, reviews, recipes, food miles, settlements, commission reporting, background jobs, and a REST API.


## Architecture

- Django 6 and Django REST Framework
- PostgreSQL 15
- Redis 7
- Celery worker and Celery Beat scheduler
- Gunicorn application server
- Docker Compose multi-container environment
- Optional Nginx reverse proxy and optional ML service
- Stripe test mode or local mock checkout only

## Prerequisites

Install the following before setup:

1. Docker Desktop with Docker Compose
2. Git


## Step-by-step Docker setup

### 1. Clone the repository

```bash
git clone https://github.com/ATCLanC3r/DESD.git
cd DESD
```

If the project was supplied as a ZIP, extract it and open a terminal in the folder containing `docker-compose.yml`.

### 2. Create the environment file

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

The defaults are suitable for a local demonstration. Before any public deployment, replace `DJANGO_SECRET_KEY` and `DB_PASSWORD` with long random values.

Stripe keys are optional. If supplied, they must begin with `pk_test_` and `sk_test_`. Never use live payment keys or real card details.

### 3. Build and start the full project

```bash
docker compose up --build
```

On the first run, Docker will:

1. Download PostgreSQL and Redis images.
2. Build the Django image.
3. Apply all database migrations.
4. Collect static files.
5. Create demonstration users, producers, products, recipes, and stories.
6. Start Django, PostgreSQL, Redis, Celery, and Celery Beat.

The first start can take several minutes. Wait until the `web` service reports that Gunicorn is listening on port 8000.

To run in the background instead:

```bash
docker compose up --build -d
docker compose ps
```

All five default services should show as running, and `web`, `db`, and `redis` should show as healthy.

### 4. Open the application

| Service | Address |
|---|---|
| Marketplace | http://localhost:8000/ |
| Product catalogue | http://localhost:8000/pt/products/ |
| REST API health | http://localhost:8000/api/health/ |
| REST API products | http://localhost:8000/api/products/ |
| Django admin | http://localhost:8000/admin/ |

### 5. Use the demonstration accounts

All seeded demonstration accounts use this password:

```text
DemoPass!2026
```

| Role | Example username |
|---|---|
| Producer | `demo_producer1` |
| Individual customer | `demo_customer1` |
| Community group | `demo_community2` |
| Restaurant | `demo_restaurant3` |
| Administrator | `demo_admin` |

These credentials are for local assessment demonstrations only.

### 6. Verify the running system

```bash
docker compose ps
docker compose logs --tail=100 web
```

The health endpoint should return:

```json
{"status":"ok","service":"brfn-marketplace"}
```

### 7. Run the automated tests

The automated suite uses an isolated SQLite test database and does not alter the Docker PostgreSQL data:

```bash
docker compose run --rm \
  -e RUN_MIGRATIONS=false \
  -e SEED_DEMO_DATA=false \
  -e USE_SQLITE=true \
  -e USE_REDIS_CACHE=false \
  web python manage.py test
```

Windows PowerShell single-line version:

```powershell
docker compose run --rm -e RUN_MIGRATIONS=false -e SEED_DEMO_DATA=false -e USE_SQLITE=true -e USE_REDIS_CACHE=false web python manage.py test
```

### 8. Stop the project

```bash
docker compose down
```

To delete local database and cache volumes and start with fresh demo data:

```bash
docker compose down -v
docker compose up --build
```

The `-v` command permanently removes local Docker data, so do not use it when records must be retained.

## Optional services

Run the Nginx reverse proxy on port 8080:

```bash
docker compose --profile proxy up -d nginx
```

Run the optional ML recommendation service on port 8001:

```bash
docker compose --profile ml up --build -d ml-service
```

The core marketplace does not require either optional profile.

## Useful commands

```bash
# Follow Django logs
docker compose logs -f web

# Open a Django shell
docker compose exec web python manage.py shell

# Apply migrations manually
docker compose exec web python manage.py migrate

# Create another administrator
docker compose exec web python manage.py createsuperuser

# Re-run seed commands only if required
docker compose exec web python manage.py seed_products2

# Check configuration
docker compose exec web python manage.py check
```

## REST API

Public read endpoints:

- `GET /api/health/`
- `GET /api/categories/`
- `GET /api/products/`
- `GET /api/products/?search=carrot`
- `GET /api/products/?category=vegetables&organic=true&available=true`

Authenticated endpoints:

- `GET /api/orders/` - returns only the logged-in customer's orders
- `GET /api/producer-orders/` - returns only the logged-in producer's paid orders
- `POST /api/products/` - producer accounts only
- `PATCH /api/products/{id}/` - owning producer only

## Payment testing

The default setup works without Stripe credentials and must be demonstrated with mock/test data. If Stripe test mode is configured, use Stripe's test card `4242 4242 4242 4242`, any future expiry date, and any three-digit CVC. Never enter real financial information.

## Troubleshooting

### Port 8000 is already in use

Stop the conflicting application or change the web mapping in `docker-compose.yml` from `8000:8000` to `8002:8000`, then open http://localhost:8002/.

### Docker services do not become healthy

```bash
docker compose ps
docker compose logs db
docker compose logs web
```

Check that Docker Desktop has enough memory and that `.env` contains matching database values.

### Database schema errors after pulling changes

```bash
docker compose exec web python manage.py migrate
```

## Assessment documents

- [Test-case coverage](docs/TEST_CASE_COVERAGE.md)
- [Links and implemented test cases](LINKS_AND_TEST_CASES.md)