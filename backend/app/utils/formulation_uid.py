"""Deterministic formulation UID for linking DB and embedding ingestion without DB lookup."""

import re
from typing import Any, Dict, Optional


def _sanitize_base(s: str) -> str:
    """Make a string safe for use in formulation_uid (no slashes, minimal length)."""
    if not s or not isinstance(s, str):
        return ""
    # Replace chars that could break paths or URLs; collapse spaces
    s = re.sub(r"[/\\\s]+", "_", s.strip())
    return s[:512] if s else ""


def document_base_id(document: Dict[str, Any], source_id: Optional[str] = None) -> str:
    """
    Compute a stable document identifier from canonical document or source_id.

    Prefer document fields (doi, pmid, url, title+year) so DB and embedding
    ingestion produce the same UID when given the same canonical. Use source_id
    only when document has no usable fields (e.g. user upload with no metadata).

    Args:
        document: canonical["document"] (title, doi, pmid, url, year, ...)
        source_id: optional external id (filename, PMID, etc.) from ingest caller

    Returns:
        Sanitized string suitable as the base part of formulation_uid.
    """
    doc = document or {}
    base = (
        doc.get("doi")
        or doc.get("pmid")
        or doc.get("url")
        or (
            _sanitize_base(str(doc.get("title") or "untitled"))
            + "_"
            + str(doc.get("year") or "")
        )
    )
    if isinstance(base, (int, float)):
        base = str(base)
    else:
        base = _sanitize_base(base) if base else ""
    if not base and source_id:
        base = _sanitize_base(str(source_id))
    if not base:
        base = "doc_unknown"
    return base


def formulation_uid_from_canonical(
    document: Dict[str, Any],
    formulation_index: int,
    source_id: Optional[str] = None,
) -> str:
    """
    Deterministic formulation UID from canonical document and formulation index.

    Both DatabaseIngestionService and EmbeddingIngestionService use this so
    embeddings link to formulations without any DB lookup. Same canonical +
    index always yields the same UID.

    Args:
        document: canonical["document"]
        formulation_index: 0-based index of the formulation in formulations[]

    Returns:
        formulation_uid string, e.g. "10.1016_j.ejpb.2013.12.016#0"
    """
    base = document_base_id(document, source_id)
    return f"{base}#{formulation_index}"
