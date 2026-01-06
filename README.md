# RAG Platform - Pharmaceutical Formulation Development System

A Retrieval-Augmented Generation (RAG) system for accelerating pharmaceutical formulation development through AI-driven recommendations for drug solubility enhancement.

## Overview

This system addresses poor drug solubility (affecting ~90% of new drug candidates) by providing data-driven formulation recommendations across three platforms:
- **Lipid-Based Systems** (SEDDS/SMEDDS)
- **Nanosuspensions**
- **Amorphous Solid Dispersions** (ASD)

## Features

- **Hybrid Retrieval System**: Combines semantic search and property-based filtering
- **Multi-Platform Recommendations**: Generates 2-3 formulation prototypes per platform
- **Experimental Plans**: Detailed step-by-step procedures
- **CMC Documentation**: Regulatory-ready documentation
- **Risk Analysis**: Identifies potential failure modes and mitigation strategies

## Architecture

- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: React + TypeScript
- **Vector DB**: ChromaDB (local) / Vertex AI Vector Search (production)
- **SQL DB**: PostgreSQL
- **LLM**: Vertex AI (Gemini/PaLM), OpenAI, Anthropic
- **Deployment**: Google Cloud Platform (GCP)

## Project Structure

```
RAG-Platform/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── api/      # API routes
│   │   ├── models/   # SQLAlchemy models
│   │   ├── schemas/  # Pydantic schemas
│   │   ├── services/ # Business logic
│   │   └── data/     # Data ingestion
│   └── tests/
├── frontend/         # React frontend
├── data/            # Data storage
├── scripts/         # Setup scripts
├── gcp/             # GCP deployment configs
└── docs/            # Documentation
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Docker & Docker Compose

### Local Development

1. **Clone the repository**
```bash
git clone https://github.com/RohitBhandarkar/RAG-Platform.git
cd RAG-Platform
```

2. **Set up backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your configuration
```

3. **Set up database**
```bash
python ../scripts/setup_database.py
```

4. **Run with Docker Compose**
```bash
cd ..
docker-compose up -d
```

5. **Access the application**
- Backend API: http://localhost:8001
- Frontend: http://localhost:3000
- API Documentation: http://localhost:8001/api/docs

## Development Status

This project is currently in **Phase 1: Project Setup (Week 1-2)** of a 13-week development plan.

See [design.md](../design.md) for detailed architecture and implementation plan.

## Configuration

### Environment Variables

See `backend/.env.example` for all configuration options.

Key variables:
- `POSTGRES_*`: Database connection
- `OPENAI_API_KEY`: OpenAI API key
- `VERTEX_AI_PROJECT_ID`: GCP project for Vertex AI
- `EMBEDDING_MODEL`: Embedding model to use

## Testing

```bash
cd backend
pytest
```

## Deployment

See [gcp/deployment/README.md](gcp/deployment/README.md) for GCP deployment instructions.

## Contributing

This is a development project. Contributions will be accepted after Phase 1 is complete.

## License

See [LICENSE](LICENSE) file for details.

## Contact

For questions or feedback, please open an issue on GitHub.

---

**Current Phase**: Phase 1 - Project Setup  
**Last Updated**: 2026-01-06
