import pytest
import httpx

from app.main import app
from app.storage import ensure_layout, summarize_layout, list_files, SOURCES, KINDS


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        yield client


def test_health_storage_endpoint(client):
    response = client.get("/health/storage")
    assert response.status_code == 200
    data = response.json()
    assert data.get("service") == "storage"
    assert data.get("status") in {"healthy", "unhealthy"}


def test_storage_summary_endpoint(client):
    response = client.get("/query/summary")
    assert response.status_code == 200

def test_storage_list_endpoint(client):
    # Use one valid combination; do not assert on contents
    response = client.get("/query/list", params={"kind": "raw", "source": "pubmed", "limit": 5})
    assert response.status_code == 200


def test_ensure_layout_returns_expected_structure():
    layout = ensure_layout()
    assert "base" in layout
    for kind in KINDS:
        assert kind in layout
        for source in SOURCES:
            assert source in layout[kind]


def test_summarize_layout_returns_expected_kinds_and_sources():
    summary = summarize_layout()
    for kind in KINDS:
        assert kind in summary
        for source in SOURCES:
            assert source in summary[kind]


def test_list_files_with_no_files_returns_list():
    # For a fresh/empty layout this should just be an empty list or small list
    files = list_files("raw", "pubmed", limit=3)
    assert isinstance(files, list)
