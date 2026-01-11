import chromadb

from app.config import settings


def get_chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)


def check_chroma_connection() -> tuple[bool, Exception]:
    try:
        client = get_chroma_client()
        client.heartbeat()
        return (True, None)
    except Exception as e:
        return (False, e)


def query_chroma(collection: str, query_texts: list[str], n_results: int = 5):
    client = get_chroma_client()
    coll = client.get_or_create_collection(name=collection)
    result = coll.query(query_texts=query_texts, n_results=n_results)
    return result
