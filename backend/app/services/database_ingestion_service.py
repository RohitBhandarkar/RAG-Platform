"""Database Ingestion Service.

Populates PostgreSQL structured tables from canonical JSON.
This handles the relational data, while EmbeddingIngestionService handles vectors.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlalchemy import text

from app.db import engine
from app.utils.formulation_uid import formulation_uid_from_canonical


logger = logging.getLogger(__name__)


class DatabaseIngestionService:
    """Service for populating PostgreSQL tables from canonical JSON."""
    
    def ingest_canonical(
        self,
        canonical: Dict[str, Any],
        source_type: str = "user_upload",
        source_id: str = None,
        file_path: str = None,
    ) -> Dict[str, Any]:
        """
        Ingest canonical JSON into PostgreSQL structured tables.
        
        Args:
            canonical: The canonical JSON dict from LLM extraction
            source_type: Type of source ('pubmed', 'patent', 'fda', 'user_upload')
            source_id: External identifier (PMID, patent number, filename)
            file_path: Path to the original file
            
        Returns:
            dict: Ingestion statistics and created IDs
        """
        stats = {
            "source_document_id": None,
            "formulations_created": 0,
            "excipients_created": 0,
            "apis_created": 0,
            "manufacturing_processes_created": 0,
            "dissolution_profiles_created": 0,
            "pk_studies_created": 0,
            "errors": [],
        }
        
        try:
            with engine.connect() as conn:
                # 1. Create source_document entry
                document = canonical.get("document", {})
                title = document.get("title", source_id or "Untitled")
                
                source_doc_id = self._insert_source_document(
                    conn,
                    source_type=source_type,
                    source_id=source_id or f"upload_{datetime.now().isoformat()}",
                    title=title,
                    file_path=file_path,
                    metadata=document,
                )
                stats["source_document_id"] = source_doc_id
                
                # 2. Process each formulation (deterministic formulation_uid: no DB lookup for embeddings)
                formulations = canonical.get("formulations", [])
                for idx, formulation in enumerate(formulations):
                    try:
                        formulation_uid = formulation_uid_from_canonical(
                            document, idx, source_id=source_id
                        )
                        form_result = self._process_formulation(
                            conn,
                            formulation,
                            source_doc_id,
                            idx,
                            formulation_uid=formulation_uid,
                        )
                        stats["formulations_created"] += 1
                        stats["excipients_created"] += form_result.get("excipients", 0)
                        stats["apis_created"] += form_result.get("apis", 0)
                        stats["manufacturing_processes_created"] += form_result.get("manufacturing", 0)
                        stats["dissolution_profiles_created"] += form_result.get("dissolution", 0)
                        stats["pk_studies_created"] += form_result.get("pk_studies", 0)
                    except Exception as e:
                        logger.error(f"Error processing formulation {idx}: {e}")
                        stats["errors"].append(f"Formulation {idx}: {str(e)}")
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"Database ingestion failed: {e}")
            stats["errors"].append(f"Fatal: {str(e)}")
            raise
        
        logger.info(f"Database ingestion complete: {stats}")
        return stats
    
    def _insert_source_document(
        self,
        conn,
        source_type: str,
        source_id: str,
        title: str,
        file_path: str = None,
        metadata: Dict = None,
    ) -> int:
        """Insert or update source_document and return ID."""
        
        # Check if document already exists
        result = conn.execute(
            text("""
                SELECT id FROM source_documents 
                WHERE source_type = :source_type AND source_id = :source_id
            """),
            {"source_type": source_type, "source_id": source_id}
        )
        existing = result.fetchone()
        
        if existing:
            # Update existing
            conn.execute(
                text("""
                    UPDATE source_documents 
                    SET title = :title, file_path = :file_path, metadata = CAST(:metadata AS jsonb)
                    WHERE id = :id
                """),
                {
                    "id": existing[0],
                    "title": title,
                    "file_path": file_path,
                    "metadata": json.dumps(metadata or {}),
                }
            )
            return existing[0]
        else:
            # Insert new
            result = conn.execute(
                text("""
                    INSERT INTO source_documents (source_type, source_id, title, file_path, metadata)
                    VALUES (:source_type, :source_id, :title, :file_path, CAST(:metadata AS jsonb))
                    RETURNING id
                """),
                {
                    "source_type": source_type,
                    "source_id": source_id,
                    "title": title,
                    "file_path": file_path,
                    "metadata": json.dumps(metadata or {}),
                }
            )
            return result.fetchone()[0]
    
    def _process_formulation(
        self,
        conn,
        formulation: Dict[str, Any],
        source_doc_id: int,
        idx: int,
        formulation_uid: str,
    ) -> Dict[str, int]:
        """Process a single formulation and its related data."""
        
        result = {
            "excipients": 0,
            "apis": 0,
            "manufacturing": 0,
            "dissolution": 0,
            "pk_studies": 0,
        }
        
        # Extract formulation details
        drug = formulation.get("drug", {})
        drug_name = drug.get("name", f"Unknown_{idx}")
        drug_metadata = drug.get("metadata", {})
        bcs_class = drug_metadata.get("bcs_class")
        
        formulation_name = formulation.get("name", formulation.get("formulation_id", f"Formulation_{idx}"))
        dosage_form = formulation.get("dosage_form", "")
        formulation_type = formulation.get("formulation_type", "")
        
        # First create the API to get api_id
        api_id = None
        if drug.get("name"):
            api_id = self._get_or_create_api(conn, drug)
        
        # Insert formulation with formulation_uid (deterministic; embeddings use same UID, no DB lookup)
        form_result = conn.execute(
            text("""
                INSERT INTO formulations 
                (source_document_id, formulation_uid, api_id, formulation_name, drug_name, dosage_form, formulation_type, bcs_class, metadata)
                VALUES (:source_doc_id, :formulation_uid, :api_id, :name, :drug_name, :dosage_form, :formulation_type, :bcs_class, CAST(:metadata AS jsonb))
                RETURNING id
            """),
            {
                "source_doc_id": source_doc_id,
                "formulation_uid": formulation_uid,
                "api_id": api_id,
                "name": formulation_name,
                "drug_name": drug_name,
                "dosage_form": dosage_form,
                "formulation_type": formulation_type,
                "bcs_class": bcs_class,
                "metadata": json.dumps({
                    "original_data": formulation,
                }),
            }
        )
        formulation_id = form_result.fetchone()[0]
        
        # Link formulation to API (junction table)
        if api_id:
            self._link_formulation_api(conn, formulation_id, api_id, drug)
            result["apis"] = 1
        
        # Process composition (excipients)
        composition = formulation.get("composition", {})
        excipients = composition.get("excipients", [])
        for exc in excipients:
            exc_id = self._get_or_create_excipient(conn, exc)
            if exc_id:
                self._link_formulation_excipient(conn, formulation_id, exc_id, exc)
                result["excipients"] += 1
        
        # Process manufacturing
        manufacturing = formulation.get("manufacturing", {})
        if manufacturing:
            self._insert_manufacturing_process(conn, formulation_id, manufacturing)
            result["manufacturing"] = 1
        
        # Process particle characteristics
        physical = formulation.get("physical_properties", {})
        particle = physical.get("particle", {})
        if particle:
            self._insert_particle_characteristics(conn, formulation_id, particle)
        
        # Process in vitro performance (dissolution)
        in_vitro = formulation.get("in_vitro_performance", [])
        if isinstance(in_vitro, list):
            for test in in_vitro:
                dissolution = test.get("dissolution", {})
                if dissolution:
                    self._insert_dissolution_profile(conn, formulation_id, dissolution)
                    result["dissolution"] += 1
        
        # Process in vivo performance (PK)
        in_vivo = formulation.get("in_vivo_performance", [])
        if isinstance(in_vivo, list):
            for study in in_vivo:
                pk = study.get("pharmacokinetics", {})
                if pk:
                    self._insert_pk_study(conn, formulation_id, pk, study)
                    result["pk_studies"] += 1
        
        return result
    
    def _get_or_create_api(self, conn, drug: Dict) -> Optional[int]:
        """Get existing API or create new one, return ID."""
        name = drug.get("name", "").strip()
        if not name:
            return None
        
        # Check if exists
        result = conn.execute(
            text("SELECT id FROM apis WHERE name = :name"),
            {"name": name}
        )
        existing = result.fetchone()
        if existing:
            return existing[0]
        
        # Create new
        metadata = drug.get("metadata", {})
        result = conn.execute(
            text("""
                INSERT INTO apis (name, bcs_class, metadata)
                VALUES (:name, :bcs_class, CAST(:metadata AS jsonb))
                RETURNING id
            """),
            {
                "name": name,
                "bcs_class": metadata.get("bcs_class"),
                "metadata": json.dumps(drug),
            }
        )
        return result.fetchone()[0]
    
    def _link_formulation_api(self, conn, formulation_id: int, api_id: int, drug: Dict):
        """Create formulation-API link."""
        conn.execute(
            text("""
                INSERT INTO formulation_apis (formulation_id, api_id, metadata)
                VALUES (:form_id, :api_id, CAST(:metadata AS jsonb))
                ON CONFLICT (formulation_id, api_id) DO NOTHING
            """),
            {
                "form_id": formulation_id,
                "api_id": api_id,
                "metadata": json.dumps(drug),
            }
        )
    
    def _get_or_create_excipient(self, conn, exc: Dict) -> Optional[int]:
        """Get existing excipient or create new one, return ID."""
        name = exc.get("name", "").strip()
        if not name:
            return None
        
        # Check if exists
        result = conn.execute(
            text("SELECT id FROM excipients WHERE name = :name"),
            {"name": name}
        )
        existing = result.fetchone()
        if existing:
            return existing[0]
        
        # Create new
        result = conn.execute(
            text("""
                INSERT INTO excipients (name, functional_category, metadata)
                VALUES (:name, :role, CAST(:metadata AS jsonb))
                RETURNING id
            """),
            {
                "name": name,
                "role": exc.get("role"),
                "metadata": json.dumps(exc),
            }
        )
        return result.fetchone()[0]
    
    def _link_formulation_excipient(self, conn, formulation_id: int, excipient_id: int, exc: Dict):
        """Create formulation-excipient link."""
        conn.execute(
            text("""
                INSERT INTO formulation_excipients 
                (formulation_id, excipient_id, amount, unit, role, metadata)
                VALUES (:form_id, :exc_id, :amount, :unit, :role, CAST(:metadata AS jsonb))
                ON CONFLICT (formulation_id, excipient_id) DO NOTHING
            """),
            {
                "form_id": formulation_id,
                "exc_id": excipient_id,
                "amount": exc.get("concentration"),
                "unit": exc.get("unit", "%"),
                "role": exc.get("role"),
                "metadata": json.dumps(exc),
            }
        )
    
    def _insert_manufacturing_process(self, conn, formulation_id: int, manufacturing: Dict):
        """Insert manufacturing process data."""
        params = manufacturing.get("process_parameters", {})
        
        # Insert manufacturing process
        mp_result = conn.execute(
            text("""
                INSERT INTO manufacturing_processes 
                (formulation_id, process_type, process_description, equipment_used, metadata)
                VALUES (:form_id, :process_type, :description, :equipment, CAST(:metadata AS jsonb))
                RETURNING id
            """),
            {
                "form_id": formulation_id,
                "process_type": manufacturing.get("process_name"),
                "description": manufacturing.get("notes"),
                "equipment": [params.get("equipment")] if params.get("equipment") else None,
                "metadata": json.dumps(manufacturing),
            }
        )
        mp_id = mp_result.fetchone()[0]
        
        # Insert process parameters as individual rows
        param_mappings = [
            ("speed", params.get("speed"), params.get("speed_unit")),
            ("duration", params.get("duration"), params.get("duration_unit")),
            ("inlet_temperature", params.get("inlet_temperature"), params.get("inlet_temperature_unit", "°C")),
            ("outlet_temperature", params.get("outlet_temperature"), params.get("outlet_temperature_unit", "°C")),
            ("feed_rate", params.get("feed_rate"), params.get("feed_rate_unit")),
            ("milling_media_size", params.get("milling_media_size"), params.get("milling_media_size_unit", "mm")),
        ]
        
        for param_name, value, unit in param_mappings:
            if value is not None:
                conn.execute(
                    text("""
                        INSERT INTO process_parameters 
                        (manufacturing_process_id, parameter_name, target_value, unit)
                        VALUES (:mp_id, :name, :value, :unit)
                    """),
                    {
                        "mp_id": mp_id,
                        "name": param_name,
                        "value": str(value),
                        "unit": unit,
                    }
                )
    
    def _insert_particle_characteristics(self, conn, formulation_id: int, particle: Dict):
        """Insert particle characteristics data."""
        size = particle.get("particle_size", {})
        pdi = particle.get("polydispersity_index", {})
        
        d50 = size.get("value") if isinstance(size, dict) else None
        
        conn.execute(
            text("""
                INSERT INTO particle_characteristics 
                (formulation_id, measurement_type, d50, span, unit, metadata)
                VALUES (:form_id, :method, :d50, :pdi, :unit, CAST(:metadata AS jsonb))
            """),
            {
                "form_id": formulation_id,
                "method": size.get("method") if isinstance(size, dict) else None,
                "d50": d50,
                "pdi": pdi.get("value") if isinstance(pdi, dict) else pdi,
                "unit": size.get("unit", "nm") if isinstance(size, dict) else "nm",
                "metadata": json.dumps(particle),
            }
        )
    
    def _insert_dissolution_profile(self, conn, formulation_id: int, dissolution: Dict):
        """Insert dissolution profile and timepoints."""
        conditions = dissolution.get("conditions", {})
        
        # Insert dissolution profile
        dp_result = conn.execute(
            text("""
                INSERT INTO dissolution_profiles 
                (formulation_id, dissolution_method, medium, rpm, metadata)
                VALUES (:form_id, :method, :medium, :rpm, CAST(:metadata AS jsonb))
                RETURNING id
            """),
            {
                "form_id": formulation_id,
                "method": conditions.get("apparatus"),
                "medium": dissolution.get("medium"),
                "rpm": conditions.get("rotation_speed"),
                "metadata": json.dumps(dissolution),
            }
        )
        dp_id = dp_result.fetchone()[0]
        
        # Insert timepoints
        results = dissolution.get("results", [])
        for r in results:
            time_point = r.get("time_point")
            percent = r.get("percent_released")
            
            if time_point is not None and percent is not None:
                # Try to parse time_point as minutes
                try:
                    time_min = int(time_point)
                except (ValueError, TypeError):
                    continue
                
                conn.execute(
                    text("""
                        INSERT INTO dissolution_timepoints 
                        (dissolution_profile_id, timepoint_minutes, percent_dissolved)
                        VALUES (:dp_id, :time, :percent)
                    """),
                    {
                        "dp_id": dp_id,
                        "time": time_min,
                        "percent": percent,
                    }
                )
    
    def _insert_pk_study(self, conn, formulation_id: int, pk: Dict, study: Dict):
        """Insert PK study and parameters."""
        # Insert PK study
        pk_result = conn.execute(
            text("""
                INSERT INTO pk_studies 
                (formulation_id, study_type, species, study_design, metadata)
                VALUES (:form_id, :study_type, :species, :design, CAST(:metadata AS jsonb))
                RETURNING id
            """),
            {
                "form_id": formulation_id,
                "study_type": study.get("study_type"),
                "species": pk.get("species") or study.get("species"),
                "design": study.get("design"),
                "metadata": json.dumps(study),
            }
        )
        pk_study_id = pk_result.fetchone()[0]
        
        # Insert PK parameters
        pk_params = pk.get("parameters", {})
        param_mappings = [
            ("Cmax", pk_params.get("cmax"), pk_params.get("cmax_unit")),
            ("Tmax", pk_params.get("tmax"), pk_params.get("tmax_unit")),
            ("AUC", pk_params.get("auc"), pk_params.get("auc_unit")),
            ("t1/2", pk_params.get("half_life"), pk_params.get("half_life_unit")),
        ]
        
        for param_name, value, unit in param_mappings:
            if value is not None:
                conn.execute(
                    text("""
                        INSERT INTO pk_parameters 
                        (pk_study_id, parameter_name, arithmetic_mean, unit)
                        VALUES (:pk_id, :name, :value, :unit)
                    """),
                    {
                        "pk_id": pk_study_id,
                        "name": param_name,
                        "value": value,
                        "unit": unit,
                    }
                )
        
        # Insert bioequivalence if available
        be = pk.get("bioequivalence", {})
        if be:
            relative_ba = be.get("relative_bioavailability")
            if relative_ba:
                conn.execute(
                    text("""
                        INSERT INTO bioequivalence_results 
                        (pk_study_id, parameter_name, test_ref_ratio, metadata)
                        VALUES (:pk_id, :name, :ratio, CAST(:metadata AS jsonb))
                    """),
                    {
                        "pk_id": pk_study_id,
                        "name": "relative_bioavailability",
                        "ratio": relative_ba,
                        "metadata": json.dumps(be),
                    }
                )


__all__ = ["DatabaseIngestionService"]
