"""Disposable PostgreSQL integration: 12 competing workers, 100 distinct jobs.

Requires TEST_DATABASE_URL. This suite intentionally never touches a live DB.
"""
import concurrent.futures
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from claimforge.core import Scheduler, FencedOut

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Requires disposable PostgreSQL TEST_DATABASE_URL")


def test_parallel_claims_and_reassignment():
    scheduler = Scheduler(URL)
    try:
        prefix = uuid.uuid4().hex
        count = 100
        workers = 12
        for index in range(count):
            scheduler.enqueue(f"{prefix}:{index}", "echo", {"index": index})

        barrier = Barrier(workers)
        started = time.perf_counter()
        def consume(index):
            client = Scheduler(URL, create_schema=False)
            claimed = []
            try:
                barrier.wait(timeout=20)
                while True:
                    lease = client.claim(f"worker-{index}", lease_seconds=20)
                    if lease is None:
                        break
                    client.complete(lease)
                    claimed.append(lease.id)
                return claimed
            finally:
                client.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            groups = list(pool.map(consume, range(workers)))
        elapsed = time.perf_counter() - started
        ids = [job_id for group in groups for job_id in group]
        assert len(ids) == count
        assert len(set(ids)) == count
        assert all(scheduler.get(job_id)["status"] == "completed" for job_id in ids)

        t0 = datetime.now(timezone.utc)
        identifier, _ = scheduler.enqueue(f"{prefix}:reclaimed", "echo", {}, now=t0)
        old = scheduler.claim("expired-worker", lease_seconds=1, now=t0)
        fresh = scheduler.claim("replacement-worker", lease_seconds=10, now=t0 + timedelta(seconds=2))
        assert old is not None and fresh is not None
        assert old.id == fresh.id == identifier
        with pytest.raises(FencedOut):
            scheduler.complete(old, now=t0 + timedelta(seconds=3))
        scheduler.complete(fresh, now=t0 + timedelta(seconds=3))
        assert scheduler.get(identifier)["status"] == "completed"
        evidence = {
            "scope": "PostgreSQL 16 on CI runner, 12 threads; completion is DB ACK only",
            "jobs_enqueued": count,
            "worker_threads": workers,
            "claims_completed": len(ids),
            "distinct_job_ids": len(set(ids)),
            "duplicate_job_claims": len(ids) - len(set(ids)),
            "worker_threads_with_claims": sum(bool(group) for group in groups),
            "elapsed_seconds": round(elapsed, 3),
            "stale_claim_rejected": True,
            "assertions_passed": True,
            "measurement_note": "Measured only after assertions on PostgreSQL; DB acknowledgement is not arbitrary job execution",
        }
        with open("postgres-evidence.json", "w", encoding="utf-8") as outfile:
            json.dump(evidence, outfile, indent=2, sort_keys=True)
        print("CLAIMFORGE_EVIDENCE=" + json.dumps(evidence, sort_keys=True), flush=True)
    finally:
        scheduler.close()


def test_concurrent_idempotent_submission():
    key = f"test-enqueue-{uuid.uuid4().hex}"
    def send(_):
        worker = Scheduler(URL, create_schema=False)
        try:
            return worker.enqueue(key, "echo", {"same": True})
        finally:
            worker.close()

    owner = Scheduler(URL)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(send, range(20)))
        assert len({job_id for job_id, _ in values}) == 1
        assert sum(int(created) for _, created in values) == 1
        assert owner.get(values[0][0])["status"] == "queued"
        evidence_path = "postgres-evidence.json"
        with open(evidence_path, "r", encoding="utf-8") as infile:
            evidence = json.load(infile)
        evidence["idempotent_parallel_submissions"] = len(values)
        evidence["idempotent_unique_jobs"] = len({job_id for job_id, _ in values})
        evidence["idempotent_actual_creations"] = sum(int(created) for _, created in values)
        with open(evidence_path, "w", encoding="utf-8") as outfile:
            json.dump(evidence, outfile, indent=2, sort_keys=True)
        print("CLAIMFORGE_IDEMPOTENCY=" + json.dumps({"submissions": len(values), "unique_jobs": 1, "new_jobs": 1}), flush=True)
    finally:
        owner.close()
