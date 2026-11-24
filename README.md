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
# Local-only development secret: local-dev-key-do-not-use-in-production
# curl -H 'X-API-Key: local-dev-key-do-not-use-in-production' http://localhost:8000/stats
```

## Test
```bash
python -m pip install -r requirements.txt pytest-cov
python -m pytest -q tests/test_core.py --cov=claimforge.core --cov=claimforge.api --cov-report=term-missing
# With a disposable PostgreSQL database:
TEST_DATABASE_URL=postgresql+psycopg://claimforge:claimforge@localhost:5432/claimforge_test python -m pytest -s -q tests/test_postgres_concurrency.py
```

## Verified GitHub Actions results

[![ClaimForge CI](https://github.com/olabs123-hue/ClaimForge-Scheduler/actions/workflows/ci.yml/badge.svg)](https://github.com/olabs123-hue/ClaimForge-Scheduler/actions/workflows/ci.yml)

The [passing CI run](https://github.com/olabs123-hue/ClaimForge-Scheduler/actions/runs/45395943869) on a GitHub-hosted Ubuntu runner verified:
- **10 passing unit/API tests**, **90.75% core/API coverage**, **4 API routes**.
- **2 passing PostgreSQL 16 integration tests** with a disposable database.
- **12 concurrent worker threads** completed **100 distinct job acknowledgements**, **0 duplicate claims**; every worker thread claimed at least one job.
- **20 concurrent idempotent submissions** resulted in **1 unique job** and **1 actual creation**.
- An expired lease token was rejected after reassignment.
- The 100-job worker test measured **0.264 s** on this runner. This is a short, synthetic DB-ack test, **not** production throughput or an exactly-once external processing guarantee.

See [machine-readable metrics](VERIFIED_CI_METRICS.json) and the CI run's uploaded unit-coverage and PostgreSQL artifacts for original evidence.

## Scope and cautions
This is an educational, independently developed service. Not Sharp Technologies proprietary code and not evidence of performance during employment. No authentication, hardened ingress or external execution sandbox; do not deploy it publicly with write endpoints or put real user data in it. Claim-token fencing protects database acknowledgements, **not external side effects**; handlers must be idempotent. The API uses a mandatory `X-API-Key` for operational endpoints and is appropriate only for authenticated staging until additional operational safeguards have been validated; the worker supports a predefined `echo` task. See [deployment and security runbook](DEPLOYMENT.md). SQLite may be used for unit tests but does not validate PostgreSQL locking.
