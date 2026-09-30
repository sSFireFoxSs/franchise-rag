"""clauses.jsonl(.gz)을 프로세스 메모리에 한 번만 올려서 공유하는 로더.

app.py(Streamlit)의 load_clauses()와 달리 st.cache_data에 의존하지 않는다 — 이 모듈은
Streamlit 밖(CLI 테스트 스크립트, 나중의 FastAPI)에서도 그대로 써야 하기 때문에
functools.lru_cache로 프로세스 단위 싱글턴 캐싱만 한다.
"""
import gzip
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from section_schema import pick_display_name  # noqa: E402

from . import config


def _open_clauses_path() -> Path:
    path = config.CLAUSES_GZ_PATH if config.CLAUSES_GZ_PATH.exists() else config.CLAUSES_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"clauses 데이터가 없음: {config.CLAUSES_GZ_PATH} / {config.CLAUSES_PATH} 둘 다 없음. "
            "scripts/03_extract_clauses.py를 먼저 실행할 것."
        )
    return path


def _iter_rows():
    path = _open_clauses_path()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


@lru_cache(maxsize=1)
def _index():
    by_brand: dict[str, list[dict]] = {}
    for row in _iter_rows():
        by_brand.setdefault(row["brandMnno"], []).append(row)
    return by_brand


def get_brand_rows(brand_mnno: str) -> list[dict]:
    return _index().get(brand_mnno, [])


def known_brand_mnnos() -> set:
    return set(_index().keys())


def display_name_for(brand_mnno: str) -> "str | None":
    rows = get_brand_rows(brand_mnno)
    if not rows:
        return None
    return pick_display_name(rows[0].get("brandNm"), rows[0].get("brandNm_matched"))


def find_row(brand_mnno: str, attr: str, jng_ifrmp_sn=None) -> "dict | None":
    """벡터검색/인용 결과(브랜드+attr)로 원본 row(표 등 전체 필드 포함)를 다시 찾는다.
    한 브랜드 문서 안에서 attr은 사실상 유일(법정서식 섹션 1개당 attr 1개)하므로 첫 매치를
    쓴다 — 아주 드물게 같은 attr이 중복되는 문서가 있어도(허용 범위) 첫 항목이면 충분하다."""
    for row in get_brand_rows(brand_mnno):
        if row.get("attr") != attr:
            continue
        if jng_ifrmp_sn is not None and str(row.get("jngIfrmpSn")) != str(jng_ifrmp_sn):
            continue
        return row
    return None


def clear_cache():
    """데이터 파일이 바뀐 뒤(재추출 등) 프로세스를 재시작하지 않고 다시 읽고 싶을 때."""
    _index.cache_clear()
