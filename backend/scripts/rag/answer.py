"""4단계: 답변 조립.

구조화 값(금액/violation_flag)은 LLM이 재생성하지 않고 데이터에서 꺼낸 그대로 문장/표에
꽂는다(환각 방지, docs/DESIGN.md 4단계 원칙). 서술형 답변만 LLM이 검색된 원문을 근거로 비교/요약
문장을 만들되, 문장마다 출처 태그를 달고 추측·추천·법률판단은 금지한다.

2026-09-15 (작업로그 (32)): "금액조회"(구조화조회) 경로에도 LLM 설명 문장을 붙이되, 아래
순서를 반드시 지킨다(retrieval.py의 structured_lookup() 주석과 같은 원칙 — 숫자 환각 방지):
  1. 그룹핑/합산은 전부 코드(group_amounts())가 결정론적으로 먼저 한다 — LLM한테 안 시킨다.
  2. 그렇게 정리된 요약만 LLM에게 컨텍스트로 주고 자연스러운 한국어 설명을 생성하게 한다
     (generate_grouped_narrative(), call_llm_json 재사용).
  3. LLM 출력에 나온 모든 금액을 파싱해서(_extract_amounts_from_text) 원본 amounts에 실제
     존재하는 값인지 전부 대조한다(_verify_numbers). 하나라도 없는 숫자가 나오면 LLM 생성
     답변을 버리고 format_grouped_fallback()의 결정론적 문장으로 폴백한다.

2026-09-15 (작업로그 (34)): 서술형(assemble_narrative_answer) 경로에도 아래 두 가지를 추가함
("핸델앤그레텔/종로김밥 필수구입물품" 실사용 테스트에서 발견된 문제 — 03_extract_clauses.py가
표 내용을 text 필드에서 빼고 저장하는데(작업로그 (23), 용량 절감 목적) 서술형 경로가 text만
컨텍스트로 썼어서, 답이 표(품목 리스트 등)로만 되어 있는 조항은 구조적으로 안 보였음):
  1. 각 hit마다 data.find_row()로 원본 row(표/금액 포함)를 다시 가져와서 [표 원본]/[금액]
     블록으로 컨텍스트에 추가한다. 여기서도 "숫자는 원문 그대로만" 원칙이 적용되므로,
     구조화 경로의 _extract_amounts_from_text/_verify_numbers를 재사용해 LLM 생성 텍스트의
     금액을 컨텍스트에 실제 존재하는 값과 전부 대조하고, 대조 실패 시(구조화처럼 깔끔한
     폴백 템플릿이 없어서) 결정론적 폴백 대신 캐비엇을 덧붙인다.
  2. attachment_refs(별첨/별지 참조, app.py의 render_attachment_note()가 쓰던 것과 같은 필드)가
     있는 hit이 있으면, LLM 호출과 무관하게 코드가 결정론적으로 안내 문구를 답변 끝에 붙인다.

2026-09-15 (작업로그 (35)): (34) 직후 실사용 테스트에서 추가로 발견된 문제 3개 수정:
  1. 표 컨텍스트를 넣기 시작하면서 LLM이 질문에 직접 답하지 않고 "품목별 상세내역/가격
     변동분석/총괄요약" 같은 보고서 형식으로 답하거나, "가장 최신/일관된 값 기준으로
     정리했습니다"처럼 원문에 없는 선별 근거를 스스로 지어내는 현상이 있었음. 원인은
     프롬프트만이 아니라 `_format_amounts_for_context()`가 무제한이라(표 항목이 100개
     넘으면 [금액] 블록 하나가 [표 원본]보다 훨씬 큰 데이터 뭉치가 됨) 컨텍스트가 실질적으로
     안 줄어들고 있었던 것 — 두 헬퍼 다 20개/1200자로 제한, 프롬프트도 "곧바로 답변/메타
     코멘트 금지/스스로 선별 금지" 규칙을 강화. 부가로 컨텍스트를 줄였는데도 답변이 문장
     중간에 잘리는 현상(done_reason="length")을 발견해서 llm.py의 ollama 호출에
     `num_ctx`(기본 8192, config.OLLAMA_NUM_CTX)를 명시 추가(기존엔 모델 기본 컨텍스트 윈도가
     작아서 프롬프트만으로 거의 다 차 있었음).
  2. `_verify_numbers()` 검증이 amounts(표 셀)에만 있는 금액만 valid로 쳐서, text(산문)에
     문장으로 박힌 금액("위약벌 1,000만원" 등)을 LLM이 원문 그대로 인용해도 false positive로
     캐비엇이 붙던 문제 — hit_text([:800]로 자른 것, LLM이 실제로 본 부분)에서도
     _extract_amounts_from_text()로 금액을 뽑아 valid_amounts에 합쳐서 해결.
  3. build_citation()의 brandNm이 franchise.ftc.go.kr 응답 자체 결손("?" 섞임, 2,441개 중
     5건 실측)을 그대로 노출하던 문제 — section_schema.pick_display_name()으로 정적
     brandNm 폴백(app.py/data.py의 같은 로직도 이 헬퍼로 통일).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from section_schema import pick_display_name  # noqa: E402

from . import data
from .llm import LLMError, call_llm, call_llm_json

_NARRATIVE_SYSTEM_PROMPT = """너는 프랜차이즈 정보공개서 조항을 비교해서 설명해주는 assistant다.
아래에 브랜드별로 검색된 조항 원문(출처 포함, 표 원본/금액 포함)이 주어진다. 반드시 이 원문
안에 있는 내용만 근거로 답하고, 원문에 없는 내용은 추측하지 마라.

규칙:
- **질문에 곧바로 자연스러운 문장으로 답해라.** "품목별 상세 내역", "가격 변동 분석", "총괄
  요약"처럼 챕터로 나눈 보고서 형식으로 답하지 마라. 브랜드당 3~5문장 이내로 핵심만 말해라.
- 표에 항목이 많으면 전부 나열하지 말고 대표적인 것 몇 개만 언급한 뒤 "더 자세한 내용은 출처를
  확인하라"는 식으로 짧게 안내해라.
- **데이터를 어떻게 가공했는지 설명하는 메타 코멘트를 쓰지 마라.** "~로 나누어 정리해드립니다",
  "~를 기준으로 정리했습니다" 같은 문구는 금지다 — 질문에 대한 답만 해라.
- 표에 같은 항목이 여러 번 나오거나 값이 겹쳐 보여도, "최신"이나 "일관된" 값을 네가 판단해서
  골라내지 마라. 그런 선별 기준이 원문에 없으면 그건 추측이다. 있는 그대로 전달하거나, 판단이
  필요한 상황이면 판단하지 말고 원문에 나온 사실만 그대로 전달해라.
- **답변 문장 안에 [브랜드명-카테고리-조항명] 형식의 출처 태그를 직접 쓰지 마라.** 출처는
  화면에 별도의 칩(버튼)으로 이미 표시되므로 본문에 또 적으면 중복이다("[표 원본]"/"[금액]"도
  컨텍스트 라벨일 뿐이니 그대로 옮겨 적지 마라 — 어떤 대괄호 태그든 답변 문장 안에는 넣지 마라).
- 특정 브랜드에 대해 검색된 원문이 없으면 "OO 브랜드는 관련 정보가 없습니다"라고 명시한다(추측 금지).
- 추천, 법률 자문, "~하는 게 좋다"류의 판단성 결론은 내리지 않는다. 조항 내용을 있는 그대로 설명만 한다.
- 숫자(금액 등)는 원문에 나온 그대로만 언급하고, 계산하거나 새로 만들어내지 않는다. 이 규칙은
  본문 텍스트뿐 아니라 "[표 원본]"/"[금액]"으로 표시된 표 데이터에서 나온 숫자에도 동일하게
  적용된다 — 표에 있는 숫자도 반올림/합산/재계산하지 말고 그대로만 옮겨 적어라.
- **금액은 항상 아라비아 숫자와 쉼표로만 표기해라(예: "730,953,000원").** "칠억 삼천만원"/
  "7억 3천만원"처럼 한글로 읽어서 쓰거나 숫자와 한글을 섞어 쓰지 마라 — 원문 숫자를 자릿수
  그대로, 한 글자도 바꾸지 않고 옮겨 적어라.
- **마크다운 문단 구분을 써라.** 브랜드가 여러 개면 브랜드마다 빈 줄로 문단을 나눠라. 한
  브랜드 안에서도 서로 성격이 다른 내용(예: 조건 설명과 예외 사항)이 이어지면 한 덩어리로
  붙여 쓰지 말고 문장 사이에 줄바꿈을 넣어라 — 모든 문장과 출처 태그를 한 문단에 다 이어
  붙이지 마라.

답변 구조(대화체로 써라 — "~를 명시하고 있습니다. 따라서 ~"류의 딱딱한 보고서체 금지):
1. 먼저 맥락을 한 줄로 짧게 잡는다(예: 이 브랜드도 다른 곳과 비슷한 구조인지 등).
2. 핵심 사실을 bullet로 짧게 나열한다(위 "3~5문장" 규칙은 산문 강제가 아니라 "장황하지
   않게"라는 뜻이니, bullet로 나눠 써도 된다). 중요한 단어는 **굵게** 강조해도 된다.
3. 검색된 원문에 없는 부분은 숨기지 말고 정직하게 명시한다 — "이 부분은 별첨/영업비밀이라
   여기서는 확인이 안 되고 본사에 직접 문의해야 합니다"처럼.
4. **질문이 예/아니오나 있음/없음으로 답할 수 있는 형태면, 마지막에 사용자의 질문을 그대로
   인용하면서 직접적인 결론을 한 줄로 재확인해라.** 예: "정리하면, '필수 구매 목록이
   있는지'에는 네, 있어요 — 다만 품목별 구체적 가격까지는 여기서 확인이 어렵고 본사 문의가
   필요해요." **이 결론 한 줄은 항상 사실(수치·존재 여부)에 대한 진술이어야 한다** — 여러
   브랜드를 비교하는 답변에서 "~가 더 유리하다/낫다"처럼 우열을 판단하는 문장으로 흘러가면
   절대 안 된다(위 추천·판단 금지 규칙과 동일). 각 브랜드는 각자의 사실만 결론짓고, 브랜드
   간 비교 판단 문장은 만들지 마라.

**간결함**: 화면 옆에 원문(정보공개서 페이지)이 항상 같이 표시되므로, 본문 답변이 원문 문구나
표 내용을 문장으로 길게 재서술/재인용할 필요는 없다. 결론과 핵심 숫자만 명확히 제시하고, 세부
근거 확인은 옆의 원문 표시에 맡겨라. 단, Ⅴ장 계약조항(해지사유·위약금·필수구매물품 등)처럼
조건의 정확한 표현 자체가 중요한 항목은 조건 문구나 숫자를 흐리게 패러프레이즈하지 말고 정확히
명시하되, 그 조건을 둘러싼 설명 문장만 줄여라.

**질문에서 구체적으로 언급한 항목(예: 식자재비, 원재료비, 인건비 등)이 검색된 원문에 전혀
나오지 않으면, 있는 내용만 설명하고 조용히 끝내지 마라** — 그 항목은 정보공개서 공개 대상이
아니라 이 데이터에 포함되어 있지 않다고 명시적으로 안내해라(추측해서 만들어내지 않는다는
원칙과 동일하게, "없다"는 사실 자체를 정직하게 말하는 것이다).
"""

_STRUCTURED_NARRATIVE_SYSTEM_PROMPT = """너는 프랜차이즈 정보공개서의 금액 정보를 자연스러운
한국어 문장으로 설명해주는 assistant다. 사용자의 원래 질문과, 그 질문에 대해 코드가 이미
조회해 둔 "그룹별 금액 목록"이 JSON으로 주어진다. 이 숫자들은 전부 검증이 끝난 사실이다 —
절대 새로 계산하거나, 반올림하거나, 합계를 내거나, 다른 숫자로 바꾸지 마라. 주어진 숫자를
그대로 옮겨 적기만 해라.

규칙:
- 반드시 JSON 객체 하나로만 응답한다: {"description": "..."}
- **질문이 실제로 묻는 핵심 수치 위주로 1~2문장 이내로 간결하게 답해라.** 질문이 특정
  지역/매장타입/상한·하한 등을 콕 집어 묻지 않았다면, 대표값(전체/합계로 보이는 그룹)
  위주로만 답하고 나머지 세부 그룹(지역별/타입별 값 등)은 "그 외 지역/매장 유형별 값은
  출처를 참고하라"는 식으로 짧게만 안내해라 — 입력에 그룹이 여러 개 있다고 전부 하나하나
  나열하지 마라.
- **질문이 쓴 표현(예: "월매출")과 실제 항목명(예: "연간 평균 매출액")이 다르면, 그 차이를
  짧게 짚어줘라.** 데이터에 없는 걸 있는 것처럼 답하지 마라.
- 입력 JSON에 "monthly_approx_won" 필드가 있으면(질문이 월 단위를 물었는데 데이터는 연
  단위인 경우), 이미 코드가 연매출을 12로 나눠 계산해 둔 근사값이니 절대 다시 계산하지
  말고 그대로 써라. 먼저 "월 매출은 대략 {monthly_approx_won}원입니다."처럼 근사치를
  "대략"/"약" 같은 표현과 함께 언급하고, 이어서 "(정확한 수치는 연매출 기준
  {monthly_approx_based_on_annual_won}원입니다)"처럼 괄호로 정확한 연매출 기준값을
  병기해라 — 근사치라는 것이 반드시 드러나야 한다. 이 필드가 없으면(연 단위 질문이거나
  근사 계산 대상이 아닌 경우) 평소대로 답해라.
- 금액을 언급할 때는 항상 입력 JSON에 있는 amount_won 값 그대로, "9,680,000원"처럼 3자리마다
  콤마를 넣은 숫자 뒤에 "원"을 붙여서 정확히 옮겨 적어라. 절대 "만원"/"천원" 등으로 단위를
  바꾸거나 값을 다시 계산하지 마라.
- **"칠억 삼천만원"/"7억 3천만원"처럼 한글로 읽어서 쓰거나 숫자·한글을 섞어 쓰지 마라 —
  반드시 아라비아 숫자와 쉼표만 써라(예: "730,000,000원").** amount_won 값을 자릿수 그대로,
  한 글자도 바꾸지 않고 옮겨 적어라.
- 입력 JSON에 없는 숫자나 항목은 절대 언급하지 마라(추측 금지).
- 추천, 유불리 판단("이게 더 낫다", "이 브랜드가 좋다" 등)은 하지 마라 — 사실 설명만 한다.
- **너는 지금 입력 JSON의 "brand" 필드에 적힌 브랜드 하나의 데이터만 받았다.** 사용자의
  원래 질문에 다른 브랜드 이름이 함께 언급되어 있어도(예: "A랑 B 보증금 비교해줘"), 그
  다른 브랜드(B)에 대해서는 어떤 언급도 하지 마라 — 데이터가 있다/없다/확인이 안 된다
  포함 일체 금지다. 그 브랜드는 너와 별도로 처리되어 각자 답변되므로, 네가 못 받은 정보를
  "없다"고 단정하는 것은 사실이 아닐 수 있는 추측이다. 너는 오직 "brand" 필드의 브랜드에
  대해서만 설명해라.
"""

# 3자리 콤마 숫자 뒤에 금액 단위가 붙은 패턴만 검증 대상으로 삼는다("2024년"의 "2024"나
# "13개 매장"의 "13" 같은 비금액 숫자를 오탐하지 않기 위함 — 단위 접미사가 없으면 아예
# 검증 대상에서 뺀다). 03_extract_clauses.py의 UNIT_MULTIPLIERS와 같은 순서/배수를 쓴다.
_UNIT_SUFFIXES = [
    ("억원", 100_000_000), ("천만원", 10_000_000), ("백만원", 1_000_000),
    ("만원", 10_000), ("천원", 1_000), ("원", 1),
]
_AMOUNT_TOKEN_RE = re.compile(r"(\d[\d,]*)\s*(" + "|".join(u for u, _ in _UNIT_SUFFIXES) + ")")


def group_amounts(amounts: list) -> dict:
    """amounts를 그룹핑 키(table_context가 있으면 그걸, 없으면 column, 그것도 없으면
    "금액")로 묶는다 — 매장타입/규모(예: 비비큐 BSK/올리브치킨/.../빌리지)나 상한·하한/
    면적당처럼 서로 다른 값인데 같은 라벨로 반복돼서 구분이 안 되던 문제(작업로그 (32))를
    코드가 먼저 결정론적으로 정리한다. 합산도 여기서 하지 않는다 — "총 계" 같은 항목은
    원본 데이터에 이미 합계로 들어있어서, 여기서 또 더하면 이중 계산이 된다."""
    groups: dict[str, list[dict]] = {}
    for a in amounts:
        key = a.get("table_context") or a.get("column") or "금액"
        groups.setdefault(key, []).append(a)
    return groups


def format_grouped_fallback(groups: dict) -> str:
    """group_amounts() 결과를 LLM 없이 결정론적으로 문장화한다 — LLM 생성이 실패하거나
    검증(_verify_numbers)을 통과 못 했을 때의 안전망(작업로그 (32)).

    2026-09-19(라운드2 작업지시 1번): 예전엔 모든 그룹을 전부 "[그룹] 라벨: 값, ..." 로
    이어붙여서, 지역별/매장타입별 그룹이 여러 개인 카테고리(평균매출액 등)에서 질문 의도와
    무관하게 모든 지역/타입 값이 대괄호로 그대로 나열되는 문제가 있었음(이 함수는 LLM을
    안 거치는 결정론적 안전망이라 "질문 의도"를 판단할 수 없으므로, 대신 첫 번째 그룹만
    상세히 보여주고 나머지는 개수만 안내한다 — 원본 표 자체는 출처 패널에서 그대로 볼 수
    있으므로 정보 손실은 없다)."""
    keys = list(groups.keys())
    if not keys:
        return "조회된 금액이 없습니다."

    def _render(items):
        item_strs = []
        for it in items:
            label = (it.get("label") or "").strip()
            won = it.get("amount_won")
            raw = it.get("raw")
            val = f"{won:,}원" if won is not None else (f"{raw}(단위 미상)" if raw else "값 없음")
            item_strs.append(f"{label}: {val}" if label else val)
        return ", ".join(item_strs)

    first_key = keys[0]
    result = f"[{first_key}] {_render(groups[first_key])}"
    rest = keys[1:]
    if rest:
        preview = ", ".join(rest[:3])
        more = f" 외 {len(rest) - 3}개" if len(rest) > 3 else ""
        result += f" (그 외 {preview}{more} 구분은 출처 표에서 확인 가능)"
    return result


def _extract_amounts_from_text(text: str) -> list[int]:
    """LLM 생성 텍스트에서 "9,680,000원"/"968만원" 같은 금액 표현을 찾아 원 단위 정수로
    환산한 리스트를 반환한다(_verify_numbers()가 이걸로 원본과 대조한다)."""
    unit_mult = dict(_UNIT_SUFFIXES)
    found = []
    for m in _AMOUNT_TOKEN_RE.finditer(text or ""):
        digits = m.group(1).replace(",", "")
        if not digits.isdigit():
            continue
        found.append(int(digits) * unit_mult[m.group(2)])
    return found


# 2026-09-19(라운드3 작업지시 3번, 회귀 조사 중 발견): "39 억 8 천 5 만 3 천 7 백 원"처럼
# 숫자를 억/천/백/만 단위로 조각내어 한글로 풀어쓴 표기는 _AMOUNT_TOKEN_RE(정상적인
# "9,680,000원"/"968만원" 형태만 인식)에 전혀 안 걸려서, 숫자 검증을 통째로 우회한 채
# (추출되는 숫자 자체가 없어서 "검증할 게 없으니 통과") 틀린 값이 그대로 나갈 수 있음을
# 실측으로 확인함(종로김밥 평균매출액 질문에서 상한값을 매출액인 것처럼 이 형식으로 답한
# 사례) — 프롬프트 지시만으로는 로컬 LLM(qwen3.5:9b)이 안 지키는 경우가 있어서 코드로도
# 걸러야 한다. "숫자+억/천/백/만"인데 바로 뒤에 "원"이 안 붙는 조각이 하나라도 있으면
# 값이 맞고 틀리고를 떠나 표기 규칙 위반이므로 검증 실패로 본다.
_FRAGMENTED_KOREAN_NUMBER_RE = re.compile(r"\d\s*(?:억|천|백|만)(?!\s*원)")


def _has_fragmented_korean_number(text: str) -> bool:
    return bool(_FRAGMENTED_KOREAN_NUMBER_RE.search(text or ""))


def _verify_numbers(text: str, valid_amounts: set) -> bool:
    """text 안의 모든 금액이 valid_amounts(원본 amounts의 amount_won 집합) 안에 실제로
    있는지 전부 대조한다. 하나라도 없으면 환각으로 간주해 False(호출부가 폴백 처리).
    한글로 조각낸 숫자 표기(_has_fragmented_korean_number)가 있으면 숫자 자체를 추출할
    수 없어 검증을 우회하므로, 그 표기 자체를 무조건 검증 실패로 취급한다."""
    if _has_fragmented_korean_number(text):
        return False
    for val in _extract_amounts_from_text(text):
        if val not in valid_amounts:
            return False
    return True


# 2026-09-20(라운드6 작업지시 1번): "빽다방이랑 핸델앤그레텔 보증금 비교해줘" 실측 재현 —
# generate_grouped_narrative()는 브랜드 하나(brand_name)의 데이터만 컨텍스트로 받는데,
# question 파라미터로 넘어가는 질문 원문엔 비교 대상인 다른 브랜드 이름도 그대로 들어있어서,
# LLM이 "그 브랜드에 대해서는 못 받았다"를 "그 브랜드는 데이터가 없다"로 지어내는 서술적
# 할루시네이션이 실측됨(핸델앤그레텔 문단엔 실제 보증금 데이터가 정상적으로 나오는데도 빽다방
# 문단에 "핸델앤그레텔에 대한 정보는 제공된 데이터가 없으므로 비교할 수 없습니다"가 붙음).
# _verify_numbers()는 숫자만 검증하므로 이런 서술적 할루시네이션은 못 잡는다 — 프롬프트
# 지시(위 _STRUCTURED_NARRATIVE_SYSTEM_PROMPT)만으론 로컬 LLM이 완벽히 안 따를 수 있어서
# (사전에 예상된 리스크), 문장 단위로 걸러내는 사후 검증을 한 겹 더 둔다. "다른 브랜드명이
# 문장에 등장 + 그 문장에 없음/불가 계열 표현이 같이 등장"하는 문장만 제거하고, 그 외
# 문장(정상적으로 지금 브랜드 얘기만 하는 문장)은 그대로 둔다 — 오탐으로 정상 문장을 지우는
# 것을 최소화하기 위해 조건을 좁게 잡았다.
_NEGATIVE_DATA_PATTERN = re.compile(
    r"없(?:습니다|다|었습니다|으므로|어서|는|음)|확인(?:이|할)?\s*(?:안|불가|어렵)|"
    r"제공되지\s*않|포함되어\s*있지\s*않|자료가\s*없|비교할\s*수\s*없"
)


def _strip_other_brand_hallucination(text: str, other_brand_names: "list[str] | None") -> str:
    """text를 문장 단위로 나눠서, other_brand_names 중 하나라도 등장하면서 동시에
    _NEGATIVE_DATA_PATTERN(없다/불가/비교 불가 등)도 함께 나오는 문장만 제거한다.
    다른 브랜드 이름이 아예 없거나 매치되는 문장이 없으면 원문 그대로 반환 — 이 필터는
    "걸리면 제거"만 하고, 안 걸리면 손대지 않는다(오탐으로 정상 문장을 지우지 않기 위함)."""
    if not other_brand_names or not text:
        return text
    # 문장 경계: 마침표/느낌표/물음표/줄바꿈 뒤. 리스트(bullet) 항목은 항목 자체가 한
    # 문장으로 취급되도록 줄바꿈도 경계에 포함한다.
    sentences = re.split(r"(?<=[.!?])\s+|\n", text)
    kept = []
    for s in sentences:
        mentions_other = any(name and name in s for name in other_brand_names)
        if mentions_other and _NEGATIVE_DATA_PATTERN.search(s):
            continue  # 다른 브랜드 + 부정 표현이 같이 있는 문장만 버림
        if s.strip():
            kept.append(s.strip())
    return " ".join(kept).strip()


# 2026-09-19(라운드3 작업지시 4번): "월매출"/"월 매출"/"한 달 매출" 등 월 단위를 묻는
# 질문인지 판별. "매출액" 카테고리(canonical_title에 "매출액" 포함)와 같이 쓰일 때만
# 근사 월매출 계산을 트리거한다(generate_grouped_narrative 참고).
_MONTHLY_QUESTION_RE = re.compile(r"월\s*매출|한\s*달\s*매출")


def _representative_annual_amount(groups: dict) -> "int | None":
    """월매출 근사치 계산에 쓸 "대표 연매출" 값을 고른다. 상한/하한/면적당 같은 파생값이
    섞인 그룹/항목은 제외하고, 순수 매출액 계열 항목의 첫 값(원본 표 순서상 보통 "전체")만
    쓴다 — 어느 그룹/항목을 대표로 삼을지 애매해지지 않도록 가장 단순한 규칙만 쓴다.
    2026-09-19(회귀 조사 중 발견): 그룹 키(table_context)가 "(단위: 천원, 부가세 별도)"
    처럼 지표를 구분 안 해주는 경우(종로김밥 등)가 있어서, 그룹 키뿐 아니라 항목 하나하나의
    column도 같이 확인한다."""
    def _is_derived(text: "str | None") -> bool:
        return any(kw in (text or "") for kw in ("상한", "하한", "면적"))

    for key, items in groups.items():
        if _is_derived(key):
            continue
        for it in items:
            if it.get("amount_won") is not None and not _is_derived(it.get("column")):
                return it["amount_won"]
    return None


def generate_grouped_narrative(question: str, brand_name: str, canonical_title: "str | None",
                                groups: dict, other_brand_names: "list[str] | None" = None) -> "str | None":
    """group_amounts() 결과를 LLM에게 컨텍스트로 주고 자연스러운 설명 문장을 생성하게 한다.
    LLM 호출 실패, 응답 형식 이상, 또는 숫자 검증 실패 시 None을 반환한다 — 호출부가
    format_grouped_fallback()으로 대체해야 한다는 신호.

    2026-09-19(라운드2 작업지시 1번): 예전엔 question을 안 받아서 LLM이 "이 그룹에 어떤
    값이 있는지"만 보고 무조건 모든 그룹을 다 설명했음(예: "육시리 월매출이 얼마야?"에
    지역별/상한하한 6개 그룹 전부를 나열) — question을 payload에 같이 줘서 LLM이 질문
    의도에 맞게 핵심만 답하고 나머지는 요약하도록 프롬프트(_STRUCTURED_NARRATIVE_SYSTEM_PROMPT)
    와 함께 바꿈. question 자체는 답변 텍스트 생성에만 쓰이고 숫자 검증(_verify_numbers)
    로직은 그대로라 환각 방지 원칙은 안 바뀜.

    2026-09-20(라운드6 작업지시 1번): other_brand_names(비교 대상인 다른 브랜드들의
    display_name, 호출부인 assemble_structured_answer()가 per_brand에서 채워서 넘김)를
    받아서, question에 그 이름이 들어있어도 이 함수는 brand_name 하나의 데이터만 받았다는
    걸 프롬프트로 명시하고(_STRUCTURED_NARRATIVE_SYSTEM_PROMPT), 생성된 문장에서도
    _strip_other_brand_hallucination()으로 다른 브랜드 + 부정 표현이 같이 나온 문장을
    사후 제거한다(프롬프트 지시만으론 로컬 LLM이 완벽히 안 따를 수 있어서 이중 방어)."""
    valid_amounts = {
        it["amount_won"] for items in groups.values() for it in items
        if it.get("amount_won") is not None
    }
    if not valid_amounts:
        return None  # 검증할 숫자가 없으면(전부 raw 미인식 등) LLM 생성 의미가 없음 -> 폴백
    # 2026-09-19(라운드3 회귀 조사 중 발견): group_amounts()가 table_context를 그룹 키로
    # 우선 쓰는데(예: 종로김밥 평균매출액 — table_context="(단위 : 천원, 부가세 별도)"라는
    # 단위 안내문일 뿐인데도 모든 지표(매출액/상한/하한/면적당)가 이 하나의 그룹으로
    # 뭉쳐짐), 이 경우 같은 그룹 안의 label(예: "전체 42")이 지표마다 전부 똑같이
    # 반복되면서도 item에는 label만 실려있어서 LLM이 어느 값이 매출액이고 어느 게 상한/
    # 하한/면적당인지 구분할 근거가 없어 잘못 골랐음(골드셋 재현 확인: 매출액 398,537,000
    # 대신 상한 1,261,411,000을 "전체 매출액"으로 답함). column(예: "...연간평균 매출액"
    # vs "...상한")은 지표마다 항상 다르므로 같이 실어서 그룹 키가 무엇이든 지표를
    # 구분할 수 있게 한다.
    payload = {
        "question": question,
        "brand": brand_name,
        "item": canonical_title,
        "groups": [
            {
                "group": key,
                "items": [
                    {"label": it.get("label"), "column": it.get("column"), "amount_won": it.get("amount_won")}
                    for it in items if it.get("amount_won") is not None
                ],
            }
            for key, items in groups.items()
        ],
    }
    # 2026-09-19(라운드3 작업지시 4번): "월매출이 얼마야?" 같은 질문에 연 단위 데이터
    # (평균매출액)만 있으면, 예전엔 "월매출 데이터는 없다"고만 안내했는데 이번엔 연매출을
    # 12로 나눈 근사 월매출을 먼저 보여주도록 바꾼다. 나눗셈은 여기서 코드가 직접 계산하고
    # (LLM이 계산하면 오류 위험 — 이 프로젝트의 "숫자는 LLM이 재생성하지 않는다" 원칙 그대로
    # 유지), 그 결과를 payload에 미리 계산된 값으로 얹어서 LLM은 문장으로 감싸기만 한다.
    # valid_amounts에도 이 근사값을 추가해야 _verify_numbers()가 "새로 지어낸 숫자"로
    # 오판하지 않는다.
    if _MONTHLY_QUESTION_RE.search(question or "") and canonical_title and "매출액" in canonical_title:
        annual = _representative_annual_amount(groups)
        if annual is not None:
            monthly_approx = round(annual / 12)
            payload["monthly_approx_won"] = monthly_approx
            payload["monthly_approx_based_on_annual_won"] = annual
            valid_amounts.add(monthly_approx)
    messages = [
        {"role": "system", "content": _STRUCTURED_NARRATIVE_SYSTEM_PROMPT},
        {"role": "user", "content": f"그룹별 금액(JSON): {json.dumps(payload, ensure_ascii=False)}"},
    ]
    try:
        result = call_llm_json(messages)
    except LLMError:
        return None
    description = result.get("description")
    if not isinstance(description, str) or not description.strip():
        return None
    description = _strip_citation_tags(description)
    description = _strip_other_brand_hallucination(description, other_brand_names)
    if not description.strip():
        return None  # 다른 브랜드 할루시네이션 문장을 걷어내고 나니 아무 내용도 안 남음 -> 폴백
    if not _verify_numbers(description, valid_amounts):
        return None
    return description.strip()


def _format_tables_for_context(tables: "list | None", max_rows: int = 20,
                                max_chars: int = 1200) -> "str | None":
    """row["tables"](rowspan/colspan까지 복원된 격자, 03_extract_clauses.py 참고)를 LLM
    컨텍스트용 평문으로 펼친다 — 행마다 셀을 " | "로 이어붙이고 행은 줄바꿈. 표/전체 길이가
    너무 길면 잘라서 "…(표 일부 생략)"을 붙인다(answer.py의 기존 800자 truncation, app.py의
    40자 라벨 truncation과 같은 원칙). 2026-09-15(작업로그 (35)): 기본값을 30행/2000자에서
    20행/1200자로 줄임 — 표가 클수록 로컬 LLM(qwen3.5:9b)이 "정리해야 할 데이터 뭉치"로
    인식해서 프롬프트 지시(보고서 형식 금지 등)를 무시하는 경향이 실측됨(아래 프롬프트
    보강만으로는 부족했음)."""
    if not tables:
        return None
    parts = []
    for table in tables:
        if not table:
            continue
        # 2026-09-20(라운드5 작업지시 1번): _format_tables_as_answer()와 같은 문제 —
        # 곱돌이곱창 평균매출액처럼 데이터 행이 전부 "해당없음"/"-"/빈 칸뿐인 표를 그대로
        # LLM 컨텍스트에 넘기면(18개 지역이 전부 같은 빈 값 반복) LLM이 그걸 "정리해야 할
        # 데이터"로 오인해서 장황하게 나열하거나 빈 칸을 그대로 옮겨 적을 위험이 있음
        # (작업지시 원문 — "LLM에게 빈 칸투성이 컨텍스트를 주면 LLM도 그걸 그대로 옮겨
        # 적을 위험이 있다"). 헤더 행(첫 행, 보통 표 구조를 설명하는 행이라 그대로 둠)을
        # 제외한 데이터 행 전부가 플레이스홀더/빈 칸뿐이면, 표 전체를 그대로 넘기지 않고
        # 짧은 안내 한 줄로 대체한다.
        # 헤더가 여러 행에 걸친 표(table_to_grid()가 rowspan을 펼치면서 상위 헤더 셀 값이
        # 다음 행에도 그대로 복제됨, 작업로그 (25))는 첫 칸이 계속 표 제목과 같은 값으로
        # 반복되는 게 신호다(_format_tables_as_answer()가 이미 쓰는 것과 같은 판별법) —
        # 이 신호로 헤더 연속 행을 걸러내야 실제 데이터 행만 놓고 판단할 수 있다.
        header_first_cell = (table[0][0] or "").strip() if table[0] else ""
        data_rows = [
            row for row in table[1:]
            if not (row and (row[0] or "").strip() == header_first_cell)
        ]
        # row[0]은 라벨(지역명 등)이라 항상 실제 텍스트라 플레이스홀더 판정에서 제외한다 —
        # 나머지 값 칸(row[1:])이 전부 플레이스홀더/빈 칸인지만 본다.
        all_placeholder = bool(data_rows) and all(
            all((str(c).strip() if c is not None else "") in _NO_VALUE_PLACEHOLDERS | {""} for c in row[1:])
            for row in data_rows
        )
        if all_placeholder:
            header_line = " | ".join(str(c) if c is not None else "" for c in table[0])
            parts.append(f"{header_line}\n(데이터 행 {len(data_rows)}개 전부 해당없음/빈 값 — 구체적 수치 없음)")
            continue
        rows = table[:max_rows]
        lines = [" | ".join(str(c) if c is not None else "" for c in row) for row in rows]
        block = "\n".join(lines)
        if len(table) > max_rows:
            block += "\n…(표 일부 생략)"
        parts.append(block)
    if not parts:
        return None
    combined = "\n\n".join(parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n…(표 일부 생략)"
    return combined


def _format_amounts_for_context(amounts: "list | None", max_items: int = 20,
                                 max_chars: int = 1200) -> "str | None":
    """row["amounts"](표에서 이미 정규화된 금액)를 "라벨: 9,680,000원" 형태로 나열한다.
    2026-09-15 (작업로그 (35)): 원래 무제한이었음 — 항목이 100개 넘는 표(예: 종로김밥
    "주요 품목별 공급가격")에서 [표 원본]보다 훨씬 큰 데이터 뭉치를 만들어서, _format_tables_for_context()
    의 truncation만으로는 컨텍스트가 안 줄어들던 진짜 원인이었음. [표 원본]과 같은 원칙으로
    제한한다(항목 20개 또는 1200자 넘으면 자름)."""
    if not amounts:
        return None
    parts = []
    for a in amounts[:max_items]:
        label = (a.get("label") or "").strip()
        won = a.get("amount_won")
        raw = a.get("raw")
        if won is not None:
            val = f"{won:,}원"
        elif raw:
            val = f"{raw}(단위 미상)"
        else:
            continue
        parts.append(f"{label}: {val}" if label else val)
    if not parts:
        return None
    combined = "; ".join(parts)
    if len(amounts) > max_items:
        combined += "; …(금액 목록 일부 생략)"
    if len(combined) > max_chars:
        combined = combined[:max_chars] + " …(금액 목록 일부 생략)"
    return combined


def _merge_header_cell(existing: "str | None", extra: "str | None") -> str:
    """헤더 텍스트를 이어붙이되 단어 단위로 중복을 걸러낸다 — "2024년 평균 매출액"에
    "매출액 면적당"을 그냥 이어붙이면 "...매출액 매출액 면적당"처럼 지저분해지는 걸
    막는다(작업로그 (38)). "매출액"은 이미 있는 단어라 건너뛰고 "면적당"만 새로 붙여서
    "...매출액 면적당"이 되게 한다. 단어 자체는 원문 그대로만 쓰고 새로 만들지 않는다."""
    existing = (existing or "").strip()
    extra = (extra or "").strip()
    if not extra:
        return existing
    if not existing:
        return extra
    if extra in existing:
        return existing
    existing_words = existing.split()
    new_words = [w for w in extra.split() if w not in existing_words]
    if not new_words:
        return existing
    return f"{existing} {' '.join(new_words)}".strip()


def _enrich_header_row(row: list) -> list:
    """헤더 한 행 안에서 텍스트가 2번 이상 반복되는 셀(작업로그 (38) — 예: 평균매출액 표의
    "면적 3.3㎡당"이 매출액/상한/하한 각각에 한 번씩 총 3번 반복됨)을, 그 반복 인스턴스들이
    전부 서로 다른(그 자체는 안 반복되는) "앵커" 셀 바로 뒤에 붙어 있을 때만 그 앵커 텍스트를
    앞에 붙여서 구분한다(예: "상한"+"면적당" -> "상한 면적당", "하한"+"면적당" -> "하한
    면적당"). 이 조건(모든 인스턴스가 실제로 서로 다른 진짜 앵커를 가짐)을 만족 못 하면
    (예: 로열티 표에서 "금액"이 앵커 없이 바로 연달아 두 번 나오는 경우처럼, 헤더 텍스트
    자체에 구분할 근거가 없는 경우) 억지로 관계없는 앞 컬럼을 갖다 붙이면 오히려 틀린
    라벨이 되므로 원문 그대로 두고, 이런 애매한 경우는 _format_tables_as_answer()의
    안전망(같은 행에서 같은 라벨에 서로 다른 값이 매핑되면 번호를 붙이는 것)에 맡긴다."""
    texts = [(c or "").strip() for c in row]
    freq: dict = {}
    for t in texts:
        if t:
            freq[t] = freq.get(t, 0) + 1
    groups: dict = {}
    for i, t in enumerate(texts):
        if not t or freq[t] <= 1:
            continue
        pred = texts[i - 1] if i > 0 else ""
        groups.setdefault(t, []).append((i, pred))
    result = list(texts)
    for t, occs in groups.items():
        preds = [p for _, p in occs]
        if any(not p or freq.get(p, 0) != 1 for p in preds):
            continue  # 앵커가 없거나 앵커 자체도 반복되면 못 믿음 -> 원문 그대로 둠
        if len(set(preds)) != len(preds):
            continue  # 서로 다른 인스턴스가 같은 앵커를 공유하면 그래도 구분이 안 됨
        for i, p in occs:
            result[i] = f"{p} {t}".strip()
    return result


# 2026-09-20(라운드5 작업지시 1번): 원문에 값 대신 "해당없음"/"-"처럼 명시적 플레이스홀더만
# 적혀있는 셀은 "실제 값이 있다"고 치지 않는다("해당없음"이라는 원문 표기 자체는 그대로
# 살려서 보여주되, "이 표는 사실상 값이 없다"는 판단에는 넣지 않는다) — 03_extract_clauses.py
# 원문 표기를 그대로 따온 것이라 새로 지어낸 문구가 아니다.
_NO_VALUE_PLACEHOLDERS = {"해당없음", "해당사항없음", "-", "없음"}


def _format_tables_as_answer(tables: "list | None", max_rows: int = 10,
                              max_chars: int = 800) -> "str | None":
    """구조화 카테고리에서 amounts는 비었지만 tables는 있는 row를 위한 결정론적(LLM 호출
    없음) 표 렌더링(작업로그 (36), 작업로그 (37)에서 형식 변경, 작업로그 (38)에서 헤더
    병합/충돌 처리 개선).

    2026-09-15 (작업로그 (37)): 처음엔 원본 표를 마크다운 코드블록으로 통째로 붙였는데,
    인용 태그를 클릭하면 출처 패널에서 원본 표를 어차피 다시 보여주고(app.py의
    render_tables_raw()), 채팅 답변 안에 표를 또 통째로 넣는 건 중복이자 작업로그 (35)에서
    서술형 경로에 강제한 "질문에 곧바로 답해라, 데이터 뭉치로 주지 마라" 원칙과도 어긋난다는
    지적을 받고 "행 라벨(헤더: 값, ...)" 형태로 기계적으로 풀어쓰는 방식으로 바꿈. 여전히
    LLM은 거치지 않는다(이 함수 안에 call_llm/call_llm_json 호출 없음 — "구조화 값은 LLM이
    재생성하지 않는다" 원칙 유지) — 표의 첫 행을 헤더로 보고, 그 다음 행부터 첫 칸을 그
    행의 라벨로, 나머지 칸은 "헤더: 값"으로 이어붙인다.

    2026-09-15 (작업로그 (38)): 헤더가 2~3행에 걸친 표에서 "상한"/"하한"처럼 한 컬럼을
    차지하면서 동시에 바로 다음 컬럼("면적당")의 상위 구분자 역할도 하는 경우, 컬럼별로
    독립적으로 헤더를 이어붙이던 예전 로직은 이 관계를 못 읽어서 서로 다른 컬럼이 같은
    최종 라벨("...면적 3.3㎡당")로 합쳐지는 문제가 있었음(전체 스캔 결과 구조화 카테고리
    amounts=[]∧tables!=[] 7,152건 중 1,222건(17%)에서 실제 충돌 발생, 상세는 docs/DESIGN.md
    작업로그 참고). _enrich_header_row()로 "앵커+반복 수식어" 관계를 일반적으로 인식해서
    헤더 단계에서부터 최대한 정확하게 구분하고(_merge_header_cell()로 단어 단위 중복 없이
    합침), 그래도 헤더 텍스트 자체가 모호해서(예: "금액"이 앵커 없이 그냥 두 번 나오는 경우)
    못 거른 경우를 위해 데이터 행 단계에서 "같은 라벨에 서로 다른 비어있지 않은 값이
    매핑되면 번호를 붙이는" 안전망을 반드시 통과시킨다(절대 구분 없이 뭉개지지 않게).
    헤더/셀 텍스트는 항상 원문 그대로만 쓰고 요약·재작성하지 않는다 — 표 구조(컬럼
    개수/이름)에 하드코딩하지 않으므로 로열티/평균매출액 등 다른 표에도 그대로 적용된다."""
    if not tables:
        return None
    parts = []
    n_rows = 0
    truncated = False
    # 2026-09-20(라운드5 작업지시 1번): "곱돌이곱창" 평균매출액처럼 지역별 매출액이
    # 대부분 "해당없음"이고 나머지 칸(면적당/상한/하한 등)이 통째로 빈 문자열인 표에서,
    # 빈 칸까지 "면적 3.3m2당: ," 처럼 그대로 나열되어 화면에 쓰레기 문자열이 노출되는
    # 걸 실측 확인함 — 값 있는 필드만 나열하고, 아래에서 행/표 전체가 빈 값뿐이면 각각
    # "정보 없음"/한 문장 안내로 대체한다.
    any_row_has_data = False
    for table in tables:
        if not table or len(table) < 2:
            continue
        header = list(table[0])
        data_start = 1
        # 헤더가 2행 이상에 걸친 표(table_to_grid()가 rowspan을 펼치면서 상위 헤더 셀 값이
        # 다음 행에도 그대로 복제됨, 작업로그 (25))에서, 그 다음 행을 첫 데이터 행으로 잘못
        # 읽지 않도록 rowspan 복제의 전형적인 신호(다음 행의 첫 칸이 헤더 첫 칸과 정확히
        # 같음)를 보고 헤더 연속으로 판단해 병합한다(작업로그 (37)). 병합 전에 그 행 자체를
        # _enrich_header_row()로 먼저 다듬은 뒤(작업로그 (38)) _merge_header_cell()로 단어
        # 단위 중복 없이 합친다.
        while data_start < len(table):
            cand = table[data_start]
            cand_first = (cand[0] or "").strip() if cand else ""
            if cand_first and cand_first == (header[0] or "").strip():
                enriched = _enrich_header_row(cand)
                for i in range(min(len(header), len(enriched))):
                    header[i] = _merge_header_cell(header[i], enriched[i])
                data_start += 1
            else:
                break
        for row in table[data_start:]:
            if n_rows >= max_rows:
                truncated = True
                break
            if not row:
                continue
            label = (row[0] or "").strip() or "(라벨 없음)"
            raw_fields = []
            for i in range(1, len(row)):
                h = (header[i] or "").strip() if i < len(header) else ""
                h = h or f"항목{i}"
                v = row[i] if row[i] is not None else ""
                raw_fields.append((h, v))
            # 안전망(작업로그 (38), 필수): 헤더 병합을 아무리 잘해도 표 자체가 모호해서
            # (예: 헤더 텍스트가 "금액"으로 완전히 똑같은데 실제로는 서로 다른 값인 경우)
            # 100% 못 거를 수 있음 — 같은 행 안에서 같은 라벨에 서로 다른 비어있지 않은
            # 값이 매핑되면 자동으로 번호를 붙여서 절대 구분 없이 뭉개지지 않게 한다.
            values_by_label: dict = {}
            for h, v in raw_fields:
                vs = (v or "").strip()
                if vs:
                    values_by_label.setdefault(h, set()).add(vs)
            ambiguous = {h for h, vs in values_by_label.items() if len(vs) > 1}
            counters: dict = {}
            fields = []
            row_has_real_value = False
            for h, v in raw_fields:
                vs = (v or "").strip()
                if not vs:
                    continue  # 빈 값 필드는 나열하지 않는다(작업지시 1번) — 라벨만 있고 값이
                    # 없는 "면적 3.3m2당: ," 같은 쓰레기 문자열을 만들지 않기 위함.
                if h in ambiguous:
                    counters[h] = counters.get(h, 0) + 1
                    h_disp = f"{h} ({counters[h]})"
                else:
                    h_disp = h
                fields.append(f"{h_disp}: {vs}")
                # "해당없음"/"-" 같은 플레이스홀더는 "값이 있다"고 치지 않는다 — 곱돌이곱창
                # 평균매출액처럼 모든 지역이 "해당없음"뿐인 표는 사실상 표 전체가 빈 값인
                # 것과 같아서, any_row_has_data가 False로 남아야 아래 "표 전체를 한 문장으로
                # 대체" 안전망이 정상 작동한다.
                if vs not in _NO_VALUE_PLACEHOLDERS:
                    row_has_real_value = True
            if fields:
                if row_has_real_value:
                    any_row_has_data = True
                parts.append(f"{label}({', '.join(fields)})")
            else:
                # 그 행에 값 있는 필드가 하나도 없으면(전부 빈 값) 라벨만 짧게 표시한다.
                parts.append(f"{label}(정보 없음)")
            n_rows += 1
        if truncated:
            break
    if not parts:
        return None
    if not any_row_has_data:
        # 표 전체가 사실상 빈 값뿐이면(행마다 "정보 없음"만 나열해봐야 지저분함) 지역/행별로
        # 나열하지 않고 한 문장으로 대체한다(작업지시 1번).
        return "이 항목은 정보공개서에 구체적 수치가 공개되어 있지 않습니다."
    # 2026-09-20(라운드6 작업지시 2번): 항목(행)이 여러 개면(예: 로열티/광고분담금/판촉분담금/
    # 지연이자/교육비처럼 하위 항목이 많고 항목당 필드도 많은 카테고리) 예전처럼 전부 쉼표로
    # 이어붙이면 한 문단처럼 뭉쳐 보인다는 지적(실측: 피자스쿨/핸델앤그레텔/101프렙 로열티,
    # 핸델앤그레텔 보증금)을 받아 항목별 줄바꿈 bullet로 바꾼다. 이 함수의 반환값은 상위
    # 호출부(assemble_structured_answer())가 "- **브랜드** [항목명]: {이 반환값}" 형태로
    # 감싸므로, 그 부모 bullet 바로 다음 줄부터 두 칸 들여쓰기 "  - "로 시작해서 마크다운
    # 렌더러(remark-gfm, ChatBubble.js)가 부모 항목 아래 중첩 리스트로 인식하게 한다.
    # 항목이 1개뿐인 표(예: 핸델앤그레텔 보증금)는 굳이 나눌 필요가 없어 기존처럼 한 줄로 둔다.
    if len(parts) > 1:
        result = "\n" + "\n".join(f"  - {p}" for p in parts)
        if truncated:
            result += "\n  - …(일부 생략)"
    else:
        result = parts[0]
        if truncated:
            result += " …(일부 생략)"
    if len(result) > max_chars:
        result = result[:max_chars] + " …(일부 생략)"
    return result


def build_citation(row: dict) -> dict:
    """out에 들어갈 출처 태그 — app.py가 이걸로 원문 뷰어를 연결한다.
    2026-09-15 (작업로그 (35)): brandNm_matched에 "?"가 섞인 경우(franchise.ftc.go.kr 응답
    자체 결손) 정적 brandNm으로 폴백 — section_schema.pick_display_name() 참고."""
    return {
        "brandMnno": row.get("brandMnno"),
        "brandNm": pick_display_name(row.get("brandNm"), row.get("brandNm_matched")),
        "category": row.get("category"),
        "canonical_title": row.get("canonical_title"),
        "attr": row.get("attr"),
        "jngIfrmpSn": row.get("jngIfrmpSn"),
    }


def citation_tag(c: dict) -> str:
    return f"[{c['brandNm']}-{c['category']}-{c['canonical_title']}]"


# 2026-09-19(라운드3 작업지시 1번): _NARRATIVE_SYSTEM_PROMPT가 더 이상 답변에 인용 태그를
# 넣으라고 지시하지 않지만, 프롬프트 지시를 LLM이 늘 따르는 건 아니라는 게 이 프로젝트에서
# 여러 번 실측됨(예: 작업로그 (35)의 한글 숫자 표기 문제) — 그래서 프롬프트 수정만 믿지
# 않고 코드로도 한 번 더 걸러낸다. citation_tag()는 항상 "[브랜드-카테고리-조항명]"처럼
# 하이픈으로 구분된 3개 구간을 대괄호 하나에 담는데, 이 도메인의 브랜드명/카테고리/조항명
# 자체에는 하이픈이 없으므로(공백/한글/괄호는 있어도) 이 패턴만 안전하게 걸러낸다 — "[표
# 원본]"/"[금액]"처럼 하이픈이 없는 컨텍스트 라벨은 원래도 답변에 나오면 안 되는 것이지만
# 이 정규식으로는 안 걸러진다(그건 프롬프트 규칙으로만 방지).
_CITATION_TAG_RE = re.compile(r"\[[^\[\]]*-[^\[\]]*-[^\[\]]*\]")


def _strip_citation_tags(text: str) -> str:
    stripped = _CITATION_TAG_RE.sub("", text or "")
    # 태그를 지우고 남은 이중 공백/줄 끝 공백을 정리(문장 사이 공백은 유지, 문단 구분용
    # 빈 줄은 그대로 둔다).
    stripped = re.sub(r"[ \t]+\n", "\n", stripped)
    stripped = re.sub(r"[ \t]{2,}", " ", stripped)
    return stripped.strip()


def not_found_reason_text(b: dict) -> str:
    """found=False인 per_brand 항목의 사유별 설명(작업로그 (31) 참고) — "이름 자체를 모름"
    (unresolved)과 "이름은 확인했지만 데이터가 없음"(no_data), "동명이인 후보가 여럿이라
    자동으로 못 정함"(ambiguous)을 구분해서, 오타 때문에 못 찾은 것처럼 오해하지 않게 한다."""
    reason = b.get("reason")
    names = ", ".join(b.get("names") or [])
    if reason == "no_data":
        return f"'{b['display_name']}'({names}) 브랜드는 확인했지만 정보공개서 데이터가 아직 없습니다."
    if reason == "ambiguous":
        return f"'{b['display_name']}'가 여러 브랜드로 해석됩니다: {names}. 정확한 이름으로 다시 질문해 주세요."
    return f"'{b['display_name']}' 브랜드를 찾지 못했습니다."


def _format_won(n: int) -> str:
    return f"{n:,}원"


def _format_total_cost_single(name: str, total_result: dict) -> "tuple[str, list[dict]]":
    """mode="single"(타입 분기 없음) — 최초 가맹금/그 밖의 비용/보증금(또는 예치가맹금)을
    안전하게 더한 단일 총액을 마크다운 표로 보여준다(작업로그 (41)). 숫자는
    total_cost.compute_total_startup_cost()가 이미 원본에서 그대로 꺼낸 것이라 여기서
    재계산하지 않는다.
    2026-09-19(라운드2 작업지시 4번): total_result에 area_note(계산에 쓰인 기준 면적,
    total_cost.find_area_note() 참고)가 있으면 총액 문장에 "(○○평 기준)"으로 붙인다.
    원문에 면적 기준 문구 자체가 없는 브랜드는 area_note가 None이라 아무것도 안 붙는다
    (억지로 만들지 않음)."""
    area_note = total_result.get("area_note")
    area_suffix = f" ({area_note})" if area_note else ""
    lines = [f"**{name}** 초기 창업비용 총액은 약 **{_format_won(total_result['total_won'])}**{area_suffix}입니다."]
    lines.append("")
    lines.append("| 항목 | 금액 |")
    lines.append("|---|---|")
    for item in total_result["breakdown"]:
        lines.append(f"| {item['label']} | {_format_won(item['amount_won'])} |")
    lines.append(f"| **합계** | **{_format_won(total_result['total_won'])}** |")
    # 2026-09-19(라운드3 작업지시 1번): [브랜드-카테고리-조항명] 인용 태그를 답변 본문에
    # 그대로 박아넣지 않는다 — 같은 정보가 이미 출처 칩(citations/sources)으로 따로
    # 표시되고 있어서 중복이었다(citations 자체는 여전히 반환해서 칩 렌더링에 씀).
    citations = [build_citation(r) for r in total_result.get("rows") or []]
    return "\n".join(lines), citations


def _format_total_cost_multi(name: str, total_result: dict) -> "tuple[str, list[dict]]":
    """mode="multi"(매장 타입/그룹이 여러 개) — 억지로 하나의 총액으로 합치지 않고
    항목별(최초 가맹금/그 밖의 비용/보증금 또는 예치가맹금)로 타입별 금액을 그대로
    나열한다(작업로그 (41), 실측 근거는 total_cost.py 모듈 docstring 참고)."""
    lines = [
        f"**{name}**: 이 브랜드는 매장 유형/규모에 따라 비용이 여러 가지라 "
        "하나의 총액으로 합산하지 않았습니다."
    ]
    for title, items in total_result["components"].items():
        lines.append("")
        lines.append(f"**{title}**")
        for it in items:
            col = it["column"] or "(구분 없음)"
            lines.append(f"- {col}: {_format_won(it['amount_won'])}")
    citations = [build_citation(r) for r in total_result.get("rows") or []]
    return "\n".join(lines), citations


def assemble_total_cost_answer(question: str, per_brand: list[dict]) -> dict:
    """per_brand: [{"brand_mnno":.., "display_name":.., "found": bool,
    "total_result": total_cost.compute_total_startup_cost() 반환값}]
    "총창업비용"(합성 카테고리, 작업로그 (41)) 답변 — total_cost.py가 이미 실측 근거대로
    안전하게 계산해둔 값을 mode별로 마크다운 표/목록으로만 감싼다. 숫자는 여기서 재계산하지
    않는다(docs/DESIGN.md 4단계 원칙과 동일 — "구조화 값은 LLM이 재생성하지 않는다")."""
    lines = []
    citations = []
    any_data = False
    for b in per_brand:
        name = b["display_name"]
        if not b["found"]:
            lines.append(f"- {not_found_reason_text(b)}")
            continue
        total_result = b["total_result"]
        mode = total_result.get("mode")
        if mode == "single":
            any_data = True
            text, cites = _format_total_cost_single(name, total_result)
            lines.append(text)
            citations.extend(cites)
        elif mode == "multi":
            any_data = True
            text, cites = _format_total_cost_multi(name, total_result)
            lines.append(text)
            citations.extend(cites)
        else:
            lines.append(
                f"- **{name}**: 이 브랜드는 표 구조가 복잡해서 총액을 자동으로 계산하기 "
                "어렵습니다. 개별 항목(가맹비, 보증금 등)을 따로 질문해 주세요."
            )

    answer_text = "\n\n".join(lines) if lines else "조회된 정보가 없습니다."
    if not any_data:
        answer_text += "\n\n(주의: 해당 브랜드로 총창업비용을 계산할 수 있는 데이터가 없습니다.)"
    return {"answer": answer_text, "citations": citations}


def assemble_structured_answer(question: str, category: "str | None",
                                per_brand: list[dict]) -> dict:
    """per_brand: [{"brand_mnno":.., "display_name":.., "found": bool, "rows": [clause row,...]}]
    구조화 카테고리 답변 — LLM은 값을 재생성하지 않고, 조회된 값을 문장으로만 감싼다."""
    lines = []
    citations = []
    any_data = False
    for b in per_brand:
        name = b["display_name"]
        # 2026-09-20(라운드6 작업지시 1번): 비교 질문("A랑 B 보증금 비교해줘")에서 generate_
        # grouped_narrative()가 A의 데이터만 보고도 question에 언급된 B를 "정보 없음"으로
        # 지어내는 걸 막기 위해, 지금 브랜드(name)를 제외한 나머지 비교 대상 브랜드 이름을
        # 미리 모아서 넘긴다.
        other_brand_names = [ob["display_name"] for ob in per_brand if ob is not b]
        if not b["found"]:
            lines.append(f"- {not_found_reason_text(b)}")
            continue
        rows = b["rows"]
        if not rows:
            lines.append(f"- **{name}**: '{category or ''}' 관련 정보가 없습니다.")
            continue
        any_data = True
        for r in rows:
            amounts = r.get("amounts") or []
            tables = r.get("tables") or []
            vflag = r.get("violation_flag")
            unit_ok = r.get("amount_unit_detected") is not None
            badge = "" if unit_ok or not amounts else " ⚠️단위미확인"
            # 2026-09-19(라운드3 작업지시 1번): [브랜드-카테고리-조항명] 인용 태그를 답변
            # 본문에 그대로 박아넣지 않는다 — 같은 정보가 이미 출처 칩(citations/sources)으로
            # 따로 표시되고 있어서 중복이었다(citations 자체는 여전히 append해서 칩 렌더링에
            # 씀). "[canonical_title]"만 있는 라벨은 citation_tag()와 다른 정보(이 줄이
            # 카테고리 안의 어떤 항목인지)라 그대로 남긴다.
            c = build_citation(r)
            citations.append(c)
            if vflag is not None:
                lines.append(f"- **{name}** [{r.get('canonical_title')}]: {vflag}")
            elif amounts:
                # 2026-09-15 (작업로그 (32)): 코드가 먼저 그룹핑(group_amounts) -> 그 결과를
                # LLM이 자연스러운 문장으로(generate_grouped_narrative) -> 숫자 검증 실패/LLM
                # 오류 시 결정론적 폴백(format_grouped_fallback) 순서. 숫자 자체는 항상 원본
                # amounts에서만 나온다(LLM이 재생성하지 않음).
                groups = group_amounts(amounts)
                narrative = generate_grouped_narrative(
                    question, name, r.get("canonical_title"), groups,
                    other_brand_names=other_brand_names,
                )
                amt_line = narrative or format_grouped_fallback(groups)
                lines.append(f"- **{name}** [{r.get('canonical_title')}]: {amt_line}{badge}")
            elif tables and (table_block := _format_tables_as_answer(tables)):
                # 2026-09-15 (작업로그 (36)): 03_extract_clauses.py의 amounts 추출이 "원" 단위
                # 금액 패턴만 잡아서, 로열티/교육비/평균매출액처럼 시간(일)ㆍ비율(%) 등 금액이
                # 아닌 값 위주인 표는 amounts가 비어있는 채로 tables만 남는 경우가 흔함(카테고리별
                # 20~83%, 실측치는 docs/DESIGN.md 개발 기록 참고). 이걸 그냥 text 안내문 스니펫으로
                # 폴백시키면 알맹이(예: "신규 교육 2일")가 안 보이는 게 문제였음 — text[:150]
                # 폴백 대신 표를 그대로(LLM 없이, 단위 변환 없이) 보여준다. tables가 있어도
                # 전부 빈 행이라 렌더링할 게 없으면(_format_tables_as_answer가 None) 아래
                # else의 text 스니펫 폴백으로 자연스럽게 넘어간다.
                lines.append(f"- **{name}** [{r.get('canonical_title')}]: {table_block}")
            else:
                snippet = (r.get("text") or "")[:150]
                lines.append(f"- **{name}** [{r.get('canonical_title')}]: {snippet}")

    answer = "\n".join(lines) if lines else "조회된 정보가 없습니다."
    if not any_data:
        answer += "\n\n(주의: 해당 브랜드/카테고리로 조회된 데이터가 없습니다. 이 서비스는 공정거래위원회 API로 수집되는 브랜드만 다룹니다.)"
    return {"answer": answer, "citations": citations}


def assemble_narrative_answer(question: str, per_brand: list[dict]) -> dict:
    """per_brand: [{"brand_mnno":.., "display_name":.., "found": bool, "hits": [vector hit,...]}]
    서술형 카테고리 답변 — LLM이 검색된 원문만 근거로 비교/요약 문장을 만든다.

    2026-09-15 (작업로그 (34)): 각 hit의 text(표 내용이 빠져있음, 작업로그 (23))만으로는
    "필수구입물품"처럼 답이 표(품목/가격 리스트)로 되어 있는 카테고리를 못 다뤄서, 여기서
    data.find_row()로 원본 row를 다시 가져와 표/금액을 컨텍스트에 추가한다. 표에서 온 숫자도
    구조화 경로와 같은 원칙으로 환각 여부를 검증하고, attachment_refs가 있으면 별도로
    캐비엇을 붙인다(app.py의 render_attachment_note()와 같은 안내 취지)."""
    citations = []
    context_blocks = []
    valid_amounts: set = set()
    attachment_tags: set = set()
    for b in per_brand:
        name = b["display_name"]
        if not b["found"]:
            context_blocks.append(f"[{name}]: ({not_found_reason_text(b)})")
            continue
        hits = b.get("hits") or []
        if not hits:
            context_blocks.append(f"[{name}]: (관련 조항이 검색되지 않음)")
            continue
        block_lines = [f"[{name}]"]
        for h in hits:
            c = build_citation(h)
            citations.append(c)
            tag = citation_tag(c)
            hit_text = h["text"][:800]
            block_lines.append(f"{tag} {h.get('canonical_title')}: {hit_text}")
            # 2026-09-15 (작업로그 (35)): amounts는 표 셀에서만 뽑히므로(03_extract_clauses.py),
            # 서술형 카테고리의 text(산문)에 문장으로 박힌 금액("위약벌 1,000만원" 등)은
            # valid_amounts에 없어서 LLM이 원문을 정확히 인용해도 false positive로 캐비엇이
            # 붙는 문제가 있었음 — 컨텍스트로 실제 넘긴 hit_text(이미 [:800]로 자른 것, LLM이
            # 못 본 부분의 숫자를 인용할 리 없으므로 그 이상은 스캔할 필요 없음)에서도 금액을
            # 뽑아 valid_amounts에 같이 넣는다.
            valid_amounts.update(_extract_amounts_from_text(hit_text))

            row = data.find_row(h.get("brandMnno"), h.get("attr"), h.get("jngIfrmpSn"))
            if row is None:
                continue  # 인용 정보로 원본 row를 못 찾으면 그냥 넘어감(에러 내지 않음)
            row_amounts = row.get("amounts") or []
            for a in row_amounts:
                if a.get("amount_won") is not None:
                    valid_amounts.add(a["amount_won"])
            tables_block = _format_tables_for_context(row.get("tables"))
            if tables_block:
                block_lines.append(f"{tag} [표 원본] {tables_block}")
            amounts_block = _format_amounts_for_context(row_amounts)
            if amounts_block:
                block_lines.append(f"{tag} [금액] {amounts_block}")
            # 2026-09-20(라운드4 작업지시 2번): 원문에 "별첨 참고" 문구가 있다는 것만으로
            # 경고를 붙이면, 정보공개서 특성상 표 뒤에 상투적으로 붙는 "세부내용은 별첨
            # 참고" 문구 때문에 실제로 amounts/tables가 멀쩡히 파싱된 행(예: 빽다방 "최초
            # 가맹금")에도 경고가 뜬다는 걸 데이터 대조로 확인함. "원문이 별첨을 언급하는가"가
            # 아니라 "이 행이 실제 파싱된 데이터 없이 별첨 참고만 있는가"로 조건을 좁힌다 —
            # amounts/tables 중 하나라도 있으면(=이 행 자체로 답이 되면) 경고를 안 붙이고,
            # 정말 데이터가 없는 행(핸델앤그레텔 "가맹점 운영에 필요한 설비 등 공급업체" 등,
            # 문구만 있고 표/금액이 실제로는 비어있는 경우)에만 경고가 남는다.
            if row.get("attachment_refs") and not row_amounts and not row.get("tables"):
                attachment_tags.add(tag)
        context_blocks.append("\n".join(block_lines))

    context = "\n\n".join(context_blocks)
    user_content = f"질문: {question}\n\n검색된 조항 원문:\n{context}"
    messages = [
        {"role": "system", "content": _NARRATIVE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        text = call_llm(messages)
    except LLMError as e:
        text = f"(LLM 답변 생성 실패: {e})\n\n검색된 원문:\n{context[:2000]}"
    else:
        text = _strip_citation_tags(text)
        # 표에서 온 금액도 컨텍스트에 들어가므로, 구조화 경로와 같은 숫자 검증을 여기도 적용한다.
        # 서술형엔 구조화처럼 깔끔한 결정론적 폴백 템플릿이 없어서, 검증 실패 시 답변을 버리지
        # 않고 캐비엇만 덧붙인다(정직하게 알리는 게 목적 — 무리한 재작성은 안 함).
        if valid_amounts and not _verify_numbers(text, valid_amounts):
            text += (
                "\n\n⚠️ 위 답변에 포함된 일부 숫자가 원문과 자동 대조되지 않았습니다 — "
                "출처 원문을 직접 확인해 주세요."
            )

    if attachment_tags:
        tags_str = ", ".join(sorted(attachment_tags))
        text += (
            f"\n\n⚠️ 다음 항목은 원문에 별첨/별지 참조가 있어 실제 세부 내용(예: 품목 목록)이 "
            f"이 데이터에는 포함되어 있지 않을 수 있습니다: {tags_str}. 가맹본부에 정보공개서 "
            f"원본 제공을 요청하거나 공정거래위원회 가맹거래정보시스템"
            f"(https://franchise.ftc.go.kr)에서 직접 확인하실 수 있습니다."
        )

    return {"answer": text, "citations": citations}
