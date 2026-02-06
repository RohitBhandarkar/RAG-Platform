"""Document API routes for research paper processing."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional
import os
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, Query

from app.data.ingestion.document_processor import DocumentProcessor
from app.data.parsers.pdf_parser import PDFParser
from app.services.llm_service import LLMService
from app.services.database_ingestion_service import DatabaseIngestionService
from app.services.embedding_service import EmbeddingIngestionService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
	"/canonical",
	summary="Process research paper PDF into canonical JSON",
	response_description="Canonical JSON structure extracted from the uploaded PDF",
)
async def process_pdf_to_canonical(
	file: UploadFile = File(..., description="PDF research paper to process"),
) -> Dict[str, Any]:
	"""Accept a PDF, run the research paper processor, and return canonical JSON.

	The endpoint:
	- Saves the uploaded PDF to a temporary file.
	- Uses :class:`DocumentProcessor` to parse the PDF, create section-based
	  chunks (including tables), and invoke the LLM service.
	- Returns the resulting canonical JSON object.
	"""

	if not file.filename or not file.filename.lower().endswith(".pdf"):
		raise HTTPException(status_code=400, detail="Only PDF files are supported")

	content = await file.read()
	if not content:
		raise HTTPException(status_code=400, detail="Uploaded file is empty")

	tmp_path: Path | None = None
	try:
		with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
			tmp.write(content)
			tmp_path = Path(tmp.name)

		processor = DocumentProcessor()
		canonical = await processor.process_document(
			file_path=tmp_path,
			source="upload",
			metadata={"original_filename": file.filename},
		)
		return canonical
	except HTTPException:
		raise
	except Exception as exc:  # pragma: no cover - safety net
		raise HTTPException(status_code=500, detail=f"Failed to process PDF: {exc}") from exc
	finally:
		if tmp_path is not None and tmp_path.exists():
			try:
				os.remove(tmp_path)
			except OSError:
				pass


@router.post(
	"/parsed",
	summary="Show parsed PDF structure (parser output)",
	response_description="Structured pages, sections, metadata, and tables extracted from the PDF",
)
async def preview_parsed_pdf(
	file: UploadFile = File(..., description="PDF research paper to parse"),
) -> Dict[str, Any]:
	"""Return the raw parsed output from the PDF parser for inspection.

	This endpoint:
	- Saves the uploaded PDF to a temporary file.
	- Uses :class:`PDFParser` to extract pages, sections, metadata and tables.
	- Returns the resulting structured representation without calling the LLM.
	"""

	if not file.filename or not file.filename.lower().endswith(".pdf"):
		raise HTTPException(status_code=400, detail="Only PDF files are supported")

	content = await file.read()
	if not content:
		raise HTTPException(status_code=400, detail="Uploaded file is empty")

	tmp_path: Path | None = None
	try:
		with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
			tmp.write(content)
			tmp_path = Path(tmp.name)

		parser = PDFParser()
		parsed = parser.parse(tmp_path)
		return parsed
	except HTTPException:
		raise
	except Exception as exc:  # pragma: no cover - safety net
		raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {exc}") from exc
	finally:
		if tmp_path is not None and tmp_path.exists():
			try:
				os.remove(tmp_path)
			except OSError:
				pass


@router.post(
	"/prompt-preview",
	summary="Show the LLM prompt built from a PDF",
	response_description="The exact prompt string that would be sent to the LLM",
)
async def preview_llm_prompt(
	file: UploadFile = File(..., description="PDF research paper used to build the LLM prompt"),
) -> Dict[str, Any]:
	"""Return the prompt that would be sent to the LLM for this PDF.

	The endpoint:
	- Saves the uploaded PDF to a temporary file.
	- Uses :class:`PDFParser` and :class:`DocumentProcessor` to follow the
	  same parsing + chunking pipeline used for canonical extraction.
	- Calls the existing prompt builder inside :class:`LLMService` to
	  construct the final extraction prompt.
	- Returns the prompt string without invoking the LLM itself.
	"""

	if not file.filename or not file.filename.lower().endswith(".pdf"):
		raise HTTPException(status_code=400, detail="Only PDF files are supported")

	content = await file.read()
	if not content:
		raise HTTPException(status_code=400, detail="Uploaded file is empty")

	tmp_path: Path | None = None
	try:
		with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
			tmp.write(content)
			tmp_path = Path(tmp.name)

		# Parse PDF to get the same structure used in the main pipeline.
		parser = PDFParser()
		parsed = parser.parse(tmp_path)
		doc_id = str(tmp_path)

		# Reuse the existing chunking logic.
		processor = DocumentProcessor()
		text_chunks, table_chunks = processor.chunk_document(
			doc_id=doc_id,
			sections=parsed.get("sections", []),
			tables=parsed.get("tables", []),
		)

		# Build the prompt using the same internal method used by generate_canonical.
		llm = LLMService()
		prompt = llm._build_prompt(  # type: ignore[attr-defined]
			parsed_document=parsed,
			text_chunks=text_chunks,
			table_chunks=table_chunks,
			extra_metadata={"original_filename": file.filename},
			source="upload",
			doc_id=doc_id,
		)

		return {"prompt": prompt}
	except HTTPException:
		raise
	except Exception as exc:  # pragma: no cover - safety net
		raise HTTPException(status_code=500, detail=f"Failed to build prompt: {exc}") from exc
	finally:
		if tmp_path is not None and tmp_path.exists():
			try:
				os.remove(tmp_path)
			except OSError:
				pass


@router.post(
	"/chunks",
	summary="Show the text and table chunks built for a PDF",
	response_description="Lists of text_chunks and table_chunks used for LLM prompting",
)
async def preview_chunks(
	file: UploadFile = File(..., description="PDF research paper used to build chunks"),
) -> Dict[str, Any]:
	"""Return the text and table chunks created from a PDF.

	This endpoint:
	- Saves the uploaded PDF to a temporary file.
	- Uses :class:`PDFParser` to parse the document.
	- Uses :class:`DocumentProcessor.chunk_document` to build
	  ``text_chunks`` and ``table_chunks`` exactly as in the canonical
	  pipeline.
	- Returns both lists for inspection.
	"""

	if not file.filename or not file.filename.lower().endswith(".pdf"):
		raise HTTPException(status_code=400, detail="Only PDF files are supported")

	content = await file.read()
	if not content:
		raise HTTPException(status_code=400, detail="Uploaded file is empty")

	tmp_path: Path | None = None
	try:
		with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
			tmp.write(content)
			tmp_path = Path(tmp.name)

		parser = PDFParser()
		parsed = parser.parse(tmp_path)
		doc_id = str(tmp_path)

		processor = DocumentProcessor()
		text_chunks, table_chunks = processor.chunk_document(
			doc_id=doc_id,
			sections=parsed.get("sections", []),
			tables=parsed.get("tables", []),
		)

		return {
			"text_chunks": text_chunks,
			"table_chunks": table_chunks,
		}
	except HTTPException:
		raise
	except Exception as exc:  # pragma: no cover - safety net
		raise HTTPException(status_code=500, detail=f"Failed to build chunks: {exc}") from exc
	finally:
		if tmp_path is not None and tmp_path.exists():
			try:
				os.remove(tmp_path)
			except OSError:
				pass


@router.post(
	"/ingest",
	summary="Ingest PDF into database with embeddings",
	response_description="Ingestion statistics including created records and embeddings",
)
async def ingest_pdf_to_database(
	file: UploadFile = File(..., description="PDF research paper to ingest"),
	source_type: str = Query("user_upload", description="Source type (pubmed, patent, fda, user_upload)"),
	generate_embeddings: bool = Query(True, description="Whether to generate and store embeddings"),
) -> Dict[str, Any]:
	"""Accept a PDF, extract canonical JSON, and populate the database.

	This endpoint performs the full ingestion pipeline:
	1. Parse the PDF using PDFParser
	2. Generate canonical JSON using LLM (Gemini)
	3. Populate PostgreSQL structured tables (formulations, excipients, APIs, etc.)
	4. Optionally generate and store vector embeddings for semantic search

	Returns:
		- canonical: The extracted canonical JSON
		- database_stats: Statistics for structured table insertions
		- embedding_stats: Statistics for embedding generation (if enabled)
	"""

	if not file.filename or not file.filename.lower().endswith(".pdf"):
		raise HTTPException(status_code=400, detail="Only PDF files are supported")

	content = await file.read()
	if not content:
		raise HTTPException(status_code=400, detail="Uploaded file is empty")

	tmp_path: Path | None = None
	try:
		# Save uploaded file temporarily
		with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
			tmp.write(content)
			tmp_path = Path(tmp.name)

		logger.info(f"Processing PDF: {file.filename}")

		# Step 1: Generate canonical JSON via DocumentProcessor
		processor = DocumentProcessor()
		canonical = await processor.process_document(
			file_path=tmp_path,
			source="upload",
			metadata={"original_filename": file.filename},
		)

		logger.info(f"Canonical JSON generated with {len(canonical.get('formulations', []))} formulations")

		# Step 2: Populate structured PostgreSQL tables
		db_service = DatabaseIngestionService()
		db_stats = db_service.ingest_canonical(
			canonical=canonical,
			source_type=source_type,
			source_id=file.filename,
			file_path=str(tmp_path),
		)

		logger.info(f"Database ingestion complete: {db_stats}")

		# Step 3: Generate and store embeddings (if enabled)
		embedding_stats = None
		if generate_embeddings:
			try:
				embedding_service = EmbeddingIngestionService()
				embedding_stats = embedding_service.ingest_from_canonical(
					canonical=canonical,
					source_document_id=db_stats.get("source_document_id"),
				)
				logger.info(f"Embedding ingestion complete: {embedding_stats}")
			except Exception as e:
				logger.error(f"Embedding generation failed: {e}")
				embedding_stats = {"error": str(e)}

		return {
			"status": "success",
			"filename": file.filename,
			"canonical": canonical,
			"database_stats": db_stats,
			"embedding_stats": embedding_stats,
		}

	except HTTPException:
		raise
	except Exception as exc:
		logger.error(f"Failed to ingest PDF: {exc}")
		raise HTTPException(status_code=500, detail=f"Failed to ingest PDF: {exc}") from exc
	finally:
		if tmp_path is not None and tmp_path.exists():
			try:
				os.remove(tmp_path)
			except OSError:
				pass


__all__ = ["router"]
