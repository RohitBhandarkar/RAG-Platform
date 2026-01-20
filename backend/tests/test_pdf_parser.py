from pathlib import Path

from app.data.parsers.pdf_parser import PDFParser


def test_detect_sections_with_headings():
	parser = PDFParser()
	pages = [
		{"page_number": 1, "text": "Introduction\nSome text"},
		{"page_number": 2, "text": "Materials and Methods\nMore text"},
		{"page_number": 3, "text": "Results\nEven more text"},
	]

	sections = parser._detect_sections(pages)
	assert len(sections) == 3
	names = [s["section_name"] for s in sections]
	assert names == ["introduction", "materials_and_methods", "results"]
	assert sections[0]["page_start"] == 1 and sections[0]["page_end"] == 1
	assert sections[1]["page_start"] == 2 and sections[1]["page_end"] == 2
	assert sections[2]["page_start"] == 3 and sections[2]["page_end"] == 3


def test_detect_sections_without_headings_creates_full_document():
	parser = PDFParser()
	pages = [
		{"page_number": 1, "text": "Some text without headings."},
		{"page_number": 2, "text": "More text without headings."},
	]

	sections = parser._detect_sections(pages)
	assert len(sections) == 1
	sec = sections[0]
	assert sec["section_name"] == "full_document"
	assert sec["page_start"] == 1
	assert sec["page_end"] == 2
	assert "Some text without headings." in sec["text"]
	assert "More text without headings." in sec["text"]


def test_extract_tables_simple_block_with_caption():
	parser = PDFParser()
	# The table has a caption line followed by a header and two data rows.
	page_text = "\n".join(
		[
			"Some introductory text",
			"Table 1 Composition of formulation",
			"Component    Amount",
			"Drug         10 mg",
			"Lipid        100 mg",
			"Trailing text",
		]
	)
	pages = [{"page_number": 1, "text": page_text}]
	sections = parser._detect_sections(pages)

	tables = parser._extract_tables(pages, sections)
	assert len(tables) == 1
	table = tables[0]
	assert table["page"] == 1
	assert table["headers"] == ["Component", "Amount"]
	assert table["rows"] == [["Drug", "10 mg"], ["Lipid", "100 mg"]]
	assert "Table 1 Composition" in table["caption"]


def test_extract_metadata_with_fake_reader():
	class FakeInfo:
		title = "Test Title"
		author = "Jane Doe"
		subject = "Test Subject"

	class FakeReader:
		metadata = FakeInfo()

	parser = PDFParser()
	file_path = Path("dummy.pdf")

	meta = parser.extract_metadata(file_path, reader=FakeReader())
	assert meta["file_name"] == "dummy.pdf"
	assert meta["title"] == "Test Title"
	assert meta["author"] == "Jane Doe"
	assert meta["subject"] == "Test Subject"
