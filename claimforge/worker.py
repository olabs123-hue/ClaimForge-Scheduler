"""Local demo worker; external effects require handler-level idempotency."""
import argparse
import os
import time
from .core import Scheduler, FencedOut


def run_worker(db_url: str, name: str, iterations: int, poll_seconds: float = .1):
    store = Scheduler(db_url)
    try:
        for _ in range(iterations):
            store.reap_exhausted()
            job = store.claim(name, lease_seconds=30)
            if job is None:
                time.sleep(poll_seconds)
                continue
            try:
                if job.kind != "echo":
                    raise ValueError("Unsupported demo job type")
                print({"worker": name, "job_id": job.id, "payload": job.payload}, flush=True)
                store.complete(job)
            except FencedOut:
                print("Lost lease ownership; completion rejected", flush=True)
            except Exception as exc:
                try:
                    store.fail(job, str(exc))
                except FencedOut:
                    pass
    finally:
        store.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--worker-id", required=True)
    p.add_argument("--iterations", type=int, default=100)
    args = p.parse_args()
    run_worker(os.getenv("DATABASE_URL", "sqlite:///./claimforge.db"), args.worker_id, args.iterations)
