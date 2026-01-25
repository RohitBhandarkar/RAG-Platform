import httpx

from app.main import app


def test_postgres_query_select_1():
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        response = client.post("/query/postgres", json={"sql": "SELECT 1 AS value"})
    assert response.status_code == 200
