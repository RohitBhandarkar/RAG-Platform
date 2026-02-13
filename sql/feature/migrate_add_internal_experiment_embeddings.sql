-- Migration: internal_experiment_results table for in-house / internal lab experimentation data.
-- Used by RAG to include relevant internal results and notes in the report; when no rows match,
-- the report states that the experiment has not been conducted in-house before.

CREATE TABLE IF NOT EXISTS internal_experiment_results (
    id SERIAL PRIMARY KEY,
    bcs_class VARCHAR(10) NOT NULL,
    molecular_weight_min DECIMAL(12, 4),
    molecular_weight_max DECIMAL(12, 4),
    experiment_summary TEXT NOT NULL,
    notes TEXT,
    outcome VARCHAR(50),
    conducted_at DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_internal_experiment_results_bcs
ON internal_experiment_results (bcs_class);

CREATE INDEX IF NOT EXISTS idx_internal_experiment_results_conducted
ON internal_experiment_results (conducted_at DESC);

COMMENT ON TABLE internal_experiment_results IS 'Internal (in-house) experimentation results and notes; matched by BCS class and optional molecular weight range for RAG report context.';

-- Migration: internal_experiment_embeddings table for vector retrieval of internal experiment results.
-- Populated later by an embedding pipeline; enables similarity search (e.g. by BCS + MW text) instead of exact relational match.

CREATE TABLE IF NOT EXISTS internal_experiment_embeddings (
    id SERIAL PRIMARY KEY,
    internal_experiment_result_id INTEGER NOT NULL REFERENCES internal_experiment_results(id) ON DELETE CASCADE,
    text_content TEXT NOT NULL,
    embedding vector(768),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_internal_experiment_embeddings_vector
ON internal_experiment_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_internal_experiment_embeddings_fk
ON internal_experiment_embeddings (internal_experiment_result_id);

COMMENT ON TABLE internal_experiment_embeddings IS 'Vector embeddings for internal experiment results; used for similarity-based retrieval (populate via separate pipeline).';

