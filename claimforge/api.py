"""Authenticated ClaimForge API.

Operational API is private by default: set a long, random CLAIMFORGE_API_KEY for
/job and /stats routes. For public demos expose only /health without credentials.
Use TLS at the ingress; this application does not terminate HTTPS itself.
"""
import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from .core import Scheduler

PRODUCTION = os.getenv("CLAIMFORGE_ENV", "development").lower() == "production"
API_KEY = os.getenv("CLAIMFORGE_API_KEY", "")
if PRODUCTION:
    if len(API_KEY) < 32:
        raise RuntimeError("Production requires CLAIMFORGE_API_KEY of at least 32 characters")
    if not os.getenv("DATABASE_URL", "").startswith(("postgresql+psycopg://", "postgresql://")):
        raise RuntimeError("Production requires a PostgreSQL DATABASE_URL")

app = FastAPI(
    title="ClaimForge Scheduler",
    version="0.2",
    description="Private operational API with public liveness health check",
    docs_url=None if PRODUCTION else "/docs",
    redoc_url=None,
    openapi_url=None if PRODUCTION else "/openapi.json",
)

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Hard limit on request body size; also enforce limits at the reverse proxy.
    if request.headers.get("content-length"):
        try:
            size = int(request.headers["content-length"])
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        if size > 65536:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def require_key(x_api_key: str | None = Header(default=None)):
    if not API_KEY or x_api_key is None or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


def get_scheduler() -> Scheduler:
    if not hasattr(app.state, "scheduler"):
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            if PRODUCTION:
                raise RuntimeError("Production database unavailable")
            db_url = "sqlite:///./claimforge.db"
        app.state.scheduler = Scheduler(db_url)
    return app.state.scheduler


class EnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9:_\\-]+$")
    kind: str = Field(pattern=r"^echo$")
    payload: dict = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=20)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", status_code=201, dependencies=[Depends(require_key)])
def create_job(req: EnqueueRequest):
    try:
        job_id, created = get_scheduler().enqueue(req.idempotency_key, req.kind, req.payload, max_attempts=req.max_attempts)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job_id": job_id, "created": created}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_key)])
def get_job(job_id: int):
    try:
        return get_scheduler().get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/stats", dependencies=[Depends(require_key)])
def stats():
    return get_scheduler().stats()
