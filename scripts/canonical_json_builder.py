import json
import os
from datetime import datetime
from pathlib import Path




def get_canonical_schema():
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
        "formulations": [
            {
                "name": "",
                "drug": {
                    "name": "",
                    "solubility": "",
                    "metadata": {
                        "bcs_class": "",
                        "molecular_weight": None,
                        "logp": None,
                        "pka": None
                    }
                },
                "formulation_type": "",
                "dosage_form": "",
                "composition": {
                    "active_ingredients": [
                        {
                            "name": "",
                            "concentration": None,
                            "unit": ""
                        }
                    ],
                    "excipients": [
                        {
                            "name": "",
                            "concentration": None,
                            "unit": "",
                            "role": ""
                        }
                    ]
                },
                "manufacturing": {
                    "process_name": "",
                    "process_parameters": {
                        "equipment": "",
                        "speed": None,
                        "speed_unit": "",
                        "duration": None,
                        "duration_unit": "",
                        "milling_media": "",
                        "milling_media_size": None,
                        "milling_media_size_unit": "",
                        "inlet_temperature": None,
                        "inlet_temperature_unit": "",
                        "outlet_temperature": None,
                        "outlet_temperature_unit": "",
                        "feed_rate": None,
                        "feed_rate_unit": "",
                        "nozzle_diameter": None,
                        "nozzle_diameter_unit": ""
                    },
                    "yield": None,
                    "yield_unit": ""
                },
                "physical_properties": {
                    "particle": {
                        "particle_size": {
                            "value": None,
                            "unit": "nm",
                            "std_dev": None,
                            "method": ""
                        },
                        "polydispersity_index": {
                            "value": None,
                            "method": ""
                        },
                        "zeta_potential": {
                            "value": None,
                            "unit": "mV"
                        }
                    },
                    "solid_state_properties": {
                        "crystallinity": "",
                        "thermal_analysis": "",
                        "notes": ""
                    },
                    "drug_loading": {
                        "value": None,
                        "unit": ""
                    },
                    "stability": ""
                },
                "in_vitro_performance": [
                    {
                        "dissolution": {
                            "medium": "",
                            "conditions": {
                                "apparatus": "",
                                "volume": None,
                                "volume_unit": "ml",
                                "temperature": None,
                                "temperature_unit": "°C",
                                "rotation_speed": None,
                                "rotation_speed_unit": "rpm"
                            },
                            "results": [
                                {
                                    "percent_released": None,
                                    "time_point": None,
                                    "time_unit": "min",
                                    "qualitative": ""
                                }
                            ]
                        }
                    }
                ],
                "in_vivo_performance": {
                    "animal_model": "",
                    "dose": {
                        "value": None,
                        "unit": "mg"
                    },
                    "pharmacokinetics": {
                        "parameters": {
                            "Cmax": {
                                "value": None,
                                "unit": "",
                                "std_dev": None
                            },
                            "Tmax": {
                                "value": None,
                                "unit": "h",
                                "std_dev": None
                            },
                            "AUC": {
                                "value": None,
                                "unit": "",
                                "std_dev": None,
                                "interval": ""
                            }
                        }
                    }
                }
            }
        ],
        "metadata": {
            "formulation_type": "",
            "data_source": "",
            "confidence_level": "",
            "curation_notes": "",
            "created_at": ""
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