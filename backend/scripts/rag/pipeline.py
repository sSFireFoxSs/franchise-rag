"""0~4단계를 엮는 단일 진입점.

app.py(Streamlit)든 나중의 FastAPI든 이 모듈의 answer_question() 하나만 호출하면 된다.
이 파일에는 streamlit import가 없어야 한다.
"""
import re
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from section_schema import STRUCTURED_CATEGORIES, TOTAL_COST_CATEGORY  # noqa: E402

from . import answer, brand_match, data, retrieval, total_cost
from .llm import LLMError, call_llm_json  # noqa: F401  (재수출용, CLI 테스트 등에서 씀)
from .nlu import extract_slots

COVERAGE_MSG = (
    "죄송합니다, 이 질문은 현재 서비스가 다루는 범위 밖입니다. 이 서비스는 정보공개서의 "
    "가맹비/가맹금·보증금·교육비·로열티·평균매출액·행정처분·계약해지·필수구입물품·영업지역·"
    "소송/법위반·위약금 조항만 다룹니다."
)

# 2026-09-19(라운드3 작업지시 6번): "육시리 창업하는데 총 얼마나 들어?"류 질문이 NLU에서
# 가끔 intent=금액조회인데 category=None으로 빠져서 total_cost.py 전용 계산 대신 일반
# 벡터서치로 새고, 완전히 엉뚱한 숫자(예: 연간 원재료 거래 총액)를 총창업비용인 것처럼
# 답한 사례가 있었음(지난 OpenAI 테스트 라운드 실측 — 이 세션에서는 Ollama로 재현 시도했으나
# 8회 전부 정상 분류돼서 재현은 못 했음, 그래도 nlu.py 프롬프트 보강만으로는 다른 LLM
# 백엔드/문구에서 또 발생할 수 있으니 코드 레벨 안전망을 같이 둔다). category가 애초에
# null일 때만(모델이 이미 다른 카테고리를 명확히 골랐으면 존중하고 덮어쓰지 않음) 이
# 키워드들로 최소한의 교정을 한다.
_TOTAL_COST_FALLBACK_RE = re.compile(r"창업\s*비용|초기\s*비용|초기\s*투자|총\s*얼마")


def answer_question(
    question: str,
    forced_brand_mnno: "str | None" = None,
    conversation_context: "list[dict[str, str]] | None" = None,
) -> dict:
    """반환값: {"answer": str, "citations": [{"brandMnno","brandNm","category",
    "canonical_title","attr","jngIfrmpSn"}, ...], "intent", "category", "canonical_title",
    "brands_resolved": [brandMnno,...], "brands_unresolved": [text,...]}

    2026-09-19(라운드3 작업지시 0번): forced_brand_mnno는 동명이인(ambiguous) 브랜드 추천
    버튼 클릭 전용 경로 — "피자스쿨" 같은 이름이 서로 다른 법인 brandMnno 여러 개에 걸리는
    경우, 후보 버튼의 표시 텍스트에 구분용 법인명/개시연도 라벨이 붙어있어서(예: "피자스쿨
    ((주)씨에이치컴퍼니, 2012년 개시)") 기존 방식(질문 문장의 브랜드 텍스트를 후보
    display_name으로 치환해서 재질문)을 그대로 쓰면 그 라벨 문자열이 brand_index에 등록된
    별칭이 아니라서 다시 매칭에 실패하거나, 라벨 없이 원래 이름 그대로 재질문하면 여전히
    똑같은 동명이인 후보가 나와서 무한 반복된다. 이미 어떤 brandMnno인지 확정된 상태이므로
    브랜드 인식 단계(resolve/find_in_text/문제 판정) 자체를 건너뛰고 그 mnno 하나로 바로
    진행한다 — NLU(intent/category/canonical_title)는 그대로 돌려서 원래 질문의 의도는
    그대로 살린다."""
    question = (question or "").strip()
    if not question:
        return _empty_result(question, answer="질문을 입력해 주세요.")

    try:
        slots = extract_slots(
            question,
            conversation_context=conversation_context,
        )
    except LLMError as e:
        return _empty_result(question, answer=f"질문을 이해하지 못했습니다. (LLM 오류: {e})")

    intent = slots["intent"]
    if intent == "커버불가" and not forced_brand_mnno:
        return _coverage_response(question, slots, intent)

    brand_texts = slots["brands"]
    if not brand_texts:
        # 2026-09-17 (작업로그 (41)): 예전엔 여기서 바로 포기하고 "브랜드명을 찾지 못했다"고
        # 반환했음 — 그런데 바로 아래 루프에는 "AI가 브랜드명을 찾았지만 틀리게 찾았을 때"만
        # find_in_text(question)으로 질문 원문을 재탐색하는 안전장치가 있어서, "AI가 브랜드명을
        # 아예 하나도 못 찾았을 때"는 이 안전장치를 탈 기회조차 없었음(실측: "비비큐 창업
        # 비용 총 얼마정도 들어?"가 이 경로로 실패 — 로컬 LLM 비결정성 때문에 표현을 조금만
        # 바꿔도 성공/실패가 갈림, "비비큐 초기 창업 비용이 대략 얼마나 돼?"는 이 버그를 안
        # 만나고 성공했었음). 질문 원문 전체를 단일 텍스트 후보로 넣어서 기존
        # resolve()->find_in_text() 흐름을 그대로 타게 한다 — resolve(question)은 질문
        # 전체가 정확히 브랜드명과 일치할 일이 거의 없어 보통 실패하고, find_in_text(question)
        # 이 질문 문장 안에서 등록된 브랜드명을 부분 문자열로 찾아낸다(새 코드 없이 기존
        # 로직 재사용). 이것도 실패하면 unresolved에 들어가서 difflib+LLM 후보 제안
        # (_suggest_for_unresolved(), 작업로그 (39)(40)(41))까지 자동으로 받게 된다(부가 효과).
        brand_texts = [question]

    # 2026-09-16 (작업로그 (39)): 브랜드가 하나도 안 풀렸을 때도(아래 `if not resolved`)
    # 이후 추천 브랜드를 클릭했을 때 원래 질문의 category/canonical_title/use_structured를
    # 그대로 재사용해야 하므로, 이 계산을 브랜드 해석보다 먼저(실패 여부와 무관하게) 해둔다.
    # 2026-09-20(라운드4 작업지시 5번): slots["category"](단일)가 slots["categories"](리스트)로
    # 바뀌었다 — "필수구매목록이랑 월매출 비교해줘"처럼 카테고리가 여러 개 언급되면 전부 담아서
    # 아래에서 카테고리별로 반복 처리한다(_answer_for_category 참고). canonical_title은
    # nlu.py가 이미 categories 1개일 때만 채워주므로 여기서 추가로 손댈 필요 없다.
    categories = list(slots["categories"])
    canonical_title = slots["canonical_title"]
    if not categories and intent == "금액조회" and _TOTAL_COST_FALLBACK_RE.search(question):
        categories = [TOTAL_COST_CATEGORY]
        canonical_title = None
    # "not resolved" 분기(브랜드 인식 실패)와 추천 버튼 재질의 흐름을 위한 대표 카테고리 —
    # 카테고리가 여러 개여도 이 필드들은 단일 값 하위호환 용도라 첫 번째만 대표로 쓴다(실제
    # per-category 처리는 브랜드가 정상 resolve된 뒤 아래에서 카테고리별로 전부 순회한다).
    primary_category = categories[0] if categories else None
    use_structured = bool(primary_category) and primary_category in STRUCTURED_CATEGORIES
    # 2026-09-17 (작업로그 (41)): "총창업비용"은 attr 기반 실제 카테고리가 아니라
    # total_cost.py가 여러 카테고리 합계를 모아 계산하는 합성 카테고리라 별도 분기로 뺀다
    # (use_structured와는 배타적 — retrieval.structured_lookup()을 그대로 안 쓰고
    # total_cost.compute_total_startup_cost()가 내부에서 여러 번 호출한다).
    use_total_cost = primary_category == TOTAL_COST_CATEGORY

    brand_index = brand_match.get_brand_index()
    known = data.known_brand_mnnos()

    # 2026-09-15: "이름 인식"과 "데이터 존재 여부"를 분리한다(작업로그 (31) 참고). 예전엔
    # resolve()/find_in_text() 호출 시점에 known_mnnos로 후보를 걸러버려서 "이름 자체를 모름"과
    # "이름은 brand_unified.jsonl에 있지만 정보공개서 데이터가 없음"이 구분이 안 됐음(둘 다
    # 그냥 "브랜드를 찾을 수 없습니다"로 나가서, 오타 때문에 못 찾은 것처럼 오해를 줬음 —
    # 실측: "매머드커피집" 질문). 여기서는 먼저 known_mnnos 없이 이름 레벨 후보를 구하고, 그
    # 다음에 데이터 보유 여부를 별도로 판정한다.
    resolved: list[tuple[str, str]] = []  # (원문 텍스트, brandMnno) — 데이터까지 확정된 것
    unresolved: list[str] = []  # 이름 자체를 못 찾음(brand_unified.jsonl에도 없음)
    problems: list[dict] = []  # 이름은 찾았지만 자동으로 하나로 못 정한 경우
    # 2026-09-20(라운드4 작업지시 1번): NLU가 같은 브랜드를 slots["brands"]에 두 번 넣는
    # 경우가 실측됨(예: 비교 질문에서 brands=["육시리","육시리"]) — 텍스트 표현이 같든
    # 다르든("육시리"/"육 시리") 최종적으로 같은 brandMnno로 풀리면 resolved에 중복으로
    # 쌓여서 assemble_*_answer()가 같은 블록을 그대로 두 번 출력했다. brandMnno 기준으로
    # 이미 확정된 것은 다시 추가하지 않는다.
    seen_resolved_mnnos: set[str] = set()
    if forced_brand_mnno:
        # 동명이인 추천 버튼 클릭 — 브랜드 인식 단계를 통째로 건너뛰고 이 mnno 하나로 확정.
        resolved = [(question, forced_brand_mnno)]
        seen_resolved_mnnos.add(forced_brand_mnno)
        brand_texts = []
    for text in brand_texts:
        name_candidates = brand_index.resolve(text)
        if not name_candidates:
            # LLM이 브랜드명을 부정확하게 옮겨 적었을 수 있음(축약/오탈자/한자 오염 실측됨) ->
            # LLM 출력이 아니라 사용자가 실제로 입력한 질문 원문에서 한 번 더 찾아본다.
            name_candidates = brand_index.find_in_text(question)
        if not name_candidates:
            unresolved.append(text)
            continue
        data_candidates = [m for m in name_candidates if m in known]
        if len(data_candidates) == 1:
            # 동명이인(같은 정규화 이름에 brandMnno 여러 개)이었어도 데이터 있는 후보가
            # 정확히 1개면 그걸로 확정(추측이 아니라 "데이터로 저절로 하나만 남는" 결정론적 상황).
            mnno = data_candidates[0]
            if mnno in seen_resolved_mnnos:
                continue  # 이미 같은 브랜드가 resolved에 있음 — 중복 텍스트로 답변을 또 만들지 않음
            seen_resolved_mnnos.add(mnno)
            resolved.append((text, mnno))
        elif not data_candidates:
            # 이름은 확인되지만(brand_unified.jsonl에 있음) 정보공개서 데이터가 없음 — "오타라서
            # 못 찾은 것"과 다르다는 걸 메시지에서 명시해야 함(실측: 매머드커피).
            names = _format_candidate_names(brand_index, name_candidates)
            problems.append({"text": text, "reason": "no_data", "names": names})
        else:
            # 이름 후보가 여럿인데 데이터 있는 것도 2개 이상이라 자동으로 하나를 못 정함.
            # RAG 아키텍처 설계 0단계 원칙("매칭이 안 되면 추측하지 않고 확인한다")대로,
            # 데이터가 더 많은 쪽을 조용히 채택하던 예전 로직을 버리고 후보를 나열한다.
            names = _format_candidate_names(brand_index, data_candidates)
            problems.append({"text": text, "reason": "ambiguous", "names": names, "mnnos": data_candidates})

    # 2026-09-20(라운드4 작업지시 4번): NLU가 복합 브랜드명을 여러 조각으로
    # 쪼개서 slots["brands"]에 넣는 경우가 있음(예: "곱돌이곱창" -> ["곰돌이","곱창"], 기존
    # 작업로그의 "170도시까스" -> ["백칠십도시","도시가스"]와 같은 뿌리). 각 조각이 개별
    # 텍스트로 resolve()/find_in_text() 둘 다 실패해서 전부 unresolved로 빠지면, 이후
    # brand_suggestions 계산 단계에서 조각마다 _suggest_for_unresolved()를 시도해도
    # brand_match.py의 suggest_similar()가 정규화 후 4글자 미만인 텍스트는 애초에 비교
    # 대상에서 빼버려서("곰돌이" 3글자, "곱창" 2글자 둘 다 min_len=4 미만) 후보 제안조차
    # 안 뜬다(직접 실측 확인). brand_texts 전체가 하나도 못 풀렸을 때만(부분적으로라도
    # 풀렸으면 이 폴백은 안 함 — 이미 뭔가 맞았는데 병합까지 시도하면 오히려 혼란을 줄 수
    # 있음), 실패한 텍스트들을 원래 순서대로 공백 없이 이어붙인 문자열 하나로
    # resolve()/find_in_text()를 한 번 더 시도한다 — 새로운 매칭 방식이 아니라 이미 있는
    # resolve()에 다른(합쳐진) 입력을 한 번 더 넣어보는 것이라 안전하다(추측성 매칭 아님).
    if not resolved and not problems and len(unresolved) >= 2:
        merged_text = "".join(unresolved)
        merged_candidates = brand_index.resolve(merged_text) or brand_index.find_in_text(question)
        merged_data_candidates = [m for m in merged_candidates if m in known]
        if len(merged_data_candidates) == 1:
            resolved.append((merged_text, merged_data_candidates[0]))
            unresolved = []
        elif merged_data_candidates:
            names = _format_candidate_names(brand_index, merged_data_candidates)
            problems.append({"text": merged_text, "reason": "ambiguous", "names": names, "mnnos": merged_data_candidates})
            unresolved = []
        elif merged_candidates:
            names = _format_candidate_names(brand_index, merged_candidates)
            problems.append({"text": merged_text, "reason": "no_data", "names": names})
            unresolved = []
        else:
            # 정확 매칭은 여전히 실패 -> 병합한 문자열 하나로 unresolved를 교체해서, 아래
            # brand_suggestions 계산이 이 병합 문자열로 fuzzy 추천(suggest_similar)을
            # 시도하게 한다(min_len=4를 통과할 만큼 길어짐 — "곰돌이"+"곱창"=5글자).
            unresolved = [merged_text]

    # 2026-09-20(라운드4 작업지시 3번): brand_suggestions(클릭 가능한 후보 버튼) 계산을
    # "resolved가 비었을 때"뿐 아니라 항상 하도록 뺐다 — 예전엔 이 계산이 `if not resolved:`
    # 분기 안에만 있어서, 비교 질문처럼 브랜드 하나는 정상 resolve되고 나머지 하나만
    # 동명이인/미해결인 경우("빽보이피자랑 피자스쿨 비교해줘") 이 분기 자체를 건너뛰어버려
    # 미해결 브랜드가 텍스트 안내(not_found_reason_text, answer.py)로만 나오고
    # brand_suggestions는 항상 빈 리스트로 끝났다(실측 확인). 텍스트 메시지 생성은 이미
    # answer.py의 assemble_*_answer()가 per_brand의 found=False 항목마다 처리하고 있으므로
    # 안 건드리고, 여기서는 candidates만 공통으로 계산해서 양쪽 분기(resolved 있음/없음)에
    # 그대로 꽂아 넣는다.
    brand_suggestions: list[dict] = []
    for t in unresolved:
        candidates = _suggest_for_unresolved(brand_index, t, question)
        if candidates:
            brand_suggestions.append({"text": t, "candidates": candidates})
    for p in problems:
        if p["reason"] == "ambiguous":
            brand_suggestions.append({
                "text": p["text"],
                "candidates": _ambiguous_candidates(brand_index, p["mnnos"]),
            })

    if not resolved:
        # 2026-09-16 (작업로그 (39)): reason="unresolved"(이름 자체를 brand_unified.jsonl
        # 에서도 못 찾음)인 경우에만 문자열 유사도 기반 추천을 붙인다. no_data/ambiguous는
        # 이미 실제 후보(이름은 확인된 것)를 나열해주고 있어서 손대지 않는다.
        lines = []
        suggestions_by_text = {s["text"]: s["candidates"] for s in brand_suggestions}
        for t in unresolved:
            lines.append(_unresolved_message(t, reason="unresolved"))
            candidates = suggestions_by_text.get(t)
            if candidates:
                names = ", ".join(c["display_name"] for c in candidates)
                lines.append(f"  혹시 이 중 하나였나요?: {names}")
        lines += [_unresolved_message(p["text"], reason=p["reason"], names=p["names"]) for p in problems]
        result = _empty_result(question, answer="\n".join(lines), intent=intent)
        # 어떤 텍스트가 왜 안 풀렸는지 로그/평가에서 보이게
        result["brands_unresolved"] = unresolved + [p["text"] for p in problems]
        # 추천 브랜드를 클릭했을 때(app.py) nlu.py를 다시 안 거치고 바로 조회할 수 있도록
        # 이번 질문에서 이미 뽑아둔 슬롯을 그대로 실어보낸다(category/canonical_title이
        # 애초에 null이면 null 그대로 — 이 경우 app.py는 "어떤 정보가 궁금한지" 되묻는다).
        result["category"] = primary_category
        result["categories"] = categories
        result["canonical_title"] = canonical_title
        result["use_structured"] = use_structured
        result["use_total_cost"] = use_total_cost
        result["brand_suggestions"] = brand_suggestions
        return result

    # 2026-09-20(라운드4 작업지시 5번): 카테고리 1개당 기존 로직(per_brand 구성 ->
    # assemble_*_answer)을 한 번씩 호출하는 방식으로 재구현했다 — 브랜드 여러 개를
    # 순회하던 기존 패턴과 동일하게, 카테고리도 그냥 순회한다. 카테고리가 1개(또는 0개)인
    # 기존 질문은 이 루프가 정확히 한 번만 돌아서 예전과 완전히 동일하게 동작한다(회귀 방지
    # 핵심 — 골드셋 40문항으로 확인).
    if not categories:
        categories = [None]
    sections: list[dict] = []
    for cat in categories:
        cat_canonical_title = canonical_title if len(categories) == 1 else None
        sections.append(_answer_for_category(
            question, cat, cat_canonical_title, resolved, unresolved, problems, brand_index,
        ))

    if len(sections) == 1:
        # 기존(카테고리 1개) 동작과 완전히 동일 — 소제목 없이 답변 텍스트 그대로.
        sec = sections[0]
        result = {"answer": sec["answer"], "citations": sec["citations"]}
        final_use_structured = sec["use_structured"]
        final_use_total_cost = sec["use_total_cost"]
    else:
        # 카테고리가 여러 개면 "**카테고리명**" 소제목으로 구분해서 전부 이어붙인다. 어느
        # 카테고리는 데이터가 있고 어느 카테고리는 없어도, 각 assemble_*_answer()가 이미
        # 그 카테고리 안에서 "데이터 없음"을 정직하게 명시하므로(any_data 체크, answer.py)
        # 여기서는 그 결과를 그대로 소제목 아래에 붙이기만 한다 — 조용히 누락되는 카테고리가
        # 없다.
        blocks = [f"**{sec['category'] or '기타'}**\n\n{sec['answer']}" for sec in sections]
        all_citations = [c for sec in sections for c in sec["citations"]]
        result = {"answer": "\n\n---\n\n".join(blocks), "citations": all_citations}
        final_use_structured = False
        final_use_total_cost = False

    result.update({
        "intent": intent,
        "category": categories[0] if categories and categories[0] else None,
        "categories": [c for c in categories if c],
        "canonical_title": canonical_title if len(categories) == 1 else None,
        "use_structured": final_use_structured,
        "use_total_cost": final_use_total_cost,
        "brands_resolved": [m for _, m in resolved],
        "brands_unresolved": unresolved + [p["text"] for p in problems],
        "brand_suggestions": brand_suggestions,
    })
    return result


def _answer_for_category(
    question: str,
    cat: "str | None",
    canonical_title: "str | None",
    resolved: list[tuple[str, str]],
    unresolved: list[str],
    problems: list[dict],
    brand_index,
) -> dict:
    """카테고리 1개에 대해 per_brand를 구성하고 answer.assemble_*_answer()를 호출한다
    (라운드4 작업지시 5번). 기존에 answer_question() 안에 딱 한 번만 있던 로직을 그대로
    빼낸 것 — 카테고리가 1개(또는 0개)인 기존 질문은 answer_question()이 이 함수를 정확히
    한 번만 호출하므로 이전과 완전히 동일하게 동작한다(회귀 방지 핵심). 반환값에
    "category"/"use_structured"/"use_total_cost"까지 같이 담아서 호출부가 여러 카테고리를
    구분/합산할 때 참고할 수 있게 한다."""
    use_structured_cat = bool(cat) and cat in STRUCTURED_CATEGORIES
    use_total_cost_cat = cat == TOTAL_COST_CATEGORY

    per_brand = []
    for text, mnno in resolved:
        display = data.display_name_for(mnno) or brand_index.display_name(mnno)
        if use_total_cost_cat:
            total_result = total_cost.compute_total_startup_cost(mnno)
            # 2026-09-19(라운드3 작업지시 2번): "BSK기준으로만 계산해줘"처럼 매장 타입이
            # 여러 개인(mode="multi") 브랜드에서 질문이 그중 하나를 콕 집어 말하면, 그
            # 타입 하나만으로 다시 계산한다(전체 타입 나열 대신). 타입 이름을 미리 알 수
            # 없으므로(브랜드마다 다름) 필터 없이 한 번 계산해서 실제 존재하는 타입 토큰과
            # 질문 문장을 대조하고, 정확히 하나만 겹칠 때만 필터를 적용한다(애매하면 안전하게
            # 전체 타입을 그대로 보여줌 — 추측하지 않는다는 이 프로젝트 원칙과 동일).
            if total_result.get("mode") == "multi":
                type_filter = _detect_type_filter(question, total_result["components"])
                if type_filter:
                    total_result = total_cost.compute_total_startup_cost(mnno, type_filter=type_filter)
            per_brand.append({
                "brand_mnno": mnno, "display_name": display, "found": True,
                "total_result": total_result,
            })
        elif use_structured_cat:
            rows = retrieval.structured_lookup(mnno, category=cat, canonical_title=canonical_title)
            per_brand.append({"brand_mnno": mnno, "display_name": display, "found": True, "rows": rows})
        else:
            try:
                hits = retrieval.vector_search(mnno, question, category=cat)
            except RuntimeError:
                hits = []  # 벡터DB 미구축 등 — 빈 결과로 처리하고 answer.py가 "정보 없음"으로 안내
            per_brand.append({"brand_mnno": mnno, "display_name": display, "found": True, "hits": hits})
    for text in unresolved:
        per_brand.append({"brand_mnno": None, "display_name": text, "found": False, "reason": "unresolved"})
    for p in problems:
        per_brand.append({
            "brand_mnno": None, "display_name": p["text"], "found": False,
            "reason": p["reason"], "names": p["names"],
        })

    if use_total_cost_cat:
        result_cat = answer.assemble_total_cost_answer(question, per_brand)
    elif use_structured_cat:
        result_cat = answer.assemble_structured_answer(question, cat, per_brand)
    else:
        result_cat = answer.assemble_narrative_answer(question, per_brand)

    return {
        "answer": result_cat.get("answer", ""),
        "citations": result_cat.get("citations") or [],
        "category": cat,
        "use_structured": use_structured_cat,
        "use_total_cost": use_total_cost_cat,
    }


def _coverage_response(question: str, slots: dict, intent: str) -> dict:
    """라운드2 작업지시 2번 실측: intent="커버불가"로 분류돼도 NLU가 브랜드명은 뽑아내는
    경우가 실제로 있음(예: "도미노피자 분쟁조정 받은 적 있어?" -> brands=["도미노피자"],
    분쟁조정은 이 서비스가 안 다루는 주제지만 브랜드명 자체는 정확히 인식됨). 예전엔
    intent="커버불가"면 브랜드 인식 자체를 아예 시도하지 않고 바로 COVERAGE_MSG만
    반환했는데, 이러면 "브랜드 이름은 맞게 불렀는데도 그냥 범위 밖 취급"당하는 느낌을
    주고, 오타/축약 등으로 브랜드명이 부정확한 경우 fuzzy 추천 기회도 못 받는다. brands가
    비어있으면(자유 서술형 문장에 브랜드가 파묻혀 NLU도 못 뽑아낸 경우, 예: "이름이 잘
    기억 안나는데 고깃집중에 무슨 시리?") 기존과 동일하게 COVERAGE_MSG만 반환한다 — 이
    경우는 brand_match.py에 남겨둔 실측 메모대로, 문자열 유사도만으로는 신호/잡음을
    구분할 수 없어서 억지로 후보를 보여주지 않는다(정직하게 범위 밖으로 안내)."""
    brand_texts = slots.get("brands") or []
    if not brand_texts:
        # 2026-09-19(라운드3 작업지시 5번): 지난 라운드에서 슬라이딩 윈도우 문자열 유사도로
        # 이 케이스(브랜드 텍스트 자체를 못 뽑음)까지 알고리즘적으로 추측해보려다가, 짧은
        # 한국어 브랜드명은 자유 서술형 문장 아무 데서나 우연히 겹쳐서 오탐과 정답을 점수로
        # 구분할 수 없음을 실측 확인하고 폐기했다(brand_match.py 주석 참고) — 같은 접근을
        # 다시 시도하지 않는다. 대신 사용자가 스스로 다시 검색해서 브랜드 텍스트가 조금이라도
        # 나오게(오타/축약이어도 괜찮음 — 아래 else 분기의 fuzzy 추천이 이미 처리) 안내
        # 문구만 덧붙인다. "이미 구현된 브랜드 추천/선택 UI"는 브랜드 텍스트가 하나라도
        # 있어야 동작하므로(아래 for 루프), 여기서는 그 UI로 유도하는 문구만 맡는다.
        guidance = (
            f"{COVERAGE_MSG}\n\n혹시 특정 브랜드를 찾고 계신 거라면, 정확한 이름이 "
            "기억나지 않아도 괜찮으니 브랜드 이름과 궁금하신 정보(가맹비, 보증금, "
            "평균매출액 등)를 함께 다시 질문해 주세요. 예: \"육시리 가맹비 얼마야?\""
        )
        return _empty_result(question, answer=guidance, intent=intent)

    brand_index = brand_match.get_brand_index()
    known = data.known_brand_mnnos()
    lines = []
    brand_suggestions = []
    for text in brand_texts:
        name_candidates = brand_index.resolve(text) or brand_index.find_in_text(question)
        data_candidates = [m for m in name_candidates if m in known]
        if len(data_candidates) == 1:
            mnno = data_candidates[0]
            display = data.display_name_for(mnno) or brand_index.display_name(mnno)
            lines.append(f"'{display}' 브랜드는 확인했습니다.")
        elif name_candidates:
            names = _format_candidate_names(brand_index, data_candidates or name_candidates)
            lines.append(f"'{text}'는 {', '.join(names)}로 확인됩니다.")
        else:
            candidates = _suggest_for_unresolved(brand_index, text, question)
            if candidates:
                names = ", ".join(c["display_name"] for c in candidates)
                lines.append(f"'{text}' 브랜드명은 정확히 확인하지 못했습니다 — 혹시 {names} 중 하나였나요?")
                brand_suggestions.append({"text": text, "candidates": candidates})
            else:
                lines.append(f"'{text}' 브랜드를 찾지 못했습니다.")
    lines.append(COVERAGE_MSG)
    result = _empty_result(question, answer="\n".join(lines), intent=intent)
    result["brand_suggestions"] = brand_suggestions
    return result


@lru_cache(maxsize=1)
def _digit_brand_candidates(brand_index) -> dict:
    """mnno_to_display 중 표시 이름이 숫자로 시작하는 것만 뽑아 {표시이름: brandMnno}로
    반환한다(작업로그 (40)). "101프렙"/"60계"처럼 숫자로 시작하는 브랜드가 167개(2026-09-16
    실측, brand_unified.jsonl 기준)나 되는데, 한글로 읽는 방식이 브랜드마다 제각각이라
    ("101프렙"->자릿수 읽기 "일공일", "60계"->숫자 그대로 읽기 "육십계") 문자열 유사도
    (suggest_similar())로는 원천적으로 못 잡는다("일공일"과 "101"은 글자가 하나도 안
    겹침). 이 변환 규칙을 하드코딩하는 대신 _llm_pick_candidate_brand()가 이 목록을
    통째로 LLM에게 보여주고 그 안에서만 고르게 한다. brand_index는 get_brand_index()가
    프로세스당 하나만 만드는 싱글턴(브랜드 인덱스는 프로세스 생애 동안 안 바뀜)이라, 매
    질문마다 12,498개 브랜드를 다시 훑지 않도록 여기서도 한 번만 계산해서 캐시한다."""
    return {
        name: mnno
        for mnno, name in brand_index.mnno_to_display.items()
        if name and name[0].isdigit()
    }


_DIGIT_BRAND_SYSTEM_PROMPT = """다음은 실제로 등록된 프랜차이즈 브랜드명 목록이다. 사용자가
입력한 텍스트는 이 중 하나를 가리키는 것일 수 있는데, 정확한 표기가 아니라 발음대로, 숫자를
자릿수별 한글로 읽어서(예: "일공일"은 "101"을 뜻함), 또는 축약해서 적었을 수 있다. 아래 목록을
보고 사용자 텍스트가 가리킬 가능성이 있는 것을 목록에 있는 표기 그대로 최대 5개 골라라.
**목록에 없는 이름을 새로 만들어내지 마라.** 해당하는 게 없으면 빈 리스트를 반환해라. 반드시
{"picks": ["...", ...]} 형식의 JSON 객체 하나로만 답하라."""


def _llm_pick_candidate_brand(text: str, question: str, name_to_mnno: dict) -> list[str]:
    """difflib 기반 suggest_similar()가 후보를 하나도 못 찾았을 때만 쓰는 폴백(작업로그
    (40)). LLM에게 실제 등록된 브랜드명 목록(name_to_mnno의 key들)을 통째로 보여주고 그중
    에서만 고르게 한다 — 목록 밖 이름을 자유롭게 만들어내지 못하게 프롬프트에 명시하지만,
    LLM이 그래도 목록에 없는 답을 낼 수 있으므로(hallucination) 여기서는 검증하지 않고
    "LLM이 고른 원본 문자열" 그대로만 반환한다. 실제 목록과의 대조(검증)는 호출부인
    _suggest_for_unresolved()가 한다 — brand_match.py의 계약("LLM 없이 순수 문자열
    유사도")을 지키기 위해 이 LLM 단계는 전부 pipeline.py 안에만 둔다."""
    names = "\n".join(name_to_mnno.keys())
    messages = [
        {"role": "system", "content": _DIGIT_BRAND_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"브랜드명 목록:\n{names}\n\n사용자 입력 텍스트: {text!r}\n질문 원문: {question!r}",
        },
    ]
    try:
        result = call_llm_json(messages, temperature=0.0)
    except LLMError:
        # LLM 호출 실패(타임아웃 등)는 조용히 무시하고 difflib 결과(보통 빈 리스트)만
        # 유지한다 — 이 폴백이 없어도 기존 "찾을 수 없습니다" 흐름으로 자연스럽게 빠진다.
        return []
    picks = result.get("picks")
    if not isinstance(picks, list):
        return []
    return [p for p in picks if isinstance(p, str)]


def _suggest_for_unresolved(brand_index, text: str, question: str) -> list[dict]:
    """reason="unresolved"인 텍스트에 대해 유사 브랜드 후보를 찾는다(작업로그 (39)(40)(41)).
    1단계(문자열 유사도, LLM 미사용): LLM 슬롯추출이 브랜드명의 일부만 뽑는 경우가
    실측됨(예: "일리터셀 와플"에서 "와플"이 빠지고 "일리터셀"만 남음) — find_in_text()가
    실패 시 질문 원문(question) 전체에서 한 번 더 찾아보는 것과 같은 이유로, text만으로
    찾은 후보와 question 전체로 찾은 후보를 병합한다(mnno당 더 높은 점수를 채택).
    2단계(LLM, 숫자 브랜드 목록이 있으면 항상 실행 — 2026-09-17 작업로그 (41) 변경): 원래는
    "1단계가 0개일 때만" 실행했는데, 실측 결과 이 게이트가 사실상 유명무실했음 —
    "일공일프랩 로열티는 어떻게 돼?"("101프렙"의 한글 자릿수읽기+오타)를 테스트해보니
    difflib가 "일공일프랩"과 우연히 글자가 겹치는 무관한 브랜드("일공일 닭곱차" 0.545,
    "일일양"/"일일향"/"오공일" 각 0.5)를 이미 찾아버려서 `by_mnno`가 비어있지 않은 상태가
    되고, 그래서 진짜 필요한 LLM 폴백(_llm_pick_candidate_brand)이 아예 안 돌았음. 4글자
    이상 텍스트는 difflib가 맞든 틀리든 거의 항상 뭔가는 찾아내기 때문에 "0개일 때만"이라는
    조건 자체가 문제였음 — 그래서 숫자로 시작하는 등록 브랜드 목록(digit_candidates)이
    있으면 difflib 결과 유무와 무관하게 항상 LLM 폴백도 같이 돌려서 병합한다(작업로그 (39)가
    text/question 두 difflib 결과를 병합하는 것과 같은 패턴 — mnno당 더 높은 score 채택).
    이 경로는 이미 resolve()/find_in_text()가 둘 다 실패한 폴백 상황이라 LLM 호출 1번
    (~2~3초) 추가되는 건 감수한다(지시사항 그대로).
    LLM에게는 실제 등록된 브랜드명 목록(digit_candidates)을 통째로 보여주고 그 표기 그대로만
    고르게 하며, 응답을 실제 목록의 키와 정확히 일치하는지 재검증해서 통과한 것만 채택한다
    (목록에 없는 걸 답했으면 hallucination으로 보고 버림 — 이게 검증 단계 전부다, 목록
    자체가 이미 brand_unified.jsonl에서 뽑은 것이라 대조가 단순 dict 조회로 끝난다). LLM
    채택 후보는 score를 difflib와 구분되는 고정값(0.99)으로 표시하고 source="llm_pick"을
    붙인다(difflib 후보는 source="difflib") — 최종 확정은 여전히 사용자가 후보 버튼을
    클릭해야만 이뤄지므로(작업로그 (39) UX 그대로), 이 구분은 표시 용도일 뿐 신뢰도 차등
    적용 등 다른 처리에는 쓰이지 않는다."""
    by_mnno: dict[str, dict] = {}
    for c in brand_index.suggest_similar(text):
        c["source"] = "difflib"
        by_mnno[c["brandMnno"]] = c
    if question and question != text:
        for c in brand_index.suggest_similar(question):
            c["source"] = "difflib"
            existing = by_mnno.get(c["brandMnno"])
            if existing is None or c["score"] > existing["score"]:
                by_mnno[c["brandMnno"]] = c

    digit_candidates = _digit_brand_candidates(brand_index)
    if digit_candidates:
        picks = _llm_pick_candidate_brand(text, question, digit_candidates)
        for pick in picks:
            mnno = digit_candidates.get(pick)  # 목록에 정확히 있는 표기만 채택(검증)
            if mnno is None:
                continue
            candidate = {
                "brandMnno": mnno,
                "display_name": brand_index.display_name(mnno),
                "score": 0.99,
                "source": "llm_pick",
            }
            existing = by_mnno.get(mnno)
            if existing is None or candidate["score"] > existing["score"]:
                by_mnno[mnno] = candidate

    candidates = sorted(by_mnno.values(), key=lambda c: c["score"], reverse=True)[:5]
    # 2026-09-17: fuzzy/LLM 후보 리스트에도 _format_candidate_names()와 같은 동명이인
    # 라벨을 붙인다 — 이름이 겹치는 후보(예: "피자스쿨"을 운영하는 서로 다른 두 법인)가
    # fuzzy 후보로 나올 때 구분 없이 "피자스쿨, 피자스쿨"처럼 중복 표시되던 문제 수정.
    # 겹치지 않는 평범한 브랜드는 라벨을 안 붙여서 노이즈를 안 만든다(같은 Counter 패턴).
    from collections import Counter

    name_counts = Counter(c["display_name"] for c in candidates)
    for c in candidates:
        if name_counts[c["display_name"]] > 1:
            label = brand_index.disambiguation_label(c["brandMnno"])
            if label:
                c["display_name"] = f"{c['display_name']}({label})"
    return candidates


def _format_candidate_names(brand_index, mnnos: list[str]) -> list[str]:
    """이름이 겹치는 후보에만 법인명/개시연도 구분 라벨을 괄호로 붙인다(작업로그 (41)).
    brand_unified.jsonl에 brandNm이 완전히 똑같은데 실제로는 다른 법인인 동명이인 브랜드가
    43쌍 있어서(예: "피자스쿨"을 (주)피자스쿨과 (주)씨에이치컴퍼니가 각각 운영), ambiguous/
    no_data 후보 나열 메시지에서 이름만 중복 표시되면 사용자가 뭘 골라야 할지 구분이 안 됐음.
    이름이 안 겹치는 평범한 브랜드는 라벨을 안 붙여서 불필요한 노이즈를 안 만든다."""
    from collections import Counter

    names = [brand_index.display_name(m) for m in mnnos]
    counts = Counter(names)
    out = []
    for m, name in zip(mnnos, names):
        if counts[name] > 1:
            label = brand_index.disambiguation_label(m)
            out.append(f"{name}({label})" if label else name)
        else:
            out.append(name)
    return sorted(set(out))


def _detect_type_filter(question: str, components: dict) -> "str | None":
    """total_cost.compute_total_startup_cost()가 mode="multi"로 반환한 components(매장
    타입별 그룹)에서 실제 타입 이름 토큰(total_cost.extract_type_tokens)을 전부 모아
    질문 문장과 대조한다. 정확히 하나의 토큰만 질문에 등장하면 그 토큰을 그대로
    type_filter로 쓴다 — 0개(타입 언급 없음)나 2개 이상(어느 타입인지 애매함)이면 필터를
    안 걸고 None을 반환해서 기존처럼 전체 타입을 그대로 보여준다(라운드3 작업지시 2번,
    추측하지 않는다는 원칙 그대로)."""
    q_lower = question.lower()
    matched: set = set()
    for items in components.values():
        for it in items:
            for token in total_cost.extract_type_tokens(it.get("column")):
                if token.lower() in q_lower:
                    matched.add(token)
    if len(matched) == 1:
        return next(iter(matched))
    return None


def _ambiguous_candidates(brand_index, mnnos: list[str]) -> list[dict]:
    """동명이인(ambiguous) 후보를 브랜드 추천 버튼 형식으로 변환한다(라운드3 작업지시
    0번 — 지금까지 ambiguous는 brand_suggestions가 비어있어서 클릭 버튼 자체가 안 떴었음,
    "피자스쿨" 재현으로 확인). fuzzy 추천(_suggest_for_unresolved)과 달리 이미 이름이
    정확히 일치하는 실제 후보들이므로(유사도 추측이 아님) score를 항상 1.0으로 고정하고
    source="ambiguous"로 표시한다 — 프론트(chat/page.js)가 이 source를 보고 "질문 문장의
    브랜드 텍스트를 치환해서 재질문"이 아니라 "이 mnno로 강제 확정해서 재질문"
    (forced_brand_mnno) 경로를 타도록 분기한다. 항상 법인명/개시연도 라벨을 붙여서
    버튼끼리 서로 구분되게 한다(이름 자체는 전부 동일하므로 라벨 없이는 구분 불가)."""
    out = []
    for m in mnnos:
        label = brand_index.disambiguation_label(m)
        name = brand_index.display_name(m)
        display = f"{name}({label})" if label else name
        out.append({"brandMnno": m, "display_name": display, "score": 1.0, "source": "ambiguous"})
    return out


def _unresolved_message(text: str, *, reason: str, names: "list[str] | None" = None) -> str:
    """이름 인식과 데이터 존재 여부를 분리한 3가지 사유별 메시지(작업로그 (31) 참고).
    - unresolved: brand_unified.jsonl에도 없는 이름 -> 오타 가능성을 안내.
    - no_data: 이름은 확인됐지만 정보공개서 데이터가 아직 없음 -> 오타가 아님을 명시.
    - ambiguous: 이름 후보가 여럿인데 데이터 있는 것도 2개 이상 -> 추측하지 않고 후보 나열."""
    if reason == "no_data":
        joined = ", ".join(names or [])
        return f"'{text}'({joined}) 브랜드는 확인했지만 정보공개서 데이터가 아직 없습니다."
    if reason == "ambiguous":
        joined = ", ".join(names or [])
        return f"'{text}'가 여러 브랜드로 해석됩니다: {joined}. 정확한 이름으로 다시 질문해 주세요."
    return f"'{text}' 브랜드를 찾을 수 없습니다. 정확한 브랜드명인지 확인해 주세요."


def _empty_result(question: str, *, answer: str, intent=None) -> dict:
    return {
        "answer": answer,
        "citations": [],
        "intent": intent,
        "category": None,
        "canonical_title": None,
        "use_structured": False,
        "use_total_cost": False,
        "brands_resolved": [],
        "brands_unresolved": [],
        "brand_suggestions": [],
    }
