from src.api.types import OptimizedQueryRequest, OptimizedQueryResponse, ConvertedQueryRequest, ConvertedQueryResponse, QueryRequest, QueryResponse
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header, Request
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )
    return api_key

def setup_routes(app):
  @app.post("/tools/optimize", response_model=OptimizedQueryResponse, tags=["Tools"])

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
      db_path = os.path.join(DEFAULT_DB_DIR, f"{req.db_name}.db")
      if not os.path.exists(db_path):
          raise HTTPException(status_code=404, detail=f"Database '{req.db_name}' not found")
      
      # Check if the extension exists
      extension_path = os.path.join(EXTENSIONS_DIR, req.extension_name)
      if not os.path.exists(extension_path):
          raise HTTPException(
              status_code=404, 
              detail=f"Extension '{req.extension_name}' not found in {EXTENSIONS_DIR}"
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
      extension_path = os.path.join(EXTENSIONS_DIR, extension_name)
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
      init_db("default")
      
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