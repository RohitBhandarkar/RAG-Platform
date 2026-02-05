from typing import Literal
import logging
from enum import Enum

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
import pytest

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

health_router = APIRouter(prefix="/health", tags=["Health"])
query_router = APIRouter(prefix="/query", tags=["Query"])
tests_router = APIRouter(prefix="/tests", tags=["Tests"])
embedding_router = APIRouter(prefix="/embeddings", tags=["Embeddings"])


class SQLQuery(BaseModel):
	sql: str


class VectorSearchQuery(BaseModel):
	table: str  # Must be one of EMBEDDING_TABLES
	query_embedding: list[float]  # 768-dim vector
	n_results: int = 5
	metadata_filter: dict | None = None


# Create Enum for embedding table selection
EmbeddingTableName = Enum("EmbeddingTableName", {
	"formulation_summary": "formulation_summary_embeddings",
	"manufacturing_process": "manufacturing_process_embeddings",
	"particle_analytics": "particle_analytics_embeddings",
	"in_vitro": "in_vitro_embeddings",
	"in_vivo": "in_vivo_embeddings",
})


@app.get("/")
def root():
	return {"message": "Backend is running", "environment": settings.ENVIRONMENT}


@app.get("/health")
def health():
	return {"status": "ok"}


@health_router.get("/postgres", summary="PostgreSQL health check")
def health_postgres():
	ok = check_db_connection()
	status = "healthy" if ok[0] else "unhealthy"
	return {
		"service": "postgres",
		"status": status,
		"database": "connected" if status else "error",
		"Exception": str(ok[1]),
	}


@health_router.get("/vector", summary="pgvector health check")
def health_vector():
	"""Check pgvector extension and embedding tables."""
	pgvector_status = check_pgvector_extension()
	embedding_counts = get_embedding_counts()
	
	is_healthy = pgvector_status.get("installed", False)
	
	return {
		"service": "pgvector",
		"status": "healthy" if is_healthy else "unhealthy",
		"pgvector": pgvector_status,
		"embedding_tables": EMBEDDING_TABLES,
		"embedding_counts": embedding_counts,
	}


@health_router.get("/database/full", summary="Full database health check with pgvector validation")
def health_database_full():
	"""
	Comprehensive database health check that validates:
	- PostgreSQL connection
	- pgvector extension installation and functionality
	- All 19 expected tables exist
	- Row counts for each table
	"""
	# Check basic connection
	conn_ok, conn_error = check_db_connection()
	
	if not conn_ok:
		return {
			"service": "postgres",
			"status": "unhealthy",
			"connection": {"connected": False, "error": str(conn_error)},
			"pgvector": {"installed": False},
			"tables": {"valid": False},
		}
	
	# Check pgvector extension
	pgvector_status = check_pgvector_extension()
	
	# Validate tables
	tables_status = validate_sql_tables()
	
	# Get row counts
	row_counts = get_table_row_counts()
	
	# Determine overall health
	is_healthy = (
		conn_ok
		and pgvector_status.get("installed", False)
		and tables_status.get("valid", False)
	)
	
	return {
		"service": "postgres",
		"status": "healthy" if is_healthy else "degraded",
		"connection": {"connected": True},
		"pgvector": pgvector_status,
		"tables": {
			"valid": tables_status.get("valid", False),
			"expected_count": tables_status.get("expected_count", 0),
			"found_count": tables_status.get("found_count", 0),
			"missing": tables_status.get("missing", []),
			"extra": tables_status.get("extra", []),
		},
		"row_counts": row_counts,
	}





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


@health_router.get("/storage", summary="Storage health check")
def health_storage():
	try:
		layout = ensure_layout()
		# Healthy only if all expected directories already exist
		all_exist = all(
			section.get("exists")
			if isinstance(section, dict) and "exists" in section
			else all(
				entry.get("exists")
				for entry in section.values()
				if isinstance(entry, dict)
			)
			for section in [layout.get("raw", {}), layout.get("processed", {}), layout.get("embeddings", {})]
		)
		status = "healthy" if all_exist else "unhealthy"
		return {"service": "storage", "status": status, "layout": layout}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Storage health check failed: {e}")


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


@tests_router.post("/run", summary="Run backend test suite")
def run_tests():
	class TestReport:
		def __init__(self):
			self.failed = []
		
		def pytest_runtest_logreport(self, report):
			if report.when == "call" and report.failed:
				self.failed.append(report.nodeid)
	
	reporter = TestReport()
	exit_code = pytest.main(["-q"], plugins=[reporter])
	return {
		"exit_code": exit_code,
		"success": exit_code == 0,
		"failed_tests": reporter.failed if reporter.failed else None
	}


# ============================================================================
# Embedding Endpoints
# ============================================================================

@embedding_router.get("/health", summary="Check embedding service health")
def embedding_health():
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


@embedding_router.post("/ingest", summary="Run full embedding ingestion")
def embedding_ingest_all():
	"""
	Generate and store embeddings for ALL structured data.
	
	This triggers embedding generation for:
	- formulation_summary_embeddings (from formulations + excipients + APIs)
	- manufacturing_process_embeddings (from manufacturing_processes + parameters)
	- particle_analytics_embeddings (from particle_characteristics + analytical_results)
	- in_vitro_embeddings (from dissolution_profiles + timepoints)
	- in_vivo_embeddings (from pk_studies + pk_parameters + BE results)
	
	⚠️ This is a long-running operation. Each record makes an API call to Vertex AI.
	"""
	try:
		ingestion_service = EmbeddingIngestionService()
		results = ingestion_service.ingest_all_embeddings()
		
		total_embedded = sum(
			r.get("embedded", 0) for r in results.values() if isinstance(r, dict) and "embedded" in r
		)
		total_errors = sum(
			r.get("errors", 0) for r in results.values() if isinstance(r, dict) and "errors" in r
		)
		
		return {
			"status": "completed",
			"total_embedded": total_embedded,
			"total_errors": total_errors,
			"details": results,
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Embedding ingestion failed: {e}")


@embedding_router.post("/ingest/{table}", summary="Run embedding ingestion for specific table")
def embedding_ingest_table(table: EmbeddingTableName):
	"""
	Generate and store embeddings for a specific data category.
	
	Choose from:
	- formulation_summary: Drug formulations with excipients and APIs
	- manufacturing_process: Manufacturing processes with parameters
	- particle_analytics: Particle characteristics and analytical results
	- in_vitro: Dissolution profiles and timepoints
	- in_vivo: PK studies with parameters and BE results
	"""
	try:
		ingestion_service = EmbeddingIngestionService()
		
		# Map table enum to ingestion method
		method_map = {
			"formulation_summary_embeddings": ingestion_service.ingest_formulation_embeddings,
			"manufacturing_process_embeddings": ingestion_service.ingest_manufacturing_embeddings,
			"particle_analytics_embeddings": ingestion_service.ingest_particle_analytics_embeddings,
			"in_vitro_embeddings": ingestion_service.ingest_in_vitro_embeddings,
			"in_vivo_embeddings": ingestion_service.ingest_in_vivo_embeddings,
		}
		
		table_name = table.value
		if table_name not in method_map:
			raise HTTPException(status_code=400, detail=f"Unknown embedding table: {table_name}")
		
		result = method_map[table_name]()
		
		return {
			"status": "completed",
			"table": table_name,
			"processed": result.get("processed", 0),
			"embedded": result.get("embedded", 0),
			"errors": result.get("errors", 0),
		}
	except HTTPException:
		raise
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Embedding ingestion failed: {e}")


@embedding_router.post("/generate", summary="Generate embedding for text")
def embedding_generate(text: str):
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
		embedding = embedding_service.generate_embedding(text)
		
		return {
			"text": text[:100] + "..." if len(text) > 100 else text,
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
app.include_router(tests_router)
app.include_router(embedding_router)
app.include_router(documents_routes.router)


__all__ = ["app"]
