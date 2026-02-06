"""Embedding service using Vertex AI text-embedding-004.

This service generates embeddings for text content and stores them in pgvector.
"""

import logging
from typing import Optional

import google.auth
from google.auth.transport.requests import Request
import requests

from app.config import settings
from app.db import engine
from sqlalchemy import text


logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using Vertex AI text-embedding-004."""
    
    def __init__(self):
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.project_id = settings.GOOGLE_CLOUD_PROJECT
        self.location = settings.VERTEX_LOCATION
        self.endpoint = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/google/models/{self.model}:predict"
        )
        self._credentials = None
    
    def _get_access_token(self) -> str:
        """Get a valid access token for Vertex AI API calls."""
        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        
        return self._credentials.token
    
    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for a single text string.
        
        Args:
            text: The text to embed
            
        Returns:
            list[float]: 768-dimensional embedding vector
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "instances": [{"content": text}],
            "parameters": {"outputDimensionality": self.dimension}
        }
        
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            
            result = response.json()
            embedding = result["predictions"][0]["embeddings"]["values"]
            
            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Embedding API request failed: {e}")
            raise RuntimeError(f"Failed to generate embedding: {e}")
    
    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in a single API call.
        
        Args:
            texts: List of texts to embed (max 250 per batch)
            
        Returns:
            list[list[float]]: List of 768-dimensional embedding vectors
        """
        if not texts:
            return []
        
        # Vertex AI supports up to 250 instances per request
        if len(texts) > 250:
            raise ValueError("Maximum 250 texts per batch")
        
        # Filter out empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            raise ValueError("All texts are empty")
        
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "instances": [{"content": t} for t in valid_texts],
            "parameters": {"outputDimensionality": self.dimension}
        }
        
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            
            result = response.json()
            embeddings = [
                pred["embeddings"]["values"] 
                for pred in result["predictions"]
            ]
            
            logger.info(f"Generated {len(embeddings)} embeddings in batch")
            return embeddings
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Batch embedding API request failed: {e}")
            raise RuntimeError(f"Failed to generate embeddings: {e}")
    
    def check_health(self) -> dict:
        """
        Check if the embedding service is operational.
        
        Returns:
            dict: Health status with model info
        """
        try:
            # Try to generate a test embedding
            test_embedding = self.generate_embedding("health check")
            return {
                "status": "healthy",
                "model": self.model,
                "dimension": len(test_embedding),
                "endpoint": self.endpoint,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.model,
                "error": str(e),
            }


class EmbeddingIngestionService:
    """Service for populating embedding tables from canonical JSON."""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
    
    def _build_formulation_summary_text(self, canonical: dict, formulation: dict) -> str:
        """Build text representation for formulation summary embedding."""
        parts = []
        
        # API info from canonical root
        api = canonical.get("api", {})
        if api.get("name"):
            parts.append(f"API: {api['name']}")
        if api.get("bcs_class"):
            parts.append(f"BCS Class: {api['bcs_class']}")
        if api.get("molecular_weight"):
            parts.append(f"MW: {api['molecular_weight']}")
        if api.get("aqueous_solubility"):
            parts.append(f"Solubility: {api['aqueous_solubility']}")
        
        # Formulation strategy
        strategy = formulation.get("formulation_strategy", {})
        if strategy.get("strategy_name"):
            parts.append(f"Strategy: {strategy['strategy_name']}")
        if strategy.get("description"):
            parts.append(f"Description: {strategy['description']}")
        
        # Components (excipients)
        components = formulation.get("components", [])
        if components:
            comp_list = []
            for comp in components:
                name = comp.get("name", "")
                role = comp.get("role", "")
                amount = comp.get("amount", {})
                val = amount.get("value", "")
                unit = amount.get("unit", "")
                if name:
                    comp_str = f"{name} ({role})" if role else name
                    if val:
                        comp_str += f" {val}{unit}"
                    comp_list.append(comp_str)
            if comp_list:
                parts.append(f"Components: {', '.join(comp_list)}")
        
        # Stage
        if formulation.get("stage"):
            parts.append(f"Stage: {formulation['stage']}")
        
        return ". ".join(parts) if parts else "Formulation data"
    
    def _build_manufacturing_text(self, formulation: dict) -> str:
        """Build text representation for manufacturing process embedding."""
        parts = []
        
        process = formulation.get("process", {})
        
        if process.get("method"):
            parts.append(f"Method: {process['method']}")
        
        # Milling parameters
        milling = process.get("milling", {})
        if milling:
            milling_parts = []
            if milling.get("time_min"):
                milling_parts.append(f"Time: {milling['time_min']} min")
            if milling.get("bead_size_mm"):
                milling_parts.append(f"Bead size: {milling['bead_size_mm']} mm")
            if milling.get("rpm"):
                milling_parts.append(f"RPM: {milling['rpm']}")
            if milling_parts:
                parts.append(f"Milling: {', '.join(milling_parts)}")
        
        if process.get("solvent_system"):
            parts.append(f"Solvent: {process['solvent_system']}")
        if process.get("temperature_c"):
            parts.append(f"Temperature: {process['temperature_c']}°C")
        if process.get("mixing"):
            parts.append(f"Mixing: {process['mixing']}")
        if process.get("notes"):
            parts.append(f"Notes: {process['notes']}")
        
        return ". ".join(parts) if parts else "Manufacturing process data"
    
    def _build_particle_analytics_text(self, formulation: dict) -> str:
        """Build text representation for particle characteristics embedding."""
        parts = []
        
        particle = formulation.get("particle_characteristics", {})
        
        if particle.get("particle_size_distribution_nm"):
            parts.append(f"Particle size: {particle['particle_size_distribution_nm']}")
        if particle.get("zeta_potential_mv"):
            parts.append(f"Zeta potential: {particle['zeta_potential_mv']} mV")
        if particle.get("dissolution_profile"):
            parts.append(f"Dissolution: {particle['dissolution_profile']}")
        
        return ". ".join(parts) if parts else "Particle characteristics data"
    
    def _build_stability_text(self, formulation: dict) -> str:
        """Build text representation for stability data (in_vitro category)."""
        parts = []
        
        stability = formulation.get("stability", {})
        
        if stability.get("conditions"):
            parts.append(f"Conditions: {stability['conditions']}")
        if stability.get("duration_months"):
            parts.append(f"Duration: {stability['duration_months']} months")
        if stability.get("summary"):
            parts.append(f"Summary: {stability['summary']}")
        
        # Also include dissolution profile from particle_characteristics
        particle = formulation.get("particle_characteristics", {})
        if particle.get("dissolution_profile"):
            parts.append(f"Dissolution: {particle['dissolution_profile']}")
        
        return ". ".join(parts) if parts else "Stability and in vitro data"
    
    def _build_pk_text(self, formulation: dict) -> str:
        """Build text representation for PK study embedding."""
        parts = []
        
        pk = formulation.get("pharmacokinetics", {})
        
        if pk.get("relative_bioavailability"):
            parts.append(f"Relative BA: {pk['relative_bioavailability']}%")
        if pk.get("cmax"):
            parts.append(f"Cmax: {pk['cmax']}")
        if pk.get("auc"):
            parts.append(f"AUC: {pk['auc']}")
        if pk.get("tmax"):
            parts.append(f"Tmax: {pk['tmax']}")
        
        return ". ".join(parts) if parts else "Pharmacokinetic data"
    
    def ingest_from_canonical(self, canonical: dict, source_document_id: int = None) -> dict:
        """
        Generate and store embeddings for all data in a canonical JSON.
        
        Args:
            canonical: The canonical JSON dict with document, api, formulations, metadata
            source_document_id: Optional ID linking to source_documents table
            
        Returns:
            dict: Statistics for each embedding type
        """
        stats = {
            "formulation_summary": {"processed": 0, "embedded": 0, "errors": 0},
            "manufacturing_process": {"processed": 0, "embedded": 0, "errors": 0},
            "particle_analytics": {"processed": 0, "embedded": 0, "errors": 0},
            "in_vitro": {"processed": 0, "embedded": 0, "errors": 0},
            "in_vivo": {"processed": 0, "embedded": 0, "errors": 0},
        }
        
        formulations = canonical.get("formulations", [])
        document = canonical.get("document", {})
        doc_title = document.get("title", "Unknown document")
        
        for idx, formulation in enumerate(formulations):
            form_id = formulation.get("formulation_id", f"form_{idx}")
            
            # 1. Formulation Summary Embedding
            stats["formulation_summary"]["processed"] += 1
            try:
                text_content = self._build_formulation_summary_text(canonical, formulation)
                if text_content and text_content != "Formulation data":
                    embedding = self.embedding_service.generate_embedding(text_content)
                    self._store_embedding(
                        table="formulation_summary_embeddings",
                        text_content=text_content,
                        embedding=embedding,
                        metadata={"formulation_id": form_id, "document": doc_title},
                        source_document_id=source_document_id,
                    )
                    stats["formulation_summary"]["embedded"] += 1
            except Exception as e:
                logger.error(f"Error embedding formulation summary {form_id}: {e}")
                stats["formulation_summary"]["errors"] += 1
            
            # 2. Manufacturing Process Embedding
            stats["manufacturing_process"]["processed"] += 1
            try:
                text_content = self._build_manufacturing_text(formulation)
                if text_content and text_content != "Manufacturing process data":
                    embedding = self.embedding_service.generate_embedding(text_content)
                    self._store_embedding(
                        table="manufacturing_process_embeddings",
                        text_content=text_content,
                        embedding=embedding,
                        metadata={"formulation_id": form_id, "document": doc_title},
                        source_document_id=source_document_id,
                    )
                    stats["manufacturing_process"]["embedded"] += 1
            except Exception as e:
                logger.error(f"Error embedding manufacturing {form_id}: {e}")
                stats["manufacturing_process"]["errors"] += 1
            
            # 3. Particle Analytics Embedding
            stats["particle_analytics"]["processed"] += 1
            try:
                text_content = self._build_particle_analytics_text(formulation)
                if text_content and text_content != "Particle characteristics data":
                    embedding = self.embedding_service.generate_embedding(text_content)
                    self._store_embedding(
                        table="particle_analytics_embeddings",
                        text_content=text_content,
                        embedding=embedding,
                        metadata={"formulation_id": form_id, "document": doc_title},
                        source_document_id=source_document_id,
                    )
                    stats["particle_analytics"]["embedded"] += 1
            except Exception as e:
                logger.error(f"Error embedding particle analytics {form_id}: {e}")
                stats["particle_analytics"]["errors"] += 1
            
            # 4. In Vitro (Stability/Dissolution) Embedding
            stats["in_vitro"]["processed"] += 1
            try:
                text_content = self._build_stability_text(formulation)
                if text_content and text_content != "Stability and in vitro data":
                    embedding = self.embedding_service.generate_embedding(text_content)
                    self._store_embedding(
                        table="in_vitro_embeddings",
                        text_content=text_content,
                        embedding=embedding,
                        metadata={"formulation_id": form_id, "document": doc_title},
                        source_document_id=source_document_id,
                    )
                    stats["in_vitro"]["embedded"] += 1
            except Exception as e:
                logger.error(f"Error embedding in vitro {form_id}: {e}")
                stats["in_vitro"]["errors"] += 1
            
            # 5. In Vivo (PK) Embedding
            stats["in_vivo"]["processed"] += 1
            try:
                text_content = self._build_pk_text(formulation)
                if text_content and text_content != "Pharmacokinetic data":
                    embedding = self.embedding_service.generate_embedding(text_content)
                    self._store_embedding(
                        table="in_vivo_embeddings",
                        text_content=text_content,
                        embedding=embedding,
                        metadata={"formulation_id": form_id, "document": doc_title},
                        source_document_id=source_document_id,
                    )
                    stats["in_vivo"]["embedded"] += 1
            except Exception as e:
                logger.error(f"Error embedding in vivo {form_id}: {e}")
                stats["in_vivo"]["errors"] += 1
        
        logger.info(f"Canonical embedding ingestion complete: {stats}")
        return stats
    
    def _store_embedding(
        self,
        table: str,
        text_content: str,
        embedding: list[float],
        metadata: dict,
        source_document_id: int = None,
    ):
        """Store an embedding in the appropriate table."""
        import json
        
        with engine.connect() as conn:
            # Use a generic insert that works for all embedding tables
            # The foreign key columns vary by table, so we store references in metadata
            if source_document_id:
                metadata["source_document_id"] = source_document_id
            
            insert_query = text(f"""
                INSERT INTO {table} 
                (text_content, embedding, metadata)
                VALUES (:text, :emb::vector, :meta::jsonb)
            """)
            
            conn.execute(insert_query, {
                "text": text_content,
                "emb": f"[{','.join(str(x) for x in embedding)}]",
                "meta": json.dumps(metadata),
            })
            conn.commit()
    
    def get_embedding_texts_preview(self, canonical: dict) -> dict:
        """
        Preview what text would be embedded for each category (without generating embeddings).
        
        Args:
            canonical: The canonical JSON dict
            
        Returns:
            dict: Text previews for each formulation and category
        """
        previews = []
        
        formulations = canonical.get("formulations", [])
        
        for idx, formulation in enumerate(formulations):
            form_id = formulation.get("formulation_id", f"form_{idx}")
            previews.append({
                "formulation_id": form_id,
                "texts": {
                    "formulation_summary": self._build_formulation_summary_text(canonical, formulation),
                    "manufacturing_process": self._build_manufacturing_text(formulation),
                    "particle_analytics": self._build_particle_analytics_text(formulation),
                    "in_vitro": self._build_stability_text(formulation),
                    "in_vivo": self._build_pk_text(formulation),
                }
            })
        
        return {"formulation_count": len(formulations), "previews": previews}


__all__ = ["EmbeddingService", "EmbeddingIngestionService"]
