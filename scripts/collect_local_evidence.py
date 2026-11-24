"""Collect route and coverage facts from a passing pytest run."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
from claimforge.api import app

coverage = json.loads(Path("coverage.json").read_text())
paths = sorted({r.path for r in app.routes if hasattr(r, "methods")
    and r.path not in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}})
result = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "Core and API modules only; local SQLite unit/API tests, not PostgreSQL concurrency",
    "api_route_count": len(paths),
    "api_paths": paths,
    "covered_percent": round(coverage["totals"]["percent_covered"], 2),
    "coverage_modules": ["claimforge/core.py", "claimforge/api.py"],
    "postgreSQL_concurrency_verified": False,
    "source": "coverage.json from test runner, after passing pytest",
}
Path("LOCAL_TEST_EVIDENCE.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
