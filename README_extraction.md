## Plan: Multi-Strategy PDF Extraction for Formulation Data

Use a shared, explicit “formulation case study” schema (including nanocrystal/nanosuspension fields) and evaluate multiple extraction branches: (A) section-aware text + tables with LLMs, (B) multimodal image+OCR+vision LLMs, (C) rule/ML hybrid with light LLM validation, and optionally (D) end-to-end multimodal “form filling”. Compare them on field-level accuracy, coverage, robustness to layout/modalities, cost, and stability using a manually annotated gold-standard dataset. The winning approach (or ensemble) will drive how data moves into Postgres and the vector DB.

### Steps

1. Define a canonical formulation case-study schema  
   - Design a JSON-like schema with categories:  
     - API properties: molecular weight, melting point, pKa, logP, aqueous solubility, BCS class.  
     - Formulation platform/subtype: SEDDS/SMEDDS, ASD, nanosuspension/nanocrystal; allow subtype labels.  
     - Formulation composition: drug name, drug load, excipient names, roles (stabilizer, surfactant, co-solvent, polymer), concentrations/ratios, units.  
     - Process parameters: process type (e.g., bead milling, high-pressure homogenization), key conditions (time, speed, pressure, temperature, solvent system, cycles), equipment.  
     - Characterization metrics: particle size (nm), PDI, zeta potential, crystallinity, saturation solubility, etc.  
     - Performance outcomes: dissolution behavior, bioavailability metrics (e.g., AUC, Cmax), in vitro/in vivo outcomes, success/failure.  
     - Stability and risk: stability endpoints (timepoints, conditions, results), failure modes (aggregation, crystal growth, phase separation), mitigation strategies.  
     - Source metadata: paper title, authors, journal, year, DOI, data source (PubMed/FDA/patent), pages/tables/figures referenced.  
   - Map these schema fields to your existing concepts:  
     - Reuse and extend API property fields from backend/app/schemas/api_properties.py and how they are used in backend/app/schemas/formulation.py and backend/app/schemas/response.py.  
     - Plan how this schema will later be reflected in ORM models in backend/app/models/formulation.py and backend/app/models/document.py, including per-paper vs per-case granularity (multiple formulations per paper).  
   - Decide per-field representation:  
     - Scalar numeric (floats/ints with explicit units), categorical enums (platform, process type, excipient role), free-text notes (rationales, risk descriptions), and lists (multiple formulations, multiple stability timepoints).  
     - Model “unknown/not reported” explicitly (e.g., null plus an optional “not_reported” flag) to distinguish missing vs absent.

2. Branch A – Section-aware chunking + LLM extraction over text and tables  
   - Parsing strategy:  
     - Implement or configure a robust PDF text parser (e.g., pymupdf/fitz or pdfplumber) in a future version of backend/app/data/parsers/pdf_parser.py to extract:  
       - Continuous text with page numbers.  
       - Heading hierarchy and section labels (Introduction, Materials and Methods, Experimental, Formulation, Results, Discussion, Conclusion, Supplementary).  
       - Basic table content as structured cells where possible (rows, columns, header rows).  
   - Chunking design in document_processor:  
     - In backend/app/data/ingestion/document_processor.py, define chunk objects with a consistent internal schema, for example:  
       - Text chunks: {chunk_id, doc_id, section_name, heading_path, page_start, page_end, text}.  
       - Table chunks: {chunk_id, doc_id, section_name, page, caption, headers, rows}.  
     - Use section-based chunking (split at headings) with additional length constraints to respect LLM token limits while preserving local context.  
   - LLM extraction workflow:  
     - Choose a strong text LLM (e.g., Gemini 1.5 Pro via Vertex AI as primary; OpenAI GPT-4.1 / GPT‑4o or Anthropic Claude 3.5 as backups).  
     - For each paper:  
       - Build prompts that include:  
         - A clear definition of your canonical schema and examples of how to fill it.  
         - Section-specific content:  
           - “Materials and Methods” / “Experimental” / “Formulation” sections for composition and process.  
           - “Results” / “Discussion” for characterization metrics, performance, and stability.  
         - Serialized tables (e.g., markdown or CSV-style) embedded into the prompt when they clearly contain numeric data for formulations.  
       - Ask for a single, strictly valid JSON output per paper listing 1..N formulations, with:  
         - Fields populated per your schema; null or empty arrays where data is absent.  
         - Optional per-field confidence scores (0–1) if the model can reasonably self-assess.  
     - Handle multi-formulation papers by allowing the model to output an array of case objects and to annotate which sections/tables each case comes from.  
   - Graphs/figures handling in Branch A:  
     - Rely only on surrounding text and figure captions (no direct image analysis) to extract numeric and qualitative results mentioned in text (e.g., “particle size decreased from 500 nm to 180 nm”, “Figure 2 shows sustained dissolution over 24 h”).  
     - Encourage the model, via instructions, to use such textual descriptions to populate characterization and performance fields.  
   - Outputs:  
     - For each paper, produce an intermediate JSON artifact that conforms to your schema and includes a “provenance” block (e.g., list of section names and table captions used).  
     - Design this JSON so it can later be persisted into Postgres and indexed in the vector DB (e.g., store text snippets and table text as candidate chunks with metadata).

3. Branch B – Multimodal image + text OCR pipeline for text, tables, graphs, and chemical diagrams  
   - High-resolution page rendering:  
     - Render each PDF page to images at high DPI (e.g., 300–400 dpi) using a library such as pymupdf or pdf2image in backend/app/data/parsers/pdf_parser.py.  
     - Maintain mapping from page images back to original page indices.  
   - OCR for text and tables:  
     - Use a strong OCR system (e.g., Google Cloud Vision API or Azure Read; Tesseract as a local fallback) to detect:  
       - Text blocks with bounding boxes and reading order.  
       - Detected tables with cell coordinates and structure (some cloud OCRs output this directly).  
     - Where OCR outputs raw text without table structure, post-process using tools like camelot or tabula-py on the underlying PDF to recover table layouts, then align with OCR positions if needed.  
   - Graphs and chart digitization:  
     - Detect figure regions (charts/graphs) and crop them from the page images.  
     - Use a vision+LLM model (e.g., Gemini 1.5 Pro Vision) or a dedicated chart-to-data tool to infer:  
       - Axis labels and units (e.g., time [h], % drug released, particle size [nm]).  
       - Legend entries mapping series names to experimental conditions or formulations.  
       - Approximate x–y data points for critical curves (e.g., dissolution profiles, particle size vs. time).  
   - Chemical structures and compounds:  
     - When chemical structures appear as images, use chemistry OCR (e.g., OSRA-style tools or vision+LLM) to infer SMILES or at least identify the compound name from nearby text.  
     - Link the detected structures/names back into your schema fields for API or excipients where appropriate.  
   - Fusion and normalization:  
     - Merge OCR text, structured tables, and chart-derived numeric series into a unified document representation:  
       - Each element (paragraph, table, figure) should have page index, bounding boxes, and a unique ID.  
     - Normalize numeric strings into typed values with consistent units (e.g., convert “0.2 µm” to 200 nm, unify °C, mg/mL); store both raw and normalized values to aid debugging.  
   - LLM/vision-based schema filling:  
     - Use a multimodal LLM (e.g., Gemini 1.5 Pro Vision) for targeted prompts:  
       - For each candidate table or figure relevant to formulations, send the structured representation and/or the cropped image plus nearby text.  
       - Ask the model to extract and map values into your canonical schema, including an `evidence_sources` field listing {page, element_type (table/figure/text), element_id}.  
     - Combine multiple multimodal calls per paper into a single consolidated JSON summary (merging across tables/figures and cross-checking with body text).  
   - Outputs:  
     - JSON with broader coverage, including data that exists only in scanned tables or graphs: particle size distributions, dissolution curves, long-term stability plots.  
     - Retain intermediate OCR and chart-digitization artifacts to support debugging and potential retraining.

4. Branch C and optional Branch D – Schema-aware IE (rules+ML) and end-to-end multimodal “form filling”  
   - Branch C: Weakly supervised rule/ML hybrid over text and tables  
     - Rule/regex extraction:  
       - Implement patterns to capture API properties, formulations, and characterization metrics from text (e.g., “molecular weight of X g/mol”, “LogP = 2.3”, “particle size of 180 ± 20 nm”, “PDI 0.15”).  
       - Recognize platforms and processes via keyword/phrase and pattern matching (“nanocrystal”, “nanosuspension”, “wet milling”, “high-pressure homogenization”, “top-down”, “bottom-up”).  
     - Table-first extraction:  
       - For structured tables, build a header-normalization and ontology mapping layer:  
         - Map column labels like “PS (nm)”, “Z-average (nm)” to particle_size_nm; “PDI”, “polydispersity index” to pdi; etc.  
         - Recognize rows representing different formulations and produce separate case entries per row where appropriate.  
     - Lightweight ML models:  
       - Optionally use small classifiers to disambiguate roles (e.g., excipient type or formulation platform) and to help choose between conflicting numeric candidates.  
     - LLM for validation and augmentation:  
       - Call a cheaper text LLM only to:  
         - Resolve conflicts among rule/ML candidates.  
         - Fill in qualitative fields (risk description, stability narrative) based on local context.  
         - Map free-text method descriptions to a limited set of process enums.  
       - Keep these calls narrow in scope to reduce cost and variance.  
     - Outputs:  
       - JSON where many numeric and categorical fields come from deterministic or weakly supervised extraction, with LLM only as a refinement layer.  
   - Branch D (optional): Few-shot multimodal “form extraction”  
     - Training examples:  
       - Manually annotate several nanocrystal/nanosuspension papers (including the Phase 1 Nanocrystal Formulation Case Study) as paired examples of:  
         - Raw document snippets (text segments, key tables, figure images/descriptions).  
         - Fully filled JSON objects following your canonical schema.  
     - Prompt design:  
       - Present the schema as a structured “form” plus 3–5 detailed examples to a powerful multimodal LLM.  
       - For a new paper, provide either the full text/images in batched chunks or a curated subset (abstract, methods, key tables, key figures) and ask the model to output the complete JSON.  
       - Strictly require JSON validity, explicit nulls, and rich `evidence_sources`.  
     - Purpose:  
       - Use this branch as an approximate upper bound on achievable quality, even if cost and latency are higher, to benchmark simpler methods (A–C).

5. Shared evaluation dataset and annotation protocol  
   - Gold-standard dataset:  
     - Select 10–30 representative papers for initial evaluation, with diversity in:  
       - Layout (native digital PDFs vs scanned, simple vs complex layouts).  
       - Data presentation styles (text-heavy vs table-heavy vs graph-heavy).  
       - Various nanocrystal/nanosuspension systems and APIs.  
     - For each paper, manually annotate the canonical case-study JSON:  
       - Capture 1..N formulations, filling all fields that are explicitly reportable.  
       - Mark fields as “not reported” or “not applicable” when appropriate, not just leaving them blank.  
   - Annotation workflow:  
     - Implement a simple tool (e.g., a small web UI or notebook-based form) that displays the PDF and allows structured input of schema fields.  
     - Store annotations as version-controlled JSON files in a dedicated path such as data/labelled/phase1_nanocrystal/.  
     - Have at least one formulation expert review a subset for quality and consistency to serve as “gold of golds”.

6. Metrics and decision criteria for comparing branches  
   - Field-level accuracy on structured fields  
     - For each numeric or categorical field (e.g., particle_size_nm, pdi, zeta_potential_mV, platform_type, process_method):  
       - Compute precision, recall, and F1 across the evaluation set.  
       - Treat a prediction as correct if:  
         - Numeric: within a predefined tolerance (e.g., ±5–10% of gold or within a small absolute error).  
         - Categorical: exact match or mapped-equivalent under your ontology (e.g., “wet media milling” vs “bead milling”).  
       - Report both macro-averaged F1 across fields and micro-averaged F1 across all scalar fields.  
   - Record-level completeness and correctness  
     - For each formulation record:  
       - Coverage = (# correctly extracted non-null fields) / (# non-null fields in ground truth).  
       - Overfill (hallucination) rate = (# fields predicted as non-null when gold is null) / (total fields where gold is null).  
       - “Critical fields all correct” rate = proportion of records where all key fields (API properties, platform, major process attributes, main performance metric) are correct.  
   - Evidence and provenance alignment  
     - When branches output `evidence_sources` (page/table/figure references):  
       - Evidence precision = fraction of extracted fields whose evidence overlaps with the gold-standard evidence (same page and, where applicable, same table/figure).  
       - Optionally track how often the system cites sources that do not actually contain the claimed value.  
   - Robustness to layout and modality  
     - Stratify metrics by document type:  
       - Native digital PDFs, scanned/image-heavy PDFs, table-dense PDFs, graph-dense PDFs.  
     - Compare branches per subset (e.g., Branch A might excel on digital text; Branch B on scanned documents and graph-based metrics).  
   - Cost and latency  
     - Track per-paper metrics:  
       - LLM tokens (prompt + completion) and number of LLM calls per branch.  
       - OCR and parsing compute time (CPU/GPU) and any external API costs.  
       - End-to-end wall-clock time from PDF to JSON.  
     - Summarize as cost-per-paper and time-per-paper, and relate these to accuracy to build a Pareto view.  
   - Stability and determinism  
     - For LLM-heavy branches, run on the same subset multiple times (e.g., three runs) and compute:  
       - Variance in field-level F1 and coverage metrics.  
       - Proportion of fields that change between runs (lower is better for repeatability).  
   - Decision and integration criteria  
     - Define in advance how you will choose the final approach:  
       - Prefer the branch or ensemble that meets a target threshold on critical-field F1 and coverage while staying under defined cost and latency budgets.  
       - Consider a hybrid:  
         - Use Branch C (rules/ML) as a base for structured, high-confidence fields.  
         - Use Branch A for text-derived fields missing from rules.  
         - Use Branch B only when information is clearly present only in figures or scanned tables.  
     - Plan how the chosen pipeline’s JSON output will feed into:  
       - Postgres schema for formulations and documents once models in backend/app/models/formulation.py and backend/app/models/document.py are implemented.  
       - Vector DB chunks and metadata (e.g., indexing text snippets, table text, and linking them with API properties, formulation platform, and key outcomes for property-based retrieval).

### Further Considerations

1. Before implementation, finalize the nanocrystal/nanosuspension-specific fields (particle size, PDI, zeta potential, key process attributes) and their units in your canonical schema so all branches target the same structure.  
2. Choose primary LLM/vision providers based on your intended production stack (e.g., Vertex AI first, with OpenAI/Anthropic as experimental baselines) and align early with your budget and latency constraints.  
3. Plan how annotation and evaluation will be maintained over time (e.g., periodically adding new labelled papers) to keep your extraction system improving and to validate changes against regressions.