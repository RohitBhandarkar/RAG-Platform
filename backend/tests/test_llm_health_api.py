import httpx

from app.main import app
from app.services import llm_service


def test_llm_health_endpoint_healthy(monkeypatch):
	def fake_check(self):  # type: ignore[override]
		return {
			"status": "healthy",
			"base_url": "http://llm-service:8000/v1",
			"models_payload": {"data": []},
		}

	monkeypatch.setattr(llm_service.LLMService, "check_health", fake_check)

	transport = httpx.ASGITransport(app=app)
	with httpx.Client(transport=transport, base_url="http://testserver") as client:
		response = client.get("/health/llm")
	assert response.status_code == 200
	data = response.json()
	assert data.get("service") == "llm"
	assert data.get("status") == "healthy"
	assert data.get("base_url") == "http://llm-service:8000/v1"
	assert "details" in data


def test_llm_health_endpoint_unhealthy(monkeypatch):
	def fake_check(self):  # type: ignore[override]
		return {
			"status": "unhealthy",
			"base_url": "http://llm-service:8000/v1",
			"error": "cannot connect",
		}

	monkeypatch.setattr(llm_service.LLMService, "check_health", fake_check)

	transport = httpx.ASGITransport(app=app)
	with httpx.Client(transport=transport, base_url="http://testserver") as client:
		response = client.get("/health/llm")
	assert response.status_code == 200
	data = response.json()
	assert data.get("service") == "llm"
	assert data.get("status") == "unhealthy"
	assert data.get("base_url") == "http://llm-service:8000/v1"
	assert data.get("details", {}).get("error") == "cannot connect"
