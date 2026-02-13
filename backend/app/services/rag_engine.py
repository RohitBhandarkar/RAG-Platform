"""RAG engine: retrieve context, generate markdown report via Vertex AI, convert to PDF."""

import logging
import re
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Dict, List, Tuple

import markdown
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.db import (
    vector_search,
    get_formulation_context_by_uids,
    get_internal_experiment_results_by_ids,
)
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Confidence: numeric score (0-1) from formulation count, has_amount, and
# pgvector similarity. Tiers: High >= 0.66, Medium 0.33-0.66, Low < 0.33.
# Formula: 0.35 * count_factor + 0.15 * has_amount + 0.5 * avg_similarity.
# ---------------------------------------------------------------------------


def _normalize_excipient_name(name: str) -> str:
    """Normalize for matching: lowercase, strip, collapse spaces."""
    if not name or not isinstance(name, str):
        return ""
    return " ".join(name.lower().strip().split())


def _compute_excipient_confidence(
    formulation_details: List[Dict[str, Any]],
    nearest_embeddings: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Compute numeric confidence (0-1) and tier per excipient from retrieved
    formulations and vector similarities. Returns dict: normalized_name ->
    { display_name, formulation_count, has_amount, confidence, confidence_score }.
    """
    # uid -> similarity (from pgvector); preserve order for rank if needed
    uid_to_similarity: Dict[str, float] = {}
    for i, row in enumerate(nearest_embeddings or []):
        uid = row.get("formulation_uid") or (row.get("metadata") or {}).get("formulation_uid")
        if uid is not None:
            uid_to_similarity[uid] = float(row.get("similarity") or 0.0)

    # aggregated by normalized name: count, has_amount, display_name, list of similarities
    agg: Dict[str, Dict[str, Any]] = {}
    for form in formulation_details or []:
        uid = form.get("formulation_uid")
        sim = uid_to_similarity.get(uid, 0.0) if uid else 0.0
        for e in form.get("excipients") or []:
            name = (e.get("name") or "").strip()
            if not name:
                continue
            key = _normalize_excipient_name(name)
            if not key:
                continue
            if key not in agg:
                agg[key] = {
                    "display_name": name,
                    "formulation_count": 0,
                    "has_amount": False,
                    "similarities": [],
                }
            agg[key]["formulation_count"] += 1
            agg[key]["similarities"].append(sim)
            if e.get("amount") is not None:
                agg[key]["has_amount"] = True

    k = max(len(nearest_embeddings), 1)
    result: Dict[str, Dict[str, Any]] = {}
    for key, v in agg.items():
        count = v["formulation_count"]
        has_amount = v["has_amount"]
        sims = v.get("similarities") or [0.0]
        avg_sim = sum(sims) / len(sims) if sims else 0.0
        count_factor = min(count / 3.0, 1.0)
        score = (
            0.35 * count_factor
            + 0.15 * (1.0 if has_amount else 0.0)
            + 0.5 * avg_sim
        )
        score = max(0.0, min(1.0, score))
        if score >= 0.66:
            tier = "High"
        elif score >= 0.33:
            tier = "Medium"
        else:
            tier = "Low"
        result[key] = {
            "display_name": v["display_name"],
            "formulation_count": count,
            "has_amount": has_amount,
            "confidence": tier,
            "confidence_score": round(score, 2),
        }
    return result


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
) -> Tuple[str, List[float], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Fetch context the same way as POST /RAG/context: embed query, vector search, load formulation details.
    Returns (query_text, query_embedding, nearest_embeddings, formulation_details).
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
    return query_text, query_embedding, nearest, formulation_details


def _build_report_prompt(
    query_text: str,
    formulation_details: List[Dict[str, Any]],
    nearest_embeddings: List[Dict[str, Any]],
    internal_experiment_results: List[Dict[str, Any]] | None = None,
) -> str:
    """Build the prompt for the LLM: context + strict instructions (no hallucinations)."""
    context_parts = []
    internal_list = internal_experiment_results or []

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

    # Excipient confidence: numeric score (0-1) + tier (High/Medium/Low)
    confidence_map = _compute_excipient_confidence(formulation_details, nearest_embeddings)
    context_parts.append("\n## Excipient metadata (include in report for each excipient)\n")
    if not confidence_map:
        context_parts.append("(No excipients in retrieved formulations.)")
    else:
        for key, meta in confidence_map.items():
            display = meta.get("display_name", key)
            conf = meta.get("confidence", "Low")
            score = meta.get("confidence_score", 0.0)
            context_parts.append(f"- **{display}**: Confidence = {conf} ({score})")

    context_parts.append("\n## Internal (in-house) experimentation")
    if not internal_list:
        context_parts.append("(No relevant in-house experimentation data found for this API profile.)")
    else:
        for i, row in enumerate(internal_list, 1):
            block = [
                f"### Internal result {i}",
                f"- Summary: {row.get('experiment_summary') or 'N/A'}",
            ]
            if row.get("notes"):
                block.append(f"- Notes: {row['notes']}")
            if row.get("outcome"):
                block.append(f"- Outcome: {row['outcome']}")
            if row.get("conducted_at"):
                block.append(f"- Conducted: {row['conducted_at']}")
            context_parts.append("\n".join(block))

    context_str = "\n\n".join(context_parts)

    system = """You are a pharmaceutical formulation scientist. Write a clear, professional **experiment report** in Markdown format.

CRITICAL — NO HALLUCINATIONS: Use ONLY the information provided in the "Retrieved formulation context" and "Retrieved text excerpts" sections below. Do not invent excipients, amounts, or experiments. If something is not stated in the context, do not include it or say "not specified in source". You may summarize and rephrase only what is present in the context.

Your report must include the following sections (use only information from the context):

1. **Title** – e.g. "Formulation Experiment Report" and a one-line summary of the input API properties.
2. **Input API summary** – Brief summary of the queried properties (molecular weight, BCS class, etc.).
3. **Recommended excipients** – List each excipient BY NAME (from "Retrieved formulation context"), with its amount when present, then the confidence for that excipient (from "Excipient metadata"). Format each line as: **Excipient Name**: amount or "amount not specified in source" — Confidence: High/Medium/Low (numeric score). Example: **HPMC E3**: 0.98 mg/mL — Confidence: Medium (0.72). You must include both the tier (High/Medium/Low) and the numeric score in parentheses. You may group by role (e.g. Stabilizers, Polymer carriers) as in the context. Do NOT list confidence alone; every bullet must include excipient name, then amount, then confidence with score.
4. **Experiments to conduct** – Based on the retrieved context, list what experiments can be performed to test these formulations (e.g. dissolution, stability, particle size, bioavailability). Only include experiments that are mentioned or clearly implied in the provided context.
5. **Internal (in-house) experimentation** – Use ONLY the "Internal (in-house) experimentation" section of the context. If that section contains one or more internal results: summarize the relevant in-house experiment results and notes (summary, outcome, conducted date when present). If the context states "(No relevant in-house experimentation data found for this API profile.)", then state clearly that **this is a novel experiment that has not been conducted in-house before**.
6. **Source summary** – One short paragraph noting that recommendations are based on retrieved literature/formulation data.

Output ONLY valid Markdown. No preamble or meta-commentary."""

    return f"{system}\n\n---\n\n# Context to use (do not invent anything not stated here)\n\n{context_str}"


def markdown_to_pdf(md_content: str) -> bytes:
    """Convert markdown to PDF using ReportLab (Unicode-safe, good formatting)."""
    html_body = markdown.markdown(
        md_content,
        extensions=["extra", "nl2br"],
    )
    return _html_to_pdf_reportlab(html_body)


def _reportlab_markup(inner_html: str) -> str:
    """Normalize HTML for ReportLab Paragraph: <strong> -> <b>, escape &, fix invalid </br>."""
    s = inner_html.strip()
    s = re.sub(r"<strong>", "<b>", s, flags=re.I)
    s = re.sub(r"</strong>", "</b>", s, flags=re.I)
    # ReportLab has no _selfClosingTag for </br>; remove invalid closing tag (only <br/> is valid).
    s = re.sub(r"</br\s*>", "", s, flags=re.I)
    s = s.replace("&", "&amp;")
    return s


def _html_to_pdf_reportlab(html_fragment: str) -> bytes:
    """Render HTML fragment to PDF with ReportLab (Unicode, headings, lists, bold)."""
    parser = _BlockHtmlParser()
    parser.feed(html_fragment.strip())
    elements = parser.elements

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    h1_style = ParagraphStyle(
        "CustomH1",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=8,
        spaceBefore=4,
    )
    h2_style = ParagraphStyle(
        "CustomH2",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=6,
        spaceBefore=10,
    )
    h3_style = ParagraphStyle(
        "CustomH3",
        parent=styles["Heading3"],
        fontSize=12,
        spaceAfter=4,
        spaceBefore=8,
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=6,
        spaceBefore=0,
    )
    list_style = ParagraphStyle(
        "CustomList",
        parent=styles["Normal"],
        fontSize=11,
        leftIndent=20,
        spaceAfter=2,
        bulletIndent=10,
    )

    story: List[Any] = []
    for item in elements:
        kind = item["kind"]
        raw = item.get("inner_html", "").strip()
        markup = _reportlab_markup(raw)
        if not markup:
            continue
        if kind == "h1":
            story.append(Paragraph(markup, h1_style))
        elif kind == "h2":
            story.append(Paragraph(markup, h2_style))
        elif kind == "h3":
            story.append(Paragraph(markup, h3_style))
        elif kind == "p":
            story.append(Paragraph(markup, body_style))
        elif kind == "li":
            # ReportLab Paragraph supports Unicode; bullet is safe
            story.append(Paragraph("&#8226; " + markup, list_style))
        elif kind == "br":
            story.append(Spacer(1, 12))

    doc.build(story)
    return buf.getvalue()


class _BlockHtmlParser(HTMLParser):
    """Extract block elements with their inner HTML for ReportLab."""

    BLOCK_TAGS = {"h1", "h2", "h3", "p", "li", "br"}

    def __init__(self) -> None:
        super().__init__()
        self.elements: List[Dict[str, Any]] = []
        self._stack: List[str] = []
        self._current_tag: str | None = None
        self._inner_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        if tag in self.BLOCK_TAGS:
            if tag == "br":
                if self._current_tag:
                    self._inner_parts.append("<br/>")
                else:
                    self.elements.append({"kind": "br", "inner_html": ""})
                return
            self._stack.append(tag)
            self._current_tag = tag
            self._inner_parts = []
        elif self._current_tag and self._inner_parts is not None:
            attrs_str = "".join(f' {k}="{v}"' for k, v in attrs if v)
            self._inner_parts.append(f"<{tag}{attrs_str}>")

    def handle_endtag(self, tag: str) -> None:
        if self._current_tag and tag == self._current_tag:
            inner = "".join(self._inner_parts).strip()
            self.elements.append({"kind": tag, "inner_html": inner})
            self._current_tag = None
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()
        elif self._current_tag and self._inner_parts is not None:
            self._inner_parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._current_tag and self._inner_parts is not None:
            self._inner_parts.append(data)


def generate_report(
    body: Any,
    *,
    llm_base_url: str = "vertex",
    report_id: str | None = None,
) -> Tuple[str, bytes]:
    """
    Full RAG pipeline: get context, generate markdown report via Vertex AI, convert to PDF.
    If report_id is provided, it is appended to the markdown (and thus visible in the PDF).
    Returns (markdown_str, pdf_bytes).
    """
    query_text, query_embedding, nearest, formulation_details = get_rag_context(body)
    internal_embedding_hits = vector_search(
        table="internal_experiment_embeddings",
        query_embedding=query_embedding,
        n_results=10,
    )
    internal_result_ids = [
        row["internal_experiment_result_id"]
        for row in internal_embedding_hits
        if row.get("internal_experiment_result_id") is not None
    ]
    internal_results = get_internal_experiment_results_by_ids(internal_result_ids)
    prompt = _build_report_prompt(query_text, formulation_details, nearest, internal_results)
    llm = LLMService(base_url=llm_base_url)
    md_output = llm.generate_text(prompt)
    if report_id:
        md_output = (
            "**Report ID:** `"
            + report_id
            + "`\n\n*Use this ID when submitting in-house experiment results (POST /RAG/internal-experiment-results).*\n\n---\n\n"
            + md_output
        )
    pdf_bytes = markdown_to_pdf(md_output)
    return md_output, pdf_bytes
