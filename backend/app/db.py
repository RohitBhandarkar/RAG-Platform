from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings


def get_database_url() -> str:
    return (
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


engine: Engine = create_engine(get_database_url(), pool_pre_ping=True)


def check_db_connection() -> tuple[bool, Exception]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return (True, None)
    except Exception as e:
        return (False, e)


# Expected tables in the RAG platform schema (18 structured + 6 embedding)
EXPECTED_TABLES = [
    # Core entity tables
    "source_documents",
    "formulations",
    "excipients",
    "apis",
    # Composition tables
    "formulation_excipients",
    "formulation_apis",
    # Manufacturing tables
    "manufacturing_processes",
    "process_parameters",
    # Analytical tables
    "particle_characteristics",
    "analytical_methods",
    "analytical_results",
    # In vitro tables
    "dissolution_profiles",
    "dissolution_timepoints",
    # In vivo tables
    "pk_studies",
    "pk_parameters",
    "bioequivalence_results",
    # Stability tables
    "stability_studies",
    "stability_results",
    # Embedding tables (replaces ChromaDB collections)
    "formulation_summary_embeddings",
    "manufacturing_process_embeddings",
    "particle_analytics_embeddings",
    "in_vitro_embeddings",
    "in_vivo_embeddings",
    "document_chunk_embeddings",
]

# Embedding table names for vector operations
EMBEDDING_TABLES = [
    "formulation_summary_embeddings",
    "manufacturing_process_embeddings",
    "particle_analytics_embeddings",
    "in_vitro_embeddings",
    "in_vivo_embeddings",
    "document_chunk_embeddings",
]


def validate_sql_tables() -> dict:
    """
    Validate that all expected tables exist in the PostgreSQL database.
    
    Returns:
        dict: Validation result with:
            - valid: bool indicating if all tables exist
            - expected: list of expected table names
            - found: list of tables that exist
            - missing: list of tables that don't exist
            - extra: list of unexpected tables in the schema
    """
    try:
        with engine.connect() as connection:
            result = connection.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
            """))
            found_tables = [row[0] for row in result.fetchall()]
        
        missing = [t for t in EXPECTED_TABLES if t not in found_tables]
        extra = [t for t in found_tables if t not in EXPECTED_TABLES]
        
        return {
            "valid": len(missing) == 0,
            "expected": EXPECTED_TABLES,
            "found": found_tables,
            "missing": missing,
            "extra": extra,
            "expected_count": len(EXPECTED_TABLES),
            "found_count": len(found_tables),
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "expected": EXPECTED_TABLES,
            "found": [],
            "missing": EXPECTED_TABLES,
            "extra": [],
        }


def check_pgvector_extension() -> dict:
    """
    Check if the pgvector extension is installed and operational.
    
    Returns:
        dict: Status of pgvector extension with:
            - installed: bool
            - version: str or None
            - vector_ops_available: bool
    """
    try:
        with engine.connect() as connection:
            # Check if extension exists
            result = connection.execute(text("""
                SELECT extversion 
                FROM pg_extension 
                WHERE extname = 'vector'
            """))
            row = result.fetchone()
            
            if row is None:
                return {
                    "installed": False,
                    "version": None,
                    "vector_ops_available": False,
                    "error": "pgvector extension not found"
                }
            
            version = row[0]
            
            # Test vector operations
            connection.execute(text("""
                SELECT '[1,2,3]'::vector <-> '[4,5,6]'::vector
            """))
            
            return {
                "installed": True,
                "version": version,
                "vector_ops_available": True,
            }
    except Exception as e:
        return {
            "installed": False,
            "version": None,
            "vector_ops_available": False,
            "error": str(e)
        }


def get_table_row_counts() -> dict:
    """
    Get row counts for all expected tables.
    
    Returns:
        dict: Table names mapped to their row counts
    """
    counts = {}
    try:
        with engine.connect() as connection:
            for table in EXPECTED_TABLES:
                try:
                    result = connection.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                    counts[table] = result.scalar()
                except Exception:
                    counts[table] = None  # Table doesn't exist or error
        return counts
    except Exception as e:
        return {"error": str(e)}


def get_embedding_counts() -> dict:
    """
    Get row counts for all embedding tables.
    
    Returns:
        dict: Embedding table names mapped to their row counts
    """
    counts = {}
    try:
        with engine.connect() as connection:
            for table in EMBEDDING_TABLES:
                try:
                    result = connection.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                    counts[table] = result.scalar()
                except Exception:
                    counts[table] = None
        return counts
    except Exception as e:
        return {"error": str(e)}


def vector_search(
    table: str,
    query_embedding: list[float],
    n_results: int = 5,
    metadata_filter: dict | None = None,
) -> list[dict]:
    """
    Perform vector similarity search on an embedding table.
    
    Args:
        table: Name of the embedding table (must be in EMBEDDING_TABLES)
        query_embedding: Query vector (384 dimensions for all-MiniLM-L6-v2)
        n_results: Number of results to return
        metadata_filter: Optional JSONB filter for metadata column
        
    Returns:
        list[dict]: Matching rows with id, text_content, similarity score, and metadata
    """
    if table not in EMBEDDING_TABLES:
        raise ValueError(f"Invalid embedding table: {table}. Must be one of {EMBEDDING_TABLES}")
    
    # Convert embedding list to pgvector format
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    
    # Build query with optional metadata filter
    base_query = f"""
        SELECT 
            id,
            text_content,
            1 - (embedding <=> CAST(:embedding AS vector)) as similarity,
            metadata
        FROM {table}
        WHERE embedding IS NOT NULL
    """
    
    if metadata_filter:
        # Add JSONB containment filter
        base_query += " AND metadata @> CAST(:metadata_filter AS jsonb)"
    
    base_query += f"""
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :n_results
    """
    
    try:
        with engine.connect() as connection:
            params = {"embedding": embedding_str, "n_results": n_results}
            if metadata_filter:
                import json
                params["metadata_filter"] = json.dumps(metadata_filter)
            
            result = connection.execute(text(base_query), params)
            rows = []
            for row in result.fetchall():
                rows.append({
                    "id": row[0],
                    "text_content": row[1],
                    "similarity": float(row[2]) if row[2] else 0.0,
                    "metadata": row[3],
                })
            return rows
    except Exception as e:
        raise RuntimeError(f"Vector search failed: {e}")


def insert_embedding(
    table: str,
    text_content: str,
    embedding: list[float],
    foreign_key_column: str,
    foreign_key_value: int,
    metadata: dict | None = None,
) -> int:
    """
    Insert a new embedding into an embedding table.
    
    Args:
        table: Name of the embedding table
        text_content: The text that was embedded
        embedding: The embedding vector (384 dimensions)
        foreign_key_column: Name of the FK column (e.g., 'formulation_id')
        foreign_key_value: ID of the related entity
        metadata: Optional metadata dict
        
    Returns:
        int: ID of the inserted row
    """
    if table not in EMBEDDING_TABLES:
        raise ValueError(f"Invalid embedding table: {table}")
    
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    
    query = f"""
        INSERT INTO {table} ({foreign_key_column}, text_content, embedding, metadata)
        VALUES (:fk_value, :text_content, CAST(:embedding AS vector), CAST(:metadata AS jsonb))
        RETURNING id
    """
    
    try:
        import json
        with engine.connect() as connection:
            result = connection.execute(
                text(query),
                {
                    "fk_value": foreign_key_value,
                    "text_content": text_content,
                    "embedding": embedding_str,
                    "metadata": json.dumps(metadata) if metadata else "{}",
                }
            )
            connection.commit()
            return result.scalar()
    except Exception as e:
        raise RuntimeError(f"Failed to insert embedding: {e}")