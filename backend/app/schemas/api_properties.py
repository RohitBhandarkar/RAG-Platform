"""API properties schemas."""

from pydantic import BaseModel, Field
from typing import Optional


class APIProperties(BaseModel):
    """Active Pharmaceutical Ingredient (API) properties."""
    molecular_weight: float = Field(..., description="Molecular weight (g/mol)", gt=0)
    melting_point: Optional[float] = Field(None, description="Melting point (°C)")
    pka: Optional[float] = Field(None, description="pKa value")
    log_p: Optional[float] = Field(None, description="LogP (partition coefficient)")
    solubility: Optional[float] = Field(None, description="Aqueous solubility (mg/mL)", ge=0)
    bcs_class: Optional[str] = Field(None, description="Biopharmaceutics Classification System class")


class APIPropertiesInput(BaseModel):
    """Input schema for API properties."""
    molecular_weight: float = Field(..., description="Molecular weight (g/mol)", gt=0)
    melting_point: Optional[float] = Field(None, description="Melting point (°C)")
    pka: Optional[float] = Field(None, description="pKa value")
    log_p: Optional[float] = Field(None, description="LogP (partition coefficient)")
    solubility: Optional[float] = Field(None, description="Aqueous solubility (mg/mL)", ge=0)


__all__ = ["APIProperties", "APIPropertiesInput"]
