"""
DataStack Compass — Classify Breaking Changes
=============================================

Phân loại các breaking changes thành các categories cụ thể và đánh giá impact.
Categories: API_CHANGE, CONFIG_CHANGE, BEHAVIOR_CHANGE, REMOVAL, DEPENDENCY_CHANGE, SECURITY, UNCATEGORIZED
Impact: High, Medium, Low
"""

import re
from typing import Dict, Any
from pyspark.sql.functions import udf
from pyspark.sql.types import StructType, StructField, StringType, BooleanType

def classify_breaking_change(text: str) -> Dict[str, Any]:
    """Phân loại breaking change theo keyword matching."""
    if not text:
        return {"text": "", "category": "UNCATEGORIZED", "impact": "Low", "action_required": False}
        
    text_lower = text.lower()
    
    categories = {
        "REMOVAL": ["removed", "deleted", "dropped", "no longer supported", "deprecated and removed"],
        "SECURITY": ["security", "authentication", "authorization", "ssl", "tls", "credential", "permission"],
        "API_CHANGE": ["api", "method", "function", "endpoint", "interface", "signature", "parameter", "return type"],
        "DEPENDENCY_CHANGE": ["requires", "dependency", "upgrade", "minimum version", "java", "scala", "python"],
        "CONFIG_CHANGE": ["configuration", "config", "property", "setting", "default value", "parameter value"],
        "BEHAVIOR_CHANGE": ["behavior", "behaviour", "semantic", "no longer", "now returns", "changed to"]
    }
    
    priority_order = ["REMOVAL", "SECURITY", "API_CHANGE", "DEPENDENCY_CHANGE", "CONFIG_CHANGE", "BEHAVIOR_CHANGE"]
    
    matched_category = "UNCATEGORIZED"
    for cat in priority_order:
        keywords = categories[cat]
        if any(kw in text_lower for kw in keywords):
            matched_category = cat
            break
            
    if matched_category in ["REMOVAL", "SECURITY"]:
        impact = "High"
    elif matched_category in ["API_CHANGE", "DEPENDENCY_CHANGE"]:
        impact = "Medium"
    elif matched_category in ["CONFIG_CHANGE", "BEHAVIOR_CHANGE"]:
        impact = "Low"
    else:
        impact = "Low"
        
    action_required = impact in ["High", "Medium"]
    
    return {
        "text": text,
        "category": matched_category,
        "impact": impact,
        "action_required": action_required
    }

breaking_change_schema = StructType([
    StructField("text", StringType(), False),
    StructField("category", StringType(), False),
    StructField("impact", StringType(), False),
    StructField("action_required", BooleanType(), False)
])

classify_breaking_change_udf = udf(classify_breaking_change, breaking_change_schema)
