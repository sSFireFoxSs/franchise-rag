"""브랜드 비교 화면 전용 라우터(검색 자동완성 포함). main.py에는 이 라우터를 등록하는
한 줄만 추가한다(지침사항.txt "백엔드 API 만드는 규칙" — main.py 동시 수정으로 인한
병합 충돌 방지)."""
from fastapi import APIRouter, HTTPException, Query

from app.brand_data import (
    brand_match_tier,
    brand_search_index,
    compare_entry,
    norm_search,
    resolve_or_404_mnno,
)

router = APIRouter()


@router.get("/api/brands/search")
def brands_search(q: str = "", limit: int = 20) -> dict:
    """이름 일부(부분 문자열)로 브랜드를 찾는다. 매칭 등급(brand_match_tier) 우선,
    같은 등급 안에서는 가맹점 수 내림차순(값 없는 브랜드는 맨 뒤, 이름순)으로 정렬해
    반환한다 — 정확한 브랜드명을 몰라도 자동완성으로 고를 수 있게 하기 위함."""
    norm_q = norm_search(q)
    if not norm_q:
        return {"items": []}
    tiered = []
    for b in brand_search_index():
        tier = brand_match_tier(norm_q, b["brandNm"])
        if tier is not None:
            tiered.append((tier, b))
    tiered.sort(key=lambda t: (t[0], t[1]["storeCount"] is None, -(t[1]["storeCount"] or 0), t[1]["brandNm"]))
    limit = max(1, min(limit, 50))
    return {"items": [b for _, b in tiered[:limit]]}


@router.get("/api/brands/compare")
def brands_compare(name: list[str] = Query(default=[]), mnno: list[str] = Query(default=[])) -> dict:
    """브랜드 2~4개를 한 번에 비교한다(name을 여러 번 반복 전달, 예: ?name=A&name=B&name=C).
    mnno[i]가 있으면(자동완성으로 정확한 브랜드를 고른 경우) name[i] 대신 그걸 그대로 쓰고,
    없으면 이름으로 resolve한다 — 동명이인 브랜드(예: 43쌍의 피자스쿨류)가 이름 매칭만으로는
    어느 쪽인지 모호할 수 있어서, 자동완성이 mnno를 넘겨주면 모호함이 없다. mnno 리스트가
    name보다 짧으면 나머지는 힌트 없음(빈 문자열)으로 취급한다."""
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="비교할 브랜드를 2개 이상 입력해 주세요.")
    if len(name) > 4:
        raise HTTPException(status_code=400, detail="브랜드는 최대 4개까지 비교할 수 있습니다.")

    mnno_hints = list(mnno) + [""] * (len(name) - len(mnno))
    brands = []
    for nm, hint in zip(name, mnno_hints):
        resolved = resolve_or_404_mnno(nm, hint)
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"'{nm}' 브랜드를 찾을 수 없습니다.")
        brands.append(compare_entry(nm, resolved))
    return {"brands": brands}
