from fastapi.testclient import TestClient
from claimforge.showcase import app

def test_public_showcase_is_read_only():
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    m = client.get('/metrics')
    assert m.status_code == 200
    assert m.json()['job_submissions_enabled'] is False
    assert m.json()['database_connected'] is False
    assert m.json()['metrics']['duplicate_claims'] == 0
    home = client.get('/')
    assert home.status_code == 200
    assert 'Read-only' in home.text or 'read-only' in home.text
    assert home.headers['x-frame-options'] == 'DENY'
    assert client.post('/jobs', json={'kind':'echo', 'payload':{}}).status_code == 404
    assert client.get('/jobs/1').status_code == 404
    assert client.get('/stats').status_code == 404
