from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from claimforge.core import Scheduler, FencedOut
from claimforge.api import app

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

@pytest.fixture
def store(tmp_path):
    s = Scheduler(f"sqlite:///{tmp_path/'scheduler.db'}")
    yield s
    s.close()


def test_idempotent_enqueue(store):
    id1, created = store.enqueue("k1", "echo", {"n": 1}, now=T0)
    assert created
    id2, created = store.enqueue("k1", "echo", {"n": 1}, now=T0)
    assert id1 == id2 and not created
    with pytest.raises(ValueError):
        store.enqueue("k1", "echo", {"n": 2})


def test_claim_and_complete(store):
    jid, _ = store.enqueue("a", "echo", {"n": 1}, now=T0)
    lease = store.claim("worker-a", now=T0)
    assert lease.id == jid and lease.attempts == 1
    assert store.claim("worker-b", now=T0) is None
    store.complete(lease, now=T0)
    assert store.get(jid)["status"] == "completed"
    assert store.claim("worker-c", now=T0) is None


def test_expired_lease_fences_stale_worker(store):
    jid, _ = store.enqueue("stale", "echo", {}, now=T0)
    old = store.claim("old", lease_seconds=10, now=T0)
    new = store.claim("new", lease_seconds=10, now=T0 + timedelta(seconds=11))
    assert new.id == jid and new.claim_token != old.claim_token
    with pytest.raises(FencedOut):
        store.complete(old, now=T0 + timedelta(seconds=12))
    store.complete(new, now=T0 + timedelta(seconds=12))
    assert store.get(jid)["status"] == "completed"


def test_lease_renewal(store):
    store.enqueue("renew", "echo", {}, now=T0)
    old = store.claim("worker", lease_seconds=5, now=T0)
    deadline = store.renew(old, lease_seconds=10, now=T0 + timedelta(seconds=4))
    assert deadline == T0 + timedelta(seconds=14)
    assert store.claim("another", now=T0 + timedelta(seconds=8)) is None
    store.complete(old, now=T0 + timedelta(seconds=9))


def test_retry_and_dead_letter(store):
    jid, _ = store.enqueue("retry", "echo", {}, max_attempts=2, now=T0)
    first = store.claim("a", now=T0)
    assert store.fail(first, "transient", backoff_seconds=5, now=T0) == "queued"
    assert store.claim("b", now=T0 + timedelta(seconds=2)) is None
    second = store.claim("b", now=T0 + timedelta(seconds=6))
    assert second.attempts == 2
    assert store.fail(second, "permanent", now=T0 + timedelta(seconds=7)) == "dead"
    assert store.get(jid)["last_error"] == "permanent"
    assert store.claim("c", now=T0 + timedelta(seconds=10)) is None


def test_expired_token_not_renewed(store):
    store.enqueue("expired", "echo", {}, now=T0)
    lease = store.claim("worker", lease_seconds=1, now=T0)
    with pytest.raises(FencedOut):
        store.renew(lease, now=T0 + timedelta(seconds=2))


def test_api_routes(store):
    app.state.scheduler = store
    try:
        client = TestClient(app)
        assert client.get('/health').json()['status'] == 'ok'
        r = client.post('/jobs', json={'idempotency_key':'route-1','kind':'echo','payload':{'hello':'world'}})
        assert r.status_code == 201 and r.json()['created']
        ident = r.json()['job_id']
        assert client.post('/jobs', json={'idempotency_key':'route-1','kind':'echo','payload':{'hello':'world'}}).json()['created'] is False
        assert client.get(f'/jobs/{ident}').json()['status'] == 'queued'
        assert client.get('/stats').json()['queued'] >= 1
        assert client.get('/jobs/100000000').status_code == 404
        assert client.post('/jobs', json={'idempotency_key':'route-1','kind':'echo','payload':{'hello':'changed'}}).status_code == 409
    finally:
        del app.state.scheduler


def test_exhausted_claim_reaper_and_invalid_stale_completion(store):
    jid, _ = store.enqueue('once', 'echo', {'v': 1}, max_attempts=1, now=T0)
    lease = store.claim('worker', lease_seconds=5, now=T0)
    assert store.reap_exhausted(now=T0 + timedelta(seconds=4)) == 0
    assert store.reap_exhausted(now=T0 + timedelta(seconds=6)) == 1
    assert store.get(jid)['status'] == 'dead'
    with pytest.raises(FencedOut):
        store.complete(lease, now=T0 + timedelta(seconds=7))
    assert store.claim('again', now=T0 + timedelta(seconds=8)) is None


def test_validation_and_no_duplicate_completed_job(store):
    with pytest.raises(ValueError):
        store.enqueue('', 'echo', {})
    with pytest.raises(ValueError):
        store.enqueue('bad', 'echo', [], now=T0)
    jid, _ = store.enqueue('done', 'echo', {}, now=T0)
    lease = store.claim('w1', now=T0)
    with pytest.raises(ValueError):
        store.renew(lease, lease_seconds=0)
    store.complete(lease, now=T0)
    with pytest.raises(FencedOut):
        store.complete(lease, now=T0)
    assert store.get(jid)['status'] == 'completed'


def test_number_of_public_routes():
    from claimforge.api import app
    paths = {r.path for r in app.routes if hasattr(r, 'methods') and r.path not in ('/openapi.json','/docs','/docs/oauth2-redirect','/redoc')}
    assert paths == {'/health', '/jobs', '/jobs/{job_id}', '/stats'}
