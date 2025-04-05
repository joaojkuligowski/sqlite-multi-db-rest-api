# SQLite Multi-DB REST API

A experimental REST API for managing multiple SQLite databases with extension support, caching, query optimization, and SQL dialect conversion. 

## Features

- **Multi-Database Support**: Create and manage multiple SQLite databases
- **SQLite Extension Management**: Load and use SQLite extensions
- **Query Cache**: LRU caching with configurable TTL for query results
- **Asynchronous Execution**: Non-blocking query execution with background processing
- **Query Optimization**: SQL query optimization using SQLGlot
- **SQL Dialect Conversion**: Convert between different SQL dialects
- **Authentication**: API key-based security

## Installation

### Prerequisites

- Python 3.8+
- pip

### Setup

1. Clone the repository:
```bash
git clone https://github.com/joaojkuligowski/sqlite-multi-db-api.git
cd sqlite-multi-db-api
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create an `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

5. Edit the `.env` file to set your API key and other configuration options.

### Running the Server

```bash
python src/main.py
```

This will start the server on http://localhost:8000.

## API Endpoints

### Query Execution

- `POST /query` - Execute a SQL query
- `GET /query/{query_id}` - Get status and results of a query

### Database Management

- `POST /db/{db_name}` - Create a new database

### Extensions Management

- `GET /extensions` - List available extensions
- `POST /extensions/load` - Load an extension into a database
- `GET /extensions/{extension_name}` - Get information about an extension
- `GET /db/{db_name}/extensions` - List extensions loaded in a database

### Query Tools

- `POST /tools/optimize` - Optimize a SQL query
- `POST /tools/convert` - Convert a query between SQL dialects

## Usage Examples

### Running a Query

```bash
curl -X POST "http://localhost:8000/query" \
     -H "X-API-Key: your-secret-api-key" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "SELECT * FROM example LIMIT 10",
       "db_name": "default",
       "cache_ttl": 300
     }'
```

### Creating a New Database

```bash
curl -X POST "http://localhost:8000/db/my_new_db" \
     -H "X-API-Key: your-secret-api-key"
```

### Loading an Extension

```bash
curl -X POST "http://localhost:8000/extensions/load" \
     -H "X-API-Key: your-secret-api-key" \
     -H "Content-Type: application/json" \
     -d '{
       "extension_name": "my_extension.so",
       "db_name": "default"
     }'
```

### Optimizing a Query

```bash
curl -X POST "http://localhost:8000/tools/optimize" \
     -H "X-API-Key: your-secret-api-key" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "SELECT a.id, b.name FROM table_a a LEFT JOIN table_b b ON a.id = b.id WHERE a.value > 10"
     }'
```

### Converting Between SQL Dialects

```bash
curl -X POST "http://localhost:8000/tools/convert" \
     -H "X-API-Key: your-secret-api-key" \
     -H "Content-Type: application/json" \
     -d '{
       "origin_dialect": "sqlite",
       "target_dialect": "mysql",
       "query": "SELECT * FROM users WHERE rowid = 1"
     }'
```

## Configuration

Edit the configuration in `src/config.py` or override using environment variables:

- `API_KEY`: Authentication key for API access
- `DB_DIR`: Directory to store SQLite databases
- `EXTENSIONS_DIR`: Directory for SQLite extensions
- `MAX_WORKERS`: Maximum number of worker threads
- `CACHE_EXPIRY`: Default cache expiration time in seconds
- `MAX_CACHE_SIZE`: Maximum number of items in the query cache

## SQLite Extensions

To use SQLite extensions:

1. Place your `.so` (Linux), `.dll` (Windows), or `.dylib` (macOS) extension files in the `extensions/` directory
2. Load extensions using the API endpoints

## Development

### Running Tests

```bash
pytest tests/
```

### Adding New Features

1. Create new models in the `src/models/` directory
2. Implement service logic in the `src/services/` directory
3. Add new endpoints in the `src/api/routes/` directory
4. Register the endpoints in `src/api/router.py`

## License

MIT

## Acknowledgements

- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLite](https://www.sqlite.org/)
- [SQLGlot](https://github.com/tobymao/sqlglot)