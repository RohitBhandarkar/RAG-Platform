
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import google.generativeai as genai

from app.config import settings


# Project root (RAG-Platform), used to locate shared resources such as
# data/canonical.json. ``__file__`` is backend/app/services/llm_service.py,
# so ``parents[3]`` points to the repository root.
ROOT_DIR = Path(__file__).resolve().parents[3]
CANONICAL_PATH = ROOT_DIR / "data" / "canonical.json"


class LLMService:
	"""Service that drives the LLM-based extraction.

	For each parsed paper it:

	1. Loads the canonical schema.
	2. Builds a prompt containing:
	   - A clear definition of the canonical schema.
	   - Section-specific content for materials/methods/experimental/
		 formulation and results/discussion.
	   - Serialized tables when available.
	   - Instructions for handling graphs and figure descriptions via
		 surrounding text only (no image analysis).
	3. Calls the configured LLM provider to obtain a single, strictly
	   valid JSON output per paper, representing 1..N formulations.
	"""

	def __init__(self, provider: str = "gemini", model: str = None) -> None:
		self.provider = provider
		# Allow overriding the model, otherwise fall back to settings.GEMINI_MODEL.
		self.model = model or settings.GEMINI_MODEL
		self._canonical_schema = self._load_canonical_schema()
		self._canonical_schema_str = json.dumps(self._canonical_schema, indent=2)

		# Configure Gemini from environment
		if self.provider == "gemini":
			api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
			if api_key:
				genai.configure(api_key=api_key)

	def _load_canonical_schema(self) -> Dict[str, Any]:
		with CANONICAL_PATH.open("r", encoding="utf-8") as f:
			return json.load(f)

	def generate_canonical(
		self,
		*,
		parsed_document: Dict[str, Any],
		text_chunks: List[Dict[str, Any]],
		table_chunks: List[Dict[str, Any]],
		extra_metadata: Dict[str, Any],
		source: str,
		doc_id: str,
	) -> Dict[str, Any]:
		"""Generate canonical JSON for a single paper.

		This method is synchronous by design; callers may wrap it in an
		async context if needed.
		"""

		prompt = self._build_prompt(
			parsed_document=parsed_document,
			text_chunks=text_chunks,
			table_chunks=table_chunks,
			extra_metadata=extra_metadata,
			source=source,
			doc_id=doc_id,
		)

		if self.provider == "gemini":
			raw = self._call_gemini(prompt)
		else:
			raise NotImplementedError(f"LLM provider '{self.provider}' is not implemented")

		return self._parse_llm_json(raw)

	def _build_prompt(
		self,
		*,
		parsed_document: Dict[str, Any],
		text_chunks: List[Dict[str, Any]],
		table_chunks: List[Dict[str, Any]],
		extra_metadata: Dict[str, Any],
		source: str,
		doc_id: str,
	) -> str:
		"""Construct a detailed extraction prompt for the LLM."""

		# Group sections by name for easier consumption in the prompt.
		sections = parsed_document.get("sections", [])
		section_text_by_name: Dict[str, List[str]] = {}
		for sec in sections:
			name = (sec.get("section_name") or "").lower()
			section_text_by_name.setdefault(name, []).append(sec.get("text", ""))

		def _join(name_keys: List[str]) -> str:
			buf: List[str] = []
			for key in name_keys:
				for k, v in section_text_by_name.items():
					if key in k:
						buf.extend(v)
			return "\n\n".join(buf).strip()

		materials_and_methods = _join(["materials_and_methods", "materials", "methods", "experimental", "formulation"])
		results_and_discussion = _join(["results", "discussion", "conclusion"])

		# Serialize tables as simple markdown for numeric extraction.
		table_md_blocks: List[str] = []
		for t in table_chunks:
			caption = t.get("caption", "")
			headers = t.get("headers", [])
			rows = t.get("rows", [])
			lines: List[str] = []
			if caption:
				lines.append(f"Table: {caption}")
			if headers:
				lines.append("| " + " | ".join(headers) + " |")
				lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
			for row in rows:
				lines.append("| " + " | ".join(row) + " |")
			table_md_blocks.append("\n".join(lines))

		tables_md = "\n\n".join(table_md_blocks)

		doc_meta = parsed_document.get("metadata", {})

		instructions = f"""You are an expert formulation scientist and information extraction model.
Your task is to read the provided research article sections and tables and
populate the following canonical JSON schema for 1..N nanocrystal or
related formulations discussed in the paper.

SCHEMA (example structure; follow these keys and nesting exactly):
{self._canonical_schema_str}

RULES:
- Output a SINGLE JSON object only, with the exact schema above.
- Include an array of formulations if multiple formulations are
  described in the paper.
- For fields that are not reported or not applicable, use null, empty
  strings, or empty arrays as appropriate, but DO NOT invent values.
- Use numeric values where possible; preserve units and semantics in
  the appropriate fields according to the schema.
- Use only the provided text, captions, and tables. Do not hallucinate
  values not supported by the document.
- For graphs and figures, rely ONLY on their textual descriptions and
  captions (e.g., "particle size decreased from 500 nm to 180 nm",
  "Figure 2 shows sustained dissolution over 24 h") to infer numeric or
  qualitative trends. You MUST NOT assume or guess values from images
  that are not described in text.

DOCUMENT CONTEXT:
- Source: {source}
- Doc ID: {doc_id}
- Parsed PDF metadata: {json.dumps(doc_meta, ensure_ascii=False)}
- Extra ingestion metadata: {json.dumps(extra_metadata, ensure_ascii=False)}

RELEVANT SECTIONS:

<MATERIALS_METHODS_EXPERIMENTAL_FORMULATION>
{materials_and_methods}
</MATERIALS_METHODS_EXPERIMENTAL_FORMULATION>

<RESULTS_DISCUSSION_STABILITY_PERFORMANCE>
{results_and_discussion}
</RESULTS_DISCUSSION_STABILITY_PERFORMANCE>

TABLES (in markdown form):
{tables_md}

Now return ONLY the filled JSON object, with no explanation or prose.
"""

		return instructions

	def _call_gemini(self, prompt: str) -> str:
		"""Call Gemini via google-generativeai and return raw text.

		This uses a Gemini text model (``gemini-1.5-pro`` by default). The
		API key must be provided in the ``GEMINI_API_KEY`` environment
		variable.
		"""

		# ``genai.configure`` is done once in ``__init__`` when the key is
		# available; if no key is configured we raise a clear error.
		if not (settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")):
			raise RuntimeError("GEMINI_API_KEY is not configured for Gemini provider")

		model = genai.GenerativeModel(self.model)
		response = model.generate_content(
			[
				"You are a precise JSON information extraction engine.",
				prompt,
			]
		)
		# ``response.text`` is a convenience property with concatenated text.
		return response.text or ""

	def _parse_llm_json(self, raw: str) -> Dict[str, Any]:
		"""Parse JSON from LLM output, handling optional code fences."""

		text = raw.strip()
		if text.startswith("```"):
			# Strip markdown code fences
			lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
			text = "\n".join(lines).strip()

		try:
			return json.loads(text)
		except json.JSONDecodeError as exc:  # pragma: no cover - defensive
			raise ValueError(f"LLM returned invalid JSON: {exc}") from exc


__all__ = ["LLMService"]

