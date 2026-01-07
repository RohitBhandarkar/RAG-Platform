# RAG Formulation Backend - Quick Start

## Setup

1. **Create and activate a virtual environment:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or on Windows: venv\Scripts\activate
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Running the Backend

### Development Mode (with auto-reload)
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Documentation

Once the server is running, access:

- **Swagger UI (Interactive):** http://localhost:8000/docs
- **ReDoc (Alternative):** http://localhost:8000/redoc
- **OpenAPI JSON:** http://localhost:8000/openapi.json

## Available Endpoints

### 1. Health Check
- **GET** `/health`
- Returns system health status and component availability
- No authentication required

### 2. RAG Query
- **POST** `/api/rag/query`
- Generate formulation recommendations based on API properties
- Request body example:
```json
{
  "molecular_weight": 450.5,
  "melting_point": 180.0,
  "pka": 7.2,
  "log_p": 3.5,
  "solubility": 0.05,
  "target_platform": "SEDDS",
  "max_results": 5
}
```

### 3. Data Ingestion
- **POST** `/api/ingestion/ingest`
- Trigger data ingestion from external sources
- Request body example:
```json
{
  "sources": ["pubmed", "fda"],
  "max_documents": 100,
  "query": "SEDDS formulation solubility enhancement"
}
```

## Testing with curl

### Health Check
```bash
curl http://localhost:8000/health
```

### RAG Query
```bash
curl -X POST "http://localhost:8000/api/rag/query" \
  -H "Content-Type: application/json" \
  -d '{
    "molecular_weight": 450.5,
    "melting_point": 180.0,
    "pka": 7.2,
    "log_p": 3.5,
    "solubility": 0.05
  }'
```

### Data Ingestion
```bash
curl -X POST "http://localhost:8000/api/ingestion/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "sources": ["pubmed"],
    "max_documents": 50
  }'
```

## Current Implementation Status

✅ **Completed:**
- FastAPI application setup with CORS
- Three main endpoints (health, RAG query, ingestion)
- Pydantic schemas for request/response validation
- Auto-generated Swagger UI documentation
- Configuration management with environment variables
- Logging setup

⚠️ **Placeholder/TODO:**
- Actual RAG engine implementation (returns mock data)
- Database connectivity checks
- Vector store integration
- LLM service integration
- Document processing pipeline
- Actual ingestion workers (PubMed, FDA, Patents)

## Next Steps

The backend is ready for development. To implement actual functionality:

1. Implement RAG engine in `app/services/rag_engine.py`
2. Implement retrieval system in `app/services/retrieval.py`
3. Implement LLM service in `app/services/llm_service.py`
4. Implement ingestion workers in `app/data/ingestion/`
5. Set up database models and connections
6. Integrate vector store (ChromaDB or Vertex AI)

## Notes

- Current responses are placeholders to demonstrate API structure
- All endpoints return valid responses for testing frontend integration
- Swagger UI provides interactive testing interface
- CORS is configured to allow all origins in development mode
