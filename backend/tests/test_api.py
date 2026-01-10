import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


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
