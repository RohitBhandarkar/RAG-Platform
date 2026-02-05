from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    GEMINI_API_KEY: str = Field(None)
    GEMINI_MODEL: str = Field("gemini-pro")

    LLM_BASE_URL: str = Field("http://localhost:11434/v1")
    LLM_MODEL: str = Field("llama3.1")

    # Vertex AI settings
    GOOGLE_CLOUD_PROJECT: str = Field(None)
    VERTEX_LOCATION: str = Field("us-central1")

    ENVIRONMENT: str = Field("development")
    API_HOST: str = Field("0.0.0.0")
    API_PORT: int = Field(8080)
    FRONTEND_URL: str = Field("http://localhost:3000")

    DOC_STORAGE_ROOT: str = Field("../data")

    POSTGRES_HOST: str = Field("localhost")
    POSTGRES_PORT: int = Field(5432)
    POSTGRES_DB: str = Field("formulation_rag")
    POSTGRES_USER: str = Field("postgres")
    POSTGRES_PASSWORD: str = Field("postgres")

    # Embedding settings (sentence-transformers)
    EMBEDDING_MODEL: str = Field("all-MiniLM-L6-v2")
    EMBEDDING_DIMENSION: int = Field(384)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

__all__ = ["Settings", "settings"]
