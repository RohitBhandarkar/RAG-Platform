"""Common response schemas."""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Overall system status")
    timestamp: datetime = Field(..., description="Check timestamp")
    environment: str = Field(..., description="Environment (development/production)")
    components: Dict[str, str] = Field(..., description="Component health statuses")
    version: str = Field(..., description="API version")


class IngestionRequest(BaseModel):
    """Request schema for data ingestion."""
    sources: List[str] = Field(..., description="Data sources to ingest from", min_length=1)
    max_documents: Optional[int] = Field(100, description="Maximum documents to ingest", ge=1)
    query: Optional[str] = Field(None, description="Search query for targeted ingestion")
    
    class Config:
        json_schema_extra = {
            "example": {
                "sources": ["pubmed", "fda"],
                "max_documents": 100,
                "query": "SEDDS formulation solubility enhancement"
            }
        }


class IngestionResponse(BaseModel):
    """Response schema for data ingestion."""
    job_id: str = Field(..., description="Ingestion job identifier")
    status: str = Field(..., description="Job status (initiated, running, completed, failed)")
    message: str = Field(..., description="Status message")
    sources: List[str] = Field(..., description="Sources being ingested")
    estimated_documents: int = Field(..., description="Estimated number of documents")
    started_at: datetime = Field(..., description="Job start time")


class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: Optional[Any] = Field(None, description="Additional error details")


__all__ = [
    "HealthResponse",
    "IngestionRequest",
    "IngestionResponse",
    "ErrorResponse"
]
