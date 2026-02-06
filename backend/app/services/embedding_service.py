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
        
        # Formulation name
        if formulation.get("name"):
            parts.append(f"Formulation: {formulation['name']}")
        
        # Drug/API info - check both structures
        drug = formulation.get("drug", {})
        if drug.get("name"):
            parts.append(f"API: {drug['name']}")
        if drug.get("solubility"):
            parts.append(f"Solubility: {drug['solubility']}")
        metadata = drug.get("metadata", {})
        if metadata.get("bcs_class"):
            parts.append(f"BCS Class: {metadata['bcs_class']}")
        
        # Also check canonical root level api (alternate schema)
        api = canonical.get("api", {})
        if api.get("name") and not drug.get("name"):
            parts.append(f"API: {api['name']}")
        if api.get("bcs_class") and not metadata.get("bcs_class"):
            parts.append(f"BCS Class: {api['bcs_class']}")
        
        # Formulation type and dosage form
        if formulation.get("formulation_type"):
            parts.append(f"Type: {formulation['formulation_type']}")
        if formulation.get("dosage_form"):
            parts.append(f"Dosage Form: {formulation['dosage_form']}")
        
        # Composition - active ingredients
        composition = formulation.get("composition", {})
        actives = composition.get("active_ingredients", [])
        if actives:
            active_list = []
            for a in actives:
                name = a.get("name", "")
                conc = a.get("concentration")
                unit = a.get("unit", "")
                if name:
                    if conc is not None:
                        active_list.append(f"{name} {conc} {unit}".strip())
                    else:
                        active_list.append(name)
            if active_list:
                parts.append(f"Active ingredients: {', '.join(active_list)}")
        
        # Composition - excipients
        excipients = composition.get("excipients", [])
        if excipients:
            exc_list = []
            for e in excipients:
                name = e.get("name", "")
                role = e.get("role", "")
                conc = e.get("concentration")
                unit = e.get("unit", "")
                if name:
                    exc_str = f"{name}"
                    if role:
                        exc_str += f" ({role})"
                    if conc is not None:
                        exc_str += f" {conc} {unit}".strip()
                    exc_list.append(exc_str)
            if exc_list:
                parts.append(f"Excipients: {', '.join(exc_list)}")
        
        # Also check old schema components
        components = formulation.get("components", [])
        if components and not excipients:
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
        
        return ". ".join(parts) if parts else "Formulation data"
    
    def _build_manufacturing_text(self, formulation: dict) -> str:
        """Build text representation for manufacturing process embedding."""
        parts = []
        
        # New schema: manufacturing
        manufacturing = formulation.get("manufacturing", {})
        if manufacturing:
            if manufacturing.get("process_name"):
                parts.append(f"Process: {manufacturing['process_name']}")
            
            params = manufacturing.get("process_parameters", {})
            if params:
                if params.get("equipment"):
                    parts.append(f"Equipment: {params['equipment']}")
                if params.get("speed") and params.get("speed_unit"):
                    parts.append(f"Speed: {params['speed']} {params['speed_unit']}")
                if params.get("duration") and params.get("duration_unit"):
                    parts.append(f"Duration: {params['duration']} {params['duration_unit']}")
                if params.get("milling_media"):
                    parts.append(f"Milling media: {params['milling_media']}")
                if params.get("milling_media_size"):
                    parts.append(f"Bead size: {params['milling_media_size']} {params.get('milling_media_size_unit', 'mm')}")
                if params.get("inlet_temperature"):
                    parts.append(f"Inlet temp: {params['inlet_temperature']} {params.get('inlet_temperature_unit', '°C')}")
                if params.get("outlet_temperature"):
                    parts.append(f"Outlet temp: {params['outlet_temperature']} {params.get('outlet_temperature_unit', '°C')}")
                if params.get("feed_rate"):
                    parts.append(f"Feed rate: {params['feed_rate']} {params.get('feed_rate_unit', '')}")
                if params.get("nozzle_diameter"):
                    parts.append(f"Nozzle: {params['nozzle_diameter']} {params.get('nozzle_diameter_unit', 'mm')}")
            
            if manufacturing.get("yield"):
                parts.append(f"Yield: {manufacturing['yield']} {manufacturing.get('yield_unit', '%')}")
        
        # Old schema: process
        process = formulation.get("process", {})
        if process and not manufacturing:
            if process.get("method"):
                parts.append(f"Method: {process['method']}")
            
            milling = process.get("milling", {})
            if milling:
                if milling.get("time_min"):
                    parts.append(f"Milling time: {milling['time_min']} min")
                if milling.get("bead_size_mm"):
                    parts.append(f"Bead size: {milling['bead_size_mm']} mm")
                if milling.get("rpm"):
                    parts.append(f"RPM: {milling['rpm']}")
            
            if process.get("temperature_c"):
                parts.append(f"Temperature: {process['temperature_c']}°C")
        
        return ". ".join(parts) if parts else "Manufacturing process data"
    
    def _build_particle_analytics_text(self, formulation: dict) -> str:
        """Build text representation for particle characteristics embedding."""
        parts = []
        
        # New schema: physical_properties.particle
        physical = formulation.get("physical_properties", {})
        if physical:
            particle = physical.get("particle", {})
            if particle:
                size = particle.get("particle_size", {})
                if size.get("value"):
                    parts.append(f"Particle size: {size['value']} {size.get('unit', 'nm')}")
                    if size.get("std_dev"):
                        parts.append(f"(SD: {size['std_dev']})")
                    if size.get("method"):
                        parts.append(f"Method: {size['method']}")
                
                pdi = particle.get("polydispersity_index", {})
                if isinstance(pdi, dict) and pdi.get("value"):
                    parts.append(f"PDI: {pdi['value']}")
                elif pdi and not isinstance(pdi, dict):
                    parts.append(f"PDI: {pdi}")
            
            solid_state = physical.get("solid_state_properties", {})
            if solid_state:
                if solid_state.get("crystallinity"):
                    parts.append(f"Form: {solid_state['crystallinity']}")
                if solid_state.get("thermal_analysis"):
                    parts.append(f"Thermal: {solid_state['thermal_analysis']}")
            
            if physical.get("drug_loading"):
                dl = physical["drug_loading"]
                if isinstance(dl, dict):
                    parts.append(f"Drug loading: {dl.get('value', '')} {dl.get('unit', '')}")
                else:
                    parts.append(f"Drug loading: {dl}")
            
            if physical.get("stability"):
                parts.append(f"Stability: {physical['stability']}")
        
        # Old schema: particle_characteristics
        old_particle = formulation.get("particle_characteristics", {})
        if old_particle and not physical:
            if old_particle.get("particle_size_distribution_nm"):
                parts.append(f"Particle size: {old_particle['particle_size_distribution_nm']}")
            if old_particle.get("zeta_potential_mv"):
                parts.append(f"Zeta potential: {old_particle['zeta_potential_mv']} mV")
        
        return ". ".join(parts) if parts else "Particle characteristics data"
    
    def _build_stability_text(self, formulation: dict) -> str:
        """Build text representation for in vitro performance (dissolution/stability)."""
        parts = []
        
        # New schema: in_vitro_performance
        in_vitro = formulation.get("in_vitro_performance", [])
        if in_vitro and isinstance(in_vitro, list):
            for idx, test in enumerate(in_vitro):
                dissolution = test.get("dissolution", {})
                if dissolution:
                    if dissolution.get("medium"):
                        parts.append(f"Medium: {dissolution['medium']}")
                    
                    conditions = dissolution.get("conditions", {})
                    if conditions:
                        if conditions.get("apparatus"):
                            parts.append(f"Apparatus: {conditions['apparatus']}")
                        if conditions.get("rotation_speed"):
                            parts.append(f"RPM: {conditions['rotation_speed']}")
                    
                    results = dissolution.get("results", [])
                    for r in results:
                        if r.get("percent_released") and r.get("time_point"):
                            parts.append(f"{r['percent_released']}% released at {r['time_point']} {r.get('time_unit', 'min')}")
                        if r.get("qualitative"):
                            parts.append(f"Result: {r['qualitative']}")
        
        # Physical properties stability
        physical = formulation.get("physical_properties", {})
        if physical.get("stability"):
            parts.append(f"Stability: {physical['stability']}")
        
        # Old schema: stability
        stability = formulation.get("stability", {})
        if stability and not in_vitro:
            if stability.get("conditions"):
                parts.append(f"Conditions: {stability['conditions']}")
            if stability.get("duration_months"):
                parts.append(f"Duration: {stability['duration_months']} months")
            if stability.get("summary"):
                parts.append(f"Summary: {stability['summary']}")
        
        return ". ".join(parts) if parts else "Stability and in vitro data"
    
    def _build_pk_text(self, formulation: dict) -> str:
        """Build text representation for PK/in vivo performance."""
        parts = []
        
        # New schema: in_vivo_performance
        in_vivo = formulation.get("in_vivo_performance", {})
        if in_vivo:
            if in_vivo.get("animal_model"):
                parts.append(f"Model: {in_vivo['animal_model']}")
            
            dose = in_vivo.get("dose", {})
            if dose.get("value"):
                parts.append(f"Dose: {dose['value']} {dose.get('unit', 'mg')}")
            
            pk = in_vivo.get("pharmacokinetics", {})
            params = pk.get("parameters", {})
            if params:
                cmax = params.get("Cmax", {})
                if cmax.get("value"):
                    parts.append(f"Cmax: {cmax['value']} {cmax.get('unit', '')} (SD: {cmax.get('std_dev', 'N/A')})")
                
                tmax = params.get("Tmax", {})
                if tmax.get("value"):
                    parts.append(f"Tmax: {tmax['value']} {tmax.get('unit', 'h')}")
                
                auc = params.get("AUC", {})
                if auc.get("value"):
                    parts.append(f"AUC: {auc['value']} {auc.get('unit', '')} ({auc.get('interval', '')})")
        
        # Old schema: pharmacokinetics
        old_pk = formulation.get("pharmacokinetics", {})
        if old_pk and not in_vivo:
            if old_pk.get("relative_bioavailability"):
                parts.append(f"Relative BA: {old_pk['relative_bioavailability']}%")
            if old_pk.get("cmax"):
                parts.append(f"Cmax: {old_pk['cmax']}")
            if old_pk.get("auc"):
                parts.append(f"AUC: {old_pk['auc']}")
            if old_pk.get("tmax"):
                parts.append(f"Tmax: {old_pk['tmax']}")
        
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
            
            # Build enriched metadata for RAG filtering
            drug = formulation.get("drug", {})
            drug_metadata = drug.get("metadata", {})
            physical_props = formulation.get("physical_properties", {})
            particle = physical_props.get("particle", {})
            particle_size = particle.get("particle_size", {})
            
            # Extract key dissolution metrics for filtering
            dissolution_metrics = {}
            in_vitro = formulation.get("in_vitro_performance", [])
            if in_vitro and isinstance(in_vitro, list):
                for test in in_vitro:
                    dissolution = test.get("dissolution", {})
                    for r in dissolution.get("results", []):
                        if r.get("percent_released") and r.get("time_point"):
                            key = f"dissolution_{r['time_point']}min"
                            dissolution_metrics[key] = r["percent_released"]
            
            # Enriched metadata for all embeddings
            enriched_metadata = {
                "formulation_id": form_id,
                "formulation_name": formulation.get("name", ""),
                "document": doc_title,
                "api_name": drug.get("name"),
                "bcs_class": drug_metadata.get("bcs_class"),
                "formulation_type": formulation.get("formulation_type"),
                "dosage_form": formulation.get("dosage_form"),
                "particle_size_nm": particle_size.get("value") if isinstance(particle_size, dict) else None,
                "solubility": drug.get("solubility"),
                **dissolution_metrics,
            }
            # Remove None values
            enriched_metadata = {k: v for k, v in enriched_metadata.items() if v is not None}
            
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
                        metadata=enriched_metadata,
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
                        metadata=enriched_metadata,
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
                        metadata=enriched_metadata,
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
                        metadata=enriched_metadata,
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
                        metadata=enriched_metadata,
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
                VALUES (:text, CAST(:emb AS vector), CAST(:meta AS jsonb))
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
    
    def generate_embeddings_from_canonical(self, canonical: dict) -> dict:
        """
        Generate embeddings for canonical JSON and return them WITHOUT storing in DB.
        
        Args:
            canonical: The canonical JSON dict
            
        Returns:
            dict: Embeddings for each formulation and category
        """
        results = []
        
        formulations = canonical.get("formulations", [])
        document = canonical.get("document", {})
        doc_title = document.get("title", "Unknown document")
        
        for idx, formulation in enumerate(formulations):
            form_id = formulation.get("formulation_id", f"form_{idx}")
            form_result = {
                "formulation_id": form_id,
                "embeddings": {}
            }
            
            # Build texts for each category
            texts = {
                "formulation_summary": self._build_formulation_summary_text(canonical, formulation),
                "manufacturing_process": self._build_manufacturing_text(formulation),
                "particle_analytics": self._build_particle_analytics_text(formulation),
                "in_vitro": self._build_stability_text(formulation),
                "in_vivo": self._build_pk_text(formulation),
            }
            
            # Generate embeddings for each category
            for category, text_content in texts.items():
                # Skip default/empty texts
                if text_content in [
                    "Formulation data",
                    "Manufacturing process data", 
                    "Particle characteristics data",
                    "Stability and in vitro data",
                    "Pharmacokinetic data",
                ]:
                    form_result["embeddings"][category] = {
                        "text": text_content,
                        "embedding": None,
                        "note": "No data available for this category"
                    }
                else:
                    try:
                        embedding = self.embedding_service.generate_embedding(text_content)
                        form_result["embeddings"][category] = {
                            "text": text_content,
                            "embedding": embedding,
                            "dimension": len(embedding),
                        }
                    except Exception as e:
                        form_result["embeddings"][category] = {
                            "text": text_content,
                            "embedding": None,
                            "error": str(e),
                        }
            
            results.append(form_result)
        
        return {
            "document_title": doc_title,
            "formulation_count": len(formulations),
            "results": results,
        }


__all__ = ["EmbeddingService", "EmbeddingIngestionService"]
