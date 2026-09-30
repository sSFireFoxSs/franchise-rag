"""0단계: 브랜드명 정규화 및 brandMnno 확보.

normalize_name()은 새로 만들지 않고 scripts/02_fetch_disclosure_content.py에 있는
것을 그대로 재사용한다(사용자 지시). 그 파일명이 숫자로 시작해서 `import`문으로는
못 불러오므로 importlib로 파일 경로 기준으로 로드한다.
"""
import difflib
import importlib.util
import json
import re
from functools import lru_cache
from pathlib import Path

from . import config

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def _load_normalize_name():
    spec = importlib.util.spec_from_file_location(
        "_ftc_fetch_content_module", _SCRIPTS_DIR / "02_fetch_disclosure_content.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # __name__ != "__main__"라 main()은 실행 안 됨
    return module.normalize_name


normalize_name = _load_normalize_name()

# 2026-09-19 (라운드2 작업지시 2번 조사 결과, 실험 후 채택하지 않음): "이름이 잘 기억
# 안나는데 고깃집중에 무슨 시리?"처럼 문장 한가운데 브랜드 파편이 파묻힌 경우를 위해
# candidate 길이만한 슬라이딩 윈도를 query 위에서 돌려 "부분 구간 유사도"를 추가로 보는
# 방식을 실험해봤으나, 3글자짜리 한국어 브랜드명(예: "육시리")은 문장 아무 데서나 2글자
# 정도만 우연히 겹쳐도 difflib 비율이 0.5~0.7대로 나와서, 실측 결과 진짜 정답("육시리",
# 0.667)과 완전히 무관한 오탐("집중소"/"혼고집"/"뼈고집"/"치킨양복점", 전부 동일하게
# 0.667)이 구분 없이 같은 점수로 섞여 나옴 — 임계값을 올리면 정답까지 같이 걸러지고,
# 내리면 오탐만 늘어나서 이 접근으로는 신호와 잡음을 분리할 수 없었음(아래 suggest_similar()
# 자체는 안 건드리고 원래 전체-문자열 비교 방식 그대로 유지). 상세 실측/결론은 docs/DESIGN.md
# 라운드2 작업 보고 참고 — "짧은 이름 + 자유 서술형 긴 문장" 조합은 문자열 유사도만으로는
# 안전하게 해결 안 되는 영역으로 정직하게 남겨둠(무리하게 규칙을 늘리지 않음).


class BrandIndex:
    """normalize_name(브랜드명/별칭) -> [brandMnno, ...] 역색인.

    brand_unified.jsonl의 brandNm + brandNm_variants를 전부 키로 등록한다. 같은
    정규화 이름이 여러 brandMnno에 걸리면(동명이인/영업표지명 충돌) 전부 후보로 남겨두고,
    이걸 데이터 보유 여부로 좁히는 건 이 클래스가 아니라 pipeline.py의 몫이다(작업로그
    (31) 참고 — "이름 인식"과 "데이터 존재 여부"를 분리하기 위함).
    """

    def __init__(self, name_to_mnnos: dict[str, list[str]], mnno_to_display: dict[str, str],
                 mnno_to_corp: "dict[str, str] | None" = None):
        self.name_to_mnnos = name_to_mnnos
        self.mnno_to_display = mnno_to_display
        # 2026-09-17 (작업로그 (41)): brandNm이 완전히 똑같은데 실제로는 다른 법인인
        # 동명이인 브랜드가 43쌍 있음(예: "피자스쿨"을 (주)피자스쿨과 (주)씨에이치컴퍼니가
        # 각각 운영) — ambiguous/no_data 후보 나열 시 이름만 중복 표시되던 걸 구분하기
        # 위한 법인명+개시연도 라벨. disambiguation_label() 참고.
        self.mnno_to_corp = mnno_to_corp or {}

    def resolve(self, text: str) -> list[str]:
        """text(사용자가 말한 브랜드명 텍스트 그대로)를 정규화해서 정확히 일치하는
        brandMnno 후보를 반환한다. 못 찾으면 빈 리스트(추측하지 않음).
        (2026-09-15: 예전엔 여기서 known_mnnos(=clauses 데이터 보유 집합)로 후보를 걸러서
        "이름 자체를 모름"과 "이름은 있는데 데이터가 없음"을 구분 못 했음 — 작업로그 (31)
        참고. 이 메서드는 이제 순수하게 "brand_unified.jsonl 기준 이름 인식"만 담당하고,
        데이터 보유 여부 판정은 pipeline.py가 별도로 한다.)"""
        norm = normalize_name(text)
        if not norm:
            return []
        return self.name_to_mnnos.get(norm, [])

    def find_in_text(self, text: str) -> list[str]:
        """질문 원문(text) 안에 등록된 브랜드명/별칭이 부분 문자열로 들어있는지 찾는다.
        (2026-09-14 실측 버그 대응: 로컬 LLM(qwen3.5:9b)이 슬롯추출 과정에서 브랜드명을
        가끔 부정확하게 옮겨 적음 — "파파존스피자"->"파파존스"로 잘리거나, "핸델앤그레텔"의
        "델"이 한자 "德尔"로 오염되는 경우가 실제로 관찰됨. temperature=0인데도 CPU 추론의
        부동소수점 비결정성 때문에 같은 질문도 매번 다르게 나올 수 있어 프롬프트 지시만으론
        완전히 못 막음. resolve()가 실패했을 때 pipeline.py가 이 함수로 "질문 원문"에서
        직접 브랜드명을 재탐색하는 결정론적 안전망으로 쓴다 — LLM 출력이 아니라 사용자가 실제로
        타이핑한 텍스트를 보므로 이 경로는 오염되지 않는다.)
        가장 긴 매칭 이름을 우선한다(짧은 이름이 긴 이름의 부분일 때 오탐 방지). resolve()와
        마찬가지로 이름 레벨 후보만 반환하고, 데이터 보유 여부는 pipeline.py가 판정한다."""
        norm_text = normalize_name(text)
        if not norm_text:
            return []
        best_len = 0
        best_mnnos: list[str] = []
        for name_norm, mnnos in self.name_to_mnnos.items():
            if len(name_norm) < 2 or len(name_norm) <= best_len:
                continue  # 너무 짧은 이름은 오탐 위험 + 이미 찾은 것보다 짧으면 볼 필요 없음
            if name_norm in norm_text:
                best_len = len(name_norm)
                best_mnnos = mnnos
        return best_mnnos

    def display_name(self, brand_mnno: str) -> str:
        return self.mnno_to_display.get(brand_mnno, brand_mnno)

    def disambiguation_label(self, brand_mnno: str) -> str:
        """동명이인 브랜드를 구분하기 위한 법인명+개시연도 라벨(작업로그 (41)).
        pipeline.py의 _format_candidate_names()가 이름이 겹치는 후보에만 이걸 괄호로
        붙인다 — 평범한(안 겹치는) 브랜드에는 이 메서드가 안 불려서 노이즈가 없다."""
        return self.mnno_to_corp.get(brand_mnno, "")

    def suggest_similar(self, text: str, top_k: int = 5, min_ratio: float = 0.5,
                         min_len: int = 4) -> list[dict]:
        """resolve()/find_in_text()가 둘 다 실패했을 때("이름 자체를 못 찾음") 쓰는
        폴백 — LLM 없이 순수 문자열 유사도(difflib.SequenceMatcher, 표준 라이브러리)로만
        비슷한 브랜드 후보를 찾는다(작업로그 (39)).

        이 프로젝트는 "이름 대조 없이 아무거나 채택"해서 서로 다른 브랜드 데이터가 섞인
        사고가 실측된 적이 있고(02_fetch_disclosure_content.py의 match_entry() 참고),
        로컬 LLM이 브랜드명을 옮겨적다 오염시키는 문제도 있어서(find_in_text() 참고),
        "비슷한 브랜드를 LLM이 알아서 골라주는" 방식은 쓰지 않는다 — 여기서는 후보만
        보여주고 최종 확정은 항상 사용자 클릭에 맡긴다("추측하지 않고 확인한다" 원칙,
        작업로그 (31)과 동일).

        브랜드마다 별칭(brandNm_variants)이 여러 개일 수 있으므로, name_to_mnnos에 이미
        등록된 모든 별칭(괄호 축약형 파생 키 포함, build_brand_index() 참고)을 text와
        비교해서 brandMnno별로 "가장 유사도가 높은 별칭" 하나만 대표값으로 남기고 그
        기준으로 브랜드를 순위 매긴다 — 그래야 "1리터셀(SELL)&디저트와플"처럼 원래
        표기가 사용자 입력과 멀어도, 파생된 축약형("1리터셀&디저트와플")과는 가까운
        경우를 놓치지 않는다.

        min_ratio 미만이면 그 브랜드는 아예 후보에서 뺀다 — 전혀 무관한 텍스트에 억지로
        아무 브랜드나 보여주지 않기 위한 최소 기준(실측: 무관한 텍스트의 최고 유사도는
        0.3~0.42 수준, "1리터셀 와플"처럼 실제로 비슷한 경우는 0.5 이상 — 아래 함수
        docstring이 아니라 작업로그 (39)에 실측치를 남겨둠).

        min_len 미만(정규화 후 글자 수)이면 아예 비교하지 않고 빈 리스트를 반환한다 —
        difflib.SequenceMatcher.ratio()는 문자열이 2~3자로 짧으면 한두 글자만 겹쳐도
        비율이 쉽게 0.5를 넘어버려서(실측: "엑스"/"와이지" 같은 2~3자 텍스트가 전혀
        무관한 브랜드와도 0.57~0.67을 찍음), min_ratio만으로는 짧은 텍스트의 우연한
        일치를 못 거른다. 반환값은 유사도 내림차순
        [{"brandMnno":.., "display_name":.., "score": float}, ...] 최대 top_k개."""
        norm_query = normalize_name(text)
        if not norm_query or len(norm_query) < min_len:
            return []
        best_by_mnno: dict[str, float] = {}
        for name_norm, mnnos in self.name_to_mnnos.items():
            if not name_norm:
                continue
            ratio = difflib.SequenceMatcher(None, norm_query, name_norm).ratio()
            if ratio < min_ratio:
                continue
            for mnno in mnnos:
                if ratio > best_by_mnno.get(mnno, -1.0):
                    best_by_mnno[mnno] = ratio
        ranked = sorted(best_by_mnno.items(), key=lambda t: t[1], reverse=True)[:top_k]
        return [
            {"brandMnno": mnno, "display_name": self.mnno_to_display.get(mnno, mnno), "score": score}
            for mnno, score in ranked
        ]


@lru_cache(maxsize=1)
def get_brand_index() -> BrandIndex:
    """build_brand_index()의 프로세스당 싱글턴 캐시 버전 — pipeline.py가 매 질문마다
    brand_unified.jsonl(12,498건)을 다시 읽지 않도록."""
    return build_brand_index()


# 2026-09-15: "비비큐(BBQ)"로 등록된 브랜드를 사용자가 "비비큐"라고만 말하면 resolve()도
# find_in_text()도 못 찾는 버그 실측(비비큐 창업비용 질문 테스트 중 발견). resolve()는 정확
# 일치만 보고, find_in_text()는 반대 방향(등록명이 질문 문장에 부분 문자열로 있는지)이라
# 질문이 등록명보다 짧은 이 케이스는 둘 다 커버 못 함. brand_unified.jsonl에서 이런 괄호
# 표기("영업표지(별칭)")를 쓰는 브랜드가 1,090건(2026-09-15 실측) — 드문 케이스가 아님.
# normalize_name()은 02_fetch_disclosure_content.py의 공용 함수라 다른 매칭(brno 매칭 등)에
# 영향 없게 그대로 두고, 괄호 제거는 여기(브랜드 인덱스 구축 시점)에서만 파생 키로 추가한다.
_PAREN_RE = re.compile(r"\([^)]*\)")
# 2026-09-17: 위와 같은 이유로, 괄호 "안" 내용("비에이치씨(BHC)"의 "BHC")도 별칭으로
# 등록돼 있지 않아서 "bhc"라고만 물으면 색인에 아예 없는 문자열이라 정확일치/find_in_text/
# suggest_similar 전부 실패함. 괄호가 여러 개일 수 있으므로 findall로 전부 뽑아서 등록한다.
_PAREN_INNER_RE = re.compile(r"\(([^)]*)\)")


def _format_corp_label(corp_nm: "str | None", start_date: "str | None") -> str:
    """동명이인 구분용 라벨(작업로그 (41)) — "(주)피자스쿨, 2006년 개시" 같은 문자열을
    만든다. corp_nm이 없으면 빈 문자열. start_date(jngBizStrtDate, 'YYYYMMDD' 형식 기대)가
    없거나 앞 4자리가 숫자가 아니면(형식이 이상하면) 연도 부분은 생략하고 법인명만 쓴다."""
    corp_nm = (corp_nm or "").strip()
    year = start_date[:4] if start_date and len(start_date) >= 4 and start_date[:4].isdigit() else ""
    if corp_nm and year:
        return f"{corp_nm}, {year}년 개시"
    return corp_nm


def build_brand_index(brand_path: Path = config.BRAND_PATH) -> BrandIndex:
    name_to_mnnos: dict[str, list[str]] = {}
    mnno_to_display: dict[str, str] = {}
    mnno_to_corp: dict[str, str] = {}

    def register(norm: str, mnno: str):
        if not norm:
            return
        name_to_mnnos.setdefault(norm, [])
        if mnno not in name_to_mnnos[norm]:
            name_to_mnnos[norm].append(mnno)

    with open(brand_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            mnno = row.get("brandMnno")
            if not mnno:
                continue
            brand_nm = row.get("brandNm")
            variants = row.get("brandNm_variants") or []
            names = [n for n in [brand_nm] + list(variants) if n]
            if not names:
                continue
            mnno_to_display[mnno] = brand_nm or names[0]
            mnno_to_corp[mnno] = _format_corp_label(row.get("corpNm"), row.get("jngBizStrtDate"))
            for name in names:
                register(normalize_name(name), mnno)
                if "(" in name and ")" in name:
                    # "비비큐(BBQ)" -> "비비큐" 축약형도 같은 mnno로 등록. 축약형이 다른
                    # 브랜드와 충돌하면(같은 축약형이 서로 다른 mnno에 걸리면) 여기서 하나를
                    # 억지로 고르지 않고 name_to_mnnos에 둘 다 후보로 남긴다 — resolve()가
                    # 그대로 여러 후보를 반환하고, pipeline.py의 "데이터 있는 쪽 우선" 로직이
                    # 나머지를 처리한다.
                    stripped = _PAREN_RE.sub("", name)
                    register(normalize_name(stripped), mnno)
                    for inner in _PAREN_INNER_RE.findall(name):
                        norm_inner = normalize_name(inner)
                        if not norm_inner:
                            continue
                        register(norm_inner, mnno)
                        # 2026-09-17: normalize_name()은 공백만 정리하고 대소문자는 안 건드림
                        # (02_fetch_disclosure_content.py의 brno 매칭에도 쓰이는 공용 함수라
                        # 여기서 동작을 바꾸지 않음). "BHC" 같은 영문 약칭은 사용자가 실제로
                        # 소문자("bhc")로 입력하는 경우가 실측됨(NLU 슬롯추출 테스트로 확인) —
                        # 대소문자만 다른 걸 못 찾으면 이번 수정의 목적 자체가 무색해지므로,
                        # 순수 알파벳 약칭에 한해 소문자 별칭도 추가로 등록한다.
                        if norm_inner.isalpha() and norm_inner.isascii():
                            register(norm_inner.lower(), mnno)

    return BrandIndex(name_to_mnnos, mnno_to_display, mnno_to_corp)
