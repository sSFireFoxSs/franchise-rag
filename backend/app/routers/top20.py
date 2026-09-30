"""TOP20 화면 전용 라우터. main.py에는 이 라우터를 등록하는 한 줄만 추가한다(지침사항.txt
"백엔드 API 만드는 규칙" — main.py 동시 수정으로 인한 병합 충돌 방지)."""
from fastapi import APIRouter, HTTPException

from app.brand_data import (
    all_brand_avg_sales,
    all_brand_cost_efficiency,
    format_won_kr,
    top_categories,
)

router = APIRouter()

_BY_OPTIONS = ("sales", "store_count", "cost_efficiency")

# 가맹점 수가 적으면 "평균매출액"(그리고 이를 나눠 쓰는 창업비용 대비 매출)이 소수
# 매장의 실적에 쏠려 순위가 왜곡된다(실측: 가맹점 3개짜리 브랜드가 1위로 나오는 등).
# 가맹사업법 시행령이 "지역별" 평균매출액 기재 생략 기준으로 쓰는 것과 같은 값(5개)을
# 그대로 채택 — 평균값 기반 지표(sales/cost_efficiency)에만 적용하고, store_count
# 자체를 보는 정렬에는 적용하지 않는다(순환 논리라 의미 없음).
_MIN_STORE_COUNT_FOR_AVG = 5


@router.get("/api/brands/top20/categories")
def brands_top20_categories() -> dict:
    return {"categories": top_categories()}


@router.get("/api/brands/top20")
def brands_top20(by: str = "sales", category: str | None = None) -> dict:
    if by not in _BY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"by는 {', '.join(_BY_OPTIONS)} 중 하나여야 합니다.")

    if by == "cost_efficiency":
        candidates = list(all_brand_cost_efficiency())
        key = "costEfficiency"
    else:
        key = "avgSalesAnnual" if by == "sales" else "storeCount"
        candidates = [b for b in all_brand_avg_sales() if b[key] is not None]
    if by in ("sales", "cost_efficiency"):
        candidates = [
            b for b in candidates
            if (b.get("storeCount") or 0) >= _MIN_STORE_COUNT_FOR_AVG
        ]
    if category:
        candidates = [b for b in candidates if b.get("category") == category]
    candidates.sort(key=lambda b: b[key], reverse=True)

    items = []
    for i, b in enumerate(candidates[:20]):
        value = b[key]
        if by == "sales":
            value_label = format_won_kr(value)
        elif by == "store_count":
            value_label = f"{value:,}개"
        else:
            value_label = f"{value:.2f}배"
        items.append({
            "rank": i + 1,
            "brandMnno": b["brandMnno"],
            "brandNm": b["brandNm"],
            "category": b.get("category"),
            "value": value,
            "valueLabel": value_label,
            "storeCount": b["storeCount"],
        })
    return {"by": by, "category": category, "items": items}
