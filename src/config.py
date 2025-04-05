import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    """Application settings configured from environment variables or defaults."""
    
    # API settings
    API_KEY: str = os.getenv("API_KEY", "your-secret-api-key")
    
    # Database settings
    DB_DIR: str = os.getenv("DB_DIR", "databases")
    EXTENSIONS_DIR: str = os.getenv("EXTENSIONS_DIR", "extensions")
    
    # Performance settings
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "30"))
    
    # Cache settings
    CACHE_EXPIRY: int = int(os.getenv("CACHE_EXPIRY", "300"))  # seconds
    MAX_CACHE_SIZE: int = int(os.getenv("MAX_CACHE_SIZE", "1000"))
    
    # Application metadata
    APP_NAME: str = "SQLite Multi-DB REST API with Extensions"
    APP_DESCRIPTION: str = "An API for querying multiple SQLite databases with support for extensions"
    APP_VERSION: str = "1.0.0"

    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create global settings instance
settings = Settings()