"""
API Tests
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


class TestAPI:
    """Test API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Test client fixture"""
        return TestClient(app)
    
    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_generate_formulation_not_implemented(self, client):
        """Test formulation generation (not yet implemented)"""
        payload = {
            "api_properties": {
                "molecular_weight": 425.5,
                "melting_point": 180.0,
                "pka": 6.5,
                "solubility": 0.05,
                "logp": 3.2
            },
            "platforms": ["SEDDS"],
            "max_results": 2
        }
        response = client.post("/api/v1/formulation/generate", json=payload)
        assert response.status_code == 501  # Not implemented yet
