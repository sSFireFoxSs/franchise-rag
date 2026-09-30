"""2단계: intent별 조회.

- 구조화조회(STRUCTURED_CATEGORIES): 벡터검색 없이 brandMnno(+category/canonical_title)로
  clauses를 필터링해서 amounts/violation_flag를 그대로 꺼낸다.
- 서술형(VECTOR_CATEGORIES): brandMnno(+category)로 먼저 필터링한 뒤, 그 안에서만 KURE-v1
  dense 벡터검색을 돌린다(docs/DESIGN.md 2단계 방침 — 전체검색 후 필터링 금지).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from section_schema import STRUCTURED_CATEGORIES, VECTOR_CATEGORIES  # noqa: E402

from . import config, data
from .embedding import embed_query, embed_texts
from .vectorstore import get_collection_or_none


def structured_lookup(brand_mnno: str, category: "str | None" = None,
                       canonical_title: "str | None" = None) -> list[dict]:
    """구조화 카테고리용: 해당 브랜드의 clauses row를 그대로 필터링해서 반환한다
    (amounts/violation_flag/tables 등 전체 필드 포함 — 숫자는 여기서 그대로 꺼내 쓰고
    LLM이 재생성하지 않는다, docs/DESIGN.md 4단계 원칙)."""
    rows = data.get_brand_rows(brand_mnno)
    if category:
        rows = [r for r in rows if r.get("category") == category]
    if canonical_title:
        rows = [r for r in rows if r.get("canonical_title") == canonical_title]
    return rows


def vector_search(brand_mnno: str, query_text: str, category: "str | None" = None,
                   top_k: "int | None" = None) -> list[dict]:
    """서술형 카테고리용: brandMnno(+category)로 먼저 메타데이터 필터링한 뒤, 그 안에서만
    dense 벡터검색. 결과 각 항목: {text, distance, brandMnno, brandNm_matched, category,
    canonical_title, section_title, attr, jngIfrmpSn}.

    2026-09-14 실측 버그: 이 chromadb 버전(1.5.9)에서 collection.query(query_embeddings=...,
    where=...)처럼 벡터검색과 메타데이터 필터를 같이 쓰면 매번
    "Internal error: Error finding id"로 죽는다. 원인을 더 좁혀보니 get(where=...)만 쓸 때도
    include에 "embeddings"를 넣는 순간 같은 에러가 남 — 저장된 벡터를 id로 되찾아오는
    경로 자체에 버그가 있는 것으로 보임(documents/metadatas만 가져오는 건 정상 동작).
    그래서 이 함수는 저장된 임베딩을 절대 안 읽어오고, get(where=...)로 후보 문서(text)만
    가져온 뒤 그 text를 다시 임베딩해서 파이썬에서 직접 코사인 유사도를 계산한다. 브랜드+
    카테고리 하나의 후보 row 수는 원래 적어서(보통 한 자리~십여 건) 재임베딩 비용도 작고,
    후보가 적으니 이게 오히려 근사(ANN) 검색보다 더 정확하다."""
    collection = get_collection_or_none()
    if collection is None:
        raise RuntimeError(
            "벡터DB(Chroma) 컬렉션이 없음 — scripts/11_build_embeddings.py를 먼저 실행할 것."
        )
    top_k = top_k or config.VECTOR_TOP_K

    where = {"brandMnno": brand_mnno}
    if category:
        where = {"$and": [{"brandMnno": brand_mnno}, {"category": category}]}

    candidates = collection.get(where=where, include=["documents", "metadatas"])
    ids = candidates.get("ids") or []
    if not ids:
        return []

    docs = candidates["documents"]
    metas = candidates["metadatas"]
    cand_vecs = embed_texts(docs)  # 저장된 벡터를 못 읽어오니(위 버그) 후보 text를 다시 임베딩

    query_vec = embed_query(query_text)
    qnorm = sum(v * v for v in query_vec) ** 0.5

    scored = []
    for _id, doc, meta, emb in zip(ids, docs, metas, cand_vecs):
        dot = sum(a * b for a, b in zip(query_vec, emb))
        enorm = sum(v * v for v in emb) ** 0.5
        cosine = dot / (qnorm * enorm) if qnorm and enorm else 0.0
        scored.append((cosine, _id, doc, meta))

    scored.sort(key=lambda t: t[0], reverse=True)

    hits = []
    for cosine, _id, doc, meta in scored[:top_k]:
        hits.append({
            "id": _id,
            "text": doc,
            "distance": 1 - cosine,  # query()의 distance(작을수록 유사)와 스케일을 맞춤
            **meta,
        })
    return hits


def is_structured_category(category: str) -> bool:
    return category in STRUCTURED_CATEGORIES


def is_vector_category(category: str) -> bool:
    return category in VECTOR_CATEGORIES
