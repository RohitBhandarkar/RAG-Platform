"""RAG context endpoint: user API input -> K nearest embeddings + formulation details."""

import base64
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.db import (
    vector_search,
    get_formulation_context_by_uids,
    create_internal_experiment_stub,
    get_internal_experiment_by_report_id,
    update_internal_experiment_from_lab,
    update_internal_experiment_partial,
    insert_internal_experiment_embedding,
    delete_internal_experiment_embeddings_for_result,
)
from app.services.embedding_service import EmbeddingService
from app.services.rag_engine import generate_report


router = APIRouter(prefix="/RAG", tags=["RAG"])


class RAGContextRequest(BaseModel):
    """Strict API properties input for RAG context retrieval (Property / Value format)."""

    molecular_weight: float = Field(..., description="Molecular Weight (Da)", gt=0)
    melting_point_tm: Optional[float] = Field(None, description="Melting Point (Tm), °C")
    glass_transition_tg: Optional[float] = Field(None, description="Glass Transition (Tg), °C")
    log_p: Optional[float] = Field(None, description="LogP")
    bcs_class: str = Field(..., description="BCS Class (I, II, III, IV)")
    target_dose: Optional[float] = Field(None, description="Target Dose (numeric part)", ge=0)
    target_dose_unit: str = Field("mg", description="Target Dose unit (e.g. mg)")
    lipid_solubility: Optional[float] = Field(None, description="Lipid Solubility (numeric part)", ge=0)
    lipid_solubility_unit: str = Field("mg/g", description="Lipid Solubility unit (e.g. mg/g)")
    k: int = Field(5, description="Number of nearest embeddings to return", ge=1, le=20)

    class Config:
        json_schema_extra = {
            "example": {
                "molecular_weight": 914.2,
                "melting_point_tm": 185.0,
                "glass_transition_tg": 68.0,
                "log_p": 6.3,
                "bcs_class": "II",
                "target_dose": 1.0,
                "target_dose_unit": "mg",
                "lipid_solubility": 40.0,
                "lipid_solubility_unit": "mg/g",
                "k": 5,
            }
        }


class RAGContextResponse(BaseModel):
    """RAG context: nearest embeddings + formulation details for downstream LLM."""

    query_text_embedded: str = Field(..., description="The text that was embedded for the search")
    k: int = Field(..., description="Number of nearest results requested")
    nearest_embeddings: List[Dict[str, Any]] = Field(
        ...,
        description="K nearest embedding rows (id, text_content, similarity, metadata, formulation_uid)",
    )
    formulation_details: List[Dict[str, Any]] = Field(
        ...,
        description="Full formulation context per formulation_uid (formulation + excipients + manufacturing_processes)",
    )


class RAGQueryResponse(BaseModel):
    """RAG query result: report_id, markdown report (source) and PDF (for download/view)."""

    report_id: str = Field(..., description="Unique ID for this report; use when populating in-house experiment results later")
    markdown: str = Field(..., description="Experiment report in Markdown (use this to verify content if PDF is faulty)")
    pdf_base64: str = Field(..., description="PDF report as base64; decode to display or download")


def _build_query_text(body: RAGContextRequest) -> str:
    """Build search query from strict API properties (Property Value format)."""
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


@router.post(
    "/context",
    summary="Get RAG context for user API input",
    response_model=RAGContextResponse,
    response_description="K nearest embeddings and formulation details to feed to the RAG model",
)
def get_rag_context(body: RAGContextRequest) -> RAGContextResponse:
    """
    Accept user API input, embed it, retrieve K nearest formulation summary embeddings,
    and return those embeddings plus full formulation details (excipients, manufacturing)
    as context for the RAG pipeline.
    """
    query_text = _build_query_text(body)

    embedding_service = EmbeddingService()
    try:
        query_embedding = embedding_service.generate_embedding(query_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    table = "formulation_summary_embeddings"
    try:
        nearest = vector_search(
            table=table,
            query_embedding=query_embedding,
            n_results=body.k,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {e}")

    formulation_uids = []
    for row in nearest:
        uid = row.get("formulation_uid") or (row.get("metadata") or {}).get("formulation_uid")
        if uid and uid not in formulation_uids:
            formulation_uids.append(uid)

    formulation_details = get_formulation_context_by_uids(formulation_uids) if formulation_uids else []

    return RAGContextResponse(
        query_text_embedded=query_text,
        k=body.k,
        nearest_embeddings=nearest,
        formulation_details=formulation_details,
    )


@router.post(
    "/query",
    summary="Generate experiment report (markdown + PDF) from user API input",
    response_description="JSON with markdown + pdf_base64, or raw PDF when format=pdf for direct download",
)
def get_rag_query(
    body: RAGContextRequest,
    format: Literal["json", "pdf"] = Query(
        "json",
        description="'json' = markdown + pdf_base64; 'pdf' = raw PDF file (direct download, e.g. from Swagger)",
    ),
):
    """
    Same input as /RAG/context. Generates report and returns either:
    - **format=json** (default): JSON with `markdown` and `pdf_base64`.
    - **format=pdf**: Raw PDF with Content-Disposition attachment so the browser/Swagger triggers a download.
    """
    report_id = str(uuid.uuid4())
    try:
        md_output, pdf_bytes = generate_report(body, llm_base_url="vertex", report_id=report_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"LLM or PDF generation failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        create_internal_experiment_stub(
            report_id=report_id,
            bcs_class=body.bcs_class,
            molecular_weight=body.molecular_weight,
        )
    except Exception as e:
        pass  # Do not fail the response if stub creation fails (e.g. table not migrated yet)

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    if format == "pdf":
        decoded_pdf = base64.b64decode(pdf_b64)
        return Response(
            content=decoded_pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="formulation_experiment_report.pdf"',
                "X-Report-Id": report_id,
            },
        )
    return RAGQueryResponse(report_id=report_id, markdown=md_output, pdf_base64=pdf_b64)


# ---------------------------------------------------------------------------
# Internal (in-house) experiment results: fetch by report_id, populate + embed
# ---------------------------------------------------------------------------


class InternalExperimentUpdateRequest(BaseModel):
    """Lab-provided data to populate the internal experiment result for a RAG report."""

    report_id: str = Field(..., description="Report ID from the RAG/query response")
    experiment_summary: str = Field(..., description="Summary of the experiment and findings")
    notes: Optional[str] = Field(None, description="Additional notes")
    outcome: Optional[str] = Field(None, description="Outcome (e.g. success, failed, partial)")
    conducted_at: Optional[str] = Field(None, description="Date conducted (YYYY-MM-DD)")


class InternalExperimentPatchRequest(BaseModel):
    """Optional fields to update on an existing internal experiment result (e.g. notes only)."""

    experiment_summary: Optional[str] = Field(None, description="Summary of the experiment and findings")
    notes: Optional[str] = Field(None, description="Additional notes")
    outcome: Optional[str] = Field(None, description="Outcome (e.g. success, failed, partial)")
    conducted_at: Optional[str] = Field(None, description="Date conducted (YYYY-MM-DD)")


class InternalExperimentSubmitResponse(BaseModel):
    """Response after submitting or updating in-house experiment (embedding created)."""

    message: str = Field(..., description="Success message")
    internal_experiment_result: Dict[str, Any] = Field(..., description="Updated row from internal_experiment_results")


@router.get(
    "/internal-experiment-results/{report_id}",
    summary="Get in-house experiment details by report ID",
    response_description="The internal experiment result row for this report (stub or populated)",
)
def get_internal_experiment_by_report(report_id: str):
    """
    Fetch the in-house experiment record linked to the given RAG report ID.
    Use the report_id returned from POST /RAG/query. Returns 404 if not found.
    """
    row = get_internal_experiment_by_report_id(report_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No internal experiment result found for report_id={report_id}")
    return row


def _build_embedding_text_and_upsert(
    updated: dict,
    report_id: str,
    internal_experiment_result_id: int,
) -> None:
    """Build text from updated row, delete existing embeddings for this result, generate new embedding, insert."""
    parts = [
        f"BCS Class {updated['bcs_class']}",
        f"Experiment: {updated.get('experiment_summary') or 'N/A'}",
    ]
    if updated.get("molecular_weight_min") is not None or updated.get("molecular_weight_max") is not None:
        mw_min = updated.get("molecular_weight_min")
        mw_max = updated.get("molecular_weight_max")
        if mw_min is not None and mw_max is not None and mw_min == mw_max:
            parts.append(f"Molecular Weight {mw_min} Da")
        else:
            parts.append(f"Molecular weight range {mw_min or '?'}-{mw_max or '?'} Da")
    if updated.get("notes"):
        parts.append(f"Notes: {updated['notes']}")
    if updated.get("outcome"):
        parts.append(f"Outcome: {updated['outcome']}")
    text_for_embedding = ". ".join(parts)

    embedding_service = EmbeddingService()
    embedding = embedding_service.generate_embedding(text_for_embedding)

    delete_internal_experiment_embeddings_for_result(internal_experiment_result_id)
    insert_internal_experiment_embedding(
        internal_experiment_result_id=internal_experiment_result_id,
        text_content=text_for_embedding,
        embedding=embedding,
        report_id=report_id,
        metadata={"report_id": report_id},
    )


@router.post(
    "/internal-experiment-results",
    summary="Submit in-house experiment (update result + create embedding)",
    response_model=InternalExperimentSubmitResponse,
    response_description="Updated experiment row and confirmation that embedding was created for RAG.",
)
def populate_internal_experiment(body: InternalExperimentUpdateRequest):
    """
    Update the internal experiment result for the given report_id with lab findings (summary, notes, outcome, date).
    Then build text from the result, generate an embedding, and store it in internal_experiment_embeddings
    (replacing any existing embedding for this result) so it appears in future RAG similarity search.
    Use the report_id returned from POST /RAG/query.
    """
    try:
        updated = update_internal_experiment_from_lab(
            report_id=body.report_id,
            experiment_summary=body.experiment_summary,
            notes=body.notes,
            outcome=body.outcome,
            conducted_at=body.conducted_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"No internal experiment result found for report_id={body.report_id}. Generate a report first via POST /RAG/query.",
        )

    try:
        _build_embedding_text_and_upsert(updated, body.report_id, updated["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    return InternalExperimentSubmitResponse(
        message="Internal experiment updated and embedding created.",
        internal_experiment_result=updated,
    )


@router.patch(
    "/internal-experiment-results/{report_id}",
    summary="Update in-house experiment notes (and/or summary, outcome, date) and refresh embedding",
    response_model=InternalExperimentSubmitResponse,
    response_description="Updated experiment row and new embedding for RAG.",
)
def patch_internal_experiment(report_id: str, body: InternalExperimentPatchRequest):
    """
    Partially update the internal experiment result (e.g. notes only). At least one field must be provided.
    After update, a new embedding is built from the full row and stored (replacing any previous embedding for this result).
    """
    if body.experiment_summary is None and body.notes is None and body.outcome is None and body.conducted_at is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of experiment_summary, notes, outcome, or conducted_at must be provided.",
        )
    try:
        updated = update_internal_experiment_partial(
            report_id=report_id,
            experiment_summary=body.experiment_summary,
            notes=body.notes,
            outcome=body.outcome,
            conducted_at=body.conducted_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"No internal experiment result found for report_id={report_id}.",
        )

    try:
        _build_embedding_text_and_upsert(updated, report_id, updated["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    return InternalExperimentSubmitResponse(
        message="Internal experiment updated and embedding refreshed.",
        internal_experiment_result=updated,
    )
