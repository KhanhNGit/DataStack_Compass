import os
import json
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

def load_fixture(filename: str):
    filepath = os.path.join(os.path.dirname(__file__), '..', 'fixtures', filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

@router.get("/bulletins")
def get_bulletins(page: int = 1, severity: Optional[str] = None):
    env = os.getenv("ENV", "dev").lower()
    
    if env == "prod":
        # Placeholder for StarRocks query in production
        # Example: data = db.query("SELECT * FROM security_bulletins WHERE ...")
        return {"data": [], "meta": {"page": page, "source": "starrocks"}, "errors": []}
    
    # Dev mode: use fixtures
    data = load_fixture("bulletins.json")
    
    # Apply severity filter
    if severity and severity != "All":
        data = [item for item in data if item.get("severity") == severity]
        
    # Basic pagination logic
    per_page = 10
    start = (page - 1) * per_page
    end = start + per_page
    paginated = data[start:end]
    
    return {
        "data": paginated,
        "meta": {
            "page": page,
            "total_count": len(data),
            "source": "fixtures"
        },
        "errors": []
    }

@router.get("/blogs")
def get_blogs(tool: Optional[str] = None, tag: Optional[str] = None):
    env = os.getenv("ENV", "dev").lower()
    
    if env == "prod":
        # Placeholder for StarRocks query in production
        return {"data": [], "meta": {"source": "starrocks"}, "errors": []}
        
    data = load_fixture("blogs.json")
    
    # Apply filters
    if tool and tool != "All":
        data = [item for item in data if item.get("tool") == tool]
        
    if tag and tag != "All":
        data = [item for item in data if tag in item.get("tags", [])]
        
    return {
        "data": data,
        "meta": {
            "total_count": len(data),
            "source": "fixtures"
        },
        "errors": []
    }
