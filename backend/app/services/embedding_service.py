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
    """Service for populating embedding tables from structured SQL data."""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
    
    def _build_formulation_text(self, formulation: dict) -> str:
        """Build text representation for a formulation."""
        parts = []
        
        if formulation.get("drug_name"):
            parts.append(f"Drug: {formulation['drug_name']}")
        if formulation.get("dosage_form"):
            parts.append(f"Dosage Form: {formulation['dosage_form']}")
        if formulation.get("route_of_administration"):
            parts.append(f"Route: {formulation['route_of_administration']}")
        if formulation.get("therapeutic_area"):
            parts.append(f"Therapeutic Area: {formulation['therapeutic_area']}")
        if formulation.get("excipients"):
            parts.append(f"Excipients: {formulation['excipients']}")
        if formulation.get("api_info"):
            parts.append(f"API: {formulation['api_info']}")
        
        return ", ".join(parts) if parts else "Formulation data"
    
    def _build_manufacturing_text(self, process: dict) -> str:
        """Build text representation for a manufacturing process."""
        parts = []
        
        if process.get("process_type"):
            parts.append(f"Process: {process['process_type']}")
        if process.get("process_description"):
            parts.append(f"Description: {process['process_description']}")
        if process.get("scale"):
            parts.append(f"Scale: {process['scale']}")
        if process.get("batch_size"):
            parts.append(f"Batch Size: {process['batch_size']}")
        if process.get("equipment_used"):
            equip = process['equipment_used']
            if isinstance(equip, list):
                equip = ", ".join(equip)
            parts.append(f"Equipment: {equip}")
        if process.get("parameters"):
            parts.append(f"Parameters: {process['parameters']}")
        
        return ", ".join(parts) if parts else "Manufacturing process data"
    
    def _build_particle_analytics_text(self, data: dict) -> str:
        """Build text representation for particle/analytics data."""
        parts = []
        
        if data.get("d50"):
            parts.append(f"D50: {data['d50']} μm")
        if data.get("d90"):
            parts.append(f"D90: {data['d90']} μm")
        if data.get("span"):
            parts.append(f"Span: {data['span']}")
        if data.get("specific_surface_area"):
            parts.append(f"Surface Area: {data['specific_surface_area']}")
        if data.get("analytical_results"):
            parts.append(f"Tests: {data['analytical_results']}")
        
        return ", ".join(parts) if parts else "Particle and analytical data"
    
    def _build_dissolution_text(self, profile: dict) -> str:
        """Build text representation for dissolution profile."""
        parts = []
        
        if profile.get("dissolution_method"):
            parts.append(f"Method: {profile['dissolution_method']}")
        if profile.get("medium"):
            parts.append(f"Medium: {profile['medium']}")
        if profile.get("rpm"):
            parts.append(f"RPM: {profile['rpm']}")
        if profile.get("temperature"):
            parts.append(f"Temperature: {profile['temperature']}°C")
        if profile.get("timepoints"):
            parts.append(f"Profile: {profile['timepoints']}")
        
        return ", ".join(parts) if parts else "Dissolution profile data"
    
    def _build_pk_text(self, study: dict) -> str:
        """Build text representation for PK study."""
        parts = []
        
        if study.get("study_type"):
            parts.append(f"Study Type: {study['study_type']}")
        if study.get("species"):
            parts.append(f"Species: {study['species']}")
        if study.get("n_subjects"):
            parts.append(f"Subjects: {study['n_subjects']}")
        if study.get("fasted_fed"):
            parts.append(f"Condition: {study['fasted_fed']}")
        if study.get("pk_parameters"):
            parts.append(f"PK: {study['pk_parameters']}")
        if study.get("be_results"):
            parts.append(f"BE: {study['be_results']}")
        
        return ", ".join(parts) if parts else "PK study data"
    
    def ingest_formulation_embeddings(self) -> dict:
        """
        Generate and store embeddings for all formulations.
        
        Returns:
            dict: Ingestion statistics
        """
        stats = {"processed": 0, "embedded": 0, "errors": 0}
        
        try:
            with engine.connect() as conn:
                # Get formulations with their excipients and APIs
                query = text("""
                    SELECT 
                        f.id,
                        f.formulation_name,
                        f.drug_name,
                        f.dosage_form,
                        f.route_of_administration,
                        f.therapeutic_area,
                        COALESCE(
                            STRING_AGG(DISTINCT e.name, ', ') FILTER (WHERE e.name IS NOT NULL),
                            ''
                        ) as excipients,
                        COALESCE(
                            STRING_AGG(DISTINCT a.name || ' (' || COALESCE(fa.amount::text, '') || ' ' || COALESCE(fa.unit, '') || ')', ', ') FILTER (WHERE a.name IS NOT NULL),
                            ''
                        ) as api_info
                    FROM formulations f
                    LEFT JOIN formulation_excipients fe ON f.id = fe.formulation_id
                    LEFT JOIN excipients e ON fe.excipient_id = e.id
                    LEFT JOIN formulation_apis fa ON f.id = fa.formulation_id
                    LEFT JOIN apis a ON fa.api_id = a.id
                    GROUP BY f.id
                """)
                
                result = conn.execute(query)
                formulations = [dict(row._mapping) for row in result]
                
                for form in formulations:
                    stats["processed"] += 1
                    try:
                        text_content = self._build_formulation_text(form)
                        embedding = self.embedding_service.generate_embedding(text_content)
                        
                        # Insert into embedding table
                        insert_query = text("""
                            INSERT INTO formulation_summary_embeddings 
                            (formulation_id, text_content, embedding, metadata)
                            VALUES (:fid, :text, :emb::vector, :meta::jsonb)
                            ON CONFLICT DO NOTHING
                        """)
                        
                        conn.execute(insert_query, {
                            "fid": form["id"],
                            "text": text_content,
                            "emb": f"[{','.join(str(x) for x in embedding)}]",
                            "meta": "{}",
                        })
                        conn.commit()
                        stats["embedded"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding formulation {form['id']}: {e}")
                        stats["errors"] += 1
                
        except Exception as e:
            logger.error(f"Formulation embedding ingestion failed: {e}")
            raise
        
        return stats
    
    def ingest_manufacturing_embeddings(self) -> dict:
        """Generate and store embeddings for manufacturing processes."""
        stats = {"processed": 0, "embedded": 0, "errors": 0}
        
        try:
            with engine.connect() as conn:
                query = text("""
                    SELECT 
                        m.id,
                        m.process_type,
                        m.process_description,
                        m.batch_size,
                        m.scale,
                        m.equipment_used,
                        COALESCE(
                            STRING_AGG(
                                pp.parameter_name || ': ' || COALESCE(pp.target_value, '') || ' ' || COALESCE(pp.unit, ''),
                                '; '
                            ) FILTER (WHERE pp.parameter_name IS NOT NULL),
                            ''
                        ) as parameters
                    FROM manufacturing_processes m
                    LEFT JOIN process_parameters pp ON m.id = pp.manufacturing_process_id
                    GROUP BY m.id
                """)
                
                result = conn.execute(query)
                processes = [dict(row._mapping) for row in result]
                
                for proc in processes:
                    stats["processed"] += 1
                    try:
                        text_content = self._build_manufacturing_text(proc)
                        embedding = self.embedding_service.generate_embedding(text_content)
                        
                        insert_query = text("""
                            INSERT INTO manufacturing_process_embeddings 
                            (manufacturing_process_id, text_content, embedding, metadata)
                            VALUES (:pid, :text, :emb::vector, :meta::jsonb)
                            ON CONFLICT DO NOTHING
                        """)
                        
                        conn.execute(insert_query, {
                            "pid": proc["id"],
                            "text": text_content,
                            "emb": f"[{','.join(str(x) for x in embedding)}]",
                            "meta": "{}",
                        })
                        conn.commit()
                        stats["embedded"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding process {proc['id']}: {e}")
                        stats["errors"] += 1
                
        except Exception as e:
            logger.error(f"Manufacturing embedding ingestion failed: {e}")
            raise
        
        return stats
    
    def ingest_particle_analytics_embeddings(self) -> dict:
        """Generate and store embeddings for particle characteristics."""
        stats = {"processed": 0, "embedded": 0, "errors": 0}
        
        try:
            with engine.connect() as conn:
                query = text("""
                    SELECT 
                        pc.id,
                        pc.formulation_id,
                        pc.d10,
                        pc.d50,
                        pc.d90,
                        pc.span,
                        pc.specific_surface_area,
                        pc.measurement_type,
                        COALESCE(
                            STRING_AGG(
                                ar.test_name || ': ' || COALESCE(ar.result_value, '') || ' ' || COALESCE(ar.unit, ''),
                                '; '
                            ) FILTER (WHERE ar.test_name IS NOT NULL),
                            ''
                        ) as analytical_results
                    FROM particle_characteristics pc
                    LEFT JOIN analytical_results ar ON pc.formulation_id = ar.formulation_id
                    GROUP BY pc.id
                """)
                
                result = conn.execute(query)
                particles = [dict(row._mapping) for row in result]
                
                for particle in particles:
                    stats["processed"] += 1
                    try:
                        text_content = self._build_particle_analytics_text(particle)
                        embedding = self.embedding_service.generate_embedding(text_content)
                        
                        insert_query = text("""
                            INSERT INTO particle_analytics_embeddings 
                            (formulation_id, text_content, embedding, metadata)
                            VALUES (:fid, :text, :emb::vector, :meta::jsonb)
                            ON CONFLICT DO NOTHING
                        """)
                        
                        conn.execute(insert_query, {
                            "fid": particle["formulation_id"],
                            "text": text_content,
                            "emb": f"[{','.join(str(x) for x in embedding)}]",
                            "meta": "{}",
                        })
                        conn.commit()
                        stats["embedded"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding particle {particle['id']}: {e}")
                        stats["errors"] += 1
                
        except Exception as e:
            logger.error(f"Particle analytics embedding ingestion failed: {e}")
            raise
        
        return stats
    
    def ingest_in_vitro_embeddings(self) -> dict:
        """Generate and store embeddings for dissolution profiles."""
        stats = {"processed": 0, "embedded": 0, "errors": 0}
        
        try:
            with engine.connect() as conn:
                query = text("""
                    SELECT 
                        dp.id,
                        dp.dissolution_method,
                        dp.medium,
                        dp.volume_ml,
                        dp.rpm,
                        dp.temperature,
                        dp.sink_conditions,
                        COALESCE(
                            STRING_AGG(
                                dt.timepoint_minutes || 'min: ' || COALESCE(dt.percent_dissolved::text, '') || '%',
                                ', '
                                ORDER BY dt.timepoint_minutes
                            ) FILTER (WHERE dt.timepoint_minutes IS NOT NULL),
                            ''
                        ) as timepoints
                    FROM dissolution_profiles dp
                    LEFT JOIN dissolution_timepoints dt ON dp.id = dt.dissolution_profile_id
                    GROUP BY dp.id
                """)
                
                result = conn.execute(query)
                profiles = [dict(row._mapping) for row in result]
                
                for profile in profiles:
                    stats["processed"] += 1
                    try:
                        text_content = self._build_dissolution_text(profile)
                        embedding = self.embedding_service.generate_embedding(text_content)
                        
                        insert_query = text("""
                            INSERT INTO in_vitro_embeddings 
                            (dissolution_profile_id, text_content, embedding, metadata)
                            VALUES (:dpid, :text, :emb::vector, :meta::jsonb)
                            ON CONFLICT DO NOTHING
                        """)
                        
                        conn.execute(insert_query, {
                            "dpid": profile["id"],
                            "text": text_content,
                            "emb": f"[{','.join(str(x) for x in embedding)}]",
                            "meta": "{}",
                        })
                        conn.commit()
                        stats["embedded"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding profile {profile['id']}: {e}")
                        stats["errors"] += 1
                
        except Exception as e:
            logger.error(f"In vitro embedding ingestion failed: {e}")
            raise
        
        return stats
    
    def ingest_in_vivo_embeddings(self) -> dict:
        """Generate and store embeddings for PK studies."""
        stats = {"processed": 0, "embedded": 0, "errors": 0}
        
        try:
            with engine.connect() as conn:
                query = text("""
                    SELECT 
                        pk.id,
                        pk.study_type,
                        pk.species,
                        pk.n_subjects,
                        pk.study_design,
                        pk.fasted_fed,
                        pk.reference_product,
                        COALESCE(
                            STRING_AGG(
                                DISTINCT pp.parameter_name || ': ' || COALESCE(pp.geometric_mean::text, '') || ' ' || COALESCE(pp.unit, ''),
                                '; '
                            ) FILTER (WHERE pp.parameter_name IS NOT NULL),
                            ''
                        ) as pk_parameters,
                        COALESCE(
                            STRING_AGG(
                                DISTINCT be.parameter_name || ' ratio: ' || COALESCE(be.test_ref_ratio::text, '') || 
                                ' (90% CI: ' || COALESCE(be.ci_lower_90::text, '') || '-' || COALESCE(be.ci_upper_90::text, '') || ')',
                                '; '
                            ) FILTER (WHERE be.parameter_name IS NOT NULL),
                            ''
                        ) as be_results
                    FROM pk_studies pk
                    LEFT JOIN pk_parameters pp ON pk.id = pp.pk_study_id
                    LEFT JOIN bioequivalence_results be ON pk.id = be.pk_study_id
                    GROUP BY pk.id
                """)
                
                result = conn.execute(query)
                studies = [dict(row._mapping) for row in result]
                
                for study in studies:
                    stats["processed"] += 1
                    try:
                        text_content = self._build_pk_text(study)
                        embedding = self.embedding_service.generate_embedding(text_content)
                        
                        insert_query = text("""
                            INSERT INTO in_vivo_embeddings 
                            (pk_study_id, text_content, embedding, metadata)
                            VALUES (:pkid, :text, :emb::vector, :meta::jsonb)
                            ON CONFLICT DO NOTHING
                        """)
                        
                        conn.execute(insert_query, {
                            "pkid": study["id"],
                            "text": text_content,
                            "emb": f"[{','.join(str(x) for x in embedding)}]",
                            "meta": "{}",
                        })
                        conn.commit()
                        stats["embedded"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding study {study['id']}: {e}")
                        stats["errors"] += 1
                
        except Exception as e:
            logger.error(f"In vivo embedding ingestion failed: {e}")
            raise
        
        return stats
    
    def ingest_all_embeddings(self) -> dict:
        """
        Run all embedding ingestion jobs.
        
        Returns:
            dict: Statistics for each embedding table
        """
        results = {}
        
        logger.info("Starting full embedding ingestion...")
        
        try:
            results["formulation_summary_embeddings"] = self.ingest_formulation_embeddings()
            logger.info(f"Formulation embeddings: {results['formulation_summary_embeddings']}")
        except Exception as e:
            results["formulation_summary_embeddings"] = {"error": str(e)}
        
        try:
            results["manufacturing_process_embeddings"] = self.ingest_manufacturing_embeddings()
            logger.info(f"Manufacturing embeddings: {results['manufacturing_process_embeddings']}")
        except Exception as e:
            results["manufacturing_process_embeddings"] = {"error": str(e)}
        
        try:
            results["particle_analytics_embeddings"] = self.ingest_particle_analytics_embeddings()
            logger.info(f"Particle analytics embeddings: {results['particle_analytics_embeddings']}")
        except Exception as e:
            results["particle_analytics_embeddings"] = {"error": str(e)}
        
        try:
            results["in_vitro_embeddings"] = self.ingest_in_vitro_embeddings()
            logger.info(f"In vitro embeddings: {results['in_vitro_embeddings']}")
        except Exception as e:
            results["in_vitro_embeddings"] = {"error": str(e)}
        
        try:
            results["in_vivo_embeddings"] = self.ingest_in_vivo_embeddings()
            logger.info(f"In vivo embeddings: {results['in_vivo_embeddings']}")
        except Exception as e:
            results["in_vivo_embeddings"] = {"error": str(e)}
        
        logger.info("Embedding ingestion complete")
        return results


__all__ = ["EmbeddingService", "EmbeddingIngestionService"]
