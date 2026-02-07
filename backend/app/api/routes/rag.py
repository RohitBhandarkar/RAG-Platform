"""RAG context endpoint: user API input -> K nearest embeddings + formulation details."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.db import vector_search, get_formulation_context_by_uids
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
    summary="Generate experiment report (PDF) from user API input",
    response_description="PDF report: excipients, amounts, and experiments (no hallucinations)",
)
def get_rag_query(body: RAGContextRequest) -> Response:
    """
    Same input as /RAG/context. Retrieves context, then uses Vertex AI to generate a markdown
    experiment report (excipients with amounts when available, experiments to conduct).
    Converts markdown to PDF and returns it. All content is grounded in retrieved context only.
    """
    try:
        md_output, pdf_bytes = generate_report(body, llm_base_url="vertex")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"LLM or PDF generation failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = "formulation_experiment_report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
