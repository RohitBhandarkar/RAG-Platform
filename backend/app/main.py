from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
import pytest

from app.config import settings
from app.db import check_db_connection, engine
from app.chroma_client import check_chroma_connection, query_chroma


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


@health_router.get("/storage", summary="Storage health check")
def health_storage():
	return {"service": "storage", "status": "not_configured"}


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


@tests_router.post("/run", summary="Run backend test suite")
def run_tests():
	exit_code = pytest.main(["-q"])
	return {"exit_code": exit_code, "success": exit_code == 0}


app.include_router(health_router)
app.include_router(query_router)
app.include_router(tests_router)


__all__ = ["app"]
