"""
Input Validators
"""
from typing import Dict, Any


def validate_api_properties(properties: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate API properties
    
    Args:
        properties: Dictionary of API properties
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ["molecular_weight"]
    
    for field in required_fields:
        if field not in properties or properties[field] is None:
            return False, f"Missing required field: {field}"
    
    # Validate ranges
    mw = properties.get("molecular_weight")
    if mw is not None and (mw < 100 or mw > 2000):
        return False, "Molecular weight must be between 100 and 2000 g/mol"
    
    pka = properties.get("pka")
    if pka is not None and (pka < 0 or pka > 14):
        return False, "pKa must be between 0 and 14"
    
    return True, ""


def validate_formulation_platform(platform: str) -> bool:
    """
    Validate formulation platform
    
    Args:
        platform: Platform name
        
    Returns:
        True if valid platform
    """
    valid_platforms = ["SEDDS", "SMEDDS", "ASD", "Nanosuspension"]
    return platform in valid_platforms


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    import re
    # Remove or replace unsafe characters
    filename = re.sub(r'[^\w\s\-\.]', '', filename)
    filename = re.sub(r'[\s]+', '_', filename)
    return filename
