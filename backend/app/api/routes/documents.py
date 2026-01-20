"""Document API routes for research paper processing."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict
import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.data.ingestion.document_processor import DocumentProcessor


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


__all__ = ["router"]
