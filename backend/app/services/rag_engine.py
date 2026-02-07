"""RAG engine: retrieve context, generate markdown report via Vertex AI, convert to PDF."""

import html
import logging
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Dict, List, Tuple

import markdown
from fpdf import FPDF

from app.db import vector_search, get_formulation_context_by_uids
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


def _build_query_text_from_body(body: Any) -> str:
    """Build search query from strict API properties (same as RAG context endpoint)."""
    parts = [
        f"Molecular Weight {body.molecular_weight} Da",
        f"BCS Class {body.bcs_class}",
    ]
    if body.melting_point_tm is not None:
        parts.append(f"Melting Point Tm {body.melting_point_tm}°C")
    if body.glass_transition_tg is not None:
        parts.append(f"Glass Transition Tg {body.glass_transition_tg}°C")
    if body.log_p is not None:
        parts.append(f"LogP {body.log_p}")
    if body.target_dose is not None:
        parts.append(f"Target Dose {body.target_dose} {body.target_dose_unit}")
    if body.lipid_solubility is not None:
        parts.append(f"Lipid Solubility {body.lipid_solubility} {body.lipid_solubility_unit}")
    return ". ".join(parts)


def get_rag_context(
    body: Any,
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Fetch context the same way as POST /RAG/context: embed query, vector search, load formulation details.
    Returns (query_text, nearest_embeddings, formulation_details).
    """
    query_text = _build_query_text_from_body(body)
    embedding_service = EmbeddingService()
    query_embedding = embedding_service.generate_embedding(query_text)
    nearest = vector_search(
        table="formulation_summary_embeddings",
        query_embedding=query_embedding,
        n_results=body.k,
    )
    formulation_uids = []
    for row in nearest:
        uid = row.get("formulation_uid") or (row.get("metadata") or {}).get("formulation_uid")
        if uid and uid not in formulation_uids:
            formulation_uids.append(uid)
    formulation_details = get_formulation_context_by_uids(formulation_uids) if formulation_uids else []
    return query_text, nearest, formulation_details


def _build_report_prompt(
    query_text: str,
    formulation_details: List[Dict[str, Any]],
    nearest_embeddings: List[Dict[str, Any]],
) -> str:
    """Build the prompt for the LLM: context + strict instructions (no hallucinations)."""
    context_parts = []

    context_parts.append("## Input API properties (query)\n" + query_text)

    context_parts.append("\n## Retrieved formulation context (use ONLY this information)\n")
    if not formulation_details:
        context_parts.append("(No formulation details were retrieved. Do not invent any; state that no matching formulations were found.)")
    for i, form in enumerate(formulation_details, 1):
        block = [
            f"### Formulation {i}: {form.get('formulation_name') or form.get('formulation_uid', '')}",
            f"- Drug: {form.get('drug_name')}, BCS: {form.get('bcs_class')}, Type: {form.get('formulation_type')}",
        ]
        excipients = form.get("excipients") or []
        if excipients:
            block.append("**Excipients:**")
            for e in excipients:
                amount_str = f" {e.get('amount')} {e.get('unit', '')}" if e.get("amount") is not None else ""
                block.append(f"  - {e.get('name')} ({e.get('role') or 'role N/A'}){amount_str}")
        else:
            block.append("**Excipients:** (none listed)")
        procs = form.get("manufacturing_processes") or []
        if procs:
            block.append("**Manufacturing:**")
            for p in procs:
                block.append(f"  - {p.get('process_type') or 'process'}: {p.get('process_description') or 'See metadata'}")
        context_parts.append("\n".join(block))

    context_parts.append("\n## Retrieved text excerpts (for experiments and rationale)\n")
    for i, row in enumerate(nearest_embeddings[:10], 1):
        context_parts.append(f"[{i}] {row.get('text_content', '')[:800]}")

    context_str = "\n\n".join(context_parts)

    system = """You are a pharmaceutical formulation scientist. Write a clear, professional **experiment report** in Markdown format.

CRITICAL — NO HALLUCINATIONS: Use ONLY the information provided in the "Retrieved formulation context" and "Retrieved text excerpts" sections below. Do not invent excipients, amounts, or experiments. If something is not stated in the context, do not include it or say "not specified in source". You may summarize and rephrase only what is present in the context.

Your report must include the following sections (use only information from the context):

1. **Title** – e.g. "Formulation Experiment Report" and a one-line summary of the input API properties.
2. **Input API summary** – Brief summary of the queried properties (molecular weight, BCS class, etc.).
3. **Recommended excipients** – List the kinds of excipients that can be used, as suggested by the retrieved formulations. For each excipient, state the **amount** only if it appears in the context (e.g. "X mg", "% w/w"); otherwise write "amount not specified in source".
4. **Experiments to conduct** – Based on the retrieved context, list what experiments can be performed to test these formulations (e.g. dissolution, stability, particle size, bioavailability). Only include experiments that are mentioned or clearly implied in the provided context.
5. **Source summary** – One short paragraph noting that recommendations are based on retrieved literature/formulation data.

Output ONLY valid Markdown. No preamble or meta-commentary."""

    return f"{system}\n\n---\n\n# Context to use (do not invent anything not stated here)\n\n{context_str}"


def markdown_to_pdf(md_content: str) -> bytes:
    """Convert markdown string to PDF bytes using fpdf2 (pure Python, no system libs)."""
    html_body = markdown.markdown(
        md_content,
        extensions=["extra", "nl2br"],
    )
    return _html_to_pdf(html_body)


def _html_to_pdf(html_fragment: str) -> bytes:
    """Render HTML fragment (from markdown) to PDF using fpdf2 (pure Python, no system deps)."""
    # Normalize: wrap in a div so we have one root if fragment is multiple roots
    normalized = f"<div>{html_fragment}</div>" if not html_fragment.strip().startswith("<") else html_fragment
    parser = _HtmlToFpdfParser()
    parser.feed(normalized)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_font("Helvetica", size=11)

    for item in parser.elements:
        kind = item["kind"]
        text = item.get("text", "").strip()
        if kind == "h1":
            pdf.set_font("Helvetica", "B", 16)
            pdf.ln(4)
            pdf.multi_cell(0, 8, text)
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 11)
        elif kind == "h2":
            pdf.set_font("Helvetica", "B", 14)
            pdf.ln(4)
            pdf.multi_cell(0, 7, text)
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 11)
        elif kind == "h3":
            pdf.set_font("Helvetica", "B", 12)
            pdf.ln(3)
            pdf.multi_cell(0, 6, text)
            pdf.ln(1)
            pdf.set_font("Helvetica", "", 11)
        elif kind == "p":
            pdf.ln(2)
            pdf.multi_cell(0, 6, html.unescape(text))
            pdf.ln(1)
        elif kind == "li":
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, html.unescape("  \u2022 " + text))
            pdf.ln(1)
        elif kind == "br":
            pdf.ln(4)

    out = pdf.output(dest="S")
    return out.encode("latin-1") if isinstance(out, str) else out


class _HtmlToFpdfParser(HTMLParser):
    """Collect block elements and text for PDF rendering."""

    BLOCK_TAGS = {"h1", "h2", "h3", "p", "li", "br"}
    HEADING_TAGS = {"h1", "h2", "h3"}

    def __init__(self) -> None:
        super().__init__()
        self.elements: List[Dict[str, Any]] = []
        self._current: Dict[str, Any] = {}
        self._stack: List[str] = []
        self._text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        self._stack.append(tag)
        if tag in self.BLOCK_TAGS:
            self._current = {"kind": tag, "text": ""}
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if tag in self.BLOCK_TAGS and self._current.get("kind") == tag:
            text = "".join(self._text).strip()
            self._current["text"] = text
            self.elements.append(dict(self._current))
            self._current = {}
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._current:
            self._text.append(data)
        elif self._stack and self._stack[-1] in self.BLOCK_TAGS:
            self._text.append(data)


def generate_report(
    body: Any,
    *,
    llm_base_url: str = "vertex",
) -> Tuple[str, bytes]:
    """
    Full RAG pipeline: get context, generate markdown report via Vertex AI, convert to PDF.
    Returns (markdown_str, pdf_bytes).
    """
    query_text, nearest, formulation_details = get_rag_context(body)
    prompt = _build_report_prompt(query_text, formulation_details, nearest)
    llm = LLMService(base_url=llm_base_url)
    md_output = llm.generate_text(prompt)
    pdf_bytes = markdown_to_pdf(md_output)
    return md_output, pdf_bytes
