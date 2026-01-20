from pathlib import Path

from app.services.llm_service import LLMService


def test_parse_llm_json_plain_and_code_fence():
	svc = LLMService(provider="dummy")

	plain = svc._parse_llm_json("{""answer"": 1}")
	assert plain["answer"] == 1

	wrapped = svc._parse_llm_json("```json\n{""answer"": 2}\n```")
	assert wrapped["answer"] == 2


def test_build_prompt_includes_context_and_sections(tmp_path):
	svc = LLMService(provider="dummy")
	parsed_document = {
		"sections": [
			{
				"section_name": "materials_and_methods",
				"heading_path": ["materials_and_methods"],
				"page_start": 1,
				"page_end": 1,
				"text": "Materials and methods section text.",
			},
			{
				"section_name": "results",
				"heading_path": ["results"],
				"page_start": 2,
				"page_end": 2,
				"text": "Results section text.",
			},
		],
		"metadata": {"file_name": "paper.pdf"},
	}

	text_chunks: list[dict] = []
	table_chunks: list[dict] = []
	extra_metadata = {"original_filename": "paper.pdf"}

	prompt = svc._build_prompt(
		parsed_document=parsed_document,
		text_chunks=text_chunks,
		table_chunks=table_chunks,
		extra_metadata=extra_metadata,
		source="upload",
		doc_id="doc-1",
	)

	assert "Source: upload" in prompt
	assert "doc-1" in prompt
	assert "paper.pdf" in prompt
	assert "Materials and methods section text." in prompt
	assert "Results section text." in prompt


def test_generate_canonical_uses_gemini(monkeypatch):
	# Patch the internal Gemini call so no real API is invoked.
	def fake_call(self, prompt: str) -> str:  # type: ignore[override]
		assert "MATERIALS_METHODS_EXPERIMENTAL_FORMULATION" in prompt
		return "{""ok"": true}"

	monkeypatch.setattr(LLMService, "_call_gemini", fake_call)
	svc = LLMService(provider="gemini", model="test-model")

	parsed_document = {"sections": [], "metadata": {}}
	result = svc.generate_canonical(
		parsed_document=parsed_document,
		text_chunks=[],
		table_chunks=[],
		extra_metadata={},
		source="upload",
		doc_id="doc-123",
	)

	assert result == {"ok": True}
