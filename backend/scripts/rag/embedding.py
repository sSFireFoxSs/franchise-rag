"""KURE-v1 임베딩 모델 로더 — 11_build_embeddings.py(적재)와 retrieval.py(질의 임베딩)가
같은 모델 인스턴스/설정을 공유하도록 여기 하나로 모은다."""
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def get_embedder():
    """SentenceTransformer 인스턴스를 프로세스당 한 번만 로드한다(수백MB~GB급 모델이라
    매번 새로 로드하면 느림). 순수 질의(구조화조회만 쓰는 경로)에서는 이 함수가 아예
    호출되지 않아서 무거운 import/로드 비용이 안 든다."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(config.EMBEDDING_MODEL_NAME, device=config.EMBEDDING_DEVICE)
    model.max_seq_length = config.EMBEDDING_MAX_SEQ_LENGTH
    return model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """텍스트 리스트를 KURE-v1로 임베딩해서 float 리스트의 리스트로 반환한다."""
    if not texts:
        return []
    model = get_embedder()
    vectors = model.encode(
        texts,
        batch_size=config.EMBEDDING_BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,  # 코사인 유사도 기준 검색이라 정규화해둠 (Chroma 기본 거리함수와 맞춤)
        convert_to_numpy=True,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
