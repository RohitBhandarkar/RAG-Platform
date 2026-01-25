"""Document API routes for research paper processing."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict
import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.data.ingestion.document_processor import DocumentProcessor
from app.data.parsers.pdf_parser import PDFParser
from app.services.llm_service import LLMService


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


__all__ = ["router"]
