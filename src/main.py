import sqlean
import os
import asyncio
import time
import hashlib
import json
import uuid
import glob
import platform
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header, Request
from fastapi.security import APIKeyHeader
import uvicorn
import sqlglot
from sqlglot.optimizer import optimize
from config import settings
from api.types import QueryRequest, QueryResponse, ConvertedQueryRequest, ConvertedQueryResponse, OptimizedQueryRequest, OptimizedQueryResponse, LoadExtensionRequest
from services.cache_service import QueryCache
# Create directories if they don't exist
os.makedirs(settings.DB_DIR, exist_ok=True)
os.makedirs(settings.EXTENSIONS_DIR, exist_ok=True)

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION
)

# Authentication system
api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )
    return api_key

# Connections and management structures
db_connections = {}  # Stores connections for each database
db_extensions = {}   # Stores loaded extensions for each DB: {db_name: [extension_names]}
query_results = {}   # Stores results for ongoing queries
executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)

# Cache instance
query_cache = QueryCache()

# Determines file extension for shared libraries based on operating system
def get_extension_file_pattern():
    system = platform.system().lower()
    if system == 'linux':
        return '*.so'
    elif system == 'darwin':
        return '*.dylib'
    elif system == 'windows':
        return '*.dll'
    else:
        return '*'  # Try any file on unknown systems
    
def load_all_extensions(db_name):
    """Load all available extensions for a database"""
    extensions = discover_extensions()
    for ext in extensions:
        try:
            load_extension(db_name, os.path.splitext(ext['name'])[0])
        except Exception as e:
            print(f"Could not load extension {ext['name']}: {str(e)}")

# Function to get or create a database connection
def get_db_connection(db_name, load_extensions=True):
    """Gets or creates a connection to the specified database"""
    if db_name not in db_connections:
        db_path = os.path.join(settings.DB_DIR, f"{db_name}.db")
        # Enable extension loading
        sqlean.extensions.enable_all()
        conn = sqlean.connect(db_path)
        conn.enable_load_extension(True)

        # Load extensions from shared libraries
        if load_extensions:
            load_all_extensions(db_name=db_name)

        # WAL mode
        conn.execute("PRAGMA journal_mode=WAL")

        conn.row_factory = sqlean.Row
        db_connections[db_name] = conn
        db_extensions[db_name] = [
            ext for ext in os.listdir(settings.EXTENSIONS_DIR)
            if ext.endswith(get_extension_file_pattern())
        ]
    return db_connections[db_name]

# Loads a specific extension in a database
def load_extension(db_name, extension_name, entry_point=None):
    """Loads a specified extension into a database"""
    conn = get_db_connection(db_name, load_extensions=False)
    extension_path = os.path.join(settings.EXTENSIONS_DIR, extension_name)
    
    try:
        if entry_point:
            conn.load_extension(extension_path, entry_point)
        else:
            conn.load_extension(extension_path)
        
        # Add to the list of loaded extensions for this database
        if extension_name not in db_extensions.get(db_name, []):
            if db_name not in db_extensions:
                db_extensions[db_name] = []
            db_extensions[db_name].append(extension_name)
        
        return True
    except sqlean.Error as e:
        raise Exception(f"Error loading extension '{extension_name}': {str(e)}")

# Function to execute queries in a separate thread
def execute_query(query_id, query, params, db_name, cache_ttl=None, force_refresh=False):
    """Executes a query in a separate thread with caching support"""
    start_time = time.time()
    try:
        # Check cache first, unless force_refresh is True
        cache_key = generate_cache_key(query, params, db_name)
        if not force_refresh:
            cached_result, hit = query_cache.get(cache_key)
            if hit:
                query_results[query_id] = {
                    "status": "completed",
                    "result": cached_result,
                    "cached": True,
                    "execution_time": 0.0
                }
                return
        
        # If not in cache or force_refresh is True, execute the query
        conn = get_db_connection(db_name)
        cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Check if it's a SELECT query or a modification operation
        if query.strip().upper().startswith("SELECT"):
            results = [dict(row) for row in cursor.fetchall()]
            
            # Store in cache if it's a SELECT query
            if not query.strip().upper().startswith("SELECT SQLITE_"):  # Don't cache metadata queries
                query_cache.set(cache_key, results, cache_ttl)
            
            query_results[query_id] = {
                "status": "completed",
                "result": results,
                "cached": False,
                "execution_time": time.time() - start_time
            }
        else:
            # For modification operations, don't use cache
            conn.commit()
            query_results[query_id] = {
                "status": "completed",
                "result": [{"rows_affected": cursor.rowcount}],
                "cached": False,
                "execution_time": time.time() - start_time
            }
    except Exception as e:
        query_results[query_id] = {
            "status": "error",
            "error": str(e),
            "execution_time": time.time() - start_time
        }
        print(f"Error executing query: {str(e)}")

# Function to generate a cache key based on query and parameters
def generate_cache_key(query, params, db_name):
    """Generates a unique cache key for a query"""
    query_normalized = " ".join(query.split()).lower()
    params_str = json.dumps(params, sort_keys=True) if params else ""
    key_data = f"{db_name}:{query_normalized}:{params_str}"
    return hashlib.md5(key_data.encode()).hexdigest()

# Periodic task to clean up expired cache
async def periodic_cache_cleanup():
    """Periodically cleans up expired cache entries"""
    while True:
        await asyncio.sleep(60)  # Every minute
        query_cache.cleanup_expired()

# Initialize a database with example table
def init_db(db_name):
    """Initializes a database with an example table"""
    print(f"Initializing database '{db_name}'")
    db_path = os.path.join(settings.DB_DIR, f"{db_name}.db")
    sqlean.extensions.enable_all()
    conn = sqlean.connect(db_path)
    # Enable extension loading
    conn.enable_load_extension(True)
    cursor = conn.cursor()
    
    # Example table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS example (
        id INTEGER PRIMARY KEY,
        name TEXT,
        value REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()

def optimize_query(query):
    """Optimizes an SQL query using sqlglot"""
    try:
        return optimize(sqlglot.parse_one(query)).sql(pretty=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error optimizing query: {str(e)}")

def convert_query(origin_dialect, target_dialect, query):
    """Converts a query from one SQL dialect to another"""
    try:
        result = sqlglot.transpile(query, read=origin_dialect, write=target_dialect)
        return result[0] if result else ""
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error converting query: {str(e)}")

# Detects and lists available extensions
def discover_extensions():
    """Discovers available SQLite extensions in the extensions directory"""
    extensions = []
    pattern = get_extension_file_pattern()
    extension_files = glob.glob(os.path.join(settings.EXTENSIONS_DIR, pattern))
    
    for file_path in extension_files:
        extension_name = os.path.basename(file_path)
        extensions.append({
            "name": extension_name,
            "path": file_path
        })
    
    return extensions

# API Endpoints

@app.post("/tools/optimize", response_model=OptimizedQueryResponse, tags=["Tools"])
async def optimize_query_endpoint(
    query_req: OptimizedQueryRequest,
    api_key: str = Depends(verify_api_key)
):
    """Optimizes an SQL query for better performance"""
    return OptimizedQueryResponse(
        optimized_query=optimize_query(query_req.query)
    )

@app.post("/tools/convert", response_model=ConvertedQueryResponse, tags=["Tools"])
async def convert_query_endpoint(
    query_req: ConvertedQueryRequest,
    api_key: str = Depends(verify_api_key)
):
    """Converts an SQL query from one dialect to another"""
    return ConvertedQueryResponse(
        converted_query=convert_query(query_req.origin_dialect, query_req.target_dialect, query_req.query)
    )


@app.post("/query", response_model=QueryResponse, tags=["Queries"])
async def run_query(
    query_req: QueryRequest, 
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Executes an SQL query against a specified database"""
    # Generate a unique ID for the query
    query_id = str(uuid.uuid4())
    
    # Initialize query status
    query_results[query_id] = {"status": "pending"}
    
    # Execute the query in a separate thread
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        executor, 
        execute_query, 
        query_id, 
        query_req.query, 
        query_req.params,
        query_req.db_name,
        query_req.cache_ttl,
        query_req.force_refresh
    )
    
    # Return the result or error
    result_data = query_results[query_id]
    
    # Clean up the result from memory after a while
    async def cleanup():
        await asyncio.sleep(300)  # Clean up after 5 minutes
        if query_id in query_results:
            del query_results[query_id]
            
    background_tasks.add_task(cleanup)
    
    # Prepare the response
    response = {
        "id": query_id,
        "status": result_data["status"],
        "cached": result_data.get("cached", False),
        "execution_time": result_data.get("execution_time")
    }
    
    if "result" in result_data:
        response["result"] = result_data["result"]
    if "error" in result_data:
        response["error"] = result_data["error"]

    print(response)
        
    return response

@app.get("/query/{query_id}", response_model=QueryResponse, tags=["Queries"])
async def get_query_status(
    query_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Retrieves the status and results of a previously executed query"""
    if query_id not in query_results:
        raise HTTPException(status_code=404, detail="Query not found")
    
    result_data = query_results[query_id]
    
    response = {
        "id": query_id,
        "status": result_data["status"],
        "cached": result_data.get("cached", False),
        "execution_time": result_data.get("execution_time")
    }
    
    if "result" in result_data:
        response["result"] = result_data["result"]
    if "error" in result_data:
        response["error"] = result_data["error"]
        
    return response

@app.post("/db/{db_name}", status_code=201, tags=["Databases"])
async def create_database(
    db_name: str,
    api_key: str = Depends(verify_api_key)
):
    """Creates a new SQLite database"""
    if not db_name.isalnum():
        raise HTTPException(status_code=400, detail="Database name must contain only letters and numbers")
    
    try:
        init_db(db_name)
        return {"message": f"Database '{db_name}' created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating database: {str(e)}")

# Extension management endpoints
@app.get("/extensions", tags=["Extensions"])
async def list_extensions(
    api_key: str = Depends(verify_api_key)
):
    """Lists all available SQLite extensions"""
    extensions = discover_extensions()
    
    # Add information about which databases have each extension loaded
    for ext in extensions:
        ext["loaded_in_dbs"] = []
        for db_name, loaded_exts in db_extensions.items():
            if os.path.basename(ext["path"]) in loaded_exts:
                ext["loaded_in_dbs"].append(db_name)
    
    return {"extensions": extensions}

@app.post("/extensions/load", tags=["Extensions"])
async def load_extension_endpoint(
    req: LoadExtensionRequest,
    api_key: str = Depends(verify_api_key)
):
    """Loads an extension into a specified database"""
    # Check if the database exists
    db_path = os.path.join(settings.DB_DIR, f"{req.db_name}.db")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail=f"Database '{req.db_name}' not found")
    
    # Check if the extension exists
    extension_path = os.path.join(settings.EXTENSIONS_DIR, req.extension_name)
    if not os.path.exists(extension_path):
        raise HTTPException(
            status_code=404, 
            detail=f"Extension '{req.extension_name}' not found in {settings.EXTENSIONS_DIR}"
        )
    
    try:
        # Try to load the extension
        load_extension(req.db_name, req.extension_name, req.entry_point)
        return {
            "message": f"Extension '{req.extension_name}' successfully loaded into database '{req.db_name}'",
            "db_name": req.db_name,
            "extension": req.extension_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/extensions/{extension_name}", tags=["Extensions"])
async def get_extension_info(
    extension_name: str,
    api_key: str = Depends(verify_api_key)
):
    """Gets information about a specific extension"""
    extension_path = os.path.join(settings.EXTENSIONS_DIR, extension_name)
    if not os.path.exists(extension_path):
        raise HTTPException(
            status_code=404, 
            detail=f"Extension '{extension_name}' not found"
        )
    
    # List databases that have this extension loaded
    loaded_in_dbs = []
    for db_name, extensions in db_extensions.items():
        if extension_name in extensions:
            loaded_in_dbs.append(db_name)
    
    return {
        "name": extension_name,
        "path": extension_path,
        "loaded_in_dbs": loaded_in_dbs
    }

@app.get("/db/{db_name}/extensions", tags=["Extensions"])
async def get_db_extensions(
    db_name: str,
    api_key: str = Depends(verify_api_key)
):
    """Lists all extensions loaded in a specific database"""
    if db_name not in db_extensions:
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found or has no extensions")
    
    return {
        "db_name": db_name,
        "extensions": db_extensions[db_name]
    }

@app.post("/extensions/upload", tags=["Extensions"])
async def upload_extension(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """Upload a new SQLite extension (placeholder for future implementation)"""
    # Basic implementation for demonstration
    # In a production system, a proper file upload should be implemented
    raise HTTPException(
        status_code=501, 
        detail="Extension upload not implemented in this version. Manually place files in the 'extensions/' directory"
    )

@app.on_event("startup")
async def startup_event():
    """Runs when the API starts up"""
    # Create the default database if it doesn't exist
    databases = os.listdir(settings.DB_DIR)
    ## initialize all databases
    for db_name in databases:
        db_path = os.path.join(settings.DB_DIR, f"{db_name}")
        if not os.path.exists(db_path):
            init_db(db_name)
            print(f"Database '{db_name}' created")
        else:
            print(f"Database '{db_name}' already exists")
        db_connections[db_name] = sqlean.connect(db_path)
        db_extensions[db_name] = []
    
    # Start the periodic cache cleanup task
    asyncio.create_task(periodic_cache_cleanup())
    
    # Try to automatically load available extensions into the default database
    try:
        extensions = discover_extensions()
        for ext in extensions:
            try:
                load_extension("default", os.path.basename(ext["path"]))
                print(f"Extension {ext['name']} automatically loaded into 'default' database")
            except Exception as e:
                print(f"Could not load extension {ext['name']}: {str(e)}")
    except Exception as e:
        print(f"Error discovering extensions: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    """Runs when the API is shutting down"""
    # Close all database connections
    for conn in db_connections.values():
        conn.close()
    # Shut down the thread pool
    executor.shutdown()

if __name__ == "__main__":
    print(settings)
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)