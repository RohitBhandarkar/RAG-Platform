<<<<<<< HEAD
"""Configuration management for the RAG application."""

from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    environment: str = Field(..., env="ENVIRONMENT")
    api_host: str = Field(..., env="API_HOST")
    api_port: int = Field(..., env="API_PORT")
    frontend_url: str = Field(..., env="FRONTEND_URL")
    
    # Database
    postgres_host: str = Field(..., env="POSTGRES_HOST")
    postgres_port: int = Field(..., env="POSTGRES_PORT")
    postgres_db: str = Field(..., env="POSTGRES_DB")
    postgres_user: str = Field(..., env="POSTGRES_USER")
    postgres_password: SecretStr = Field(..., env="POSTGRES_PASSWORD")
    
    # Vector Database
    chroma_host: str = Field(..., env="CHROMA_HOST")
    chroma_port: int = Field(..., env="CHROMA_PORT")
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


=======
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
	ENVIRONMENT: str = Field("development")
	API_HOST: str = Field("0.0.0.0")
	API_PORT: int = Field(8000)

	POSTGRES_HOST: str = Field("localhost")
	POSTGRES_PORT: int = Field(5432)
	POSTGRES_DB: str = Field("formulation_rag")
	POSTGRES_USER: str = Field("postgres")
	POSTGRES_PASSWORD: str = Field("postgres")

	class Config:
		env_file = ".env"
		env_file_encoding = "utf-8"
		extra = "ignore"


settings = Settings()

>>>>>>> e79806a (feat: postgresql connection)
__all__ = ["Settings", "settings"]
