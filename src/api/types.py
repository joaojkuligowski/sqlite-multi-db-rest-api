from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class QueryRequest(BaseModel):
    query: str
    params: Optional[Dict[str, Any]] = None
    db_name: str = "default"  # Database name to use
    cache_ttl: Optional[int] = None  # Custom TTL in seconds
    force_refresh: bool = False  # Ignore cache

class ConvertedQueryRequest(BaseModel):
    origin_dialect: str
    target_dialect: str
    query: str 

class OptimizedQueryRequest(BaseModel):
    query: str

# Response models
class ConvertedQueryResponse(BaseModel):
    converted_query: str

class OptimizedQueryResponse(BaseModel):
    optimized_query: str

class QueryResponse(BaseModel):
    id: str
    status: str
    result: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    cached: bool = False
    execution_time: Optional[float] = None

class ExtensionInfo(BaseModel):
    name: str
    path: str
    loaded_in_dbs: List[str]

class LoadExtensionRequest(BaseModel):
    extension_name: str
    db_name: str
    entry_point: Optional[str] = None