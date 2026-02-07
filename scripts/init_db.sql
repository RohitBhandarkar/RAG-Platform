-- ============================================================================
-- RAG Platform Database Initialization
-- PostgreSQL + pgvector schema for pharmaceutical formulation data
-- ============================================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- CORE ENTITY TABLES
-- ============================================================================

-- 1. source_documents: Raw document metadata
CREATE TABLE IF NOT EXISTS source_documents (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL,          -- 'pubmed', 'patent', 'fda', 'user_upload'
    source_id VARCHAR(255) NOT NULL,           -- PMID, patent number, NDA, filename
    title TEXT,
    file_path TEXT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,                            -- Flexible metadata storage
    UNIQUE(source_type, source_id)
);

-- 2. formulations: Core formulation entity
CREATE TABLE IF NOT EXISTS formulations (
    id SERIAL PRIMARY KEY,
    source_document_id INTEGER REFERENCES source_documents(id) ON DELETE CASCADE,
    formulation_uid VARCHAR(512) UNIQUE,       -- Deterministic: document_base_id#index (no DB lookup for embeddings)
    api_id INTEGER,                            -- Direct FK to apis for fast queries (set after api created)
    formulation_name VARCHAR(255),
    drug_name VARCHAR(255),
    dosage_form VARCHAR(100),                  -- 'tablet', 'capsule', 'suspension', etc.
    formulation_type VARCHAR(100),             -- 'nanosuspension', 'spray-dried', 'wet granulation', etc.
    bcs_class VARCHAR(10),                     -- Denormalized from apis for fast filtering
    route_of_administration VARCHAR(100),
    therapeutic_area VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- 3. excipients: Master list of excipients
CREATE TABLE IF NOT EXISTS excipients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    cas_number VARCHAR(50),
    functional_category VARCHAR(100),          -- 'binder', 'disintegrant', 'lubricant', etc.
    description TEXT,
    metadata JSONB
);

-- 4. apis: Active Pharmaceutical Ingredients
CREATE TABLE IF NOT EXISTS apis (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    cas_number VARCHAR(50),
    molecular_weight DECIMAL(12, 4),
    smiles TEXT,
    bcs_class VARCHAR(10),                     -- 'I', 'II', 'III', 'IV'
    solubility_classification VARCHAR(50),
    permeability_classification VARCHAR(50),
    metadata JSONB,
    UNIQUE(name, cas_number)
);

-- ============================================================================
-- COMPOSITION TABLES (Many-to-Many Relationships)
-- ============================================================================

-- 5. formulation_excipients: Junction table for formulation-excipient relationships
CREATE TABLE IF NOT EXISTS formulation_excipients (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    excipient_id INTEGER REFERENCES excipients(id) ON DELETE CASCADE,
    amount DECIMAL(12, 4),
    unit VARCHAR(50),                          -- 'mg', '%w/w', 'mg/mL', etc.
    role VARCHAR(100),                         -- Specific role in this formulation
    is_critical BOOLEAN DEFAULT FALSE,
    metadata JSONB,
    UNIQUE(formulation_id, excipient_id)
);

-- 6. formulation_apis: Junction table for formulation-API relationships
CREATE TABLE IF NOT EXISTS formulation_apis (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    api_id INTEGER REFERENCES apis(id) ON DELETE CASCADE,
    amount DECIMAL(12, 4),
    unit VARCHAR(50),
    salt_form VARCHAR(100),                    -- 'HCl', 'sodium', 'free base', etc.
    metadata JSONB,
    UNIQUE(formulation_id, api_id)
);

-- ============================================================================
-- MANUFACTURING & PROCESS TABLES
-- ============================================================================

-- 7. manufacturing_processes: Manufacturing process details
CREATE TABLE IF NOT EXISTS manufacturing_processes (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    process_type VARCHAR(100),                 -- 'wet_granulation', 'direct_compression', etc.
    process_description TEXT,
    batch_size VARCHAR(100),
    scale VARCHAR(50),                         -- 'lab', 'pilot', 'commercial'
    equipment_used TEXT[],
    metadata JSONB
);

-- 8. process_parameters: Critical process parameters (CPP)
CREATE TABLE IF NOT EXISTS process_parameters (
    id SERIAL PRIMARY KEY,
    manufacturing_process_id INTEGER REFERENCES manufacturing_processes(id) ON DELETE CASCADE,
    parameter_name VARCHAR(255) NOT NULL,
    target_value VARCHAR(100),
    lower_limit VARCHAR(100),
    upper_limit VARCHAR(100),
    unit VARCHAR(50),
    is_critical BOOLEAN DEFAULT TRUE,
    impact_description TEXT,
    metadata JSONB
);

-- ============================================================================
-- ANALYTICAL & QUALITY TABLES
-- ============================================================================

-- 9. particle_characteristics: Particle size and distribution data
CREATE TABLE IF NOT EXISTS particle_characteristics (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    measurement_type VARCHAR(100),             -- 'laser_diffraction', 'sieve_analysis', etc.
    d10 DECIMAL(12, 4),
    d50 DECIMAL(12, 4),
    d90 DECIMAL(12, 4),
    span DECIMAL(12, 4),
    specific_surface_area DECIMAL(12, 4),
    unit VARCHAR(50) DEFAULT 'μm',
    metadata JSONB
);

-- 10. analytical_methods: Analytical testing methods
CREATE TABLE IF NOT EXISTS analytical_methods (
    id SERIAL PRIMARY KEY,
    method_name VARCHAR(255) NOT NULL,
    method_type VARCHAR(100),                  -- 'HPLC', 'dissolution', 'content_uniformity', etc.
    description TEXT,
    parameters JSONB,                          -- Column, mobile phase, detection, etc.
    validation_status VARCHAR(50),
    metadata JSONB
);

-- 11. analytical_results: Test results linked to formulations
CREATE TABLE IF NOT EXISTS analytical_results (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    analytical_method_id INTEGER REFERENCES analytical_methods(id) ON DELETE SET NULL,
    test_name VARCHAR(255),
    result_value VARCHAR(100),
    unit VARCHAR(50),
    specification_min VARCHAR(100),
    specification_max VARCHAR(100),
    pass_fail VARCHAR(10),
    test_date DATE,
    metadata JSONB
);

-- ============================================================================
-- IN VITRO PERFORMANCE TABLES
-- ============================================================================

-- 12. dissolution_profiles: Dissolution testing data
CREATE TABLE IF NOT EXISTS dissolution_profiles (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    dissolution_method VARCHAR(255),           -- 'USP Apparatus 2 (Paddle)', etc.
    medium VARCHAR(255),                       -- '0.1N HCl', 'pH 6.8 phosphate buffer', etc.
    volume_ml INTEGER,
    rpm INTEGER,
    temperature DECIMAL(5, 2),
    sink_conditions BOOLEAN,
    metadata JSONB
);

-- 13. dissolution_timepoints: Individual timepoint data
CREATE TABLE IF NOT EXISTS dissolution_timepoints (
    id SERIAL PRIMARY KEY,
    dissolution_profile_id INTEGER REFERENCES dissolution_profiles(id) ON DELETE CASCADE,
    timepoint_minutes INTEGER NOT NULL,
    percent_dissolved DECIMAL(6, 2),
    std_deviation DECIMAL(6, 2),
    n_replicates INTEGER,
    metadata JSONB
);

-- ============================================================================
-- IN VIVO PERFORMANCE TABLES
-- ============================================================================

-- 14. pk_studies: Pharmacokinetic study metadata
CREATE TABLE IF NOT EXISTS pk_studies (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    study_type VARCHAR(100),                   -- 'single_dose', 'multiple_dose', 'BE', etc.
    species VARCHAR(100),                      -- 'human', 'rat', 'dog', 'monkey'
    n_subjects INTEGER,
    study_design VARCHAR(255),                 -- 'crossover', 'parallel', etc.
    fasted_fed VARCHAR(50),                    -- 'fasted', 'fed', 'both'
    reference_product VARCHAR(255),
    metadata JSONB
);

-- 15. pk_parameters: PK parameter results
CREATE TABLE IF NOT EXISTS pk_parameters (
    id SERIAL PRIMARY KEY,
    pk_study_id INTEGER REFERENCES pk_studies(id) ON DELETE CASCADE,
    parameter_name VARCHAR(50) NOT NULL,       -- 'Cmax', 'Tmax', 'AUC0-t', 'AUC0-inf', 't1/2', etc.
    geometric_mean DECIMAL(15, 4),
    arithmetic_mean DECIMAL(15, 4),
    cv_percent DECIMAL(8, 2),
    unit VARCHAR(50),
    metadata JSONB
);

-- 16. bioequivalence_results: BE study results
CREATE TABLE IF NOT EXISTS bioequivalence_results (
    id SERIAL PRIMARY KEY,
    pk_study_id INTEGER REFERENCES pk_studies(id) ON DELETE CASCADE,
    parameter_name VARCHAR(50) NOT NULL,       -- 'Cmax', 'AUC0-t', 'AUC0-inf'
    test_ref_ratio DECIMAL(8, 4),
    ci_lower_90 DECIMAL(8, 4),
    ci_upper_90 DECIMAL(8, 4),
    meets_be_criteria BOOLEAN,
    metadata JSONB
);

-- ============================================================================
-- STABILITY TABLES
-- ============================================================================

-- 17. stability_studies: Stability study metadata
CREATE TABLE IF NOT EXISTS stability_studies (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER REFERENCES formulations(id) ON DELETE CASCADE,
    study_type VARCHAR(100),                   -- 'accelerated', 'long_term', 'intermediate', 'stress'
    storage_condition VARCHAR(100),            -- '25°C/60%RH', '40°C/75%RH', etc.
    container_closure VARCHAR(255),
    packaging_description TEXT,
    start_date DATE,
    metadata JSONB
);

-- 18. stability_results: Stability testing results
CREATE TABLE IF NOT EXISTS stability_results (
    id SERIAL PRIMARY KEY,
    stability_study_id INTEGER REFERENCES stability_studies(id) ON DELETE CASCADE,
    timepoint_months INTEGER NOT NULL,
    test_name VARCHAR(255),
    result_value VARCHAR(100),
    unit VARCHAR(50),
    specification_min VARCHAR(100),
    specification_max VARCHAR(100),
    pass_fail VARCHAR(10),
    metadata JSONB
);

-- ============================================================================
-- VECTOR EMBEDDING TABLES (Replacing ChromaDB Collections)
-- ============================================================================

-- 19. formulation_summary_embeddings: High-level formulation context
-- formulation_uid: deterministic link from embedding to formulation (no DB lookup on ingest)
CREATE TABLE IF NOT EXISTS formulation_summary_embeddings (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER NULL REFERENCES formulations(id) ON DELETE CASCADE,
    formulation_uid VARCHAR(512),             -- Deterministic: same as formulations.formulation_uid
    text_content TEXT NOT NULL,                -- Constructed text for embedding
    embedding vector(768),                     -- Vertex AI text-embedding-004
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 20. manufacturing_process_embeddings: Manufacturing process descriptions
CREATE TABLE IF NOT EXISTS manufacturing_process_embeddings (
    id SERIAL PRIMARY KEY,
    manufacturing_process_id INTEGER NULL REFERENCES manufacturing_processes(id) ON DELETE CASCADE,
    formulation_uid VARCHAR(512),             -- Link to formulation for RAG (deterministic)
    text_content TEXT NOT NULL,
    embedding vector(768),                     -- Vertex AI text-embedding-004
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 21. particle_analytics_embeddings: Particle characteristics and analytical results
CREATE TABLE IF NOT EXISTS particle_analytics_embeddings (
    id SERIAL PRIMARY KEY,
    formulation_id INTEGER NULL REFERENCES formulations(id) ON DELETE CASCADE,
    formulation_uid VARCHAR(512),             -- Deterministic: same as formulations.formulation_uid
    text_content TEXT NOT NULL,
    embedding vector(768),                     -- Vertex AI text-embedding-004
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 22. in_vitro_embeddings: Dissolution profiles and in vitro performance
CREATE TABLE IF NOT EXISTS in_vitro_embeddings (
    id SERIAL PRIMARY KEY,
    dissolution_profile_id INTEGER NULL REFERENCES dissolution_profiles(id) ON DELETE CASCADE,
    formulation_uid VARCHAR(512),             -- Link to formulation for RAG (deterministic)
    text_content TEXT NOT NULL,
    embedding vector(768),                     -- Vertex AI text-embedding-004
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 23. in_vivo_embeddings: PK studies and bioequivalence results
CREATE TABLE IF NOT EXISTS in_vivo_embeddings (
    id SERIAL PRIMARY KEY,
    pk_study_id INTEGER NULL REFERENCES pk_studies(id) ON DELETE CASCADE,
    formulation_uid VARCHAR(512),             -- Link to formulation for RAG (deterministic)
    text_content TEXT NOT NULL,
    embedding vector(768),                     -- Vertex AI text-embedding-004
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 24. [REMOVED] document_chunk_embeddings - using structured extraction instead

-- Create indexes for vector similarity search (HNSW for better performance)
CREATE INDEX IF NOT EXISTS idx_formulation_summary_emb_vector 
ON formulation_summary_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_manufacturing_process_emb_vector 
ON manufacturing_process_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_particle_analytics_emb_vector 
ON particle_analytics_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_in_vitro_emb_vector 
ON in_vitro_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_in_vivo_emb_vector 
ON in_vivo_embeddings USING hnsw (embedding vector_cosine_ops);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Source documents
CREATE INDEX IF NOT EXISTS idx_source_documents_source_type ON source_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_source_documents_source_id ON source_documents(source_id);

-- Formulations
CREATE INDEX IF NOT EXISTS idx_formulations_drug_name ON formulations(drug_name);
CREATE INDEX IF NOT EXISTS idx_formulations_dosage_form ON formulations(dosage_form);
CREATE INDEX IF NOT EXISTS idx_formulations_source_doc ON formulations(source_document_id);
CREATE INDEX IF NOT EXISTS idx_formulations_api ON formulations(api_id);
CREATE INDEX IF NOT EXISTS idx_formulations_bcs ON formulations(bcs_class);
CREATE INDEX IF NOT EXISTS idx_formulations_type ON formulations(formulation_type);

-- APIs
CREATE INDEX IF NOT EXISTS idx_apis_bcs_class ON apis(bcs_class);
CREATE INDEX IF NOT EXISTS idx_apis_name ON apis(name);

-- Manufacturing
CREATE INDEX IF NOT EXISTS idx_manufacturing_formulation ON manufacturing_processes(formulation_id);
CREATE INDEX IF NOT EXISTS idx_process_params_process ON process_parameters(manufacturing_process_id);

-- Dissolution
CREATE INDEX IF NOT EXISTS idx_dissolution_formulation ON dissolution_profiles(formulation_id);
CREATE INDEX IF NOT EXISTS idx_dissolution_tp_profile ON dissolution_timepoints(dissolution_profile_id);

-- PK
CREATE INDEX IF NOT EXISTS idx_pk_studies_formulation ON pk_studies(formulation_id);
CREATE INDEX IF NOT EXISTS idx_pk_params_study ON pk_parameters(pk_study_id);

-- Stability
CREATE INDEX IF NOT EXISTS idx_stability_formulation ON stability_studies(formulation_id);
CREATE INDEX IF NOT EXISTS idx_stability_results_study ON stability_results(stability_study_id);

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE source_documents IS 'Raw document metadata from PubMed, patents, FDA labels, and user uploads';
COMMENT ON TABLE formulations IS 'Core pharmaceutical formulation entities extracted from documents';
COMMENT ON TABLE excipients IS 'Master list of pharmaceutical excipients';
COMMENT ON TABLE apis IS 'Active Pharmaceutical Ingredients with physicochemical properties';
COMMENT ON TABLE formulation_excipients IS 'Junction table linking formulations to their excipients';
COMMENT ON TABLE formulation_apis IS 'Junction table linking formulations to their APIs';
COMMENT ON TABLE manufacturing_processes IS 'Manufacturing process descriptions and parameters';
COMMENT ON TABLE process_parameters IS 'Critical Process Parameters (CPPs) for manufacturing';
COMMENT ON TABLE particle_characteristics IS 'Particle size distribution and surface area data';
COMMENT ON TABLE analytical_methods IS 'Analytical testing methods and their parameters';
COMMENT ON TABLE analytical_results IS 'Test results from analytical methods';
COMMENT ON TABLE dissolution_profiles IS 'In vitro dissolution testing conditions';
COMMENT ON TABLE dissolution_timepoints IS 'Dissolution data at specific timepoints';
COMMENT ON TABLE pk_studies IS 'Pharmacokinetic study metadata';
COMMENT ON TABLE pk_parameters IS 'PK parameter results (Cmax, AUC, etc.)';
COMMENT ON TABLE bioequivalence_results IS 'Bioequivalence study results with confidence intervals';
COMMENT ON TABLE stability_studies IS 'Stability study conditions and metadata';
COMMENT ON TABLE stability_results IS 'Stability testing results over time';
COMMENT ON TABLE formulation_summary_embeddings IS 'Vector embeddings for formulation summaries (replaces ChromaDB formulation_summaries)';
COMMENT ON TABLE manufacturing_process_embeddings IS 'Vector embeddings for manufacturing processes (replaces ChromaDB manufacturing_processes)';
COMMENT ON TABLE particle_analytics_embeddings IS 'Vector embeddings for particle/analytics data (replaces ChromaDB particle_and_analytics)';
COMMENT ON TABLE in_vitro_embeddings IS 'Vector embeddings for dissolution/in vitro data (replaces ChromaDB in_vitro_performance)';
COMMENT ON TABLE in_vivo_embeddings IS 'Vector embeddings for PK/in vivo data (replaces ChromaDB in_vivo_performance)';

-- ============================================================================
-- GRANT PERMISSIONS (for application user)
-- ============================================================================

-- Grant all privileges to postgres user (default for Docker setup)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- ============================================================================
-- VERIFICATION QUERY
-- ============================================================================

-- This will be executed to verify the setup
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_type = 'BASE TABLE';
    
    RAISE NOTICE 'RAG Platform database initialized with % tables', table_count;
END $$;
