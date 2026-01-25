import httpx

from app.main import app


class DummyProcessor:
	def __init__(self) -> None:
		self.calls: list[dict] = []

	async def process_document(self, file_path, source: str = "upload", metadata: dict = None):
		self.calls.append({"file_path": file_path, "source": source, "metadata": metadata})
		return {
			"canonical": True,
			"source": source,
			"original_filename": metadata.get("original_filename") if metadata else None,
		}


def test_canonical_endpoint_happy_path(monkeypatch):
	from app.api.routes import documents

	dummy = DummyProcessor()

	# Replace the DocumentProcessor used by the route with our dummy one.
	monkeypatch.setattr(documents, "DocumentProcessor", lambda: dummy)

	files = {"file": ("paper.pdf", b"%PDF-1.4 dummy data", "application/pdf")}
	transport = httpx.ASGITransport(app=app)
	with httpx.Client(transport=transport, base_url="http://testserver") as client:
		response = client.post("/documents/canonical", files=files)
	assert response.status_code == 200
	body = response.json()
	assert body["canonical"] is True
	assert body["source"] == "upload"
	assert body["original_filename"] == "paper.pdf"
	assert len(dummy.calls) == 1


def test_canonical_endpoint_rejects_non_pdf():
	files = {"file": ("notes.txt", b"hello", "text/plain")}
	transport = httpx.ASGITransport(app=app)
	with httpx.Client(transport=transport, base_url="http://testserver") as client:
		response = client.post("/documents/canonical", files=files)
	assert response.status_code == 400
	body = response.json()
	assert "Only PDF files are supported" in body.get("detail", "")


def test_canonical_endpoint_rejects_empty_pdf():
	files = {"file": ("paper.pdf", b"", "application/pdf")}
	transport = httpx.ASGITransport(app=app)
	with httpx.Client(transport=transport, base_url="http://testserver") as client:
		response = client.post("/documents/canonical", files=files)
	assert response.status_code == 400
	body = response.json()
	assert "empty" in body.get("detail", "").lower()
