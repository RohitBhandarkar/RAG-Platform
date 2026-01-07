"""Formulation-related Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class APIProperties(BaseModel):
    """Active Pharmaceutical Ingredient (API) properties."""
    molecular_weight: float = Field(..., description="Molecular weight (g/mol)", gt=0)
    melting_point: Optional[float] = Field(None, description="Melting point (°C)")
    pka: Optional[float] = Field(None, description="pKa value")
    log_p: Optional[float] = Field(None, description="LogP (partition coefficient)")
    solubility: Optional[float] = Field(None, description="Aqueous solubility (mg/mL)", ge=0)
    bcs_class: Optional[str] = Field(None, description="Biopharmaceutics Classification System class")


class RAGQueryRequest(BaseModel):
    """Request schema for RAG query endpoint."""
    molecular_weight: float = Field(..., description="Molecular weight (g/mol)", gt=0)
    melting_point: Optional[float] = Field(None, description="Melting point (°C)")
    pka: Optional[float] = Field(None, description="pKa value")
    log_p: Optional[float] = Field(None, description="LogP (partition coefficient)")
    solubility: Optional[float] = Field(None, description="Aqueous solubility (mg/mL)", ge=0)
    
    # Optional query parameters
    target_platform: Optional[str] = Field(None, description="Preferred formulation platform (SEDDS, ASD, Nanosuspension)")
    max_results: int = Field(5, description="Maximum number of retrieved documents", ge=1, le=20)
    
    class Config:
        json_schema_extra = {
            "example": {
                "molecular_weight": 450.5,
                "melting_point": 180.0,
                "pka": 7.2,
                "log_p": 3.5,
                "solubility": 0.05,
                "target_platform": "SEDDS",
                "max_results": 5
            }
        }


class FormulationStrategy(BaseModel):
    """A single formulation strategy recommendation."""
    platform: str = Field(..., description="Formulation platform (SEDDS, ASD, Nanosuspension)")
    description: str = Field(..., description="Strategy description and rationale")
    excipients: List[str] = Field(..., description="Recommended excipients")
    ratios: str = Field(..., description="Excipient ratios")
    processing_notes: str = Field(..., description="Processing conditions and notes")


class RetrievedDocument(BaseModel):
    """Information about a retrieved document."""
    document_id: str = Field(..., description="Document identifier")
    title: str = Field(..., description="Document title")
    relevance_score: float = Field(..., description="Relevance score (0-1)", ge=0, le=1)
    excerpt: str = Field(..., description="Relevant excerpt from document")


class RAGQueryResponse(BaseModel):
    """Response schema for RAG query endpoint."""
    query_id: str = Field(..., description="Unique query identifier")
    formulation_strategies: List[FormulationStrategy] = Field(..., description="Formulation recommendations")
    experimental_plan: str = Field(..., description="Experimental plan and procedures")
    risk_analysis: str = Field(..., description="Risk analysis and mitigation strategies")
    cmc_guidelines: str = Field(..., description="CMC documentation guidelines")
    retrieved_documents: List[RetrievedDocument] = Field(..., description="Retrieved source documents")
    processing_time_ms: int = Field(..., description="Query processing time in milliseconds")


__all__ = [
    "APIProperties",
    "RAGQueryRequest",
    "RAGQueryResponse",
    "FormulationStrategy",
    "RetrievedDocument"
]
