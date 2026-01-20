"""PDF parser for research papers.

This implementation focuses on extracting:

* Continuous text with page numbers.
* A simple heading hierarchy and section labels for common scientific
  sections (Introduction, Materials and Methods, Experimental,
  Formulation, Results, Discussion, Conclusion, Supplementary).

Table extraction is intentionally left as a stub for now so that it can
be implemented with a dedicated library (e.g., camelot or tabula) in a
later iteration.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import re
from PyPDF2 import PdfReader


class PDFParser:
    """Parse PDF documents for downstream processing."""

    # Common section headings we care about for scientific papers.
    _SECTION_KEYWORDS: List[tuple[str, str]] = [
        ("introduction", "introduction"),
        ("materials_and_methods", "materials and methods"),
        ("experimental", "experimental"),
        ("formulation", "formulation"),
        ("results", "results"),
        ("discussion", "discussion"),
        ("conclusion", "conclusion"),
        ("supplementary", "supplementary"),
    ]

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse a PDF into pages and coarse sections.

        Args:
            file_path: Path to the PDF document.

        Returns:
            A dictionary containing:
            - pages: list of {page_number, text}
            - sections: list of {section_name, heading_path,
              page_start, page_end, text}
            - metadata: basic PDF metadata (title, author, etc.)
            - tables: currently an empty list (stub for later use)
        """

        reader = PdfReader(str(file_path))

        pages: List[Dict[str, Any]] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append({"page_number": idx, "text": text})

        sections = self._detect_sections(pages)
        tables = self._extract_tables(pages, sections)
        metadata = self.extract_metadata(file_path, reader)

        return {
            "pages": pages,
            "sections": sections,
            "metadata": metadata,
            "tables": tables,
        }

    def _detect_sections(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect coarse sections based on simple heading heuristics.

        This method scans each page for known section keywords and defines a
        section as the range of pages between two successive detected
        headings.
        """

        heading_pages: List[tuple[int, str]] = []  # (page_number, section_name)

        for page in pages:
            page_number = page["page_number"]
            text_lower = (page.get("text") or "").lower()
            for section_name, keyword in self._SECTION_KEYWORDS:
                if keyword in text_lower:
                    heading_pages.append((page_number, section_name))
                    break

        if not heading_pages:
            # Fallback: single section covering the entire document.
            joined_text = "\n\n".join(p["text"] for p in pages)
            return [
                {
                    "section_name": "full_document",
                    "heading_path": ["full_document"],
                    "page_start": pages[0]["page_number"] if pages else 1,
                    "page_end": pages[-1]["page_number"] if pages else 1,
                    "text": joined_text,
                }
            ]

        heading_pages.sort(key=lambda x: x[0])
        sections: List[Dict[str, Any]] = []

        for i, (page_start, section_name) in enumerate(heading_pages):
            page_end = (
                heading_pages[i + 1][0] - 1
                if i + 1 < len(heading_pages)
                else pages[-1]["page_number"]
            )
            text_parts = [
                p["text"]
                for p in pages
                if page_start <= p["page_number"] <= page_end
            ]
            section_text = "\n\n".join(text_parts).strip()
            sections.append(
                {
                    "section_name": section_name,
                    "heading_path": [section_name],
                    "page_start": page_start,
                    "page_end": page_end,
                    "text": section_text,
                }
            )

        return sections

    def _extract_tables(
        self,
        pages: List[Dict[str, Any]],
        sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Heuristically extract simple tables from page text.

        This implementation looks for contiguous line blocks on each page
        where lines appear to contain multiple columns separated by
        multiple spaces, tabs, or vertical bars. It is intentionally
        lightweight and will not capture all table layouts, but it
        provides a reasonable starting point for numeric extraction.
        """

        tables: List[Dict[str, Any]] = []

        def split_cells(line: str) -> List[str]:
            # Split on two or more spaces, tabs, or pipe separators.
            cells = [c.strip() for c in re.split(r"\s{2,}|\t|\s\|\s", line.strip()) if c.strip()]
            return cells

        # Helper: map a page to its containing section name, if any.
        def section_for_page(page_number: int) -> Optional[str]:
            for sec in sections:
                start = sec.get("page_start")
                end = sec.get("page_end")
                if start is not None and end is not None and start <= page_number <= end:
                    return sec.get("section_name")
            return None

        for page in pages:
            page_number = page["page_number"]
            text = page.get("text") or ""
            if not text.strip():
                continue

            lines = text.splitlines()
            current_block: List[tuple[int, List[str]]] = []  # (line_index, cells)

            def flush_block() -> None:
                if len(current_block) < 2:
                    return  # need at least header + one row

                # Determine caption as the closest non-empty non-table line above the block.
                first_idx = current_block[0][0]
                caption = ""
                for ci in range(first_idx - 1, -1, -1):
                    candidate = lines[ci].strip()
                    if not candidate:
                        continue
                    # If this line also looks tabular, skip it.
                    if len(split_cells(candidate)) >= 2:
                        continue
                    caption = candidate
                    break

                headers = current_block[0][1]
                rows = [cells for _, cells in current_block[1:]]

                tables.append(
                    {
                        "page": page_number,
                        "section_name": section_for_page(page_number),
                        "caption": caption,
                        "headers": headers,
                        "rows": rows,
                    }
                )

            for idx, line in enumerate(lines):
                cells = split_cells(line)
                if len(cells) >= 2:
                    current_block.append((idx, cells))
                else:
                    flush_block()
                    current_block = []

            # Flush any trailing block at end of page
            flush_block()
            current_block = []

        return tables

    def extract_tables(self, file_path: Path) -> list:
        """Extract tables from a PDF file.

        This is a convenience wrapper around the internal table
        detection used by :meth:`parse`.
        """

        reader = PdfReader(str(file_path))
        pages: List[Dict[str, Any]] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append({"page_number": idx, "text": text})

        sections = self._detect_sections(pages)
        return self._extract_tables(pages, sections)

    def extract_metadata(self, file_path: Path, reader: Optional[PdfReader] = None) -> Dict[str, Any]:
        """Extract basic PDF metadata (title, author, etc.)."""

        if reader is None:
            reader = PdfReader(str(file_path))

        info = getattr(reader, "metadata", None) or {}

        return {
            "file_name": file_path.name,
            "title": getattr(info, "title", "") or "",
            "author": getattr(info, "author", "") or "",
            "subject": getattr(info, "subject", "") or "",
        }

