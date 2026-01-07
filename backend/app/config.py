"""Configuration management for the RAG application."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    
    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "formulation_rag"
    postgres_user: str = "postgres"
    postgres_password: str = "your_password_here"
    
    # Vector Database
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    use_vertex_vector_search: bool = False
    
    # LLM Providers
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    
    # GCP Settings
    vertex_ai_project_id: Optional[str] = None
    vertex_ai_location: str = "us-central1"
    use_vertex_embeddings: bool = False
    
    # Embeddings
    embedding_model: str = "text-embedding-3-large"
    embedding_dimension: int = 3072
    
    # Cloud Storage
    gcs_bucket_raw: Optional[str] = None
    gcs_bucket_processed: Optional[str] = None
    
    # Secret Manager
    secret_manager_project_id: Optional[str] = None
    
    # Vertex AI Vector Search
    vertex_index_endpoint: Optional[str] = None
    vertex_index_id: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


__all__ = ["Settings", "settings"]
