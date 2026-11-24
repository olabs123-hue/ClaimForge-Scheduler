# Production deployment runbook (Render)

**Current deployment status:** not deployed. The GitHub Actions tests are verified, but production security requires additional operational safeguards and the Render workspace must be confirmed.

## Minimum deployment plan
1. In the correct Render workspace, provision a dedicated PostgreSQL 16+ database with a nonpublic connection string. Do not put database URLs in Git.
2. Create a Render Docker web service from this repository, bound to its default `main` branch. The Dockerfile starts Uvicorn on port 8000.
3. Set `CLAIMFORGE_ENV=production`, `DATABASE_URL=postgresql+psycopg://...`, and `CLAIMFORGE_API_KEY` to a **random, secret string of at least 32 characters**. Use Render's secret environment-variable storage; never commit secrets.
4. Configure TLS, HTTP-to-HTTPS redirection, and strict firewall/network policies at the platform edge. Use Render `/health` as the liveness path.
5. Public `/health` may return `200`; requests to `/jobs`, `/jobs/{id}`, `/stats` without the `X-API-Key` header must return `401`.
6. Set up a separate managed worker process with the same private `DATABASE_URL`, not the web service. If a background worker plan is unavailable, **do not describe the deployment as an operating scheduler**; it is an API-only staging surface.
7. Enable logs without request headers, audit records for administrative events, backups, restore tests, rate limiting, alerting, resource limits, and secret rotation before using it for sensitive or real workloads.
8. Rotate database and API credentials upon compromise. Use a managed secrets manager and least-privilege database roles.
9. Follow the project's passing GitHub Actions checks; a passing unit test alone does not establish that a live deployment is hardened.

## Required application settings
| Variable | Meaning |
|---|---|
| `CLAIMFORGE_ENV` | `production` to fail closed |
| `CLAIMFORGE_API_KEY` | 32+ character secret; required for operational routes |
| `DATABASE_URL` | Private PostgreSQL SQLAlchemy URL |
| `PORT` | Injected by platform if applicable |

## Security limits
This project is a technical demonstration, **not independently security-audited for production**. API keys provide a single shared credential without distinct users, expiry, RBAC or audit attribution. `X-API-Key` should only travel over HTTPS; keep it out of logs, analytics and screenshots. Per-client rate limiting and resilient HTTP body-stream caps belong at the reverse proxy. External side effects still require idempotent handlers; a database claim token doesn't imply exactly-once actions elsewhere.

## Validation after deployment
```bash
# No secret in this request:
curl -i https://YOUR-SERVICE.onrender.com/health

# Should fail closed with HTTP 401:
curl -i https://YOUR-SERVICE.onrender.com/stats
curl -i -X POST https://YOUR-SERVICE.onrender.com/jobs -H 'Content-Type: application/json' \
  -d '{"idempotency_key":"probe","kind":"echo","payload":{}}'
```

The command above must not create a job without a key. Run authenticated checks only from an authorized environment and keep test data synthetic.
