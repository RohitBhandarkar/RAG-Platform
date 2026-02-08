-- Migration: add formulation_uid for deterministic ID handoff (no DB lookup during embedding ingest)
-- Run this on existing databases created before formulation_uid was added to init_db.sql

-- formulations: add formulation_uid
ALTER TABLE formulations ADD COLUMN IF NOT EXISTS formulation_uid VARCHAR(512);
CREATE UNIQUE INDEX IF NOT EXISTS idx_formulations_formulation_uid ON formulations(formulation_uid) WHERE formulation_uid IS NOT NULL;

-- formulation_summary_embeddings
ALTER TABLE formulation_summary_embeddings ADD COLUMN IF NOT EXISTS formulation_uid VARCHAR(512);
ALTER TABLE formulation_summary_embeddings ALTER COLUMN formulation_id DROP NOT NULL;

-- manufacturing_process_embeddings
ALTER TABLE manufacturing_process_embeddings ADD COLUMN IF NOT EXISTS formulation_uid VARCHAR(512);
ALTER TABLE manufacturing_process_embeddings ALTER COLUMN manufacturing_process_id DROP NOT NULL;

-- particle_analytics_embeddings
ALTER TABLE particle_analytics_embeddings ADD COLUMN IF NOT EXISTS formulation_uid VARCHAR(512);
ALTER TABLE particle_analytics_embeddings ALTER COLUMN formulation_id DROP NOT NULL;

-- in_vitro_embeddings
ALTER TABLE in_vitro_embeddings ADD COLUMN IF NOT EXISTS formulation_uid VARCHAR(512);
ALTER TABLE in_vitro_embeddings ALTER COLUMN dissolution_profile_id DROP NOT NULL;

-- in_vivo_embeddings
ALTER TABLE in_vivo_embeddings ADD COLUMN IF NOT EXISTS formulation_uid VARCHAR(512);
ALTER TABLE in_vivo_embeddings ALTER COLUMN pk_study_id DROP NOT NULL;
