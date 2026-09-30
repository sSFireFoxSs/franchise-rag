"""RAG 1차 구현 — 임베딩 빌드 스크립트 (1회성).

clauses.jsonl(.gz) 중 서술형 카테고리(VECTOR_CATEGORIES: 계약해지/필수구입물품/영업지역/
소송·법위반/위약금·손해배상)만 골라서 KURE-v1(nlpai-lab/KURE-v1)으로 text 필드를 임베딩하고
Chroma(PersistentClient, data/vectordb/)에 적재한다. 구조화 카테고리(가맹비/가맹금·보증금·
교육비·로열티·평균매출액·행정처분)는 벡터검색이 필요 없어서(docs/DESIGN.md 방침) 여기서 아예
제외한다 — 임베딩 대상이 전체 89,969건 중 약 62,000건으로 줄어 시간이 절약된다.

임베딩 입력은 각 row의 `text` 필드만 쓴다(브랜드명 등 다른 텍스트를 섞지 않음 — 브랜드
필터링은 메타데이터로 별도 처리하므로 임베딩 자체에 브랜드명을 넣을 필요가 없다).

이어하기(resume) 지원: Chroma 컬렉션에 이미 있는 id는 건너뛴다. 그래서 중간에 멈춰도
다시 실행하면 이어서 진행된다.

사용법:
  python scripts/11_build_embeddings.py               # 전체
  python scripts/11_build_embeddings.py --limit 200    # 브랜드 200개만 (테스트용)
  python scripts/11_build_embeddings.py --rebuild      # 컬렉션을 지우고 처음부터 다시
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from section_schema import VECTOR_CATEGORIES  # noqa: E402
from utils import get_logger  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import config  # noqa: E402
from rag.embedding import embed_texts  # noqa: E402
from rag.vectorstore import get_client, get_or_create_collection  # noqa: E402

logger = get_logger("11_build_embeddings")

CLAUSES_PATH = config.CLAUSES_GZ_PATH if config.CLAUSES_GZ_PATH.exists() else config.CLAUSES_PATH


def iter_vector_rows(limit_brands=None):
    """clauses 데이터에서 VECTOR_CATEGORIES에 속한 row만, (jngIfrmpSn, attr) 조합별로
    유일한 id를 붙여서 순서대로 낸다."""
    import gzip
    import json

    opener = gzip.open if CLAUSES_PATH.suffix == ".gz" else open
    occurrence = {}
    seen_brands = set()
    with opener(CLAUSES_PATH, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("category") not in VECTOR_CATEGORIES:
                continue
            brand_mnno = row["brandMnno"]
            if limit_brands is not None:
                seen_brands.add(brand_mnno)
                if len(seen_brands) > limit_brands:
                    break
            key = (row.get("jngIfrmpSn"), row.get("attr"))
            occurrence[key] = occurrence.get(key, 0) + 1
            row_id = f"{key[0]}::{key[1]}::{occurrence[key]}"
            yield row_id, row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="브랜드 N개만 처리(테스트용)")
    ap.add_argument("--batch-size", type=int, default=64, help="한 번에 임베딩/적재할 row 수")
    ap.add_argument("--rebuild", action="store_true", help="기존 컬렉션을 삭제하고 처음부터 다시 만듦")
    args = ap.parse_args()

    if not CLAUSES_PATH.exists():
        logger.error(f"{CLAUSES_PATH} 가 없습니다. 먼저 03_extract_clauses.py를 실행하세요.")
        return

    if args.rebuild:
        client = get_client()
        try:
            client.delete_collection(config.VECTORDB_COLLECTION)
            logger.info(f"기존 컬렉션 삭제함: {config.VECTORDB_COLLECTION}")
        except Exception:
            pass

    collection = get_or_create_collection()
    existing_count = collection.count()
    logger.info(f"컬렉션 '{config.VECTORDB_COLLECTION}' 로드 (기존 {existing_count}건, "
                f"모델={config.EMBEDDING_MODEL_NAME}, device={config.EMBEDDING_DEVICE})")

    # 이어하기: 컬렉션에 이미 있는 id는 건너뛴다. id만 가져오면 되므로 include=[]로 최소 조회.
    existing_ids = set(collection.get(include=[])["ids"]) if existing_count else set()
    if existing_ids:
        logger.info(f"이미 적재된 {len(existing_ids)}건은 건너뜁니다 (이어하기)")

    batch_ids, batch_texts, batch_metas = [], [], []
    n_seen = 0
    n_skipped = 0
    n_added = 0

    def flush():
        nonlocal batch_ids, batch_texts, batch_metas, n_added
        if not batch_ids:
            return
        vectors = embed_texts(batch_texts)
        collection.upsert(ids=batch_ids, embeddings=vectors, documents=batch_texts, metadatas=batch_metas)
        n_added += len(batch_ids)
        logger.info(f"진행: {n_added}건 적재 (스킵 {n_skipped}건, 조회 {n_seen}건)")
        batch_ids, batch_texts, batch_metas = [], [], []

    for row_id, row in iter_vector_rows(limit_brands=args.limit):
        n_seen += 1
        if row_id in existing_ids:
            n_skipped += 1
            continue
        text = (row.get("text") or "").strip()
        if not text:
            n_skipped += 1
            continue
        meta = {
            "brandMnno": row.get("brandMnno") or "",
            "brandNm_matched": row.get("brandNm_matched") or row.get("brandNm") or "",
            "category": row.get("category") or "",
            "canonical_title": row.get("canonical_title") or "",
            "chapter": row.get("chapter") or "",
            "attr": row.get("attr") or "",
            "jngIfrmpSn": str(row.get("jngIfrmpSn") or ""),
            "section_title": (row.get("section_title") or "")[:200],
        }
        batch_ids.append(row_id)
        batch_texts.append(text)
        batch_metas.append(meta)
        if len(batch_ids) >= args.batch_size:
            flush()

    flush()
    logger.info("=" * 60)
    logger.info(f"완료: 조회 {n_seen}건 / 스킵(이미 있음·빈 텍스트) {n_skipped}건 / 신규 적재 {n_added}건")
    logger.info(f"컬렉션 총 건수: {collection.count()}")

    # 2026-09-14 실측 버그 대응: 대량 upsert 직후 프로세스가 바로 끝나버리면, chromadb가
    # 내부적으로 비동기 처리하는 HNSW 세그먼트 컴팩션(로그의 "backfill request to compactor")이
    # 다 안 끝난 상태로 남아서 -- 같은 프로세스 안에서는 collection.count()가 멀쩡히 되는데도 --
    # 다음에 새 프로세스가 이 컬렉션을 열면 "Error loading hnsw index"로 아예 못 읽는 문제가
    # 재현됨(원인 확정은 아니지만 이 sleep을 넣은 뒤로는 재현 안 됨). 프로세스 종료 전에
    # 컴팩션이 따라잡을 시간을 준다.
    if n_added > 0:
        logger.info("컴팩션 대기 중 (10초)...")
        time.sleep(10)


if __name__ == "__main__":
    main()
