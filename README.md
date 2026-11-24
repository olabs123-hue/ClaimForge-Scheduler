# ClaimForge — PostgreSQL Job Scheduler

Independent backend-engineering demonstration built with Python, FastAPI, SQLAlchemy and PostgreSQL.

## Features
- Transactional job claims using PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`.
- Lease expiry, renewal, claim-token fencing, bounded retries, exhausted-job cleanup.
- Idempotent submission with unique keys and request-payload consistency checks.
- Four documented HTTP routes: `GET /health`, `POST /jobs`, `GET /jobs/{job_id}`, `GET /stats`.
- Docker Compose API, PostgreSQL 16 and worker services.
- GitHub Actions for unit tests, coverage and disposable-PostgreSQL concurrency tests.

## Run locally
```bash
docker compose up --build
# API docs: http://localhost:8000/docs
```

## Test
```bash
python -m pip install -r requirements.txt pytest-cov
python -m pytest -q tests/test_core.py --cov=claimforge.core --cov=claimforge.api --cov-report=term-missing
# With a disposable PostgreSQL database:
TEST_DATABASE_URL=postgresql+psycopg://claimforge:claimforge@localhost:5432/claimforge_test python -m pytest -s -q tests/test_postgres_concurrency.py
```

Local verification previously produced **10 passing tests**, **90.75% core/API coverage**, and **4 API routes**. Those numbers describe a local unit/API run. **Do not claim database concurrency results until the PostgreSQL GitHub Actions job passes.** The Postgres test targets 12 workers and 100 jobs plus 20 concurrent submissions, and emits an evidence JSON file only after assertions pass.

## Scope and cautions
This is an educational, independently developed service. Not Sharp Technologies proprietary code and not evidence of performance during employment. No authentication, hardened ingress or external execution sandbox; do not deploy it publicly with write endpoints or put real user data in it. Claim-token fencing protects database acknowledgements, **not external side effects**; handlers must be idempotent. The API is local-only; the worker only supports a predefined `echo` task. SQLite may be used for unit tests but does not validate PostgreSQL locking.
