from typing import Literal
import logging

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
import pytest

from app.config import settings
from app.db import check_db_connection, engine
from app.chroma_client import check_chroma_connection, query_chroma
from app.storage import ensure_layout, summarize_layout, list_files
from app.api.routes import documents as documents_routes
from app.services.llm_service import LLMService


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


class SQLQuery(BaseModel):
	sql: str


class ChromaQuery(BaseModel):
	collection: str
	query_texts: list[str]
	n_results: int = 5


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


@health_router.get("/vector", summary="Vector DB health check")
def health_vector():
	ok = check_chroma_connection()
	status = "healthy" if ok[0] else "unhealthy"
	return {"service": "chroma", "status": status, "Exception": str(ok[1])}


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


@query_router.post("/postgres", summary="Run SQL query on PostgreSQL")
def run_postgres_query(query: SQLQuery):
	with engine.connect() as connection:
		result = connection.execute(text(query.sql))
		rows = [dict(row._mapping) for row in result]
	return {"rows": rows}


@query_router.post("/chroma", summary="Run query against ChromaDB")
def run_chroma_query(body: ChromaQuery):
	try:
		result = query_chroma(
			collection=body.collection,
			query_texts=body.query_texts,
			n_results=body.n_results,
		)
		return result
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Chroma query failed: {e}")


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


app.include_router(health_router)
app.include_router(query_router)
app.include_router(tests_router)
app.include_router(documents_routes.router)


__all__ = ["app"]
