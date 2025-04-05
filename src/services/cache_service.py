import time
import json
import hashlib
from typing import Dict, Any, List, Tuple, Optional
from config import settings

class QueryCache:
    """
    LRU cache implementation for query results with expiration.
    
    Features:
    - Time-based expiration
    - LRU (Least Recently Used) eviction policy
    - Cache statistics
    - Custom TTL per item
    """
    
    def __init__(self):
        """Initialize the cache."""
        self.cache = {}  # {hash: {result, timestamp, hits, last_hit_time}}
        self.expiration_times = {}  # {hash: expiration_time}
        self.lru_keys = []  # List to implement LRU
        self.max_cache_size = settings.MAX_CACHE_SIZE
        self.default_ttl = settings.CACHE_EXPIRY
    
    def get(self, cache_key: str) -> Tuple[Optional[Any], bool]:
        """
        Retrieve an item from the cache if it exists and is valid.
        
        Args:
            cache_key: The key to look up in the cache
            
        Returns:
            Tuple of (result, hit) where:
            - result is the cached data or None if not found
            - hit is a boolean indicating if the cache lookup was successful
        """
        if cache_key in self.cache:
            cache_item = self.cache[cache_key]
            expiry = self.expiration_times.get(cache_key, time.time() + self.default_ttl)
            
            # Check if the cache has expired
            if time.time() < expiry:
                # Update usage statistics
                cache_item["hits"] += 1
                cache_item["last_hit_time"] = time.time()
                
                # Update position in LRU list
                if cache_key in self.lru_keys:
                    self.lru_keys.remove(cache_key)
                self.lru_keys.append(cache_key)
                
                return cache_item["result"], True
            else:
                # Remove expired item
                self._remove_item(cache_key)
        
        return None, False
    
    def set(self, cache_key: str, result: Any, ttl: Optional[int] = None) -> None:
        """
        Add or update an item in the cache.
        
        Args:
            cache_key: The key to store the result under
            result: The data to cache
            ttl: Time-to-live in seconds, uses default if None
        """
        if len(self.cache) >= self.max_cache_size:
            # Remove the least recently used item
            self._remove_lru_item()
        
        # Calculate expiration time
        expiry_time = time.time() + (ttl if ttl is not None else self.default_ttl)
        
        # Store result and metadata
        self.cache[cache_key] = {
            "result": result,
            "timestamp": time.time(),
            "hits": 1,
            "last_hit_time": time.time()
        }
        self.expiration_times[cache_key] = expiry_time
        
        # Add to LRU list
        if cache_key in self.lru_keys:
            self.lru_keys.remove(cache_key)
        self.lru_keys.append(cache_key)
    
    def _remove_item(self, cache_key: str) -> None:
        """
        Remove an item from the cache.
        
        Args:
            cache_key: The key to remove
        """
        if cache_key in self.cache:
            del self.cache[cache_key]
        if cache_key in self.expiration_times:
            del self.expiration_times[cache_key]
        if cache_key in self.lru_keys:
            self.lru_keys.remove(cache_key)
    
    def _remove_lru_item(self) -> None:
        """Remove the least recently used item from the cache."""
        if self.lru_keys:
            lru_key = self.lru_keys.pop(0)
            self._remove_item(lru_key)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Return statistics about the cache.
        
        Returns:
            Dictionary containing cache stats
        """
        stats = {
            "total_items": len(self.cache),
            "hits_by_query": {k: v["hits"] for k, v in self.cache.items()},
            "total_size": sum(len(json.dumps(v["result"])) for v in self.cache.values()),
            "expiration_times": {k: time.ctime(v) for k, v in self.expiration_times.items()}
        }
        return stats
    
    def clear(self) -> None:
        """Clear all items from the cache."""
        self.cache.clear()
        self.expiration_times.clear()
        self.lru_keys.clear()
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired items from the cache.
        
        Returns:
            Number of items removed
        """
        current_time = time.time()
        expired_keys = [
            k for k, v in self.expiration_times.items() 
            if current_time > v
        ]
        
        for key in expired_keys:
            self._remove_item(key)
        
        return len(expired_keys)


# Generate a cache key based on the query and parameters
def generate_cache_key(query: str, params: Optional[Dict[str, Any]], db_name: str) -> str:
    """
    Generate a unique cache key based on the query, parameters, and database name.
    
    Args:
        query: SQL query string
        params: Query parameters
        db_name: Database name
        
    Returns:
        MD5 hash to use as cache key
    """
    query_normalized = " ".join(query.split()).lower()
    params_str = json.dumps(params, sort_keys=True) if params else ""
    key_data = f"{db_name}:{query_normalized}:{params_str}"
    return hashlib.md5(key_data.encode()).hexdigest()