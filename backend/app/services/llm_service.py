
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

import requests
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest

from app.config import settings


# Set up logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
		logger.info(f"Starting canonical generation for doc_id={doc_id}, source={source}")
		logger.debug(f"Document has {len(text_chunks)} text chunks and {len(table_chunks)} table chunks")

		prompt = self._build_prompt(
			parsed_document=parsed_document,
			text_chunks=text_chunks,
			table_chunks=table_chunks,
			extra_metadata=extra_metadata,
			source=source,
			doc_id=doc_id,
		)
		
		logger.info(f"Built prompt for {doc_id} (length: {len(prompt)} chars)")
		logger.debug(f"Prompt preview (first 500 chars): {prompt[:500]}...")

		raw = self._call_http_llm(prompt)
		
		logger.info(f"Received LLM response for {doc_id} (length: {len(raw)} chars)")
		logger.debug(f"Raw LLM response: {raw}")
		
		result = self._parse_llm_json(raw)
		logger.info(f"Successfully parsed canonical JSON for {doc_id}")
		logger.debug(f"Parsed result keys: {list(result.keys())}")
		
		return result

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

OUTPUT FORMAT REQUIREMENTS:
1. Return EXACTLY ONE valid, complete JSON object.
2. The JSON MUST be syntactically valid and fully parseable.
3. All brackets {{ }} and [ ] MUST be properly opened and closed.
4. All strings MUST be properly quoted and terminated.
5. NO trailing commas after the last item in arrays or objects.
6. DO NOT truncate - you MUST complete the entire JSON structure.
7. Begin your response with {{ and end with }}.

CONTENT RULES:
- If multiple formulations exist, include them in the formulations array within the SINGLE JSON object.
- DO NOT output multiple separate JSON objects.
- DO NOT add any text, explanations, or comments before or after the JSON.
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

BREVITY GUIDELINES (to ensure complete output):
- Keep string values concise - summarize key points rather than quoting verbatim.
- Limit free-text fields (notes, observations, descriptions) to 1-2 sentences maximum.
- Focus on extracting key numeric values and structured data.
- Omit redundant or repetitive information across formulations.

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

REMINDER: Output ONLY the complete, valid JSON object. Ensure ALL brackets are properly closed.
"""

		return instructions

	def _call_http_llm(self, prompt: str) -> str:
		"""Call either vLLM's OpenAI-compatible endpoint or Vertex AI Gemini.

		If base_url is 'vertex', uses Vertex AI Gemini API.
		Otherwise, uses vLLM's OpenAI-compatible endpoint.
		"""
		logger.info(f"Calling LLM with base_url={self.base_url}, model={self.model}")

		if self.base_url == "vertex":
			return self._call_vertex_gemini(prompt)

		url = f"{self.base_url}/chat/completions"
		logger.debug(f"Using OpenAI-compatible endpoint: {url}")
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
		
		logger.info("Starting Vertex AI Gemini call")

		project = settings.GOOGLE_CLOUD_PROJECT
		location = settings.VERTEX_LOCATION or "us-central1"

		if not project:
			logger.error("GOOGLE_CLOUD_PROJECT not set for Vertex AI")
			raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set to use Vertex AI")

		# Use the model from settings (e.g., gemini-2.5-pro)
		model = self.model or "gemini-2.5-pro"
		
		logger.info(f"Vertex AI config: project={project}, location={location}, model={model}")

		# Vertex AI publisher model endpoint
		url = (
			f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
			f"/locations/{location}/publishers/google/models/{model}:generateContent"
		)
		
		logger.debug(f"Vertex AI endpoint: {url}")

		# Get credentials with Application Default Credentials
		logger.debug("Obtaining Google Cloud credentials")
		credentials, _ = google.auth.default(
			scopes=["https://www.googleapis.com/auth/cloud-platform"]
		)
		credentials.refresh(GoogleAuthRequest())
		logger.debug("Credentials obtained and refreshed")

		payload = {
			"contents": [
				{
					"role": "user",
					"parts": [{"text": prompt}],
				}
			],
			"generationConfig": {
				"temperature": 0.0,
				"maxOutputTokens": 32768,
				"responseMimeType": "application/json",
			},
		}
		
		logger.debug(f"Request payload config: temperature=0.0, maxOutputTokens=32768, responseMimeType=application/json")
		logger.debug(f"Prompt length: {len(prompt)} chars")

		logger.info("Sending request to Vertex AI")
		resp = requests.post(
			url,
			headers={
				"Authorization": f"Bearer {credentials.token}",
				"Content-Type": "application/json",
			},
			json=payload,
			timeout=300,
		)

		logger.info(f"Received response from Vertex AI: status_code={resp.status_code}")

		if resp.status_code >= 400:
			logger.error(f"Vertex AI error response: {resp.text}")
			raise RuntimeError(f"Vertex AI error {resp.status_code}: {resp.text}")

		obj = resp.json()
		logger.debug(f"Response JSON keys: {list(obj.keys())}")
		
		try:
			# Vertex response: candidates[0].content.parts[0].text
			text_response = obj["candidates"][0]["content"]["parts"][0]["text"]
			logger.info(f"Successfully extracted text response (length: {len(text_response)} chars)")
			logger.debug(f"Response preview (first 500 chars): {text_response[:500]}...")
			return text_response
		except (KeyError, TypeError, IndexError) as exc:
			logger.error(f"Failed to parse Vertex AI response structure: {exc}")
			logger.error(f"Response JSON: {json.dumps(obj, indent=2)[:1000]}...")
			raise RuntimeError("Unexpected response format from Vertex AI") from exc

	def _call_vertex_gemini_text(self, prompt: str) -> str:
		"""Call Vertex AI Gemini for plain text (e.g. markdown). No responseMimeType so output is not forced to JSON."""
		project = settings.GOOGLE_CLOUD_PROJECT
		location = settings.VERTEX_LOCATION or "us-central1"
		if not project:
			raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set to use Vertex AI")
		model = self.model or "gemini-2.0-flash"
		url = (
			f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
			f"/locations/{location}/publishers/google/models/{model}:generateContent"
		)
		credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
		credentials.refresh(GoogleAuthRequest())
		payload = {
			"contents": [{"role": "user", "parts": [{"text": prompt}]}],
			"generationConfig": {
				"temperature": 0.2,
				"maxOutputTokens": 8192,
			},
		}
		resp = requests.post(
			url,
			headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"},
			json=payload,
			timeout=300,
		)
		if resp.status_code >= 400:
			raise RuntimeError(f"Vertex AI error {resp.status_code}: {resp.text}")
		obj = resp.json()
		return obj["candidates"][0]["content"]["parts"][0]["text"]

	def generate_text(self, prompt: str) -> str:
		"""Generate plain text (e.g. markdown) using the configured LLM. For Vertex AI, uses Gemini without JSON mode."""
		if self.base_url == "vertex":
			return self._call_vertex_gemini_text(prompt)
		# Fallback: OpenAI-compatible chat
		url = f"{self.base_url}/chat/completions"
		payload = {
			"model": self.model,
			"messages": [{"role": "user", "content": prompt}],
			"temperature": 0.2,
			"max_tokens": 8192,
		}
		data = json.dumps(payload).encode("utf-8")
		req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
		with request.urlopen(req, timeout=300) as resp:
			body = json.loads(resp.read().decode("utf-8"))
		return body["choices"][0]["message"]["content"]

	def check_health(self) -> Dict[str, Any]:
		"""Lightweight health check against the LLM endpoint.

		For Vertex AI: verifies authentication and project configuration.
		For vLLM: calls GET {base_url}/models to list available models.
		"""

		# Vertex AI health check
		if self.base_url == "vertex":
			try:
				project = settings.GOOGLE_CLOUD_PROJECT
				location = settings.VERTEX_LOCATION or "us-central1"
				
				if not project:
					return {
						"status": "unhealthy",
						"base_url": self.base_url,
						"error": "GOOGLE_CLOUD_PROJECT not configured",
					}

				# Get credentials
				credentials, _ = google.auth.default(
					scopes=["https://www.googleapis.com/auth/cloud-platform"]
				)
				credentials.refresh(GoogleAuthRequest())

				# Actually test the model endpoint with a minimal request
				model = self.model or "gemini-2.5-pro"
				url = (
					f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
					f"/locations/{location}/publishers/google/models/{model}:generateContent"
				)
				
				test_payload = {
					"contents": [{"role": "user", "parts": [{"text": "test"}]}],
					"generationConfig": {"maxOutputTokens": 5},
				}
				
				resp = requests.post(
					url,
					headers={
						"Authorization": f"Bearer {credentials.token}",
						"Content-Type": "application/json",
					},
					json=test_payload,
					timeout=10,
				)
				
				if resp.status_code >= 400:
					error_detail = resp.json().get("error", {})
					return {
						"status": "unhealthy",
						"base_url": self.base_url,
						"mode": "vertex",
						"model": model,
						"project": project,
						"location": location,
						"error": f"Model test failed: {error_detail.get('message', resp.text)}",
					}

				return {
					"status": "healthy",
					"base_url": self.base_url,
					"mode": "vertex",
					"model": model,
					"project": project,
					"location": location,
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
		"""Parse JSON from LLM output, handling optional code fences and common formatting issues."""
		
		logger.info(f"Starting JSON parsing (raw length: {len(raw)} chars)")
		logger.debug(f"Raw response (first 1000 chars): {raw[:1000]}")

		text = raw.strip()
		logger.debug(f"After strip (length: {len(text)} chars)")
		
		# Remove markdown code fences
		if text.startswith("```"):
			logger.debug("Detected markdown code fences, removing...")
			lines = text.splitlines()
			# Remove first line if it's a fence (```json or ```)
			if lines[0].strip().startswith("```"):
				lines = lines[1:]
				logger.debug(f"Removed first fence line: {text.splitlines()[0]}")
			# Remove last line if it's a fence
			if lines and lines[-1].strip() == "```":
				lines = lines[:-1]
				logger.debug("Removed last fence line")
			text = "\n".join(lines).strip()
			logger.debug(f"After fence removal (length: {len(text)} chars)")
		
		# Try to extract JSON if there's text before/after
		# Look for content between { and }
		if not text.startswith("{") and not text.startswith("["):
			logger.debug("JSON doesn't start with { or [, searching for start...")
			start_idx = text.find("{")
			if start_idx == -1:
				start_idx = text.find("[")
			if start_idx != -1:
				logger.debug(f"Found JSON start at index {start_idx}")
				text = text[start_idx:]
			else:
				logger.warning("Could not find JSON start marker")
		
		# Find the end of the first complete JSON object/array
		# This handles "extra data" errors when LLM adds content after JSON
		if text.startswith("{"):
			logger.debug("Finding matching closing brace for JSON object")
			# Find matching closing brace
			brace_count = 0
			for i, char in enumerate(text):
				if char == "{":
					brace_count += 1
				elif char == "}":
					brace_count -= 1
					if brace_count == 0:
						if i < len(text) - 1:
							logger.debug(f"Trimming extra content after JSON (from index {i+1})")
							logger.debug(f"Extra content: {text[i+1:i+101]}...")
						text = text[:i + 1]
						break
		elif text.startswith("["):
			logger.debug("Finding matching closing bracket for JSON array")
			# Find matching closing bracket
			bracket_count = 0
			for i, char in enumerate(text):
				if char == "[":
					bracket_count += 1
				elif char == "]":
					bracket_count -= 1
					if bracket_count == 0:
						if i < len(text) - 1:
							logger.debug(f"Trimming extra content after JSON (from index {i+1})")
							logger.debug(f"Extra content: {text[i+1:i+101]}...")
						text = text[:i + 1]
						break

		logger.debug(f"Final text for JSON parsing (length: {len(text)} chars)")
		logger.debug(f"Final text preview: {text[:500]}...")

		try:
			result = json.loads(text)
			logger.info("Successfully parsed JSON")
			logger.debug(f"Parsed JSON structure: {type(result)}, keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
			return result
		except json.JSONDecodeError as exc:
			# Provide more helpful error message with context
			error_context = text[max(0, exc.pos - 100):min(len(text), exc.pos + 100)]
			logger.error(f"JSON parsing failed at position {exc.pos}: {exc.msg}")
			logger.error(f"Error context: ...{error_context}...")
			logger.error(f"Full response length: {len(raw)} chars")
			logger.debug(f"Failed text (first 2000 chars): {text[:2000]}")
			raise ValueError(
				f"LLM returned invalid JSON at position {exc.pos}: {exc.msg}\n"
				f"Context: ...{error_context}...\n"
				f"Full response length: {len(raw)} chars"
			) from exc


__all__ = ["LLMService"]

