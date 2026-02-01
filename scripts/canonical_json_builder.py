import json
import os
from datetime import datetime
from pathlib import Path




def get_canonical_schema():
    formulation_template = {
        "formulation_id": "",
        "stage": "",
        "formulation_strategy": {
            "strategy_name": "Nanocrystal",
            "description": "",
            "expected_benefits": [],
            "constraints": []
        },
        "components": [
            {
                "name": "",
                "role": "",
                "amount": {
                    "value": None,
                    "unit": ""
                }
            }
        ],
        "process": {
            "method": "",
            "milling": {
                "time_min": None,
                "bead_size_mm": None,
                "rpm": None
            },
            "solvent_system": "",
            "temperature_c": None,
            "mixing": "",
            "notes": ""
        },
        "particle_characteristics": {
            "particle_size_distribution_nm": "",
            "zeta_potential_mv": None,
            "dissolution_profile": ""
        },
        "stability": {
            "conditions": "",
            "duration_months": None,
            "summary": ""
        },
        "pharmacokinetics": {
            "relative_bioavailability": None,
            "cmax": None,
            "auc": None,
            "tmax": None
        }
    }

    return {
        "document": {
            "title": "",
            "authors": [],
            "journal": "",
            "year": None,
            "doi": "",
            "pmid": "",
            "url": "",
            "abstract_summary": "",
            "document_type": "",
            "ingestion_notes": ""
        },
        "api": {
            "name": "",
            "synonyms": [],
            "molecular_weight": None,
            "melting_point_c": None,
            "glass_transition_temp_c": None,
            "logp": None,
            "logd": None,
            "pka": None,
            "bcs_class": "",
            "aqueous_solubility": "",
            "stability_sensitivities": [],
            "dose_mg": None
        },
        "formulations": [formulation_template],
        "metadata": {
            "formulation_type": "nanocrystal",
            "data_source": "",
            "confidence_level": "",
            "curation_notes": "",
            "created_at": datetime.now().isoformat()
        }
    }


def create_canonical_json(output_path: str = None):
    if output_path is None:
        script_dir = Path(__file__).parent
        output_path = script_dir.parent / "data" / "canonical.json"
    
    try:
        output_path = Path(output_path)

        schema = get_canonical_schema()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        
        print(f"Canonical JSON created at: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error creating canonical JSON: {e}")
        return None

if __name__ == "__main__":
    create_canonical_json()