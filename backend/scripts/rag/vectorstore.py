"""Chroma(PersistentClient) 접근 — LangChain 등 래퍼 없이 chromadb 네이티브 클라이언트를
직접 쓴다(사용자 확정 사항: 지금은 하이브리드가 없어서 그 정도 추상화가 필요 없음)."""
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def get_client():
    import chromadb

    config.VECTORDB_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.VECTORDB_DIR))


def get_or_create_collection():
    client = get_client()
    return client.get_or_create_collection(
        name=config.VECTORDB_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def get_collection_or_none():
    """빌드가 아직 안 됐을 수도 있는 조회 경로(retrieval.py)용 — 없으면 예외 대신 None."""
    client = get_client()
    try:
        return client.get_collection(name=config.VECTORDB_COLLECTION)
    except Exception:
        return None
