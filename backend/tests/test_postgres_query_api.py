from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_postgres_query_select_1():
    response = client.post("/postgres/query", json={"sql": "SELECT 1 AS value"})
    assert response.status_code == 200
