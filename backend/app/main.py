from typing import Literal
import logging
from enum import Enum

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from app.config import settings
from app.db import (
    check_db_connection,
    engine,
    validate_sql_tables,
    check_pgvector_extension,
    get_table_row_counts,
    get_embedding_counts,
    vector_search,
    EMBEDDING_TABLES,
    EXPECTED_TABLES,
)
from app.storage import ensure_layout, summarize_layout, list_files
from app.api.routes import documents as documents_routes
from app.api.routes import rag as rag_routes
from app.services.llm_service import LLMService
from app.services.embedding_service import EmbeddingService, EmbeddingIngestionService


# Create Enum for table dropdown in Swagger
TableName = Enum("TableName", {table: table for table in EXPECTED_TABLES})


# Configure logging
logging.basicConfig(
	level=logging.DEBUG,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	handlers=[logging.StreamHandler()]
)

# Set specific logger levels
logging.getLogger("app.services.llm_service").setLevel(logging.DEBUG)
logging.getLogger("app.data.ingestion.document_processor").setLevel(logging.INFO)

app = FastAPI(title="RAG Backend", version="0.1.0")

# CORS: allow webapp (localhost + Vercel or other deployed origin)
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = [settings.FRONTEND_URL] if settings.FRONTEND_URL else ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

health_router = APIRouter(prefix="/health", tags=["Health"])
query_router = APIRouter(prefix="/query", tags=["Query"])
embedding_router = APIRouter(prefix="/embeddings", tags=["Embeddings"])


class SQLQuery(BaseModel):
	sql: str


class VectorSearchQuery(BaseModel):
	table: str  # Must be one of EMBEDDING_TABLES
	query_embedding: list[float]  # 768-dim vector
	n_results: int = 5
	metadata_filter: dict | None = None


class CanonicalEmbeddingRequest(BaseModel):
	"""Request body for ingesting embeddings from canonical JSON."""
	canonical_json: dict
	source_document_id: int | None = None
	source_id: str | None = None  # Optional; when set, formulation_uid matches DB ingest (e.g. filename, PMID)


class TextEmbeddingRequest(BaseModel):
	"""Request body for generating a single text embedding."""
	text: str


@app.get("/")
def root():
	return {"message": "Backend is running", "environment": settings.ENVIRONMENT}


@app.get("/health")
def health():
	return {"status": "ok"}


@health_router.get("/all", summary="Combined health check for all services")
def health_all():
	"""
	Combined health check for all services:
	- PostgreSQL + pgvector
	- LLM backend
	- Storage
	"""
	# PostgreSQL + pgvector
	pg_conn_ok, pg_error = check_db_connection()
	pgvector_status = check_pgvector_extension() if pg_conn_ok else {"installed": False}
	tables_status = validate_sql_tables() if pg_conn_ok else {"valid": False}
	embedding_counts = get_embedding_counts() if pg_conn_ok else {}
	
	# LLM
	llm_service = LLMService()
	llm_info = llm_service.check_health()
	
	# Storage
	try:
		ensure_layout()
		storage_ok = True
	except Exception:
		storage_ok = False
	
	# Overall status
	all_healthy = (
		pg_conn_ok
		and pgvector_status.get("installed", False)
		and tables_status.get("valid", False)
		and llm_info.get("status") == "healthy"
		and storage_ok
	)
	
	return {
		"status": "healthy" if all_healthy else "degraded",
		"services": {
			"postgres": {
				"connected": pg_conn_ok,
				"pgvector_installed": pgvector_status.get("installed", False),
				"tables_valid": tables_status.get("valid", False),
				"missing_tables": tables_status.get("missing", []),
				"embedding_counts": embedding_counts,
			},
			"llm": {
				"status": llm_info.get("status", "unhealthy"),
				"base_url": llm_info.get("base_url"),
			},
			"storage": {
				"status": "healthy" if storage_ok else "unhealthy",
			},
		},
	}


@health_router.get("/llm", summary="LLM backend health check")
def health_llm():
	"""Check connectivity to the configured LLM HTTP endpoint.

	This pings the OpenAI-compatible server's ``/models`` endpoint via
	:class:`LLMService` and reports whether the service is reachable from
	this backend (including on GCP VMs).
	"""

	service = LLMService()
	info = service.check_health()
	return {
		"service": "llm",
		"status": info.get("status", "unhealthy"),
		"base_url": info.get("base_url", service.base_url),
		"details": {k: v for k, v in info.items() if k not in {"status", "base_url"}},
	}


@query_router.get("/get", summary="Get all records from a table")
def query_get_table(table: TableName):
	"""
	Fetch all records from the selected table.
	"""
	table_name = table.value
	try:
		with engine.connect() as connection:
			result = connection.execute(text(f'SELECT * FROM "{table_name}"'))
			rows = [dict(row._mapping) for row in result]
		return {"table": table_name, "count": len(rows), "rows": rows}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Query failed: {e}")


@query_router.delete("/purge", summary="Delete all records from a table")
def query_purge_table(table: TableName):
	"""
	Delete all records from the selected table.
	WARNING: This cannot be undone!
	"""
	table_name = table.value
	try:
		with engine.connect() as connection:
			result = connection.execute(text(f'DELETE FROM "{table_name}"'))
			connection.commit()
			deleted_count = result.rowcount
		return {"table": table_name, "deleted": deleted_count, "status": "purged"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Purge failed: {e}")


@query_router.delete("/purgeall", summary="Delete all records from ALL tables")
def query_purge_all():
	"""
	Delete all records from ALL tables.
	WARNING: This will empty the entire database! Cannot be undone!
	
	Tables are purged in reverse order to respect foreign key constraints.
	"""
	results = {}
	# Reverse order to handle FK dependencies (children first, parents last)
	tables_in_order = list(reversed(EXPECTED_TABLES))
	
	try:
		with engine.connect() as connection:
			for table_name in tables_in_order:
				try:
					result = connection.execute(text(f'DELETE FROM "{table_name}"'))
					results[table_name] = {"deleted": result.rowcount, "status": "purged"}
				except Exception as e:
					results[table_name] = {"deleted": 0, "status": "error", "error": str(e)}
			connection.commit()
		return {"status": "completed", "tables": results}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Purge all failed: {e}")


@query_router.post("/sql", summary="Run raw SQL query (advanced)")
def run_postgres_query(query: SQLQuery):
	"""
	Run a raw SQL query. Use with caution.
	"""
	try:
		with engine.connect() as connection:
			result = connection.execute(text(query.sql))
			# Check if it's a SELECT query (returns rows)
			if result.returns_rows:
				rows = [dict(row._mapping) for row in result]
				return {"rows": rows, "count": len(rows)}
			else:
				connection.commit()
				return {"affected_rows": result.rowcount, "status": "executed"}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"SQL query failed: {e}")


@query_router.post("/vector", summary="Run vector similarity search")
def run_vector_search(body: VectorSearchQuery):
	"""
	Perform vector similarity search on an embedding table.
	
	Tables available:
	- formulation_summary_embeddings
	- manufacturing_process_embeddings
	- particle_analytics_embeddings
	- in_vitro_embeddings
	- in_vivo_embeddings
	- document_chunk_embeddings
	"""
	try:
		results = vector_search(
			table=body.table,
			query_embedding=body.query_embedding,
			n_results=body.n_results,
			metadata_filter=body.metadata_filter,
		)
		return {"table": body.table, "n_results": len(results), "results": results}
	except ValueError as e:
		raise HTTPException(status_code=400, detail=str(e))
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Vector search failed: {e}")


@query_router.get("/summary", summary="Summarize document store layout")
def storage_summary():
	try:
		return summarize_layout()
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Storage summary failed: {e}")


@query_router.get("/list", summary="List files in document store")
def storage_list(
	kind: Literal["raw", "processed"],
	source: Literal["pubmed", "patents", "fda", "user_uploads"],
	limit: int = 20,
):
	try:
		files = list_files(kind=kind, source=source, limit=limit)
		return {"kind": kind, "source": source, "count": len(files), "files": files}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Listing files failed: {e}")


@health_router.get("/embeddings", summary="Check embedding service health")
def health_embeddings():
	"""
	Check the health and connectivity of the Vertex AI embedding service.
	
	Tests:
	- Vertex AI API connectivity
	- text-embedding-004 model availability
	- Token generation capability
	"""
	try:
		embedding_service = EmbeddingService()
		health_info = embedding_service.check_health()
		return {
			"service": "embedding",
			**health_info,
		}
	except Exception as e:
		return {
			"service": "embedding",
			"status": "unhealthy",
			"error": str(e),
		}


@embedding_router.post("/ingest", summary="Ingest embeddings from canonical JSON")
def embedding_ingest_canonical(body: CanonicalEmbeddingRequest):
	"""
	Generate and store embeddings from a canonical JSON document.
	
	This processes the canonical JSON and creates embeddings for:
	- formulation_summary_embeddings (API + formulation strategy + components)
	- manufacturing_process_embeddings (process method, milling, temperature)
	- particle_analytics_embeddings (particle size, zeta potential)
	- in_vitro_embeddings (stability, dissolution profile)
	- in_vivo_embeddings (PK parameters: Cmax, AUC, Tmax, BA)
	
	Each formulation in the canonical JSON generates up to 5 embeddings.
	
	⚠️ Each embedding makes an API call to Vertex AI text-embedding-004.
	"""
	try:
		ingestion_service = EmbeddingIngestionService()
		results = ingestion_service.ingest_from_canonical(
			canonical=body.canonical_json,
			source_document_id=body.source_document_id,
			source_id=body.source_id,
		)
		
		total_embedded = sum(
			r.get("embedded", 0) for r in results.values() if isinstance(r, dict)
		)
		total_errors = sum(
			r.get("errors", 0) for r in results.values() if isinstance(r, dict)
		)
		
		return {
			"status": "completed",
			"total_embedded": total_embedded,
			"total_errors": total_errors,
			"details": results,
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Embedding ingestion failed: {e}")


@embedding_router.post("/preview", summary="Preview embedding texts from canonical JSON")
def embedding_preview(body: CanonicalEmbeddingRequest):
	"""
	Preview the text content that would be embedded from a canonical JSON.
	
	This does NOT generate embeddings or call Vertex AI.
	Use this to verify what text will be embedded before running ingestion.
	
	Returns the constructed text for each embedding category per formulation.
	"""
	try:
		ingestion_service = EmbeddingIngestionService()
		preview = ingestion_service.get_embedding_texts_preview(body.canonical_json)
		return preview
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Preview failed: {e}")


@embedding_router.post("/generate-from-canonical", summary="Generate embeddings from canonical JSON (no DB storage)")
def embedding_generate_from_canonical(body: CanonicalEmbeddingRequest):
	"""
	Generate embeddings from a canonical JSON and return them directly.
	
	This calls Vertex AI to generate real embeddings but does NOT store them in the database.
	Use this to inspect embeddings before committing to storage.
	
	Returns the text and 768-dim embedding vector for each category per formulation.
	
	⚠️ Each embedding makes an API call to Vertex AI text-embedding-004.
	"""
	try:
		ingestion_service = EmbeddingIngestionService()
		result = ingestion_service.generate_embeddings_from_canonical(body.canonical_json)
		return result
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Embedding generation failed: {e}")


@embedding_router.post("/generate", summary="Generate embedding for text")
def embedding_generate(body: TextEmbeddingRequest):
	"""
	Generate a 768-dimensional embedding vector for the given text.
	
	Uses Vertex AI text-embedding-004 model.
	
	This can be used for:
	- Testing the embedding service
	- Generating query embeddings for similarity search
	- Debugging embedding outputs
	"""
	try:
		embedding_service = EmbeddingService()
		embedding = embedding_service.generate_embedding(body.text)
		
		return {
			"text": body.text[:100] + "..." if len(body.text) > 100 else body.text,
			"model": embedding_service.model,
			"dimension": len(embedding),
			"embedding": embedding,
		}
	except ValueError as e:
		raise HTTPException(status_code=400, detail=str(e))
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Embedding generation failed: {e}")


app.include_router(health_router)
app.include_router(query_router)
app.include_router(embedding_router)
app.include_router(documents_routes.router)
app.include_router(rag_routes.router)


__all__ = ["app"]
