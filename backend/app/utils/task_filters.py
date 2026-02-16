"""Utility functions for applying task filters to location queries."""
from typing import List, Optional, Any
from sqlalchemy import text, and_, or_
from sqlalchemy.sql import Select


def apply_task_filters(query: Select, filters: Optional[List[dict]], table_alias: str = "locations") -> Select:
    """
    Apply task filters to a SQLAlchemy query.
    
    Args:
        query: The base SQLAlchemy select query
        filters: List of filter dictionaries with format:
            [{"field": "BusStopType", "operator": "equals", "value": "MKD"}, ...]
        table_alias: The table alias for the locations table (default: "locations")
    
    Supported operators:
        - equals: field == value
        - not_equals: field != value  
        - contains: field ILIKE %value%
        - in_list: field IN (value1, value2, ...)
        - is_null: field IS NULL
        - is_not_null: field IS NOT NULL
    
    Returns:
        Modified query with filters applied
    """
    if not filters:
        return query
    
    for filter_def in filters:
        field = filter_def.get("field")
        operator = filter_def.get("operator", "equals")
        value = filter_def.get("value")
        
        if not field:
            continue
        
        # Build the JSON accessor for the field
        # Using original_data->>'FieldName' for JSONB text extraction
        json_accessor = f"original_data->>'{field}'"
        
        if operator == "equals":
            query = query.where(
                text(f"{json_accessor} = :filter_value_{field}")
            ).params(**{f"filter_value_{field}": value})
            
        elif operator == "not_equals":
            query = query.where(
                text(f"({json_accessor} IS NULL OR {json_accessor} != :filter_value_{field})")
            ).params(**{f"filter_value_{field}": value})
            
        elif operator == "contains":
            query = query.where(
                text(f"{json_accessor} ILIKE :filter_value_{field}")
            ).params(**{f"filter_value_{field}": f"%{value}%"})
            
        elif operator == "in_list":
            # Value should be a list
            if isinstance(value, list) and len(value) > 0:
                placeholders = ", ".join([f":filter_value_{field}_{i}" for i in range(len(value))])
                params = {f"filter_value_{field}_{i}": v for i, v in enumerate(value)}
                query = query.where(
                    text(f"{json_accessor} IN ({placeholders})")
                ).params(**params)
                
        elif operator == "is_null":
            query = query.where(
                text(f"({json_accessor} IS NULL OR {json_accessor} = '')")
            )
            
        elif operator == "is_not_null":
            query = query.where(
                text(f"({json_accessor} IS NOT NULL AND {json_accessor} != '')")
            )
    
    return query


def get_available_filter_fields(original_data_sample: dict) -> List[dict]:
    """
    Get list of available filter fields from a sample location's original_data.
    
    Args:
        original_data_sample: A sample original_data dict from a location
        
    Returns:
        List of field info dicts: [{"field": "BusStopType", "sample_values": ["MKD", "CUS", ...]}, ...]
    """
    if not original_data_sample:
        return []
    
    return [
        {"field": key, "type": type(value).__name__}
        for key, value in original_data_sample.items()
        if value is not None
    ]


def validate_filters(filters: List[dict]) -> tuple[bool, str]:
    """
    Validate a list of filter definitions.
    
    Args:
        filters: List of filter dictionaries
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(filters, list):
        return False, "Filters must be a list"
    
    valid_operators = ["equals", "not_equals", "contains", "in_list", "is_null", "is_not_null"]
    
    for i, filter_def in enumerate(filters):
        if not isinstance(filter_def, dict):
            return False, f"Filter {i} must be a dictionary"
        
        if "field" not in filter_def:
            return False, f"Filter {i} missing 'field' key"
        
        operator = filter_def.get("operator", "equals")
        if operator not in valid_operators:
            return False, f"Filter {i} has invalid operator '{operator}'. Valid: {valid_operators}"
        
        # Value is required for most operators
        if operator not in ["is_null", "is_not_null"] and "value" not in filter_def:
            return False, f"Filter {i} missing 'value' key (required for operator '{operator}')"
        
        # in_list requires a list value
        if operator == "in_list" and not isinstance(filter_def.get("value"), list):
            return False, f"Filter {i} with 'in_list' operator requires value to be a list"
    
    return True, ""
