"""Document Processor

Orchestrates the research paper processing pipeline:

1. Parse PDF documents using :mod:`PDFParser`.
2. Create section-aware text and table chunks for LLM consumption.
3. Delegate to :mod:`llm_service` to populate the canonical JSON schema
   for each paper.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.data.parsers.pdf_parser import PDFParser
from app.services.llm_service import LLMService


class DocumentProcessor:
    """Main document processing pipeline for research papers."""

    def __init__(self) -> None:
        self._parser = PDFParser()
        self._llm = LLMService()

    async def process_document(
        self,
        file_path: Path,
        source: str = "upload",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a single document and return canonical JSON.

        Args:
            file_path: Path to the document file.
            source: Document source (pubmed, fda, patent, upload).
            metadata: Optional additional metadata.

        Returns:
            Canonical JSON structure (see ``data/canonical.json``).
        """

        parsed = self._parser.parse(file_path)
        doc_id = str(file_path)

        text_chunks, table_chunks = self.chunk_document(
            doc_id=doc_id,
            sections=parsed.get("sections", []),
            tables=parsed.get("tables", []),
        )

        # Delegate to the LLM service to fill in the canonical schema.
        canonical = self._llm.generate_canonical(
            parsed_document=parsed,
            text_chunks=text_chunks,
            table_chunks=table_chunks,
            extra_metadata=metadata or {},
            source=source,
            doc_id=doc_id,
        )

        return canonical

    async def process_batch(
        self,
        file_paths: List[Path],
        source: str = "upload",
    ) -> List[Dict[str, Any]]:
        """Process multiple documents in batch."""

        results: List[Dict[str, Any]] = []
        for file_path in file_paths:
            result = await self.process_document(file_path, source)
            results.append(result)
        return results

    def chunk_document(
        self,
        doc_id: str,
        sections: List[Dict[str, Any]],
        tables: Optional[List[Dict[str, Any]]] = None,
        max_chars: int = 4000,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Create section-based text and table chunks.

        Text chunks follow the schema::

            {
                "chunk_id": str,
                "doc_id": str,
                "section_name": str,
                "heading_path": list[str],
                "page_start": int,
                "page_end": int,
                "text": str,
            }

        Table chunks follow the schema::

            {
                "chunk_id": str,
                "doc_id": str,
                "section_name": str | None,
                "page": int,
                "caption": str,
                "headers": list[str],
                "rows": list[list[str]],
            }

        Section-based chunking is used to preserve local context while
        ensuring each chunk stays under ``max_chars`` so prompts fit within
        typical LLM context limits.
        """

        text_chunks: List[Dict[str, Any]] = []
        table_chunks: List[Dict[str, Any]] = []

        # Text chunks
        chunk_counter = 0
        for section in sections:
            section_name = section.get("section_name", "")
            heading_path = section.get("heading_path", [section_name])
            page_start = section.get("page_start")
            page_end = section.get("page_end")
            text = section.get("text", "")

            if not text:
                continue

            start = 0
            while start < len(text):
                end = min(start + max_chars, len(text))
                chunk_text = text[start:end]
                chunk_counter += 1
                chunk_id = f"{doc_id}::text::{chunk_counter}"
                text_chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "section_name": section_name,
                        "heading_path": heading_path,
                        "page_start": page_start,
                        "page_end": page_end,
                        "text": chunk_text,
                    }
                )
                start = end

        # Table chunks (if any are provided in the parsed document)
        tables = tables or []
        for idx, table in enumerate(tables, start=1):
            chunk_id = f"{doc_id}::table::{idx}"
            table_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "section_name": table.get("section_name"),
                    "page": table.get("page"),
                    "caption": table.get("caption", ""),
                    "headers": table.get("headers", []),
                    "rows": table.get("rows", []),
                }
            )

        return text_chunks, table_chunks

