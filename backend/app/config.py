from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    GEMINI_API_KEY: str =Field(None)
    GEMINI_MODEL: str = Field("gemini-3-pro-preview")

    ENVIRONMENT: str = Field("development")
    API_HOST: str = Field("0.0.0.0")
    API_PORT: int = Field(8000)
    FRONTEND_URL: str = Field("http://localhost:3000")

    DOC_STORAGE_ROOT: str = Field("../data")

    POSTGRES_HOST: str = Field("localhost")
    POSTGRES_PORT: int = Field(5432)
    POSTGRES_DB: str = Field("formulation_rag")
    POSTGRES_USER: str = Field("postgres")
    POSTGRES_PASSWORD: str = Field("postgres")

    CHROMA_HOST: str = Field("localhost")
    CHROMA_PORT: int = Field(8000)
    USE_VERTEX_VECTOR_SEARCH: bool = Field(False)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

__all__ = ["Settings", "settings"]
