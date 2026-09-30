"""top20/compare 라우터가 공유하는 데이터 계층.

브랜드별 구조화 데이터(평균매출액/가맹비/보증금/총창업비용) 파싱·집계·검색 로직을 여기
한 곳에만 두고, backend/app/routers/top20.py와 backend/app/routers/compare.py가 이 모듈을
가져다 쓴다 — 두 라우터가 같은 파싱 로직을 각자 복붙하면 나중에 한쪽만 고쳐서 값이
어긋나는 사고가 나기 쉬워서, 계산 로직 자체는 여기 하나로 모아둔다(라우터 파일 분리는
main.py 충돌 방지 목적이지 로직 중복을 정당화하지 않음).

RAG 파이프라인(backend/scripts/rag/)은 여기서도 수정 없이 그대로 가져다 쓴다.
"""
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))
BRAND_UNIFIED_PATH = BACKEND_ROOT / "data" / "brand" / "brand_unified.jsonl"

from rag import brand_match as rag_brand_match  # noqa: E402
from rag import data as rag_data  # noqa: E402
from rag import retrieval as rag_retrieval  # noqa: E402
from rag import total_cost as rag_total_cost  # noqa: E402


def _parse_comma_int(raw: Any) -> "int | None":
    """"1,261,411" 같은 콤마 포함 raw 문자열을 정수로 파싱한다. amounts[].amount_won은
    "천원" 단위 가정하에 raw*1000으로 이미 변환돼 있어서(retrieval.py 추출 단계), 가맹점
    수처럼 금액이 아닌 컬럼(raw 그대로가 개수)에는 amount_won을 쓰면 안 되고 raw를 직접
    파싱해야 한다."""
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    if not s or s in ("-", "N/A"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def format_won_kr(won: "int | None") -> str:
    """사람이 읽기 좋은 "3억 9,854만원" 형식으로 포맷한다."""
    if won is None:
        return ""
    neg = "-" if won < 0 else ""
    won = abs(won)
    eok, rem = divmod(won, 100_000_000)
    man = round(rem / 10_000)
    if man == 10_000:
        eok += 1
        man = 0
    if eok and man:
        return f"{neg}{eok}억 {man:,}만원"
    if eok:
        return f"{neg}{eok}억원"
    if man:
        return f"{neg}{man:,}만원"
    return f"{neg}{won:,}원"


_AVG_SALES_LABEL_STORE_RE = re.compile(r"^전체\s+([\d,]+)")


def _norm_ws(s: "str | None") -> str:
    return "".join((s or "").split())


def parse_avg_sales_row(brand_mnno: str) -> dict:
    """평균매출액 카테고리 row들에서 "전체"(지역별 합산 아님) 행의 가맹점 수/연간 평균
    매출액/3.3㎡당 매출액만 뽑는다. 지역별 행을 합산하면 안 된다는 요구사항을 지키기 위해
    label이 "전체"로 시작하는 amounts 항목만 본다(완전일치 대신 startswith인 이유: 표 추출
    과정에서 "전체" 뒤에 다음 컬럼 값이 그대로 붙어버리는 경우가 실측됨 — 예: "전체 10 9").
    같은 이유로 "가맹점수" 컬럼이 별도 항목으로 안 뽑히고 label 문자열 안에 숫자로만
    남아있는 경우가 있어서, 컬럼 매칭으로 가맹점 수를 못 찾으면 label 앞부분 숫자를
    폴백으로 쓴다(실측: 2,427개 브랜드 중 약 57%가 이 방식으로 매칭됨 — 나머지는 표
    형식이 더 달라서 못 찾음, 값 없는 브랜드는 top20/compare에서 제외/null 처리)."""
    store_count = None
    avg_sales_won = None
    avg_sales_per33_won = None
    for row in rag_retrieval.structured_lookup(brand_mnno, category="평균매출액"):
        for a in row.get("amounts") or []:
            label = (a.get("label") or "").strip()
            if not label.startswith("전체"):
                continue
            col = _norm_ws(a.get("column"))
            if "가맹점수" in col and "산출대상" not in col and "매출액" not in col:
                if store_count is None:
                    store_count = _parse_comma_int(a.get("raw"))
            elif "면적" in col and "상한" not in col and "하한" not in col:
                if avg_sales_per33_won is None:
                    avg_sales_per33_won = a.get("amount_won")
            elif "평균매출액" in col and "상한" not in col and "하한" not in col:
                if avg_sales_won is None:
                    avg_sales_won = a.get("amount_won")
        if store_count is None:
            for a in row.get("amounts") or []:
                m = _AVG_SALES_LABEL_STORE_RE.match((a.get("label") or "").strip())
                if m:
                    store_count = _parse_comma_int(m.group(1))
                    break
    # 표 추출 과정에서 여러 컬럼 값이 라벨/셀 하나로 뭉개져 들어오는 아티팩트가 실측됨
    # (예: 라벨 전체가 숫자 나열로 오염되어 가맹점 수가 725,134처럼 나옴) — 국내에 이 정도
    # 규모의 단일 프랜차이즈 브랜드는 없으므로 상식적 상한을 넘는 값은 신뢰하지 않고 버린다.
    if store_count is not None and store_count > 100_000:
        store_count = None
    return {
        "storeCount": store_count,
        "avgSalesAnnual": avg_sales_won,
        "avgSalesPer33": avg_sales_per33_won,
    }


@lru_cache(maxsize=1)
def _brand_category_map() -> dict:
    """brand_unified.jsonl(공정위 원본 브랜드 메타데이터, RAG 파이프라인과 무관한 별도
    소스)에서 brandMnno -> 업종 중분류(indutyMlsfcNm)만 뽑아 캐싱한다. 대분류(외식/서비스/
    도소매 3종)는 너무 뭉뚱그려져서 TOP20 카테고리 필터로는 중분류(한식/커피/치킨 등,
    마이프차의 업종 태그와 같은 급)를 쓴다."""
    out: dict[str, str] = {}
    if not BRAND_UNIFIED_PATH.exists():
        return out
    with open(BRAND_UNIFIED_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            cat = d.get("indutyMlsfcNm")
            if cat:
                out[d["brandMnno"]] = cat
    return out


@lru_cache(maxsize=1)
def all_brand_avg_sales() -> list[dict]:
    """전체 브랜드(known_brand_mnnos())를 순회하며 평균매출액 "전체" 행을 한 번만 모아
    캐싱한다(모듈 프로세스 생애 동안 1회 계산 — top20 요청마다 2,400여 개 브랜드를 다시
    훑지 않도록). data.py의 clauses 인덱스 자체가 이미 lru_cache 싱글턴이라 이 순회는
    디스크 재접근 없이 메모리 내 dict 조회만 한다."""
    category_map = _brand_category_map()
    out = []
    for mnno in rag_data.known_brand_mnnos():
        parsed = parse_avg_sales_row(mnno)
        if parsed["storeCount"] is None and parsed["avgSalesAnnual"] is None:
            continue
        display = rag_data.display_name_for(mnno) or mnno
        out.append({
            "brandMnno": mnno,
            "brandNm": display,
            "category": category_map.get(mnno),
            **parsed,
        })
    return out


@lru_cache(maxsize=1)
def all_brand_cost_efficiency() -> list[dict]:
    """TOP20 "창업비용 대비 매출" 정렬용. all_brand_avg_sales()로 이미 연평균매출액이
    있는 브랜드만 추려서(전체 순회 비용을 줄이려는 목적), 그중 총창업비용까지 단일
    금액으로 안전하게 나오는(mode="single") 브랜드에 한해 costEfficiency =
    avgSalesAnnual / totalStartupCost 를 계산한다. 매장 타입별로 총창업비용이 갈려서
    단일 금액으로 못 합치는 브랜드(mode="multi")나 총창업비용 자체가 없는 브랜드
    (mode="unavailable")는 비율을 계산할 근거가 없으므로 순위 후보에서 제외한다 —
    데이터 없는 브랜드에 임의값을 채우지 않는다는 원칙과 동일하게, 값을 추정하지 않고
    빼는 쪽을 택함.

    amount_unit_detected가 None인 원본 row(단위를 "천원"으로 확신할 수 없는 경우)가
    섞여 있으면, 실제로 총창업비용이 1000배 작게 계산돼 비율이 비정상적으로 커지는
    사례가 실측됨(예: 국수역(驛) — 매출/비용 비율이 25,000배로 나옴, 대조해보니
    총창업비용이 13,000원으로 계산돼 있었음 = "천원" 단위를 못 읽은 것). 단위를
    확신할 수 없는 데이터로 만든 비율은 신뢰할 수 없으므로, breakdown에 쓰인 row 중
    하나라도 amount_unit_detected가 None이면 이 브랜드는 순위 후보에서 제외한다.

    두 번째로 실측된 문제(이마트에브리데이 — 비율이 160배로 나와 육안으로도 비현실적
    이었음): "그 밖에 지급하여야 하는 비용"(인테리어/설비 등 실제 창업비용의 대부분을
    차지하는 항목) 없이 가맹비/예치가맹금만으로 총창업비용이 계산된 브랜드가 있었다.
    두 가지 원인이 섞여 있었음:
    (a) 실제로는 금액 데이터가 있는데 total_cost.py가 완전일치로만 "총계" 라벨을
        인정하는 규칙 때문에 라벨이 "총계 총계"처럼 중복 추출된 경우 합계에서 통째로
        누락됨(실측: 그 밖의 비용 347,325,000원이 빠지고 가맹비 11,000,000원만
        잡혀 비율이 160배로 나옴).
    (b) 애초에 "그 밖에 지급하여야 하는 비용" 표 자체가 비어있는(추출 데이터 0건)
        브랜드도 있음(실측: 국밥엔 — 예치가맹금 3,300,000원만으로 총창업비용이 계산돼
        비율이 125배로 나옴). 이 경우 원인이 원본 정보공개서에 실제로 해당 항목이
        없어서인지, 추출 과정에서 빠진 것인지 이 계층에서는 구분할 수 없음.
    두 경우 모두 "인테리어/설비 등 실제 창업비용을 구성하는 항목 없이 가맹비만으로
    계산된 총창업비용"이라 매출 대비 비율이 비교 지표로서 신뢰하기 어렵다. total_cost.py
    는 수정 대상이 아니므로, 여기서는 "그 밖의 비용" 항목이 실제로 합계에 반영된
    (breakdown에 포함된) 브랜드만 순위 후보로 인정한다 — 추정으로 값을 보정하지 않고
    신뢰할 수 없는 값은 빼는 원칙을 그대로 적용한 것."""
    out = []
    for b in all_brand_avg_sales():
        if b["avgSalesAnnual"] is None:
            continue
        tc = rag_total_cost.compute_total_startup_cost(b["brandMnno"])
        if tc.get("mode") != "single":
            continue
        total_cost = tc["total_won"]
        if not total_cost:
            continue
        if any(r.get("amount_unit_detected") is None for r in tc.get("rows", [])):
            continue
        breakdown_labels = {row["label"] for row in tc.get("breakdown", [])}
        if rag_total_cost.OTHER_COST_TITLE not in breakdown_labels:
            continue
        out.append({
            **b,
            "totalStartupCost": total_cost,
            "costEfficiency": b["avgSalesAnnual"] / total_cost,
        })
    return out


def top_categories(limit: int = 10) -> list[dict]:
    """TOP20 카테고리 탭에 쓸 상위 업종 목록. 실제 순위 후보(all_brand_avg_sales() 결과)
    안에서 브랜드 수가 많은 순으로만 추린다 — brand_unified 전체(12,498건) 기준이 아니라
    이 서비스에서 실제로 순위를 매길 수 있는 브랜드(2,427개) 기준이어야 탭을 눌렀을 때
    "데이터 없음"만 뜨는 카테고리가 안 나온다."""
    from collections import Counter
    counts = Counter(b["category"] for b in all_brand_avg_sales() if b.get("category"))
    return [{"key": cat, "label": cat, "count": n} for cat, n in counts.most_common(limit)]


def resolve_brand_mnno(brand_name: str) -> "str | None":
    """brand_match.BrandIndex로 이름 -> brandMnno를 찾고, clauses 데이터가 실제로 있는
    후보로 좁힌다(pipeline.py의 resolve()->find_in_text() 폴백 패턴과 동일)."""
    brand_index = rag_brand_match.get_brand_index()
    known = rag_data.known_brand_mnnos()
    candidates = brand_index.resolve(brand_name) or brand_index.find_in_text(brand_name)
    data_candidates = [m for m in candidates if m in known]
    if not data_candidates:
        return None
    return data_candidates[0]


def resolve_or_404_mnno(name: str, mnno_hint: str) -> "str | None":
    """mnno_hint(자동완성으로 정확한 브랜드를 고른 경우)가 있으면 그걸 그대로 쓰고,
    없으면 이름으로 resolve한다. 못 찾으면 None(호출부가 404로 변환)."""
    known = rag_data.known_brand_mnnos()
    if mnno_hint and mnno_hint in known:
        return mnno_hint
    return resolve_brand_mnno(name)


def norm_search(s: "str | None") -> str:
    return _norm_ws(s).lower()


@lru_cache(maxsize=1)
def brand_search_index() -> list[dict]:
    """clauses 데이터가 있는 전체 브랜드(2,427개)를 이름+가맹점수로 인덱싱한다(1회 계산,
    top20과 같은 캐싱 패턴). 사용자에게 정확한 브랜드명 스펠링을 요구하지 않고 자동완성으로
    후보를 보여주기 위한 용도 — brand_unified.jsonl 전체(12,498건)가 아니라 실제 비교 가능한
    (clauses 보유) 브랜드로만 범위를 좁힌다."""
    store_counts = {b["brandMnno"]: b["storeCount"] for b in all_brand_avg_sales()}
    out = []
    for mnno in rag_data.known_brand_mnnos():
        display = rag_data.display_name_for(mnno) or mnno
        out.append({"brandMnno": mnno, "brandNm": display, "storeCount": store_counts.get(mnno)})
    return out


_BRAND_TOKEN_SPLIT_RE = re.compile(r"[\s()&/·\-,]+")


def brand_match_tier(norm_q: str, brand_nm: str) -> "int | None":
    """검색어가 브랜드명 어디에 걸리는지에 따라 1~3등급을 매긴다(등급 낮을수록 우선순위
    높음). 실측: 부분 문자열 매칭만으로 정렬을 가맹점 수에만 맡기면 "지" 한 글자에도
    "지쿠"처럼 이름이 검색어로 시작하는 브랜드보다 "하남돼지집"처럼 검색어가 단어 중간에
    낀 대형 브랜드가 먼저 뜨는 문제가 있었음. 그렇다고 "이름이 검색어로 시작"만 허용하면
    "계림원누릉지통닭구이"를 "누"로 찾는 케이스를 놓치므로, 부분 포함 매칭 자체는 유지하되
    3단계로 나눠 관련성 높은 매칭을 먼저 보여준다.
    1등급: 브랜드명 전체가 검색어로 시작 (지쿠, 지니스…)
    2등급: 공백/괄호/기호로 나눈 단어 중 하나가 검색어로 시작 (예: "계림원 누릉지 통닭구이"
      형태라면 "누"에 2등급)
    3등급: 그 외 어디든 포함 (하남돼지집처럼 단어 중간에 낀 경우 — 그래도 후보에는 남김)
    """
    norm_name = norm_search(brand_nm)
    if norm_q not in norm_name:
        return None
    if norm_name.startswith(norm_q):
        return 1
    tokens = [t for t in _BRAND_TOKEN_SPLIT_RE.split(brand_nm) if t]
    if any(norm_search(t).startswith(norm_q) for t in tokens):
        return 2
    return 3


def _total_amount_won(rows: list[dict]) -> "tuple[int | None, str | None]":
    """total_cost._extract_total_rows()를 재사용해서 "총계/합계" row만 뽑는다.
    완전일치 총계 행이 정확히 1개면 그 금액을, 아니면 None + 사유(note)를 반환한다
    (여러 개면 매장 타입별로 갈려서 단일 값으로 합칠 수 없음 — total_cost.py의
    is_multi 판단과 같은 이유)."""
    totals = [(r, a) for r in rows for a in rag_total_cost._extract_total_rows(r)]
    if not totals:
        return None, "정보 없음"
    if len(totals) > 1:
        return None, "매장 타입/그룹별로 값이 달라 단일 금액으로 표시할 수 없음"
    return totals[0][1]["amount_won"], None


# 평균매출액 row의 column 텍스트에서 "평균매출액"/"평균매출액(상한)"/"평균매출액(3.3㎡당)"
# 같은 짧은 표시용 라벨을 만든다. parse_avg_sales_row()가 store_count/avgSalesAnnual을
# 뽑을 때 쓰는 "상한"/"하한"/"면적" 판별 기준과 동일 — 그 로직을 라벨 생성용으로 재사용.
def _revenue_metric_label(column: "str | None") -> str:
    col = _norm_ws(column)
    is_upper = "상한" in col
    is_lower = "하한" in col
    is_per_area = "면적" in col
    label = "평균매출액"
    qualifiers = []
    if is_upper:
        qualifiers.append("상한")
    elif is_lower:
        qualifiers.append("하한")
    if is_per_area:
        qualifiers.append("3.3㎡당")
    if qualifiers:
        label += f"({', '.join(qualifiers)})"
    return label


def _row_source(row: "dict | None") -> "dict | None":
    """clauses row에서 원문 조각 + 구조화 표(amounts)를 뽑는다. text는 /api/chat의
    _enrich_source()와 같은 800자 절단 규칙을 쓴다 — 숫자만 딱딱 비교해주고 끝나면
    경쟁 서비스(마이프차 등)와 차별점이 없으므로, 숫자를 만든 근거가 된 정보공개서
    원문을 나란히 보여주는 게 이 서비스의 핵심 가치라는 요구사항에 따른 것.
    amounts는 원본 PDF의 표(지역/구분별 금액)가 파싱된 형태 — text는 이 표를 한 줄
    문자열로 펴놓은 것뿐이라, 화면엔 amounts를 표로 우선 보여주고 text는 검증용
    원문으로 보조 노출한다.

    가맹비/보증금/총창업비용 row는 amounts의 label이 이미 짧고 깔끔해서(예: "가맹비",
    "교육비") 그대로 쓴다. 평균매출액 row는 label에 지역명+숫자+헤더 텍스트가 다
    뭉쳐 있어서(원본 표를 한 줄로 펴놓은 부작용) 그대로 쓰면 안 읽힌다 — "전체" 지역
    행만 남기고, label 대신 _revenue_metric_label()로 만든 짧은 라벨을 쓴다."""
    if row is None:
        return None
    text = (row.get("text") or "")[:800]
    if not text:
        return None

    raw_amounts = row.get("amounts") or []
    is_revenue = row.get("category") == "평균매출액"
    if is_revenue:
        raw_amounts = [a for a in raw_amounts if (a.get("label") or "").strip().startswith("전체")]

    amounts = [
        {
            "label": _revenue_metric_label(a.get("column")) if is_revenue else a.get("label"),
            "column": None if is_revenue else a.get("column"),
            "amountWon": a.get("amount_won"),
            "raw": a.get("raw"),
        }
        for a in raw_amounts
    ]
    return {
        "category": row.get("category"),
        "canonicalTitle": row.get("canonical_title"),
        "text": text,
        "amounts": amounts,
    }


def _compare_sources(avg_sales_rows: list[dict], first_fee_rows: list[dict],
                      deposit_rows: list[dict], tc: dict) -> list[dict]:
    """비교표의 각 숫자(평균매출액/최초 가맹금/보증금/총창업비용)를 만든 근거 row의 원문을
    모은다. attr 기준으로 중복 제거한다 — 총창업비용 계산에 쓰인 row(tc["rows"])가 최초
    가맹금/보증금 row와 같은 것일 수 있어서(예치가맹금이 base일 때) 같은 원문이 두 번
    나오지 않게 한다."""
    seen_attrs: set = set()
    sources: list[dict] = []
    for row in [
        avg_sales_rows[0] if avg_sales_rows else None,
        first_fee_rows[0] if first_fee_rows else None,
        deposit_rows[0] if deposit_rows else None,
        *(tc.get("rows") or []),
    ]:
        if row is None:
            continue
        attr = row.get("attr")
        if attr in seen_attrs:
            continue
        source = _row_source(row)
        if source is None:
            continue
        seen_attrs.add(attr)
        sources.append(source)
    return sources


def compare_entry(brand_name: str, brand_mnno: str) -> dict:
    avg_sales = parse_avg_sales_row(brand_mnno)
    avg_sales_rows = rag_retrieval.structured_lookup(brand_mnno, category="평균매출액")

    fee_rows = rag_retrieval.structured_lookup(brand_mnno, category=rag_total_cost.FEE_CATEGORY)
    first_fee_rows = [r for r in fee_rows if r.get("canonical_title") == rag_total_cost.FIRST_FEE_TITLE]
    franchise_fee, fee_note = _total_amount_won(first_fee_rows)

    deposit_rows = rag_retrieval.structured_lookup(brand_mnno, category=rag_total_cost.DEPOSIT_CATEGORY)
    deposit, deposit_note = _total_amount_won(deposit_rows)

    tc = rag_total_cost.compute_total_startup_cost(brand_mnno)
    total_startup_cost = tc["total_won"] if tc.get("mode") == "single" else None
    total_note = None
    if tc.get("mode") == "unavailable":
        total_note = "정보 없음"
    elif tc.get("mode") == "multi":
        total_note = "매장 타입/그룹별로 값이 달라 단일 금액으로 표시할 수 없음"

    notes: dict[str, str] = {}
    if avg_sales["avgSalesAnnual"] is None:
        notes["avgSalesAnnual"] = "정보 없음"
    if fee_note:
        notes["franchiseFee"] = fee_note
    if deposit_note:
        notes["deposit"] = deposit_note
    if total_note:
        notes["totalStartupCost"] = total_note

    return {
        "brandMnno": brand_mnno,
        "brandNm": rag_data.display_name_for(brand_mnno) or brand_name,
        "storeCount": avg_sales["storeCount"],
        "avgSalesAnnual": avg_sales["avgSalesAnnual"],
        "avgSalesPer33": avg_sales["avgSalesPer33"],
        "franchiseFee": franchise_fee,
        "deposit": deposit,
        "totalStartupCost": total_startup_cost,
        "notes": notes,
        "sources": _compare_sources(avg_sales_rows, first_fee_rows, deposit_rows, tc),
    }
