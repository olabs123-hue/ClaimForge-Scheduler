"""Read-only public showcase. No database connection, worker, or job mutations."""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app = FastAPI(title="ClaimForge Engineering Showcase", docs_url=None, redoc_url=None, openapi_url=None)
REPO = "https://github.com/olabs123-hue/ClaimForge-Scheduler"
CI = "https://github.com/olabs123-hue/ClaimForge-Scheduler/actions/runs/45397446865"

EVIDENCE = {
    "product": "ClaimForge",
    "deployment_mode": "read-only engineering showcase",
    "database_connected": False,
    "worker_running": False,
    "job_submissions_enabled": False,
    "github_repository": REPO,
    "verified_ci_run": "https://github.com/olabs123-hue/ClaimForge-Scheduler/actions/runs/45397446865",
    "metrics": {
        "unit_api_tests_passed": 13,
        "postgresql_integration_tests_passed": 2,
        "core_api_coverage_percent": 87.02,
        "concurrent_worker_threads": 12,
        "distinct_jobs_acknowledged": 100,
        "duplicate_claims": 0,
        "parallel_idempotent_submissions": 20,
        "unique_jobs_created": 1,
        "stale_lease_rejection": True,
    },
    "limitations": "Synthetic GitHub Actions tests; database acknowledgements are not proof of exactly-once external processing or a production throughput claim.",
}

@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
    response.headers["Cache-Control"] = "public, max-age=60"
    return response

@app.get("/health")
def health():
    return {"status": "ok", "mode": "showcase", "database_connected": False}

@app.get("/metrics")
def metrics():
    return EVIDENCE

@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ClaimForge — Systems Reliability</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#0c1018;color:#f1f5fb}main{max-width:1060px;margin:0 auto;padding:70px 28px 90px}header{display:flex;align-items:center;justify-content:space-between;gap:16px}.mark{font-weight:800;letter-spacing:-.05em;font-size:23px}.eyebrow{font-size:12px;letter-spacing:.17em;text-transform:uppercase;color:#8bb9ff;font-weight:700}.status{font-size:12px;border:1px solid #476088;border-radius:30px;padding:8px 12px;color:#b5d2ff}h1{font-size:clamp(43px,8vw,82px);letter-spacing:-.065em;line-height:1.03;max-width:930px;margin:79px 0 22px}p{color:#aebacb;line-height:1.65;font-size:17px;max-width:740px}.actions{display:flex;gap:12px;flex-wrap:wrap;margin:34px 0 62px}a{color:inherit;text-decoration:none}.btn{padding:14px 18px;border-radius:10px;border:1px solid #3e5069;font-weight:650}.primary{background:#cbe2ff;color:#12243b;border-color:#cbe2ff}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}.metric{padding:25px 20px;border:1px solid #2c3748;background:#141b27;border-radius:15px}.num{font-size:36px;letter-spacing:-.05em;font-weight:800}.metric small{display:block;color:#98a8c0;margin-top:8px;line-height:1.5}.line{margin:52px 0;border-top:1px solid #293648}.cols{display:grid;grid-template-columns:1fr 1fr;gap:30px}.cols h2{font-size:21px;letter-spacing:-.025em}ul{color:#aebacb;line-height:2;padding-left:21px}.notice{margin-top:45px;padding:19px 23px;background:#162131;border:1px solid #2c456a;border-radius:12px;color:#bdcde4;line-height:1.7}code{font-size:.9em;color:#cce2ff}@media(max-width:700px){main{padding:34px 19px 60px}h1{margin-top:55px}.metrics{grid-template-columns:repeat(2,1fr)}.cols{grid-template-columns:1fr}.num{font-size:29px}}</style></head><body><main>
<header><div class="mark">ClaimForge<span style="color:#9bbfff">.</span></div><div class="status">Read-only verification showcase</div></header>
<h1>Concurrency tested.<br>Failures anticipated.</h1>
<p>ClaimForge is a PostgreSQL-backed job scheduler implementing transactional <code>SKIP LOCKED</code> claims, lease renewal, claim-token fencing, idempotent submission and bounded retries.</p>
<div class="actions"><a class="btn primary" href="https://github.com/olabs123-hue/ClaimForge-Scheduler">View source on GitHub ↗</a><a class="btn" href="https://github.com/olabs123-hue/ClaimForge-Scheduler/actions/runs/45397446865">Inspect passing CI ↗</a><a class="btn" href="/metrics">Machine-readable metrics ↗</a></div>
<div class="eyebrow" style="margin-bottom:18px">Verified in GitHub Actions</div>
<div class="metrics"><div class="metric"><div class="num">12</div><small>Concurrent worker threads</small></div><div class="metric"><div class="num">100</div><small>Distinct job DB acknowledgements</small></div><div class="metric"><div class="num">0</div><small>Duplicate job claims</small></div><div class="metric"><div class="num">87.02%</div><small>Core / API test coverage</small></div></div>
<div class="line"></div><div class="cols"><section><h2>Reliability primitives</h2><ul><li>PostgreSQL <code>FOR UPDATE SKIP LOCKED</code></li><li>Lease renewal and expiration</li><li>Fencing of stale worker acknowledgements</li><li>Idempotent submission under contention</li><li>Bounded retries and dead-job transitions</li></ul></section><section><h2>Reproducible evidence</h2><ul><li>Unit/API and PostgreSQL integration suites</li><li>20 competing submissions → 1 unique job</li><li>Expired-token rejection tested</li><li>Docker Compose for local API and worker</li><li>CI artifacts and metrics available on GitHub</li></ul></section></div>
<div class="notice"><strong>Deployment boundary.</strong> This page is a read-only showcase. No database or worker is connected to this public site, and job submission is disabled. All metrics are synthetic CI test results on a GitHub-hosted runner, not production throughput or exactly-once external execution guarantees.</div>
</main></body></html>"""
