"""Local-only educational API. No authentication: do NOT expose publicly."""
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .core import Scheduler

app = FastAPI(title="ClaimForge Scheduler", version="0.1", description="Local development only; no authentication")


def get_scheduler() -> Scheduler:
    if not hasattr(app.state, "scheduler"):
        app.state.scheduler = Scheduler(os.getenv("DATABASE_URL", "sqlite:///./claimforge.db"))
    return app.state.scheduler


class EnqueueRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=80)
    payload: dict
    max_attempts: int = Field(default=3, ge=1, le=20)


@app.get("/health")
def health():
    return {"status": "ok", "scope": "local-educational"}


@app.post("/jobs", status_code=201)
def create_job(req: EnqueueRequest):
    try:
        job_id, created = get_scheduler().enqueue(req.idempotency_key, req.kind, req.payload, max_attempts=req.max_attempts)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job_id": job_id, "created": created}


@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    try:
        return get_scheduler().get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/stats")
def stats():
    return get_scheduler().stats()
