from sqlalchemy import bindparam, create_engine, text
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
    # Internal (in-house) experimentation
    "internal_experiment_results",
    "internal_experiment_embeddings",
    # Embedding tables (replaces ChromaDB collections)
    "formulation_summary_embeddings",
    "manufacturing_process_embeddings",
    "particle_analytics_embeddings",
    "in_vitro_embeddings",
    "in_vivo_embeddings",
]

# Embedding table names for vector operations
EMBEDDING_TABLES = [
    "formulation_summary_embeddings",
    "manufacturing_process_embeddings",
    "particle_analytics_embeddings",
    "in_vitro_embeddings",
    "in_vivo_embeddings",
    "document_chunk_embeddings",
    "internal_experiment_embeddings",
]

# Tables that have formulation_uid column (for RAG context linking)
EMBEDDING_TABLES_WITH_UID = [
    "formulation_summary_embeddings",
    "manufacturing_process_embeddings",
    "particle_analytics_embeddings",
    "in_vitro_embeddings",
    "in_vivo_embeddings",
]

# Tables that have internal_experiment_result_id (for RAG internal-experiment retrieval)
EMBEDDING_TABLES_WITH_INTERNAL_RESULT_ID = [
    "internal_experiment_embeddings",
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
    include_uid = table in EMBEDDING_TABLES_WITH_UID
    include_internal_result_id = table in EMBEDDING_TABLES_WITH_INTERNAL_RESULT_ID

    # Build query; include formulation_uid or internal_experiment_result_id when present
    if include_uid:
        base_query = f"""
            SELECT 
                id,
                text_content,
                1 - (embedding <=> CAST(:embedding AS vector)) as similarity,
                metadata,
                formulation_uid
            FROM {table}
            WHERE embedding IS NOT NULL
        """
    elif include_internal_result_id:
        base_query = f"""
            SELECT 
                id,
                text_content,
                1 - (embedding <=> CAST(:embedding AS vector)) as similarity,
                metadata,
                internal_experiment_result_id
            FROM {table}
            WHERE embedding IS NOT NULL
        """
    else:
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
                out = {
                    "id": row[0],
                    "text_content": row[1],
                    "similarity": float(row[2]) if row[2] else 0.0,
                    "metadata": row[3],
                }
                if include_uid:
                    out["formulation_uid"] = row[4]
                elif include_internal_result_id:
                    out["internal_experiment_result_id"] = row[4]
                rows.append(out)
            return rows
    except Exception as e:
        raise RuntimeError(f"Vector search failed: {e}")


def get_formulation_context_by_uids(formulation_uids: list[str]) -> list[dict]:
    """
    Fetch full formulation context (formulation + excipients + manufacturing) by formulation_uid list.

    Returns one dict per formulation with keys: formulation, excipients, manufacturing_processes.
    Formulations not found are skipped; order is not guaranteed.
    """
    if not formulation_uids:
        return []
    uids = [u for u in formulation_uids if u]
    if not uids:
        return []
    try:
        with engine.connect() as connection:
            # formulations by formulation_uid
            placeholders = ", ".join([f":uid{i}" for i in range(len(uids))])
            params = {f"uid{i}": uids[i] for i in range(len(uids))}
            result = connection.execute(
                text(f"""
                    SELECT id, formulation_uid, source_document_id, api_id, formulation_name,
                           drug_name, dosage_form, formulation_type, bcs_class,
                           route_of_administration, therapeutic_area, created_at, metadata
                    FROM formulations
                    WHERE formulation_uid IN ({placeholders})
                """),
                params,
            )
            form_rows = result.fetchall()
            if not form_rows:
                return []
            form_by_id = {}
            form_by_uid = {}
            for r in form_rows:
                fid = r[0]
                uid = r[1]
                form_by_id[fid] = {
                    "id": fid,
                    "formulation_uid": uid,
                    "source_document_id": r[2],
                    "api_id": r[3],
                    "formulation_name": r[4],
                    "drug_name": r[5],
                    "dosage_form": r[6],
                    "formulation_type": r[7],
                    "bcs_class": r[8],
                    "route_of_administration": r[9],
                    "therapeutic_area": r[10],
                    "created_at": str(r[11]) if r[11] else None,
                    "metadata": r[12],
                    "excipients": [],
                    "manufacturing_processes": [],
                }
                form_by_uid[uid] = form_by_id[fid]
            fids = list(form_by_id.keys())

            # formulation_excipients + excipients
            fid_placeholders = ", ".join([f":fid{i}" for i in range(len(fids))])
            fid_params = {f"fid{i}": fids[i] for i in range(len(fids))}
            exc_result = connection.execute(
                text(f"""
                    SELECT fe.formulation_id, e.name, fe.amount, fe.unit, fe.role
                    FROM formulation_excipients fe
                    JOIN excipients e ON e.id = fe.excipient_id
                    WHERE fe.formulation_id IN ({fid_placeholders})
                """),
                fid_params,
            )
            for r in exc_result.fetchall():
                form_by_id[r[0]]["excipients"].append({
                    "name": r[1],
                    "amount": float(r[2]) if r[2] is not None else None,
                    "unit": r[3],
                    "role": r[4],
                })

            # manufacturing_processes
            mp_result = connection.execute(
                text(f"""
                    SELECT formulation_id, id, process_type, process_description,
                           batch_size, scale, equipment_used, metadata
                    FROM manufacturing_processes
                    WHERE formulation_id IN ({fid_placeholders})
                """),
                fid_params,
            )
            for r in mp_result.fetchall():
                form_by_id[r[0]]["manufacturing_processes"].append({
                    "id": r[1],
                    "process_type": r[2],
                    "process_description": r[3],
                    "batch_size": r[4],
                    "scale": r[5],
                    "equipment_used": list(r[6]) if r[6] else [],
                    "metadata": r[7],
                })

            return [form_by_uid[uid] for uid in uids if uid in form_by_uid]
    except Exception as e:
        raise RuntimeError(f"get_formulation_context_by_uids failed: {e}")


def get_internal_experiment_results(
    bcs_class: str,
    molecular_weight: float | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Fetch internal (in-house) experiment results matching the given BCS class and
    optional molecular weight. Rows with both molecular_weight_min and molecular_weight_max
    NULL match any MW; otherwise MW must fall within the range.

    Returns list of dicts with keys: id, bcs_class, molecular_weight_min, molecular_weight_max,
    experiment_summary, notes, outcome, conducted_at, created_at, metadata.
    """
    if not bcs_class or not bcs_class.strip():
        return []
    try:
        with engine.connect() as connection:
            if molecular_weight is not None:
                result = connection.execute(
                    text("""
                        SELECT id, bcs_class, molecular_weight_min, molecular_weight_max,
                               experiment_summary, notes, outcome, conducted_at, created_at, metadata
                        FROM internal_experiment_results
                        WHERE bcs_class = :bcs_class
                          AND (
                            (molecular_weight_min IS NULL AND molecular_weight_max IS NULL)
                            OR (
                              (molecular_weight_min IS NULL OR molecular_weight_min <= :mw)
                              AND (molecular_weight_max IS NULL OR molecular_weight_max >= :mw)
                            )
                          )
                        ORDER BY conducted_at DESC NULLS LAST, created_at DESC
                        LIMIT :limit
                    """),
                    {"bcs_class": bcs_class.strip(), "mw": molecular_weight, "limit": limit},
                )
            else:
                result = connection.execute(
                    text("""
                        SELECT id, bcs_class, molecular_weight_min, molecular_weight_max,
                               experiment_summary, notes, outcome, conducted_at, created_at, metadata
                        FROM internal_experiment_results
                        WHERE bcs_class = :bcs_class
                        ORDER BY conducted_at DESC NULLS LAST, created_at DESC
                        LIMIT :limit
                    """),
                    {"bcs_class": bcs_class.strip(), "limit": limit},
                )
            rows = result.fetchall()
            return [
                {
                    "id": r[0],
                    "bcs_class": r[1],
                    "molecular_weight_min": float(r[2]) if r[2] is not None else None,
                    "molecular_weight_max": float(r[3]) if r[3] is not None else None,
                    "experiment_summary": r[4],
                    "notes": r[5],
                    "outcome": r[6],
                    "conducted_at": str(r[7]) if r[7] else None,
                    "created_at": str(r[8]) if r[8] else None,
                    "metadata": r[9],
                }
                for r in rows
            ]
    except Exception as e:
        if "internal_experiment_results" in str(e) and "does not exist" in str(e).lower():
            return []
        raise RuntimeError(f"get_internal_experiment_results failed: {e}")


def get_internal_experiment_results_by_ids(ids: list[int]) -> list[dict]:
    """
    Fetch full rows from internal_experiment_results by id list (e.g. from vector search).
    Returns list of dicts with same shape as get_internal_experiment_results; order follows ids.
    """
    if not ids:
        return []
    unique_ids = list(dict.fromkeys(i for i in ids if i is not None))
    if not unique_ids:
        return []
    try:
        stmt = text("""
            SELECT id, bcs_class, molecular_weight_min, molecular_weight_max,
                   experiment_summary, notes, outcome, conducted_at, created_at, metadata
            FROM internal_experiment_results
            WHERE id IN :ids
        """).bindparams(bindparam("ids", expanding=True))
        with engine.connect() as connection:
            result = connection.execute(stmt, {"ids": unique_ids})
            rows_by_id = {
                r[0]: {
                    "id": r[0],
                    "bcs_class": r[1],
                    "molecular_weight_min": float(r[2]) if r[2] is not None else None,
                    "molecular_weight_max": float(r[3]) if r[3] is not None else None,
                    "experiment_summary": r[4],
                    "notes": r[5],
                    "outcome": r[6],
                    "conducted_at": str(r[7]) if r[7] else None,
                    "created_at": str(r[8]) if r[8] else None,
                    "metadata": r[9],
                }
                for r in result.fetchall()
            }
            return [rows_by_id[i] for i in unique_ids if i in rows_by_id]
    except Exception as e:
        if "internal_experiment_results" in str(e) and "does not exist" in str(e).lower():
            return []
        raise RuntimeError(f"get_internal_experiment_results_by_ids failed: {e}")


def create_internal_experiment_stub(
    report_id: str,
    bcs_class: str,
    molecular_weight: float | None = None,
) -> int:
    """
    Create a placeholder row in internal_experiment_results when a RAG report is generated.
    Chemists can later populate experiment_summary, notes, outcome, conducted_at via the API.
    Returns the id of the created row.
    """
    if not report_id or not bcs_class:
        raise ValueError("report_id and bcs_class are required")
    mw_min = molecular_weight if molecular_weight is not None else None
    mw_max = molecular_weight if molecular_weight is not None else None
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    INSERT INTO internal_experiment_results
                    (report_id, bcs_class, molecular_weight_min, molecular_weight_max, experiment_summary)
                    VALUES (:report_id, :bcs_class, :mw_min, :mw_max, 'To be populated')
                    RETURNING id
                """),
                {
                    "report_id": report_id,
                    "bcs_class": bcs_class.strip(),
                    "mw_min": mw_min,
                    "mw_max": mw_max,
                },
            )
            connection.commit()
            return result.scalar()
    except Exception as e:
        raise RuntimeError(f"create_internal_experiment_stub failed: {e}")


def _row_to_internal_experiment_dict(row) -> dict:
    """Convert a result row to the standard internal experiment dict."""
    return {
        "id": row[0],
        "report_id": row[1],
        "bcs_class": row[2],
        "molecular_weight_min": float(row[3]) if row[3] is not None else None,
        "molecular_weight_max": float(row[4]) if row[4] is not None else None,
        "experiment_summary": row[5],
        "notes": row[6],
        "outcome": row[7],
        "conducted_at": str(row[8]) if row[8] else None,
        "created_at": str(row[9]) if row[9] else None,
        "metadata": row[10],
    }


def get_internal_experiment_by_report_id(report_id: str) -> dict | None:
    """
    Fetch the first internal_experiment_results row for the given report_id.
    Returns None if not found. (For multiple rows, use get_internal_experiment_results_by_report_id.)
    """
    rows = get_internal_experiment_results_by_report_id(report_id)
    return rows[0] if rows else None


def get_internal_experiment_results_by_report_id(report_id: str) -> list[dict]:
    """
    Fetch all internal_experiment_results rows for the given report_id (ordered by id).
    Allows multiple in-house experiment entries per report.
    """
    if not report_id:
        return []
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    SELECT id, report_id, bcs_class, molecular_weight_min, molecular_weight_max,
                           experiment_summary, notes, outcome, conducted_at, created_at, metadata
                    FROM internal_experiment_results
                    WHERE report_id = :report_id
                    ORDER BY id
                """),
                {"report_id": report_id},
            )
            return [_row_to_internal_experiment_dict(r) for r in result.fetchall()]
    except Exception as e:
        if "internal_experiment_results" in str(e) and "does not exist" in str(e).lower():
            return []
        raise RuntimeError(f"get_internal_experiment_results_by_report_id failed: {e}")


def get_stub_internal_experiment_by_report_id(report_id: str) -> dict | None:
    """Return the first row for this report_id that is still a stub (experiment_summary = 'To be populated')."""
    if not report_id:
        return None
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    SELECT id, report_id, bcs_class, molecular_weight_min, molecular_weight_max,
                           experiment_summary, notes, outcome, conducted_at, created_at, metadata
                    FROM internal_experiment_results
                    WHERE report_id = :report_id AND experiment_summary = 'To be populated'
                    ORDER BY id
                    LIMIT 1
                """),
                {"report_id": report_id},
            )
            row = result.fetchone()
            return _row_to_internal_experiment_dict(row) if row else None
    except Exception as e:
        if "internal_experiment_results" in str(e) and "does not exist" in str(e).lower():
            return None
        raise RuntimeError(f"get_stub_internal_experiment_by_report_id failed: {e}")


def insert_internal_experiment_result(
    report_id: str,
    bcs_class: str,
    molecular_weight_min: float | None,
    molecular_weight_max: float | None,
    experiment_summary: str,
    notes: str | None = None,
    outcome: str | None = None,
    conducted_at: str | None = None,
) -> dict:
    """
    Insert a new internal_experiment_results row (e.g. additional experiment for same report).
    Returns the new row as a dict.
    """
    if not report_id or not bcs_class or not experiment_summary:
        raise ValueError("report_id, bcs_class and experiment_summary are required")
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    INSERT INTO internal_experiment_results
                    (report_id, bcs_class, molecular_weight_min, molecular_weight_max,
                     experiment_summary, notes, outcome, conducted_at)
                    VALUES (:report_id, :bcs_class, :mw_min, :mw_max, :experiment_summary,
                            :notes, :outcome, CAST(:conducted_at AS DATE))
                    RETURNING id, report_id, bcs_class, molecular_weight_min, molecular_weight_max,
                              experiment_summary, notes, outcome, conducted_at, created_at, metadata
                """),
                {
                    "report_id": report_id,
                    "bcs_class": bcs_class.strip(),
                    "mw_min": molecular_weight_min,
                    "mw_max": molecular_weight_max,
                    "experiment_summary": experiment_summary.strip(),
                    "notes": notes.strip() if notes else None,
                    "outcome": outcome.strip() if outcome else None,
                    "conducted_at": conducted_at if conducted_at else None,
                },
            )
            connection.commit()
            row = result.fetchone()
            if not row:
                raise RuntimeError("Insert did not return row")
            return _row_to_internal_experiment_dict(row)
    except Exception as e:
        raise RuntimeError(f"insert_internal_experiment_result failed: {e}")


def update_internal_experiment_from_lab(
    report_id: str,
    experiment_summary: str,
    notes: str | None = None,
    outcome: str | None = None,
    conducted_at: str | None = None,
) -> dict | None:
    """
    Add or update an in-house experiment for this report_id.
    If a stub row exists (experiment_summary = 'To be populated'), update it.
    Otherwise insert a new row (copying bcs_class and MW from an existing row for this report).
    Returns the updated or new row, or None if no row exists for report_id when adding another.
    """
    if not report_id or not experiment_summary:
        raise ValueError("report_id and experiment_summary are required")
    stub = get_stub_internal_experiment_by_report_id(report_id)
    if stub:
        # Update the stub row by id
        try:
            with engine.connect() as connection:
                result = connection.execute(
                    text("""
                        UPDATE internal_experiment_results
                        SET experiment_summary = :experiment_summary,
                            notes = :notes,
                            outcome = :outcome,
                            conducted_at = CAST(:conducted_at AS DATE)
                        WHERE id = :id
                        RETURNING id, report_id, bcs_class, molecular_weight_min, molecular_weight_max,
                                  experiment_summary, notes, outcome, conducted_at, created_at, metadata
                    """),
                    {
                        "id": stub["id"],
                        "experiment_summary": experiment_summary.strip(),
                        "notes": notes.strip() if notes else None,
                        "outcome": outcome.strip() if outcome else None,
                        "conducted_at": conducted_at if conducted_at else None,
                    },
                )
                connection.commit()
                row = result.fetchone()
                return _row_to_internal_experiment_dict(row) if row else None
        except Exception as e:
            raise RuntimeError(f"update_internal_experiment_from_lab failed: {e}")
    # No stub: add a new row (copy bcs/mw from any existing row for this report)
    existing = get_internal_experiment_results_by_report_id(report_id)
    if not existing:
        return None
    first = existing[0]
    return insert_internal_experiment_result(
        report_id=report_id,
        bcs_class=first["bcs_class"],
        molecular_weight_min=first.get("molecular_weight_min"),
        molecular_weight_max=first.get("molecular_weight_max"),
        experiment_summary=experiment_summary,
        notes=notes,
        outcome=outcome,
        conducted_at=conducted_at,
    )


def update_internal_experiment_partial(
    report_id: str,
    experiment_summary: str | None = None,
    notes: str | None = None,
    outcome: str | None = None,
    conducted_at: str | None = None,
    result_id: int | None = None,
) -> dict | None:
    """
    Partially update one internal_experiment_results row for this report_id.
    If result_id is given, update that row (must belong to report_id). Otherwise update the first row.
    Only provided (non-None) fields are updated. Returns the full updated row, or None if not found.
    """
    if not report_id:
        raise ValueError("report_id is required")
    updates = []
    params: dict = {"report_id": report_id}
    if experiment_summary is not None:
        updates.append("experiment_summary = :experiment_summary")
        params["experiment_summary"] = experiment_summary.strip()
    if notes is not None:
        updates.append("notes = :notes")
        params["notes"] = notes.strip() if notes else None
    if outcome is not None:
        updates.append("outcome = :outcome")
        params["outcome"] = outcome.strip() if outcome else None
    if conducted_at is not None:
        updates.append("conducted_at = CAST(:conducted_at AS DATE)")
        params["conducted_at"] = conducted_at if conducted_at else None
    if not updates:
        if result_id is not None:
            rows = get_internal_experiment_results_by_report_id(report_id)
            for r in rows:
                if r["id"] == result_id:
                    return r
            return None
        return get_internal_experiment_by_report_id(report_id)
    set_clause = ", ".join(updates)
    where = "report_id = :report_id"
    if result_id is not None:
        where += " AND id = :result_id"
        params["result_id"] = result_id
    else:
        # Update only the first row (by id) for this report_id
        where += " AND id = (SELECT id FROM internal_experiment_results WHERE report_id = :report_id ORDER BY id LIMIT 1)"
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(f"""
                    UPDATE internal_experiment_results
                    SET {set_clause}
                    WHERE {where}
                    RETURNING id, report_id, bcs_class, molecular_weight_min, molecular_weight_max,
                              experiment_summary, notes, outcome, conducted_at, created_at, metadata
                """),
                params,
            )
            connection.commit()
            row = result.fetchone()
            return _row_to_internal_experiment_dict(row) if row else None
    except Exception as e:
        if "internal_experiment_results" in str(e) and "does not exist" in str(e).lower():
            return None
        raise RuntimeError(f"update_internal_experiment_partial failed: {e}")


def delete_internal_experiment_embeddings_for_result(internal_experiment_result_id: int) -> int:
    """
    Delete all embedding rows for this internal_experiment_result_id (so we can replace with a fresh one).
    Returns the number of rows deleted.
    """
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    DELETE FROM internal_experiment_embeddings
                    WHERE internal_experiment_result_id = :result_id
                """),
                {"result_id": internal_experiment_result_id},
            )
            connection.commit()
            return result.rowcount
    except Exception as e:
        raise RuntimeError(f"delete_internal_experiment_embeddings_for_result failed: {e}")


def insert_internal_experiment_embedding(
    internal_experiment_result_id: int,
    text_content: str,
    embedding: list[float],
    report_id: str | None = None,
    metadata: dict | None = None,
) -> int:
    """
    Insert a row into internal_experiment_embeddings (with optional report_id).
    Returns the id of the inserted row.
    """
    import json
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    INSERT INTO internal_experiment_embeddings
                    (internal_experiment_result_id, text_content, embedding, report_id, metadata)
                    VALUES (:fk_value, :text_content, CAST(:embedding AS vector), :report_id, CAST(:metadata AS jsonb))
                    RETURNING id
                """),
                {
                    "fk_value": internal_experiment_result_id,
                    "text_content": text_content,
                    "embedding": embedding_str,
                    "report_id": report_id,
                    "metadata": json.dumps(metadata) if metadata else "{}",
                },
            )
            connection.commit()
            return result.scalar()
    except Exception as e:
        raise RuntimeError(f"insert_internal_experiment_embedding failed: {e}")


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