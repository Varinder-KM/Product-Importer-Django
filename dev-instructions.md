# Development Environment Setup

These steps assume a fresh machine with Python 3.11+ installed. The project uses `python -m venv` for virtual environments and loads configuration from `.env` via [`python-dotenv`](https://pypi.org/project/python-dotenv/).

## 1. Clone and bootstrap

```bash
git clone <your-fork-url>
cd product-importer-django
cp .env.example .env
```

Edit `.env` with your local credentials (see **Database** and **Redis** sections below).

Create a virtual environment (recommended):

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.\\.venv\\Scripts\\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

To install development extras:

```bash
pip install -r requirements-dev.txt
```

Create the upload directory structure (once per machine):

```bash
python scripts/setup_upload_dirs.py
```

The `Makefile` includes helper targets (POSIX shells). For example:

```bash
make setup-venv          # python -m venv .venv
make install-requirements
make migrate
make runserver
make run-celery-worker
```

On Windows you can run the equivalent commands manually (shown in comments within the `Makefile` steps above).

## 2. PostgreSQL

### Installation

- **Ubuntu/Debian:** `sudo apt update && sudo apt install postgresql postgresql-contrib`
- **macOS (Homebrew):** `brew install postgresql@14` (then follow brew caveats to start the service)
- **Windows (Chocolatey):** `choco install postgresql14` (launch StackBuilder or use pgAdmin to manage services)
- Official downloads: <https://www.postgresql.org/download/>

### Create database and user

```bash
psql -U postgres
```

Inside the `psql` prompt:

```sql
CREATE USER product_importer WITH PASSWORD 'change-me';
CREATE DATABASE product_importer OWNER product_importer;
GRANT ALL PRIVILEGES ON DATABASE product_importer TO product_importer;
```

Example DSN for `.env`:

```
DATABASE_URL=postgres://product_importer:change-me@localhost:5432/product_importer
```

## 3. Redis

- **Ubuntu/Debian:** `sudo apt install redis-server`
- **macOS (Homebrew):** `brew install redis`
- **Windows (Chocolatey):** `choco install redis-64`
- Documentation & binaries: <https://redis.io/docs/getting-started/installation/>

Start the Redis server (examples):

```bash
# Ubuntu/macOS (Homebrew services)
redis-server
# macOS with brew services
brew services start redis
# Windows (PowerShell, from install directory)
redis-server.exe
```

Set the connection string in `.env`:

```
REDIS_URL=redis://localhost:6379/0
```

## 4. Running the project

Once PostgreSQL and Redis are running and `.venv` is activated:

```bash
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/> to verify the server is running.

Celery worker (in a separate terminal):

```bash
celery -A config worker --loglevel=info
# or
./scripts/run_celery_worker.sh
```

### ASGI server (WebSockets)

For Channels/WebSocket support, run an ASGI server instead of `runserver`:

```bash
# Option 1
daphne config.asgi:application
# Option 2 (auto-reload)
uvicorn config.asgi:application --reload
```

### CSV import tuning

The importer streams CSV rows in batches (default `5,000`). Tweak `PRODUCT_IMPORT_BATCH_SIZE` in `.env` to balance throughput and memory:

```
PRODUCT_IMPORT_BATCH_SIZE=5000
```

Larger batches reduce COPY overhead but require more RAM; smaller batches provide more responsive progress updates.

### Bulk deletion

The UI (`/upload/`) includes a "Delete All Products" workflow. Configure thresholds in `.env`:

```
PRODUCT_BULK_DELETE_THRESHOLD=10000      # switch to async delete when record count exceeds this value
PRODUCT_DELETE_BATCH_SIZE=1000           # batch size for incremental deletes
PRODUCT_DELETE_TRUNCATE_THRESHOLD=200000 # use TRUNCATE when record count exceeds this
PRODUCT_DELETE_CONFIRM_PHRASE="DELETE ALL PRODUCTS"
```

For counts below the threshold, deletion happens synchronously. Above it, a Celery task runs in the background; progress is broadcast over WebSockets (with Redis) and can be monitored on the upload page or via `GET /api/products/deletion/<job_id>/progress/`.

Optional beat scheduler:

```bash
celery -A config beat --loglevel=info
```

## 5. Troubleshooting

- Ensure `.env` is present in the project root; `python-dotenv` loads it automatically in `config/settings.py`.
- If migrations fail, verify PostgreSQL credentials and that the user has permissions on the database.
- For Redis connection issues, make sure the Redis server is running and accessible at the host/port in `.env`.

