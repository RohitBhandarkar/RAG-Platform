import pytest
import httpx
from app.main import app


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body.get("message") == "Backend is running"


def test_health_checks_database_connection(client):
    response = client.get("/health/postgres")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in {"healthy", "unhealthy"}
    assert "database" in data
