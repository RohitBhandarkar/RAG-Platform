-- Migration: add report_id to internal_experiment_results and internal_experiment_embeddings.
-- report_id links a RAG report to its stub row and to the embedding created when the lab populates it.

ALTER TABLE internal_experiment_results
ADD COLUMN IF NOT EXISTS report_id VARCHAR(64) UNIQUE;

ALTER TABLE internal_experiment_embeddings
ADD COLUMN IF NOT EXISTS report_id VARCHAR(64);


COMMENT ON COLUMN internal_experiment_results.report_id IS 'ID of the RAG report that prompted this experiment (stub created at report time, populated later by lab).';
COMMENT ON COLUMN internal_experiment_embeddings.report_id IS 'ID of the RAG report; set when lab populates the experiment and we create the embedding.';
