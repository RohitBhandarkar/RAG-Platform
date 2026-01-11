from pathlib import Path
from typing import Dict, List

from app.config import settings


SOURCES = ["pubmed", "patents", "fda", "user_uploads"]
KINDS = ["raw", "processed"]


def get_base_path() -> Path:
	"""Resolve the base path for the document store."""
	return Path(settings.DOC_STORAGE_ROOT).expanduser().resolve()


def ensure_layout() -> Dict:
	base = get_base_path()
	layout = {
		"base": str(base),
		"raw": {},
		"processed": {},
		"embeddings": {},
	}

	for kind in KINDS:
		for source in SOURCES:
			path = base / kind / source
			layout[kind][source] = {
				"path": str(path),
				"exists": path.is_dir(),
			}

	# Embeddings root (no per-source subdivision yet)
	embeddings_path = base / "embeddings"
	layout["embeddings"] = {
		"path": str(embeddings_path),
		"exists": embeddings_path.is_dir(),
	}

	return layout


def summarize_layout() -> Dict:
	"""Summarize counts of files under each logical directory.

	Counts regular files recursively under raw/processed/source.
	"""
	base = get_base_path()
	summary: Dict[str, Dict[str, int]] = {"raw": {}, "processed": {}}

	for kind in KINDS:
		for source in SOURCES:
			path = base / kind / source
			if path.is_dir():
				count = sum(1 for p in path.rglob("*") if p.is_file())
			else:
				count = 0
			summary[kind][source] = count

	return summary


def list_files(kind: str, source: str, limit: int = 20) -> List[str]:
	"""List up to `limit` files under the given kind/source.

	Returns paths relative to the base directory.
	"""
	if kind not in KINDS:
		raise ValueError(f"Unsupported kind: {kind}")
	if source not in SOURCES:
		raise ValueError(f"Unsupported source: {source}")

	base = get_base_path()
	root = base / kind / source
	if not root.is_dir():
		return []

	files: List[str] = []
	for p in sorted(root.rglob("*")):
		if p.is_file():
			files.append(str(p.relative_to(base)))
			if len(files) >= limit:
				break

	return files
