"""External smoke test of the Render read-only public showcase.

Run after the showcase has been deployed. No credentials and no job submissions.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "https://claimforge-showcase-olabs123.onrender.com"
TIMEOUT_SECONDS = 25


def request(path: str, method: str = "GET", data: bytes | None = None):
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers={"User-Agent": "ClaimForge-public-smoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read(65536).decode("utf-8"), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(4096).decode("utf-8"), dict(error.headers)


def main():
    for attempt in range(1, 9):
        try:
            status, raw, _ = request("/health")
            if status == 200 and json.loads(raw).get("status") == "ok":
                break
            print(f"Warmup attempt {attempt}: /health returned HTTP {status}")
        except Exception as exc:
            print(f"Warmup attempt {attempt}: {type(exc).__name__}: {exc}")
        if attempt == 8:
            raise RuntimeError("Live /health did not become healthy")
        time.sleep(8)

    status, raw, headers = request("/")
    assert status == 200 and "ClaimForge" in raw and "read-only" in raw.lower()
    assert headers.get("X-Frame-Options") == "DENY", headers

    status, raw, _ = request("/metrics")
    assert status == 200
    result = json.loads(raw)
    assert result["deployment_mode"] == "read-only engineering showcase"
    assert result["database_connected"] is False
    assert result["worker_running"] is False
    assert result["job_submissions_enabled"] is False
    assert result["metrics"]["unit_api_tests_passed"] == 13
    assert result["metrics"]["core_api_coverage_percent"] == 87.02
    assert result["metrics"]["duplicate_claims"] == 0
    assert result["metrics"]["distinct_jobs_acknowledged"] == 100

    # No credential ever provided, and no write endpoint exists on showcase.
    status, _, _ = request("/jobs", method="POST", data=b'{"kind":"echo"}')
    assert status == 404, f"POST /jobs unexpectedly returned {status}"
    status, _, _ = request("/stats")
    assert status == 404, f"Operational /stats unexpectedly returned {status}"
    status, _, _ = request("/jobs/1")
    assert status == 404, f"Operational job lookup unexpectedly returned {status}"

    summary = {
        "result": "passed",
        "target": BASE_URL,
        "health": 200,
        "homepage": 200,
        "metrics": 200,
        "jobs_post": 404,
        "jobs_get": 404,
        "stats_get": 404,
        "unit_api_tests": 13,
        "core_api_coverage_percent": 87.02,
        "note": "External HTTP smoke only; cannot establish production processing reliability",
    }
    print("LIVE_SHOWCASE_SMOKE=" + json.dumps(summary, sort_keys=True))
    with open("live-showcase-smoke.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
