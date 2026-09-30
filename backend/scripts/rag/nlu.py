"""1단계: 의도분류 + 슬롯추출 (LLM 호출 1번, 구조화 출력).

docs/DESIGN.md "RAG 질의응답 아키텍처 설계" 1단계 스펙 그대로: intent/brands(텍스트)/category/
canonical_title을 한 번에 뽑는다. brands는 텍스트 그대로만 뽑고(정규화/ID변환은 0단계
brand_match.py 담당), category/canonical_title은 section_schema의 실제 스키마를 few-shot으로
줘서 우리 스키마 밖 값이 나오지 않게 한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from section_schema import (  # noqa: E402
    SECTION_SCHEMA,
    STRUCTURED_CATEGORIES,
    TOTAL_COST_CATEGORY,
    VECTOR_CATEGORIES,
)

from .llm import call_llm_json

VALID_INTENTS = {"금액조회", "조항검색", "통계조회", "비교", "커버불가"}


def _norm_title(s: str) -> str:
    """canonical_title 비교용 정규화 — 공백 유무 차이만으로 다른 값 취급하지 않기 위함
    (실측 버그: LLM이 "영업 중의 비용 부담(로열티 등)"을 "영업 중의 비용 부담 (로열티 등)"처럼
    괄호 앞에 공백을 하나 더 넣어서 반환 → 기존엔 정확일치 필터라 조용히 0건이 돼버렸음)."""
    return "".join((s or "").split())


_BY_CATEGORY: dict[str, list[str]] = {}
for _category, _canonical_title, _chapter in SECTION_SCHEMA.values():
    _BY_CATEGORY.setdefault(_category, [])
    if _canonical_title not in _BY_CATEGORY[_category]:
        _BY_CATEGORY[_category].append(_canonical_title)
# 정규화된 title -> (그 카테고리의) 정식 title. 카테고리 무관하게 전역으로 찾아도 됨 —
# canonical_title 문구 자체가 카테고리 간에 겹치지 않기 때문.
_NORM_TITLE_LOOKUP = {
    _norm_title(title): title for titles in _BY_CATEGORY.values() for title in titles
}


def _category_hint_text() -> str:
    by_cat = _BY_CATEGORY
    lines = []
    for cat in sorted(by_cat):
        titles = " / ".join(by_cat[cat])
        # 2026-09-14 실측 버그: 여기에 "[구조화조회]" 같은 부가 태그를 category 이름 옆에
        # 붙여뒀더니 모델이 category 값 자체에 그 태그까지 그대로 베껴 써서(예: "보증금
        # [구조화조회]") _validate()에서 무효 처리되는 일이 있었음 — category 줄에는
        # 순수 이름만 두고, 구조화/서술형 구분은 모델이 몰라도 되는 내부 로직(retrieval.py)
        # 이므로 프롬프트에서 아예 뺐다.
        lines.append(f"- {cat}: {titles}")
    # 2026-09-17 (작업로그 (41)): "총창업비용"은 SECTION_SCHEMA의 실제 장(章) 카테고리가
    # 아니라 total_cost.py가 여러 카테고리 합계를 모아 계산하는 합성 카테고리라
    # _BY_CATEGORY(SECTION_SCHEMA 기반)에는 없음 — 여기서 수동으로 한 줄 추가한다.
    # 2026-09-19(라운드3 작업지시 6번): "육시리 창업하는데 총 얼마나 들어?"류 질문이 가끔
    # category=null(intent는 금액조회로 맞게 나와도 category를 못 채움)로 빠져서
    # total_cost.py 전용 계산 대신 일반 벡터서치로 새서 완전히 엉뚱한 숫자(예: 연간 원재료
    # 거래 총액)를 총창업비용인 것처럼 답한 사례가 있었음(지난 OpenAI 테스트 라운드 실측).
    # 구체적인 트리거 표현을 예시로 나열해서 "이런 질문은 이 카테고리다"를 더 명확히 한다.
    lines.append(
        f"- {TOTAL_COST_CATEGORY}: (canonical_title 없음, 초기 투자비용/창업비용 총액을 "
        "물어보는 질문 — 예: \"총 얼마나 들어\", \"초기비용\", \"창업비용\", \"오픈하는데 "
        "돈이 얼마나 들어\", \"초기 투자금\")"
    )
    return "\n".join(lines)


_CATEGORY_HINT = _category_hint_text()

_SYSTEM_PROMPT = f"""너는 프랜차이즈 정보공개서 비교 서비스의 질문 분류기다.
사용자 질문을 보고 아래 JSON 스키마 그대로 답하라. 설명 없이 JSON 객체 하나만 출력한다.

{{
  "intent": "금액조회" | "조항검색" | "통계조회" | "비교" | "커버불가",
  "brands": ["현재 질문에 명시된 브랜드명, 또는 후속 질문에서 대화 문맥으로 복원한 브랜드명"],
  "categories": ["아래 카테고리 목록 중 해당하는 것 전부(순서대로, 1개 이상), 해당 없으면 빈 리스트 []"],
  "canonical_title": "categories가 정확히 1개일 때만 그 category 아래 목록 중 하나로 채운다, 특정 안 되거나 categories가 2개 이상이면 null"
}}

카테고리 목록 (category: canonical_title 후보들):
{_CATEGORY_HINT}

intent 판단 기준:
- "금액조회": 특정 금액/숫자를 물어봄 (가맹비/가맹금, 보증금, 교육비, 로열티, 평균매출액 등 구조화조회 카테고리,
  또는 "초기 창업비용/총 얼마 드나" 같은 총창업비용 질문)
- "통계조회": 행정처분/법위반 이력의 유무나 건수처럼 카운트/여부성 질문 (행정처분 카테고리)
- "조항검색": 계약해지 조건, 영업지역, 필수구입물품, 손해배상 조건, 소송이력 등 서술형 내용을 물어봄
- "비교": 브랜드가 2개 이상이고 서로 비교해달라는 질문 (categories/canonical_title은 비교 축을 그대로 채움)
- "커버불가": 위 카테고리 어디에도 안 맞는 질문(상권정보, 분쟁조정, 법률 자문, 추천 등)

규칙:
- messages의 마지막 user 메시지가 현재 질문이고, 그 앞의 user/assistant 메시지는 현재 질문에서 생략된
  의미를 복원하기 위한 대화 문맥이다.
- 현재 질문에 브랜드명이 명시되어 있으면 이전 대화의 브랜드보다 현재 질문의 브랜드를 우선하고,
  현재 질문에 적힌 브랜드만 brands에 넣는다.
- 현재 질문에 브랜드명이 없지만 "그럼", "그러면", "그 브랜드는", "보증금은?", "계약해지 조건은?"
  같이 직전 대화를 이어가는 후속 질문이면, 가장 최근의 관련 대화에서 명시적으로 확인된 브랜드명을
  brands에 복원한다.
- 문맥에서 브랜드를 복원할 때는 가장 최근 관련 user 질문에서 사용자가 쓴 브랜드 표현을 그대로 사용한다.
  줄이거나(예: "파파존스피자"->"파파존스") 한자/다른 표기로 바꾸지 말고 띄어쓰기까지 유지한다.
- 현재 질문에 새로운 브랜드가 명시되어 있으면 이전 브랜드를 함께 넣지 않는다.
  예: 이전 대화가 "피자스쿨 가맹비 얼마야?"이고 현재 질문이 "GS25는?"이면 brands는 ["GS25"]다.
- 현재 질문이 독립적인 질문이고 브랜드도 없으며 이전 대화를 이어가는 표현도 아니라면 brands는 빈 리스트로 둔다.
- **질문 하나에 카테고리가 여러 개 언급되면(예: "필수구매목록이랑 월매출 비교해줘" -> 필수구입물품 +
  평균매출액) 하나만 고르지 말고 categories에 언급된 것을 전부 담아라.** 보통은 카테고리가 1개뿐인
  질문이 대부분이므로 그때는 categories에 1개만 담으면 된다.
- categories가 애매하면 가장 가까운 것을 고르되, 정말 대응이 안 되면 빈 리스트로 두고 intent를
  "커버불가"로 한다.
- **"창업비용/초기비용/총 얼마 드나"류로 여러 항목을 합친 총액을 물어보는 질문은 반드시
  categories에 "총창업비용"을 채워라 — 빈 리스트로 남기지 마라.** 이걸 비워두면 엉뚱한
  검색 결과가 나온다(예: 창업비용 대신 원재료 거래 총액 같은 무관한 숫자를 답하게 됨).
"""


def extract_slots(
    question: str,
    conversation_context: "list[dict[str, str]] | None" = None,
) -> dict:
    """LLM으로 intent/brands/categories/canonical_title을 뽑는다. 실패 시(LLM 오류/JSON 파싱
    실패) LLMError를 그대로 올린다 — pipeline이 이걸 보고 사용자에게 "질문을 이해하지 못했다"고
    정직하게 답하게 한다(추측 금지 원칙과 동일).

    2026-09-20(라운드4 작업지시 5번): category(단일 문자열/null)를 categories(리스트)로
    바꿨다 — "필수구매목록이랑 월매출 비교해줘"처럼 한 질문에 카테고리가 2개 이상 있으면
    예전엔 LLM이 하나만 고르고 나머지는 슬롯에 담기지도 않은 채 조용히 사라졌음(사용자에게
    "데이터 없음" 안내조차 없었음 — 조용한 누락은 이 프로젝트의 "추측/누락 없이 정직하게"
    원칙에 어긋남). canonical_title은 categories가 정확히 1개일 때만 유효하게 둔다(카테고리가
    여러 개면 canonical_title이 어느 카테고리 소속인지 애매해지므로 단순화 — pipeline.py가
    카테고리별로 반복 호출할 때 canonical_title 없이 category 레벨로만 조회한다)."""
    if conversation_context is None:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
    else:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            *conversation_context,
        ]

    result = call_llm_json(messages)
    return _validate(result)


_VALID_CATEGORIES = STRUCTURED_CATEGORIES | VECTOR_CATEGORIES | {TOTAL_COST_CATEGORY}


def _validate(result: dict) -> dict:
    intent = result.get("intent")
    if intent not in VALID_INTENTS:
        intent = "커버불가"

    brands = result.get("brands") or []
    if not isinstance(brands, list):
        brands = []
    brands = [b for b in brands if isinstance(b, str) and b.strip()]

    # 2026-09-20(라운드4 작업지시 5번): 리스트로 받되, 모델이 예전 스키마 습관대로
    # "category"(단일 문자열)를 반환하는 경우도 하위호환으로 리스트에 감싸서 받는다
    # (프롬프트를 아무리 명확히 해도 로컬 LLM이 예전 필드명을 쓸 가능성을 배제 못 함 —
    # 실제로 이런 폴백이 없으면 이 경우 카테고리가 통째로 유실된다).
    raw_categories = result.get("categories")
    if not isinstance(raw_categories, list):
        single = result.get("category")
        raw_categories = [single] if isinstance(single, str) and single.strip() else []
    categories: list[str] = []
    for c in raw_categories:
        if isinstance(c, str) and c in _VALID_CATEGORIES and c not in categories:
            categories.append(c)

    raw_title = result.get("canonical_title")
    canonical_title = None
    if isinstance(raw_title, str) and raw_title.strip():
        snapped = _NORM_TITLE_LOOKUP.get(_norm_title(raw_title))
        if snapped is None:
            pass  # 스키마에 없는 title -> canonical_title 없이 category 레벨로 폴백(전부 보여줌)
        elif not categories:
            # category를 안 뽑았어도 title로 역추정 가능하면 채워준다(1개짜리 categories로 확정).
            canonical_title = snapped
            for cat, titles in _BY_CATEGORY.items():
                if snapped in titles:
                    categories = [cat]
                    break
        elif len(categories) == 1 and snapped in _BY_CATEGORY.get(categories[0], []):
            canonical_title = snapped
        # else: categories가 2개 이상이거나 title이 categories랑 안 맞음(모델이 잘못 조합)
        # -> title 버리고 categories만 신뢰(카테고리가 여러 개면 canonical_title 단순화 원칙).

    return {
        "intent": intent,
        "brands": brands,
        "categories": categories,
        "canonical_title": canonical_title,
    }
