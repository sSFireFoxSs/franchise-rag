"""4단계 확장: "총창업비용" 합성 카테고리(작업로그 (41)).

section_schema.py의 실제 장(章) 카테고리가 아니라, 이 모듈이 여러 카테고리(최초 가맹금/
그 밖에 지급하여야 하는 비용/예치가맹금 또는 보증금)의 "합계"만 모아서 초기 창업비용
총액을 계산해서 보여주는 합성 카테고리다. retrieval.py의 구조화조회를 그대로 재사용하고,
숫자는 여기서 그대로 꺼내 쓸 뿐 새로 계산하거나 LLM이 재생성하지 않는다(docs/DESIGN.md 4단계
원칙과 동일).

실측 근거(반드시 이대로 지킬 것 — 부분 포함(in) 매칭 대신 완전일치만 인정):
- 라벨에 "계" 글자가 포함되면 합계로 간주하는 방식은 위험함을 실측으로 확인함(128가지
  라벨이 "계"를 포함했는데 대부분 "가맹비 계약 체결과 동시 지급..." 같은 무관한 문구였음).
  공백을 제거한 라벨 전체가 TOTAL_LABELS_NORM과 완전히 일치할 때만 합계로 인정한다.
- (2026-09-17, 사용자 지적으로 발견해서 정정한 버그) 처음엔 "예치가맹금과 별도 보증금
  숫자가 자주 겹치니 둘 중 하나만 보증금 몫으로 쓰고, 최초 가맹금은 항상 별도로 더한다"는
  공식으로 짰었는데, 이게 **이중계산 버그**였음. 실측 확인: "예치가맹금의 범위와 그 금액"은
  최초 가맹금과 별도로 추가되는 금액이 아니라, **최초 가맹금(가입비+교육비)에 보증금
  성격의 금액을 더해서 다시 계산한 값**이다(비비큐 BSK: 최초가맹금 9,680,000원=가입비
  5,500,000+교육비4,180,000, 예치가맹금 14,180,000원=가입비+교육비+계약이행보증금
  5,000,000으로 정확히 일치. 백청우칼국수: 최초가맹금16,500,000+보증금5,000,000=
  예치가맹금21,500,000으로 정확히 일치). 그래서 최초 가맹금+그 밖의 비용+예치가맹금을
  셋 다 더하면 가입비/교육비를 두 번 세는 버그가 생긴다. 올바른 공식:
  - 예치가맹금 데이터가 있으면: 총창업비용 = **예치가맹금 합계 + 그 밖의 비용 합계**만
    쓴다(최초 가맹금은 이미 예치가맹금에 포함돼 있으므로 breakdown/components에도 아예
    안 보여준다 — 같이 보여주면 사용자가 직접 더해서 이중계산할 위험이 있음).
  - 예치가맹금 데이터가 없을 때만(2026-09-17 실측: 2,418개 브랜드 중 39개, 1.6%): 총창업
    비용 = 최초 가맹금 합계 + (있으면) 별도 보증금 카테고리 합계 + 그 밖의 비용 합계.
- "교육비" 카테고리(교육ㆍ훈련의 최소시간 및 비용)는 최초 가맹금에 이미 포함된 교육비
  구성요소와 거의 같은 숫자라 총창업비용 계산에 포함하지 않는다(이미 최초 가맹금 합계
  안에 들어있다고 봄).
- 매장 타입/평수가 여러 개인 브랜드(예: 비비큐 BSK/올리브치킨 등 6타입)는 최초 가맹금
  표의 타입 이름과 "그 밖에 지급하여야 하는 비용" 표의 그룹 이름이 표기 방식이 달라서
  자동으로 정확히 매칭시키기 어렵다 — 억지로 하나의 총액으로 합치지 않고 타입별/그룹별
  합계를 각각 따로 보여준다. 최초 가맹금/그 밖의 비용/보증금 각각의 완전일치 합계 행이
  정확히 1개씩만 있는(타입 분기가 없는) 브랜드만 셋을 안전하게 더해 단일 총액을 보여준다.
- (2026-09-17, 구현 중 실측으로 발견해서 추가한 보정) "그 밖에 지급하여야 하는 비용"
  섹션은 그룹마다 "총계"가 절대금액("금액" 컬럼)과 "면적 3.3㎡당 금액"(단가) 두 줄로
  나오는 경우가 흔함(예: 핸델앤그레텔) — 라벨만 완전일치로 걸러내면 이 단가 줄까지
  "또 다른 합계"로 오인해서 타입이 하나뿐인 브랜드도 "multi"로 잘못 분류하는 버그가
  있었음. 컬럼/표 구분 텍스트에 "면적"이 들어간 항목은 절대금액이 아니므로 제외한다.
  같은 이유로 "지급기한"/"비고" 같은 절차성 컬럼에 금액이 그대로 복제되어 실제로는
  하나뿐인 항목이 여러 개로 보이는 추출 아티팩트도 있어서(실측: 특정 브랜드의 "최초
  가맹금" 표에서 33,000,000원이 "금액"/"지급기한"/"비고" 3개 컬럼에 걸쳐 그대로
  복제됨), 03_extract_clauses.py가 label 조립 때 이미 쓰던 것과 같은 컬럼 판별 로직
  (_LABEL_EXCLUDE_HEADER_RE, 작업로그 (32))으로 이런 절차 컬럼을 그룹에서 제외한다.
  (처음엔 "같은 금액이 중복되면 버린다"는 값 기준 중복 제거로 방어했었는데, 이게
  비비큐처럼 서로 다른 매장 타입 6개 중 5개가 우연히 정확히 같은 금액(15,180,000원)인
  **진짜** 멀티 타입 케이스까지 하나로 뭉개버리는 회귀를 실측으로 발견해서 컬럼 판별
  방식으로 교체함 — 값이 같다고 같은 항목인 게 아님.)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from . import retrieval

FIRST_FEE_TITLE = "최초 가맹금"
OTHER_COST_TITLE = "그 밖에 지급하여야 하는 비용"
DEPOSIT_FEE_TITLE = "예치가맹금의 범위와 그 금액"  # 가맹비/가맹금 카테고리 소속
FEE_CATEGORY = "가맹비/가맹금"
DEPOSIT_CATEGORY = "보증금"

TOTAL_LABELS = {"총계", "총 계", "합계", "합 계", "합계액", "합 계 액", "[합계]", "[ 합계 ]"}


def _norm_label(s: "str | None") -> str:
    return "".join((s or "").split())


TOTAL_LABELS_NORM = {_norm_label(x) for x in TOTAL_LABELS}


def _is_area_metric(a: dict) -> bool:
    """"면적 3.3㎡당 금액"처럼 절대금액이 아니라 단가(면적당)인 항목인지 판단한다(위
    docstring 참고, 2026-09-17 구현 중 실측으로 발견). column/table_context 어디든
    "면적"이 들어있으면 절대 총액이 아니므로 제외."""
    return "면적" in (a.get("column") or "") or "면적" in (a.get("table_context") or "")


# 03_extract_clauses.py의 _LABEL_EXCLUDE_HEADER_RE/_is_identifying_header()와 동일한
# 패턴(작업로그 (32) 참고) — "지급기한"/"비고" 같은 절차·안내성 컬럼을 그룹으로 안 친다.
_NON_GROUP_COLUMN_RE = re.compile(r"지급|반환|귀책|조건|사유|기한|여부|대상|방법|시기|참고|비고")


def _is_procedural_column(a: dict) -> bool:
    compact = "".join((a.get("column") or "").split())
    return bool(_NON_GROUP_COLUMN_RE.search(compact))


def _extract_total_rows(row: dict) -> list[dict]:
    """row['amounts']에서 라벨이 TOTAL_LABELS_NORM과 완전일치하는 것만 반환한다.
    부분 포함(in) 매칭 금지 — 실측 근거는 모듈 docstring 참고. 면적당 단가 항목과
    지급기한/비고 같은 절차성 컬럼(모듈 docstring의 추출 아티팩트 설명 참고)은 제외한다."""
    out = []
    for a in row.get("amounts") or []:
        won = a.get("amount_won")
        if won is None:
            continue
        if _norm_label(a.get("label")) not in TOTAL_LABELS_NORM:
            continue
        if _is_area_metric(a):
            continue
        if _is_procedural_column(a):
            continue
        out.append(a)
    return out


# 2026-09-19(라운드2 작업지시 4번): "육시리 창업하는데 총 얼마나 들어?" -> 단일 총액만
# 나오고 어떤 면적(평수) 기준인지 안 보이는 문제. 실측(육시리 BRD_20170216)해보니 "그 밖에
# 지급하여야 하는 비용" 섹션의 표 캡션 문단(row["text"])에 "※ 40 평기준(1평=3.3㎡)"처럼
# 면적 기준이 적혀있음 — table_context/column에는 없고 자유 서술 text에만 있어서 별도로
# 찾아야 한다. multi 모드(비비큐 등)는 매장 타입별 table_context 자체가 이미 "8평 기준"
# 같은 문구를 포함해서 _format_total_cost_multi()가 그대로 보여주므로 손 안 댐 — single
# 모드에서만 breakdown에 안 보이던 것.
_AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*평(?:\s*기준)?")


def find_area_note(rows: list[dict]) -> "str | None":
    """총창업비용 계산에 쓰인 기준 면적을 원문에서 찾는다. 원문에 실제로 면적 기준
    문구가 있을 때만 반환하고, 없으면 억지로 만들지 않고 None을 반환한다(작업 지시 4번
    — "기준 면적 정보 자체가 없는 브랜드는 억지로 만들지 말고 생략")."""
    for row in rows:
        for a in row.get("amounts") or []:
            ctx = a.get("table_context")
            if ctx:
                m = _AREA_RE.search(ctx)
                if m:
                    return f"{m.group(1)}평 기준"
        m = _AREA_RE.search(row.get("text") or "")
        if m:
            return f"{m.group(1)}평 기준"
    return None


def _group_label(a: dict) -> str:
    """multi 모드에서 보여줄 그룹/타입 구분 라벨. "최초 가맹금"류는 표가 1개라 컬럼명
    (예: "타입별 금액 BSK")에 그룹명이 들어있고, "그 밖에 지급하여야 하는 비용"류는
    표가 여러 개라 table_context(예: "(가) BSK ...")에 그룹명이 들어있다(작업로그 (30)).
    표 구조가 다르면 이 필드 우선순위도 달라지므로 어느 쪽이든 값이 있는 걸 쓴다."""
    return a.get("table_context") or a.get("column") or ""


# 2026-09-19(라운드3 작업지시 2번): "BSK기준으로만 계산해줘"처럼 mode="multi"인 브랜드의
# 특정 매장 타입 하나만 골라서 계산해달라는 요청 — 라벨/컬럼명에서 "단위"/"금액"/평수
# 같은 보일러플레이트를 뺀 실제 타입 이름 토큰만 뽑는다. pipeline.py가 이 토큰들을 질문
# 문장과 대조해서 정확히 하나만 겹치면 type_filter로 넘긴다(_detect_type_filter 참고).
_TYPE_TOKEN_STOPWORDS = {"단위", "타입별", "금액", "기준", "포함", "부가세", "vat", "면적", "당", "구분"}
_TYPE_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")


def extract_type_tokens(label: "str | None") -> set:
    """라벨(예: "타입별 금액 BSK", "(가) BSK (단위: 천원, VAT 포함, 8평 기준)")에서 실제
    매장 타입 이름으로 보이는 토큰만 뽑는다. 숫자만/평수/보일러플레이트 단어는 제외한다."""
    out = set()
    for t in _TYPE_TOKEN_RE.findall(label or ""):
        if len(t) < 2 or t.lower() in _TYPE_TOKEN_STOPWORDS:
            continue
        if re.fullmatch(r"\d+평?", t):
            continue
        out.add(t)
    return out


def compute_total_startup_cost(brand_mnno: str, type_filter: "str | None" = None) -> dict:
    """반환값:
    - {"mode": "unavailable"}: base(예치가맹금 또는 최초 가맹금) 합계 자체를 못 찾음
      (완전일치 라벨 없음, 또는 type_filter와 일치하는 타입이 없음).
    - {"mode": "single", "total_won": int, "breakdown": [{"label":.., "amount_won":..}, ...],
       "rows": [clause row, ...]}: 타입 분기가 없어 안전하게 합산 가능(또는 type_filter로
       정확히 하나의 타입만 골라져서 안전하게 합산 가능해진 경우).
    - {"mode": "multi", "components": {"예치가맹금의 범위와 그 금액": [{"column":..,
       "amount_won":..}, ...], ...}, "rows": [clause row, ...]}: 매장 타입/그룹이 여러
       개라 억지로 합치지 않음.
    "교육비" 카테고리는 최초 가맹금(또는 예치가맹금)에 이미 포함된 것으로 보고 의도적으로
    제외한다. "예치가맹금"이 있으면 그게 이미 "최초 가맹금+보증금"을 합쳐 다시 계산한
    값이므로(모듈 docstring 참고, 2026-09-17 버그 수정) base로 예치가맹금만 쓰고 최초
    가맹금/별도 보증금은 더하지도 보여주지도 않는다. 예치가맹금이 없을 때만 최초 가맹금을
    base로 쓰고, 있으면 별도 보증금 카테고리를 추가로 더한다.

    2026-09-19(라운드3 작업지시 2번): type_filter가 주어지면(예: "BSK") 그룹 라벨
    (_group_label)에 그 문자열이 대소문자 구분 없이 부분 포함된 항목만 남긴다 — 정확히
    1개만 남으면 자연스럽게 mode="single"이 되어 그 타입 하나만의 총액을 안전하게
    보여줄 수 있다(억지로 새로 계산하지 않고 기존 필터링 로직을 그대로 재사용)."""
    fee_rows = retrieval.structured_lookup(brand_mnno, category=FEE_CATEGORY)
    deposit_rows = retrieval.structured_lookup(brand_mnno, category=DEPOSIT_CATEGORY)

    first_fee_rows = [r for r in fee_rows if r.get("canonical_title") == FIRST_FEE_TITLE]
    other_cost_rows = [r for r in fee_rows if r.get("canonical_title") == OTHER_COST_TITLE]
    deposit_fee_rows = [r for r in fee_rows if r.get("canonical_title") == DEPOSIT_FEE_TITLE]

    first_fee_totals = [(r, a) for r in first_fee_rows for a in _extract_total_rows(r)]
    other_cost_totals = [(r, a) for r in other_cost_rows for a in _extract_total_rows(r)]
    deposit_fee_totals = [(r, a) for r in deposit_fee_rows for a in _extract_total_rows(r)]
    deposit_cat_totals = [(r, a) for r in deposit_rows for a in _extract_total_rows(r)]

    if type_filter:
        needle = type_filter.lower()
        def _matches(pair):
            return needle in _group_label(pair[1]).lower()
        first_fee_totals = [p for p in first_fee_totals if _matches(p)]
        other_cost_totals = [p for p in other_cost_totals if _matches(p)]
        deposit_fee_totals = [p for p in deposit_fee_totals if _matches(p)]
        deposit_cat_totals = [p for p in deposit_cat_totals if _matches(p)]

    if deposit_fee_totals:
        # 예치가맹금 = 최초 가맹금(가입비+교육비) + 보증금 성격 금액을 합쳐 다시 계산한
        # 값이므로(모듈 docstring 실측 근거) base는 예치가맹금 하나만 쓴다 — 최초 가맹금과
        # 별도 보증금은 이미 포함돼 있어 더하지 않고, 이중계산 오해를 막기 위해 breakdown/
        # components에도 아예 안 보여준다.
        base_label = DEPOSIT_FEE_TITLE
        base_totals = deposit_fee_totals
        extra_deposit_totals: list = []
    elif first_fee_totals:
        base_label = FIRST_FEE_TITLE
        base_totals = first_fee_totals
        extra_deposit_totals = deposit_cat_totals
    else:
        return {"mode": "unavailable"}

    is_multi = len(base_totals) > 1 or len(other_cost_totals) > 1 or len(extra_deposit_totals) > 1
    # 매장 타입이 여러 개면 같은 row 하나에 "총계" 항목이 여러 개 들어있어서(예: 비비큐의
    # "예치가맹금" row 하나에 타입별 총계가 6개) 그대로 나열하면 같은 row가 여러 번 겹친다
    # — attr 기준(한 브랜드 안에서 canonical_title당 사실상 유일, data.py의 find_row()와
    # 같은 전제)으로 중복 제거해서 citation이 중복되지 않게 한다.
    all_rows = []
    seen_attrs: set = set()
    for r, _ in base_totals + other_cost_totals + extra_deposit_totals:
        attr = r.get("attr")
        if attr in seen_attrs:
            continue
        seen_attrs.add(attr)
        all_rows.append(r)

    if is_multi:
        components = {
            base_label: [{"column": _group_label(a), "amount_won": a["amount_won"]} for _, a in base_totals],
        }
        if other_cost_totals:
            components[OTHER_COST_TITLE] = [
                {"column": _group_label(a), "amount_won": a["amount_won"]} for _, a in other_cost_totals
            ]
        if extra_deposit_totals:
            components[DEPOSIT_CATEGORY] = [
                {"column": _group_label(a), "amount_won": a["amount_won"]} for _, a in extra_deposit_totals
            ]
        return {"mode": "multi", "components": components, "rows": all_rows}

    breakdown = [{"label": base_label, "amount_won": base_totals[0][1]["amount_won"]}]
    total = base_totals[0][1]["amount_won"]
    if other_cost_totals:
        breakdown.append({"label": OTHER_COST_TITLE, "amount_won": other_cost_totals[0][1]["amount_won"]})
        total += other_cost_totals[0][1]["amount_won"]
    if extra_deposit_totals:
        breakdown.append({"label": DEPOSIT_CATEGORY, "amount_won": extra_deposit_totals[0][1]["amount_won"]})
        total += extra_deposit_totals[0][1]["amount_won"]

    return {
        "mode": "single", "total_won": total, "breakdown": breakdown, "rows": all_rows,
        "area_note": find_area_note(all_rows),
    }
