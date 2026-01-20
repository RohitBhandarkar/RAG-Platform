import asyncio
from pathlib import Path

from app.data.ingestion.document_processor import DocumentProcessor


def test_chunk_document_splits_long_sections():
	processor = DocumentProcessor()
	text = "a" * 5000
	sections = [
		{
			"section_name": "introduction",
			"heading_path": ["introduction"],
			"page_start": 1,
			"page_end": 2,
			"text": text,
		}
	]

	text_chunks, table_chunks = processor.chunk_document(
		"doc1", sections, tables=[], max_chars=2000
	)

	assert len(text_chunks) == 3
	assert text_chunks[0]["text"] == "a" * 2000
	assert text_chunks[1]["text"] == "a" * 2000
	assert text_chunks[2]["text"] == "a" * 1000
	assert text_chunks[0]["page_start"] == 1
	assert text_chunks[0]["page_end"] == 2
	assert table_chunks == []


def test_chunk_document_creates_table_chunks():
	processor = DocumentProcessor()
	sections: list[dict] = []
	tables = [
		{
			"page": 1,
			"section_name": "results",
			"caption": "Size and zeta potential",
			"headers": ["Size", "Zeta"],
			"rows": [["200 nm", "-20 mV"]],
		}
	]

	text_chunks, table_chunks = processor.chunk_document("docT", sections, tables=tables)
	assert text_chunks == []
	assert len(table_chunks) == 1
	chunk = table_chunks[0]
	assert chunk["chunk_id"].startswith("docT::table::1")
	assert chunk["section_name"] == "results"
	assert chunk["caption"] == "Size and zeta potential"
	assert chunk["headers"] == ["Size", "Zeta"]
	assert chunk["rows"] == [["200 nm", "-20 mV"]]


def test_process_document_uses_parser_and_llm():
	class DummyParser:
		def __init__(self) -> None:
			self.called_with = None

		def parse(self, file_path: Path) -> dict:
			self.called_with = file_path
			return {
				"sections": [
					{
						"section_name": "introduction",
						"heading_path": ["introduction"],
						"page_start": 1,
						"page_end": 1,
						"text": "Intro text",
					}
				],
				"tables": [
					{
						"page": 1,
						"section_name": "introduction",
						"caption": "Comp table",
						"headers": ["A", "B"],
						"rows": [["1", "2"]],
					}
				],
				"metadata": {"file_name": "dummy.pdf"},
			}

	class DummyLLM:
		def __init__(self) -> None:
			self.called = False
			self.last_args: dict | None = None

		def generate_canonical(self, **kwargs):
			self.called = True
			self.last_args = kwargs
			return {"ok": True, "doc_id": kwargs["doc_id"]}

	processor = DocumentProcessor()
	processor._parser = DummyParser()
	processor._llm = DummyLLM()

	file_path = Path("dummy.pdf")
	result = asyncio.run(processor.process_document(file_path, source="upload", metadata={"foo": "bar"}))

	assert result == {"ok": True, "doc_id": str(file_path)}
	assert processor._parser.called_with == file_path
	assert processor._llm.called is True
	assert processor._llm.last_args is not None
	args = processor._llm.last_args
	assert args["source"] == "upload"
	assert args["doc_id"] == str(file_path)
	assert args["extra_metadata"] == {"foo": "bar"}
	assert len(args["text_chunks"]) == 1
	assert len(args["table_chunks"]) == 1
