"""Transactional jobs with lease expiry, retries and claim-token fencing.

PostgreSQL claims use SELECT ... FOR UPDATE SKIP LOCKED.
SQLite is supported for unit tests; SQLite does not validate multi-worker claims.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[str | None] = mapped_column(String(64))
    worker_id: Mapped[str | None] = mapped_column(String(100))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


@dataclass(frozen=True)
class Lease:
    id: int
    kind: str
    payload: dict[str, Any]
    claim_token: str
    worker_id: str
    attempts: int
    lease_until: datetime


class FencedOut(RuntimeError):
    """Token no longer owns the job; must not commit side effects."""


class Scheduler:
    def __init__(self, url: str, *, create_schema: bool = True):
        self.engine = create_engine(url, pool_pre_ping=True)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        if create_schema:
            Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def enqueue(self, key: str, kind: str, payload: dict, *, max_attempts: int = 3, now: datetime | None = None) -> tuple[int, bool]:
        if not (1 <= len(key) <= 120 and 1 <= len(kind) <= 80 and 1 <= max_attempts <= 20):
            raise ValueError("Invalid key, type or retry limit")
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")
        now = now or utcnow()
        with self.Session.begin() as db:
            stmt = select(Job).where(Job.idempotency_key == key)
            existing = db.scalar(stmt)
            if existing:
                if existing.kind != kind or existing.payload != payload or existing.max_attempts != max_attempts:
                    raise ValueError("Idempotency key reused with different request")
                return existing.id, False
            job = Job(idempotency_key=key, kind=kind, payload=payload, max_attempts=max_attempts, available_at=now, created_at=now, updated_at=now)
            if self.engine.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
                inserted_id = db.scalar(insert(Job).values(idempotency_key=key, kind=kind, payload=payload, status="queued", attempts=0, max_attempts=max_attempts, available_at=now, created_at=now, updated_at=now).on_conflict_do_nothing(index_elements=[Job.idempotency_key]).returning(Job.id))
                stored = db.scalar(stmt)
                if stored.kind != kind or stored.payload != payload or stored.max_attempts != max_attempts:
                    raise ValueError("Idempotency key reused with different request")
                return stored.id, inserted_id is not None
            db.add(job)
            db.flush()
            return job.id, True

    def claim(self, worker_id: str, *, lease_seconds: int = 30, now: datetime | None = None) -> Lease | None:
        if not (1 <= len(worker_id) <= 100 and 1 <= lease_seconds <= 3600):
            raise ValueError("Invalid worker or lease")
        now = now or utcnow()
        with self.Session.begin() as db:
            eligible = or_(
                (Job.status == "queued") & (Job.available_at <= now),
                (Job.status == "leased") & (Job.lease_until <= now),
            )
            stmt = select(Job).where(eligible, Job.attempts < Job.max_attempts).order_by(Job.available_at, Job.id).limit(1)
            if db.bind.dialect.name == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
            job = db.scalar(stmt)
            if job is None:
                return None
            token = secrets.token_hex(16)
            job.claim_token = token
            job.worker_id = worker_id
            job.status = "leased"
            job.attempts += 1
            job.lease_until = now + timedelta(seconds=lease_seconds)
            job.updated_at = now
            db.flush()
            return Lease(job.id, job.kind, job.payload, token, worker_id, job.attempts, job.lease_until)

    def _fenced_update(self, db: Session, lease: Lease, values: dict, *, now: datetime) -> None:
        result = db.execute(update(Job).where(Job.id == lease.id, Job.claim_token == lease.claim_token, Job.worker_id == lease.worker_id, Job.status == "leased", Job.lease_until > now).values(**values, updated_at=now).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise FencedOut("Claim expired, was reassigned or token is invalid")

    def renew(self, lease: Lease, *, lease_seconds: int = 30, now: datetime | None = None) -> datetime:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease")
        now = now or utcnow()
        deadline = now + timedelta(seconds=lease_seconds)
        with self.Session.begin() as db:
            self._fenced_update(db, lease, {"lease_until": deadline}, now=now)
        return deadline

    def complete(self, lease: Lease, *, now: datetime | None = None) -> None:
        now = now or utcnow()
        with self.Session.begin() as db:
            self._fenced_update(db, lease, {"status": "completed", "claim_token": None, "worker_id": None, "lease_until": None}, now=now)

    def fail(self, lease: Lease, error: str, *, backoff_seconds: int = 2, now: datetime | None = None) -> str:
        if not 0 <= backoff_seconds <= 3600:
            raise ValueError("Invalid backoff")
        now = now or utcnow()
        with self.Session.begin() as db:
            job = db.get(Job, lease.id, with_for_update=True)
            if job is None or job.claim_token != lease.claim_token or job.worker_id != lease.worker_id:
                raise FencedOut("Lease was reassigned")
            status = "dead" if job.attempts >= job.max_attempts else "queued"
            self._fenced_update(db, lease, {
                "status": status, "claim_token": None, "worker_id": None, "lease_until": None,
                "available_at": now + timedelta(seconds=backoff_seconds), "last_error": str(error)[:500],
            }, now=now)
        return status

    def reap_exhausted(self, *, now: datetime | None = None) -> int:
        now = now or utcnow()
        with self.Session.begin() as db:
            result = db.execute(update(Job).where(
                Job.status == "leased", Job.lease_until <= now,
                Job.attempts >= Job.max_attempts,
            ).values(status="dead", claim_token=None, worker_id=None,
                     lease_until=None, updated_at=now,
                     last_error="Lease expired after retry budget exhausted").execution_options(synchronize_session=False))
            return result.rowcount

    def max_attempts(self, job_id: int) -> int:
        with self.Session() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            return job.max_attempts

    def get(self, job_id: int) -> dict:
        with self.Session() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            return {k: getattr(job, k) for k in ("id", "idempotency_key", "kind", "payload", "status", "attempts", "max_attempts", "worker_id", "last_error")}

    def stats(self) -> dict[str, int]:
        with self.Session() as db:
            rows = db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
        return {k: v for k, v in rows}
