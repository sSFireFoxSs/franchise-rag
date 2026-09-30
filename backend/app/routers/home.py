"""홈 화면 전용 라우터. main.py에는 이 라우터를 등록하는 한 줄만 추가한다(top20.py와
동일 원칙 — main.py 동시 수정으로 인한 병합 충돌 방지).

brand_data.py(top20/compare 공용 파일)는 건드리지 않고, 거기 있는 기존 함수를 그대로
가져다 쓰기만 한다 — 홈 화면 전용 계산이라 공용 파일에 넣을 이유가 없고, 팀원이 같이
수정할 수 있는 파일에 손대는 걸 피한다."""
from fastapi import APIRouter

from app.brand_data import all_brand_avg_sales, rag_data

router = APIRouter()


@router.get("/api/home/stats")
def home_stats_endpoint() -> dict:
    clause_index = rag_data._index()
    disclosure_item_count = sum(len(rows) for rows in clause_index.values())
    rankable_brand_count = sum(
        1 for b in all_brand_avg_sales() if b.get("avgSalesAnnual") is not None
    )
    return {
        "brandCount": len(clause_index),
        "disclosureItemCount": disclosure_item_count,
        "rankableBrandCount": rankable_brand_count,
    }
