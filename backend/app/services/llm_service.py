
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

import requests
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest

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
	3. Calls vLLM's OpenAI-compatible HTTP endpoint (locally or on GCP)
	   to obtain a single, strictly valid JSON output per paper.
	"""

	def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
		# Allow overriding base URL/model, otherwise fall back to settings.
		self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
		self.model = model or settings.LLM_MODEL
		self._canonical_schema = self._load_canonical_schema()
		self._canonical_schema_str = json.dumps(self._canonical_schema, indent=2)

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

		raw = self._call_http_llm(prompt)
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

	def _call_http_llm(self, prompt: str) -> str:
		"""Call either vLLM's OpenAI-compatible endpoint or Vertex AI Gemini.

		If base_url is 'vertex', uses Vertex AI Gemini API.
		Otherwise, uses vLLM's OpenAI-compatible endpoint.
		"""

		if self.base_url == "vertex":
			return self._call_vertex_gemini(prompt)

		url = f"{self.base_url}/chat/completions"
		payload = {
			"model": self.model,
			"messages": [
				{
					"role": "system",
					"content": (
						"You are a precise JSON information extraction engine. "
						"You ONLY output a single JSON object that conforms to the provided schema."
					),
				},
				{"role": "user", "content": prompt},
			],
			"temperature": 0.0,
			"max_tokens": 4096,
		}

		data = json.dumps(payload).encode("utf-8")
		req = request.Request(url, data=data, headers={"Content-Type": "application/json"})

		try:
			with request.urlopen(req, timeout=300) as resp:  # type: ignore[call-arg]
				body = resp.read().decode("utf-8")
		except error.HTTPError as exc:  # pragma: no cover - defensive
			msg = exc.read().decode("utf-8", "ignore")
			raise RuntimeError(f"LLM HTTP error {exc.code}: {msg}") from exc
		except error.URLError as exc:  # pragma: no cover - defensive
			raise RuntimeError(f"Failed to reach LLM server: {exc.reason}") from exc

		obj = json.loads(body)
		try:
			# OpenAI-compatible format: {"choices": [{"message": {"content": "..."}}]}
			return obj["choices"][0]["message"]["content"]
		except (KeyError, TypeError, IndexError) as exc:  # pragma: no cover - defensive
			raise RuntimeError("Unexpected response format from LLM server") from exc

	def _call_vertex_gemini(self, prompt: str) -> str:
		"""Call Vertex AI Gemini API for text generation."""

		project = settings.GOOGLE_CLOUD_PROJECT
		location = settings.VERTEX_LOCATION or "us-central1"

		if not project:
			raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set to use Vertex AI")

		# Use the model from settings (e.g., gemini-1.5-pro)
		model = self.model or "gemini-1.5-pro"

		# Vertex AI publisher model endpoint
		url = (
			f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
			f"/locations/{location}/publishers/google/models/{model}:generateContent"
		)

		# Get credentials with Application Default Credentials
		credentials, _ = google.auth.default(
			scopes=["https://www.googleapis.com/auth/cloud-platform"]
		)
		credentials.refresh(GoogleAuthRequest())

		payload = {
			"contents": [
				{
					"role": "user",
					"parts": [{"text": prompt}],
				}
			],
			"generationConfig": {
				"temperature": 0.0,
				"maxOutputTokens": 8192,
			},
		}

		resp = requests.post(
			url,
			headers={
				"Authorization": f"Bearer {credentials.token}",
				"Content-Type": "application/json",
			},
			json=payload,
			timeout=300,
		)

		if resp.status_code >= 400:
			raise RuntimeError(f"Vertex AI error {resp.status_code}: {resp.text}")

		obj = resp.json()
		try:
			# Vertex response: candidates[0].content.parts[0].text
			return obj["candidates"][0]["content"]["parts"][0]["text"]
		except (KeyError, TypeError, IndexError) as exc:
			raise RuntimeError("Unexpected response format from Vertex AI") from exc

	def check_health(self) -> Dict[str, Any]:
		"""Lightweight health check against the LLM endpoint.

		For Vertex AI: verifies authentication and project configuration.
		For vLLM: calls GET {base_url}/models to list available models.
		"""

		# Vertex AI health check
		if self.base_url == "vertex":
			try:
				project = settings.GOOGLE_CLOUD_PROJECT
				if not project:
					return {
						"status": "unhealthy",
						"base_url": self.base_url,
						"error": "GOOGLE_CLOUD_PROJECT not configured",
					}

				# Verify credentials can be obtained
				credentials, _ = google.auth.default(
					scopes=["https://www.googleapis.com/auth/cloud-platform"]
				)
				credentials.refresh(GoogleAuthRequest())

				return {
					"status": "healthy",
					"base_url": self.base_url,
					"mode": "vertex",
					"model": self.model,
					"project": project,
					"location": settings.VERTEX_LOCATION,
				}
			except Exception as exc:
				return {
					"status": "unhealthy",
					"base_url": self.base_url,
					"error": str(exc),
				}

		# vLLM health check
		url = f"{self.base_url}/models"
		req = request.Request(url, headers={"Accept": "application/json"})

		try:
			with request.urlopen(req, timeout=5) as resp:  # type: ignore[call-arg]
				body = resp.read().decode("utf-8")
		except error.HTTPError as exc:
			msg = exc.read().decode("utf-8", "ignore")
			return {
				"status": "unhealthy",
				"base_url": self.base_url,
				"error": f"HTTP {exc.code}: {msg}",
			}
		except error.URLError as exc:
			return {
				"status": "unhealthy",
				"base_url": self.base_url,
				"error": str(exc.reason),
			}

		try:
			payload = json.loads(body)
		except json.JSONDecodeError:
			return {
				"status": "unhealthy",
				"base_url": self.base_url,
				"error": "Invalid JSON in /models response",
			}

		# If we successfully parsed JSON, treat as healthy and include payload
		# for debugging/inspection.
		return {
			"status": "healthy",
			"base_url": self.base_url,
			"models_payload": payload,
		}

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

