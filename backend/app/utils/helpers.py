"""
Helper Functions
"""
from datetime import datetime
from typing import Any


def get_timestamp() -> str:
    """Get current timestamp in ISO format"""
    return datetime.utcnow().isoformat() + "Z"


def format_api_properties(properties: dict) -> str:
    """
    Format API properties for display
    
    Args:
        properties: Dictionary of API properties
        
    Returns:
        Formatted string
    """
    formatted = []
    if properties.get("molecular_weight"):
        formatted.append(f"MW: {properties['molecular_weight']} g/mol")
    if properties.get("melting_point"):
        formatted.append(f"MP: {properties['melting_point']}°C")
    if properties.get("pka"):
        formatted.append(f"pKa: {properties['pka']}")
    if properties.get("solubility"):
        formatted.append(f"Solubility: {properties['solubility']} mg/mL")
    if properties.get("logp"):
        formatted.append(f"LogP: {properties['logp']}")
    
    return ", ".join(formatted)


def truncate_text(text: str, max_length: int = 200) -> str:
    """
    Truncate text to maximum length
    
    Args:
        text: Input text
        max_length: Maximum length
        
    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
