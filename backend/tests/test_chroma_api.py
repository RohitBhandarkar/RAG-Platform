from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_chroma_health_endpoint():
    response = client.get("/health/vector")
    assert response.status_code == 200
    data = response.json()
    assert data.get("service") == "chroma"
    assert data.get("status") in {"healthy", "unhealthy"}


def test_chroma_query_endpoint_exists():
    payload = {
        "collection": "test_collection",
        "query_texts": ["test"],
        "n_results": 1,
    }
    response = client.post("/query/chroma", json=payload)
    assert response.status_code in {200, 500}
