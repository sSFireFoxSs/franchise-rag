"""
3단계: 02에서 저장한 본문 XML에서 조항(섹션)을 뽑아 clauses.jsonl로 만든다.

2026-09-11 (21)(22): 키워드 매칭 방식을 버리고 attr 코드 기반으로 재설계함.
- 예전: 섹션 제목에 "가맹비"/"위약금" 같은 키워드가 있는지로 뽑을지/카테고리를 정했음.
  문제: "가맹금 예치"(은행 안내문)와 "최초 가맹금"(실제 금액)이 둘 다 "가맹금"이라는 단어를
  포함해서 같은 카테고리로 잘못 뭉쳐지는 등 오분류가 있었음.
- 지금: 원문 XML의 헤딩 태그(<hN attrb_sn="..." attr="...">)에 공정위가 붙여놓은 고정
  필드 코드가 있는 걸 발견함(전체 2,256개 브랜드 전수조사로 확인 — 브랜드/연도 상관없이
  attr 코드는 항상 동일, 예외 0건, 고유 코드 110개). 이제 이 attr 코드로 섹션을 식별하고
  scripts/section_schema.py에 정의된 매핑으로 카테고리를 정한다. 자세한 내용은 section_schema.py
  상단 설명과 docs/DESIGN.md 개발 기록 참고.
- 표(table)도 이제 정규식으로 태그만 지우는 대신 BeautifulSoup으로 행/열 구조를 살려서
  `tables` 필드에 저장하고, 표 안의 금액처럼 보이는 셀은 숫자로 정규화해서 `amounts` 필드에
  따로 뽑아둔다(예: "1,100,000" / "1,100만원" -> 1100000).

본문 API 응답은 <?xml ...?> 표준 선언이 아니라 <xml version="1.0" ...> 형태로 오고
닫히지 않는 태그가 섞여있어(비표준) 통짜로 ElementTree에 넣으면 못 읽는다. 그래서 헤딩
위치는 정규식으로 찾고(<h1..h6 title="...">), 그 사이 구간만 잘라서 BeautifulSoup(lxml)으로
파싱한다 — 조각 단위라 태그 안 닫힘 문제 영향이 적고, lxml이 웬만한 깨진 마크업은 알아서
복구해서 읽는다.

사용법:
  pip install beautifulsoup4 lxml --break-system-packages   # 없으면 먼저 설치
  python scripts/03_extract_clauses.py
  python scripts/03_extract_clauses.py --limit 100   # 샘플만 (테스트용)
"""
import argparse
import gzip
import html
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from section_schema import lookup
from utils import DATA_DIR, append_jsonl, get_logger, read_jsonl

logger = get_logger("03_extract_clauses")

DISCLOSURE_DIR = DATA_DIR / "disclosure"
UNIFIED_PATH = DISCLOSURE_DIR / "disclosure_unified.jsonl"
OUT_PATH = DISCLOSURE_DIR / "clauses.jsonl"
# git에는 이 gzip 압축본만 올린다 (2026-09-11 (23)번 로그 참고 — 원본 평문은 ~130MB로
# GitHub 100MB 제한을 넘어서, 압축본(약 26MB)만 커밋하고 평문은 .gitignore 처리함).
# 로컬 스크립트/앱은 평문 OUT_PATH를 그대로 쓰고, 커밋 직전에만 이 gz를 새로 만든다.
OUT_PATH_GZ = DISCLOSURE_DIR / "clauses.jsonl.gz"

HEADING_RE = re.compile(r'<h([1-6])([^>]*)\btitle="([^"]*)"[^>]*>', re.IGNORECASE)
ATTR_RE = re.compile(r'\battr="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")

# 2026-09-11: "별첨/별지/붙임" 참조 감지 — RAG의 "근거/출처 제공" 단계에서 조항이 실제로는
# 첨부자료(별첨)를 봐야 완전한데 그 원문이 우리 코퍼스(API 응답)에 아예 없다는 걸, UI가 텍스트를
# 다시 스캔해서 알아내는 게 아니라 데이터 자체에 구조화된 필드로 박아두기 위함. 이렇게 하면
# 나중에 RAG 답변 생성 단계에서도(LLM이 눈치채길 바라지 않고) 이 필드를 보고 항상 "이 항목은
# 별첨을 참고해야 하나 공개 데이터에는 없다"는 캐비엇을 붙일 수 있음 — 근거를 조작/누락하지
# 않고 "코퍼스에 없는 건 없다고 정직하게" 답하게 만드는 게 핵심. (app.py의 별첨 안내 토글과
# 동일한 로직을 여기로 옮겨서 단일 소스로 관리함.)
# 2026-09-11 오탐 수정: "별지"가 "개별지도"(교육 프랜차이즈의 책상/파티션 등 품목명), "특별지원"
# 같은 무관한 단어 안에 우연히 부분 문자열로 들어있는 경우가 있었음(에듀코치/에듀플렉스에서
# "개별지도책상"이 별첨 참조로 잘못 잡힘 — 사용자가 "진짜 별첨 자료가 있는 브랜드 있어?"라고
# 묻는 과정에서 데이터를 훑다가 발견함). "별지" 앞에 "개"가 오거나 뒤에 "원"이 오면 매치하지
# 않도록 제외했다.
ATTACHMENT_RE = re.compile(r"별첨|붙임|(?<!개)별지(?!원)")

# 2026-09-14: Ⅲ장 "법 위반 이력 있음/없음" 플래그를 text 안 자연어 문장에서 별도 필드로
# 구조화한다(COREC_ACTN_INFO=시정조치, CVLST_INFO=민사소송/화해, PETY_ADJU_INFO=형의 선고).
# 법정서식 문구가 "~받은 사실이 없습니다"/"~있습니다"가 기본이지만 브랜드마다 조사(은/이)나
# 따옴표, "[N]회" 카운트형("~사실이 [0]회 있으며 자세한 내용은...")까지 섞여있어서 검증 필요했음
# (400개 브랜드 샘플로 실측: 정상 분류 97%+, 나머지는 아래 None 처리).
# "~있습니다"라고 써놓고 뒤에 붙는 표에는 "해당사항없음"만 있는 모순적 서식도 실제로 있어서
# (예: BRD_20090100338) — 이런 경우 있음/없음 텍스트가 섹션 안에 둘 다 나타나 판별이 애매하므로
# 억지로 하나를 고르지 않고 None(사람이 원문 확인 필요)으로 남긴다. amount_unit_detected와
# 같은 "모르면 null" 원칙.
VIOLATION_FLAG_ATTRS = {"COREC_ACTN_INFO", "CVLST_INFO", "PETY_ADJU_INFO"}
VIOLATION_COUNT_RE = re.compile(r"\[?(\d+)\]?\s*회")
VIOLATION_POLARITY_RE = re.compile(r"(있|없)(습니다|음|으며)")


def detect_violation_flag(attr: str, fragment: str):
    """법 위반 이력 섹션(위 3개 attr)에서만 "있음"/"없음"/None(애매)을 판별한다."""
    if attr not in VIOLATION_FLAG_ATTRS:
        return None
    compact = re.sub(r"\s+", "", TAG_RE.sub("", fragment or ""))
    count_m = VIOLATION_COUNT_RE.search(compact)
    if count_m:
        return "있음" if int(count_m.group(1)) > 0 else "없음"
    polarities = {m.group(1) for m in VIOLATION_POLARITY_RE.finditer(compact)}
    if len(polarities) == 1:
        return "있음" if "있" in polarities else "없음"
    return None

# 금액 셀 판별용. 표 순서(끝에 붙는 단위 우선순위 중요 - "천만원"을 "만원"보다 먼저 검사해야 함)
UNIT_MULTIPLIERS = [
    ("억원", 100_000_000),
    ("천만원", 10_000_000),
    ("백만원", 1_000_000),
    ("만원", 10_000),
    ("천원", 1_000),
    ("원", 1),
]
UNIT_MULTIPLIER_BY_NAME = dict(UNIT_MULTIPLIERS)
NUMBER_RE = re.compile(r"^-?[\d,]+(\.\d+)?$")
PLAIN_COMMA_NUMBER_RE = re.compile(r"^\d{1,3}(,\d{3})+$")  # "1,100,000" (콤마 3자리 구분만, 단위 없음)
# 2026-09-11 (25번 로그): 표에 "금액"/"면적 3.3㎡당 금액"처럼 컬럼이 여러 개 있을 때,
# 작은 쪽 컬럼(예: 단가)은 콤마 없이 "275"/"147"처럼 그냥 써놓는 경우가 많아서 위 패턴에
# 안 걸림. 콤마 유무와 상관없이 3자리 이상 순수 숫자면 금액 후보로 봄(1~2자리는 "3명"
# 같은 카운트/순번과 헷갈릴 위험이 커서 제외).
PLAIN_NUMBER_RE = re.compile(r"^\d{3,}$")

# 2026-09-11 (24번 로그): 표 셀 자체에는 단위 없이 숫자만 있고, 그 대신 표 바로 위 캡션
# ("(단위 : 천원, VAT 포함)")이나 표 헤더 셀("금액(천원)")에 단위를 한 번만 선언해두는
# 브랜드가 많다는 걸 발견함. 이걸 못 잡으면 "5,500"(천원 단위, 실제 550만원)을 5,500원으로
# 잘못 읽어서 브랜드마다 금액이 1,000배/10,000배씩 틀어지는 심각한 문제가 생김.
UNIT_TOKEN_RE = re.compile(r"(억원|천만원|백만원|만원|천원|원)")
# "단위" 라는 글자가 나오면 그 뒤 20자 안에서 단위 토큰을 찾는다 (캡션형: "단위 : 천원",
# 헤더 셀형: "금액( 단위:원 )" 둘 다 이 패턴으로 잡힘)
_UNIT_AFTER_LABEL_RE = re.compile(r"단위")
# "단위"라는 글자 없이 헤더 셀에 "금액(천원)"처럼 괄호로만 단위를 표시하는 경우의 폴백
_UNIT_PAREN_RE = re.compile(r"\(([가-힣]{1,4}원)\)")

# 2026-09-15: 한 섹션 안에 표가 여러 개 있을 때(예: 비비큐 "그 밖에 지급하여야 하는 비용" —
# 매장타입(BSK/올리브치킨/...)별로 표가 따로 6개 있고, 표마다 "(가) BSK (단위: 천원, ...
# 8평 기준)"처럼 바로 위 문단에 그 표가 무엇에 대한 것인지 + 단위를 같이 적어둠), 이 문단을
# 못 잡으면 두 가지 문제가 동시에 생김: (1) 표가 여러 개라 같은 라벨("총 계" 등)이 반복되는데
# 어느 표(매장타입) 소속인지 구분이 안 됨, (2) 단위를 섹션 전체에서 한 번만 찾다 보니(당시엔
# 우연히 전부 "천원"이라 값 자체는 안 틀렸지만) 표마다 단위가 다른 브랜드가 있으면 잘못
# 환산될 여지가 있었음. find_table_caption()으로 표 바로 위 문단을 찾아서 (a) 그 표 전용
# 단위 인식에 우선 쓰고(없으면 섹션 전체 단위로 폴백), (b) amounts의 table_context 필드로
# 그대로 노출해서 "이 금액이 어느 표/매장타입 소속인지" 구분 가능하게 한다.
def find_table_caption(table_tag, max_hops: int = 10):
    """표 바로 위(가장 가까운) 형제 요소의 텍스트를 캡션으로 반환한다. 형제를 거슬러
    올라가다 다른 <table>에 닿으면(=캡션 문단 없이 표가 연달아 나오는 경우) None."""
    sib = table_tag.find_previous_sibling()
    hops = 0
    while sib is not None and hops < max_hops:
        if getattr(sib, "name", None) == "table":
            return None
        txt = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
        if txt:
            return re.sub(r"\s+", " ", txt)
        sib = sib.find_previous_sibling()
        hops += 1
    return None


# 2026-09-15: label(항목명) 추출 버그 수정. 예전엔 "amount 컬럼이 아닌 셀은 전부 label"로
# 뭉뚱그려서, "지급대상"/"지급기한"/"반환조건"/"비고"처럼 안내·절차성 컬럼까지 항목명에
# 다 같이 이어붙었음(비비큐 케이스에서 라벨이 안내문구로 뒤덮여 못 읽는 지경까지 감).
# 헤더 셀 이름으로 "이 컬럼이 항목을 식별하는 컬럼인지(구분/항목 등, label에 포함) 아니면
# 절차/안내성 컬럼인지(지급대상/지급기한/반환조건/비고 등, label에서 제외)"를 가려낸다.
_LABEL_EXCLUDE_HEADER_RE = re.compile(r"지급|반환|비고|귀책|조건|사유|기한|여부|대상|방법|시기|참고|안내")


def _is_identifying_header(header_cell):
    if not header_cell:
        return True  # 헤더가 없거나 비어있으면 판단할 근거가 없으므로 안전하게 포함시킴
    compact = re.sub(r"\s+", "", header_cell)
    return not _LABEL_EXCLUDE_HEADER_RE.search(compact)


# 2026-09-18: "가맹점수"/"번호"처럼 금액이 아닌 정수 컬럼이 amounts에 금액으로 잘못 섞여
# 들어가는 버그 수정. 표에 "2024년말 가맹점수" 같은 컬럼이 있으면 콤마 없는 3자리 이상 숫자
# (PLAIN_NUMBER_RE, 작업로그 (25))에 걸려서 매출액과 나란히 amounts에 들어감(예: 피나치공
# BRD_20080100496 평균매출액 섹션에서 "가맹점수" 562건이 562,000원처럼 보이는 값으로 섞임).
# 컬럼 헤더(combine_header 결과) 텍스트로 판별해서 실측상 안전하게 제외 가능한 것만 추린다.
# - "연도"/"년도"는 부분일치 금지, 전체일치만 제외: "2024년도 가맹점사업자의 연간 평균
#   매출액"처럼 실제 금액 컬럼 헤더에 "년도" 글자가 포함된 경우가 있어서(1,500건+), 부분일치로
#   걸러내면 정상 금액이 잘못 제거된다. 헤더 텍스트가 "연도" 또는 "년도" 단어 하나로만
#   이루어진 경우에만 제외한다.
# - "%"는 제외 키워드에 넣지 않는다 — 대신 실측상 안전한 "비율"/"비중"만 채택한다.
_AMOUNT_EXCLUDE_HEADER_RE = re.compile(r"가맹점수|매장수|번호|순번|연번|비율|비중")
_AMOUNT_EXCLUDE_HEADER_EXACT = {"연도", "년도"}


def _is_excluded_amount_header(header_text):
    """이 컬럼(헤더 텍스트 기준)이 금액이 아닌 값(가맹점수/순번 등)을 담는 컬럼이면 True."""
    if not header_text:
        return False
    compact = re.sub(r"\s+", "", header_text)
    if not compact:
        return False
    if compact in _AMOUNT_EXCLUDE_HEADER_EXACT:
        return True
    return bool(_AMOUNT_EXCLUDE_HEADER_RE.search(compact))


def find_default_unit_multiplier(probe_text: str):
    """섹션 안에서 '단위' 선언을 찾아 기본 배수를 반환한다. 못 찾으면 (1, None)
    (=원 단위로 간주, 별도 선언 없었다는 뜻).
    원문에 "천 원"처럼 글자 사이에 공백이 섞여 나오는 경우가 있어서(원문 자체 표기가
    들쭉날쭉함), 공백을 다 지운 버전에서 검색한다 — "단위" 위치를 찾을 때도, 단위 토큰을
    찾을 때도 공백 유무에 흔들리지 않게 함."""
    compact = re.sub(r"\s+", "", probe_text)
    for m in _UNIT_AFTER_LABEL_RE.finditer(compact):
        window = compact[m.end(): m.end() + 10]
        unit_m = UNIT_TOKEN_RE.search(window)
        if unit_m:
            unit = unit_m.group(1)
            for u, mult in UNIT_MULTIPLIERS:
                if u == unit:
                    return mult, unit
    for m in _UNIT_PAREN_RE.finditer(compact):
        inner = m.group(1)
        for u, mult in UNIT_MULTIPLIERS:
            if u == inner:
                return mult, inner
    return 1, None


def parse_amount_won(cell_text: str, default_mult: int = 1):
    """표 셀 문자열에서 금액(원 단위 정수)을 뽑아본다. 못 알아보면 None.
    - 셀 자체에 단위(예: "1,100만원")가 붙어있으면 그 단위를 그대로 씀(최우선).
    - 단위 없이 숫자만 있으면(예: "5,500") default_mult를 곱함 — 이 섹션에 "단위: 천원"
      같은 캡션/헤더 선언이 있었다면 1000을 곱해 원 단위로 환산, 없었으면 1(그대로 원).
    - "이백만원"처럼 한글로 쓴 숫자, "132,000~66,000" 같은 범위 값은 대상 밖(못 알아봄 처리).
    - 대괄호("[11,000]")나 원화기호가 깨져서 붙는 "\5,500,000" 같은 표기는 벗겨내고 시도함."""
    s = cell_text.strip().replace(" ", "").replace("\xa0", "")
    if not s:
        return None
    s = s.strip("[]()")  # 괄호로 감싼 숫자
    s = s.lstrip("\\₩")  # 원화기호가 백슬래시 등으로 깨져서 앞에 붙는 경우
    if not s:
        return None
    for unit, mult in UNIT_MULTIPLIERS:
        if s.endswith(unit):
            num_part = s[: -len(unit)]
            if num_part and NUMBER_RE.match(num_part):
                try:
                    return int(float(num_part.replace(",", "")) * mult)
                except ValueError:
                    return None
            return None
    if PLAIN_COMMA_NUMBER_RE.match(s) or PLAIN_NUMBER_RE.match(s):
        return int(s.replace(",", "")) * default_mult
    return None


def table_to_grid(table_tag):
    """<table> 하나를 colspan/rowspan까지 반영해서 완전한 격자(2차원 리스트, 빈 칸 없음)로
    바꾼다. 정부 법정서식 표들이 "지급대상"처럼 같은 값을 여러 행에 걸쳐 rowspan으로 한 번만
    적어두는 경우가 흔한데(예: 핸델앤그레텔 "그 밖에 지급하여야 하는 비용" 표), 이걸 안
    풀어주면 rowspan 아래 행들의 셀이 왼쪽으로 밀려서 헤더 열 이름과 엉뚱하게 매칭됨
    (작업로그 (25) 참고). tr.find_all(["td","th"])만 쓰던 예전 방식보다 느리지만 표가 크지
    않아서 문제없음."""
    grid = []
    pending: dict[int, list] = {}  # col_idx -> [남은 행 수, 텍스트]
    for tr in table_tag.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        row = []
        col_idx = 0
        cell_idx = 0
        while cell_idx < len(cells) or col_idx in pending:
            if col_idx in pending:
                remaining, text = pending[col_idx]
                row.append(text)
                if remaining <= 1:
                    del pending[col_idx]
                else:
                    pending[col_idx][0] = remaining - 1
                col_idx += 1
                continue
            cell = cells[cell_idx]
            cell_idx += 1
            text = cell.get_text(" ", strip=True)
            try:
                colspan = max(1, int(cell.get("colspan", 1)))
            except (TypeError, ValueError):
                colspan = 1
            try:
                rowspan = max(1, int(cell.get("rowspan", 1)))
            except (TypeError, ValueError):
                rowspan = 1
            for _ in range(colspan):
                while col_idx in pending:  # 이미 위에서 내려오는 rowspan이 이 자리를 쓰고 있으면 건너뜀
                    remaining, ptext = pending[col_idx]
                    row.append(ptext)
                    if remaining <= 1:
                        del pending[col_idx]
                    else:
                        pending[col_idx][0] = remaining - 1
                    col_idx += 1
                row.append(text)
                if rowspan > 1:
                    pending[col_idx] = [rowspan - 1, text]
                col_idx += 1
        grid.append(row)
    return grid


def strip_tags(fragment: str) -> str:
    text = TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_tables_and_text(fragment: str):
    """섹션 조각(fragment)에서 (tables, amounts, text)를 뽑는다.
    tables: [[[cell, cell, ...], ...], ...]  (표가 여러 개면 리스트가 여러 개)
    amounts: [{"label":..., "amount_won":..., "raw":...}, ...]
    text: 표를 뺀 본문 서술 부분만 평문화한 것.
    (2026-09-11 (23): text에 표 내용까지 통짜로 들어가면 tables/amounts와 내용이
    통째로 중복돼서 용량만 커짐 - 전체 브랜드 기준 예상 166MB로 git 100MB 제한 초과.
    표는 tables/amounts로만 구조화해서 보관하고, text는 표를 제외한 서술 부분만 남기기로 함.
    표 안의 숫자/항목명으로 전문 검색은 안 되지만(amounts.label로 검색 가능), 용량은
    크게 줄어듦. 작업로그 (23) 참고.)"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # bs4가 없으면 예전처럼 태그만 지우는 방식으로 폴백 (표 구조/금액 추출은 포기)
        return [], [], strip_tags(fragment), None

    soup = BeautifulSoup(fragment, "lxml")

    # 표를 지우기 전에(=아직 헤더 셀 텍스트가 살아있을 때) 이 섹션 전체에서 "단위" 선언을
    # 찾는다. 캡션형("1) 최초 가맹금을... (단위 : 천원, VAT 포함)")과 헤더 셀형
    # ("금액(천원)")을 둘 다 여기서 잡아서, 표 셀 자체엔 단위가 안 붙은 숫자에 곱해준다.
    probe_text = soup.get_text(" ", strip=True)
    default_mult, detected_unit = find_default_unit_multiplier(probe_text)

    tables = []
    amounts = []
    table_tags = soup.find_all("table")
    multi_table = len(table_tags) > 1
    for table_tag in table_tags:
        # 표가 여러 개인 섹션(예: 비비큐 "그 밖에 지급하여야 하는 비용" — 매장타입별로 표가
        # 따로 있음)은 바로 위 문단에 그 표가 뭘 의미하는지(+단위)가 적혀있는 경우가 많아서
        # (find_table_caption() 상단 주석 참고), 이 표 전용 단위/구분 정보로 우선 사용한다.
        caption = find_table_caption(table_tag) if multi_table else None
        table_mult, table_unit = find_default_unit_multiplier(caption) if caption else (1, None)
        if table_unit is None:
            table_mult, table_unit = default_mult, detected_unit

        raw_grid = table_to_grid(table_tag)  # colspan/rowspan 반영된 격자
        rows = []
        for cells in raw_grid:
            cells = [re.sub(r"\s+", " ", c.replace("\xa0", " ")).strip() for c in cells]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
        # 금액 추출: 헤더 행은 라벨 후보에서 제외하고 데이터 행만 본다.
        # 2026-09-15: 헤더가 여러 행에 걸친 표(예: 비비큐 "최초 가맹금" — 1행 "타입별 금액"
        # (colspan) + 2행 "BSK/올리브치킨/.../빌리지" 매장타입명, 또는 육시리 "평균매출액" —
        # 1행 "연간 평균 매출액"(colspan) + 2행 "평균/상한/하한" + 3행 "금액/면적 3.3㎡당")를
        # 예전엔 rows[0] 하나만 헤더로 보고 나머지 헤더 행(진짜 구분 정보가 있는 행)을 그냥
        # 버리고 있었음 — 그 결과 매장타입/상한·하한 구분이 전부 "타입별 금액"/"연간 평균
        # 매출액" 같은 뭉뚱그린 라벨 하나로 뭉개져서, 답변에 같은 라벨이 여러 번 중복되며
        # 어느 값이 뭔지 구분이 안 되는 문제가 있었음. 이제 "금액으로 안 읽히는 셀만 있는
        # 행"이 맨 위에서부터 몇 개 연속되는지 세어서 그 전부를 헤더로 모으고(header_rows),
        # 각 컬럼의 "column" 라벨은 그 헤더 행들의 텍스트를 순서대로 이어붙여서 만든다 —
        # 매장타입/상한·하한처럼 실제로 구분되는 정보가 컬럼마다 다르게 살아남는다.
        if len(rows) > 1:
            header_rows: list[list[str]] = []
            data_rows = []
            for idx, row in enumerate(rows):
                if any(parse_amount_won(c, table_mult) is not None for c in row):
                    data_rows = rows[idx:]
                    break
                header_rows.append(row)
        else:
            header_rows, data_rows = [], rows
        last_header = header_rows[-1] if header_rows else None

        def combine_header(col_idx: int) -> "str | None":
            parts = []
            for hrow in header_rows:
                if col_idx < len(hrow):
                    t = hrow[col_idx].strip()
                    if t and t not in parts:
                        parts.append(t)
            return " ".join(parts) if parts else None

        for row in data_rows:
            amount_cells = [(i, c, parse_amount_won(c, table_mult)) for i, c in enumerate(row)]
            amount_cells = [
                (i, c, v) for i, c, v in amount_cells
                if v is not None and not _is_excluded_amount_header(combine_header(i))
            ]
            if not amount_cells:
                continue
            amount_idx = {ai for ai, _, _ in amount_cells}
            # 2026-09-15 (label 정제): label에는 항목을 "식별"하는 컬럼만 남기고, 지급대상/
            # 지급기한/반환조건/비고 같은 절차·안내성 컬럼은 뺀다(_is_identifying_header 참고,
            # 헤더가 여러 행이어도 항상 가장 아래쪽(=가장 구체적인) 헤더 행 기준으로 판단).
            # 식별 컬럼이 하나도 안 남으면(전부 안내성으로 판정된 경우) 정보를 아예 잃는
            # 것보다는 예전처럼 전체를 라벨로 남기는 쪽을 폴백으로 쓴다.
            if last_header:
                label_idx = [
                    i for i in range(len(row))
                    if i not in amount_idx
                    and _is_identifying_header(last_header[i] if i < len(last_header) else None)
                ]
                if not label_idx:
                    label_idx = [i for i in range(len(row)) if i not in amount_idx]
            else:
                label_idx = [i for i in range(len(row)) if i not in amount_idx]
            label = " ".join(row[i] for i in label_idx if row[i]).strip()
            for i, raw, val in amount_cells:
                column = combine_header(i)
                entry = {"label": label, "column": column, "amount_won": val, "raw": raw}
                if multi_table:
                    entry["table_context"] = caption
                amounts.append(entry)
        # text에는 표 내용을 안 넣을 거라 트리에서 통째로 제거 (get_text 전에)
        table_tag.decompose()

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return tables, amounts, text, detected_unit


# 2026-09-19: 표/캡션 근처에 "단위" 선언이 아예 없는 섹션은 amount_unit_detected가 계속
# null로 남았음(예: 피자엠소마 BRD_20200018 평균매출액 — 문서 자체에는 단위 선언이 있지만
# 그 위치가 이 섹션의 fragment 범위(헤딩~다음 헤딩 사이) 밖이라 find_default_unit_multiplier()가
# 못 찾음). 실측(전체 "금액 카테고리+amounts 있음+단위 null" 2,094건 조사) 결과 995건은 같은
# 문서(source_xml) 안의 다른 섹션들이 전부 단일 단위로 일치해서 안전하게 물려받을 수 있었고,
# 5건은 문서 안에 단위 정보 자체가 없어 진짜 미확인, 1,094건은 문서 안에 서로 다른 단위가
# 섞여있어 애매해서 이번 범위에서 제외함(무리하게 하나를 고르지 않음 — amount_unit_detected의
# "모르면 null" 원칙 그대로 유지). 문서(=한 번의 extract_sections() 호출, 브랜드 1건의 XML)
# 단위로 이미 탐지된 amount_unit_detected 값들을 모아서 단일 값 하나로만 수렴할 때만
# null 섹션에 물려주고, amounts의 raw 텍스트를 그 단위로 다시 파싱해 amount_won도 갱신한다.
# 표 근처에서 직접 탐지된 것과 이번에 문서 단위로 물려받은 것을 구분할 수 있게
# amount_unit_source 필드를 새로 남긴다("table_detected" | "document_fallback" | None).
def apply_document_unit_fallback(sections):
    detected = {s["amount_unit_detected"] for s in sections if s.get("amount_unit_detected")}
    doc_default_unit = next(iter(detected)) if len(detected) == 1 else None
    doc_default_mult = UNIT_MULTIPLIER_BY_NAME.get(doc_default_unit) if doc_default_unit else None

    for s in sections:
        if s["amount_unit_detected"] is not None:
            s["amount_unit_source"] = "table_detected"
        elif doc_default_unit is not None:
            for entry in s["amounts"]:
                recalculated = parse_amount_won(entry["raw"], doc_default_mult)
                if recalculated is not None:
                    entry["amount_won"] = recalculated
            s["amount_unit_detected"] = doc_default_unit
            s["amount_unit_source"] = "document_fallback"
        else:
            s["amount_unit_source"] = None
    return sections


def find_attachment_mentions(text: str, tables):
    """조항 텍스트/표 안에서 "별첨/별지/붙임" 참조를 찾아 짧은 문맥 스니펫 리스트로 반환한다.
    (app.py에 있던 같은 로직을 데이터 추출 단계로 옮겨온 것 — 위 ATTACHMENT_RE 주석 참고.)"""
    mentions = []
    seen = set()

    def add(snippet):
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if snippet and snippet not in seen:
            seen.add(snippet)
            mentions.append(snippet)

    for m in ATTACHMENT_RE.finditer(text or ""):
        s = max(0, m.start() - 30)
        e = min(len(text), m.end() + 60)
        add(text[s:e])

    for table in (tables or []):
        for row in (table or []):
            for cell in (row or []):
                if isinstance(cell, str) and ATTACHMENT_RE.search(cell):
                    add(cell)

    return mentions


def extract_sections(xml_text: str):
    """attr 코드가 SECTION_SCHEMA에 있는(=우리가 쓰기로 한) 섹션만 골라서 반환한다."""
    matches = list(HEADING_RE.finditer(xml_text))
    sections = []
    for i, m in enumerate(matches):
        attrs_str = m.group(2)
        attr_m = ATTR_RE.search(attrs_str)
        attr = attr_m.group(1) if attr_m else None
        schema = lookup(attr) if attr else None
        if schema is None:
            continue  # 표준 서식 밖이거나(코드 없음), 비교 목적과 안 맞아 스킵하기로 한 섹션

        category, canonical_title, chapter = schema
        level = int(m.group(1))
        title = html.unescape(m.group(3))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(xml_text)
        fragment = xml_text[start:end]

        tables, amounts, text, detected_unit = parse_tables_and_text(fragment)
        attachment_refs = find_attachment_mentions(text, tables)
        violation_flag = detect_violation_flag(attr, fragment)
        sections.append({
            "attr": attr,
            "category": category,
            "canonical_title": canonical_title,
            "chapter": chapter,
            "level": level,
            "title": title,
            "tables": tables,
            "amounts": amounts,
            "amount_unit_detected": detected_unit,
            "text": text,
            "attachment_refs": attachment_refs,
            "has_attachment_gap": bool(attachment_refs),
            "violation_flag": violation_flag,
        })
    return apply_document_unit_fallback(sections)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="샘플로 처리할 브랜드 수 (미지정=전체)")
    ap.add_argument("--start", type=int, default=0,
                     help="이 순번(status=OK인 브랜드 기준, 0부터)부터 처리 시작. 전체를 한 번에 "
                          "돌리기엔 너무 오래 걸리는 환경(예: 3분 제한이 있는 실행기)에서 여러 번에 "
                          "나눠 이어 돌릴 때 씀 — 작업로그 참고. 0이 아니면 기존 결과 파일을 지우지 "
                          "않고 이어붙인다(append).")
    args = ap.parse_args()

    if not UNIFIED_PATH.exists():
        logger.error(f"{UNIFIED_PATH} 가 없습니다. 먼저 02_fetch_disclosure_content.py 를 실행하세요.")
        return

    if args.start == 0 and OUT_PATH.exists():
        OUT_PATH.unlink()  # 처음부터 돌리는 거면 매번 새로 만든다 (스키마가 바뀔 수 있으므로)

    n_brands = 0
    n_clauses = 0
    n_amounts = 0
    no_content_hits = []

    ok_idx = 0
    processed = 0
    for row in read_jsonl(UNIFIED_PATH):
        if row.get("status") != "OK":
            continue
        xml_path = DATA_DIR.parent / row["xml_path"]
        if not xml_path.exists():
            continue
        if ok_idx < args.start:
            ok_idx += 1
            continue
        ok_idx += 1
        if args.limit is not None and processed >= args.limit:
            break
        processed += 1

        xml_text = xml_path.read_text(encoding="utf-8")
        sections = extract_sections(xml_text)
        n_brands += 1

        hit_any = False
        for sec in sections:
            hit_any = True
            n_clauses += 1
            n_amounts += len(sec["amounts"])
            append_jsonl(OUT_PATH, {
                "brandMnno": row["brandMnno"],
                "brandNm": row["brandNm"],
                "brandNm_matched": row.get("brandNm_matched"),
                "jngIfrmpSn": row["jngIfrmpSn"],
                "attr": sec["attr"],
                "category": sec["category"],
                "chapter": sec["chapter"],
                "canonical_title": sec["canonical_title"],
                "section_level": sec["level"],
                "section_title": sec["title"],
                "text": sec["text"],
                "text_length": len(sec["text"]),
                "tables": sec["tables"],
                "amounts": sec["amounts"],
                "amount_unit_detected": sec["amount_unit_detected"],
                "amount_unit_source": sec.get("amount_unit_source"),
                "attachment_refs": sec["attachment_refs"],
                "has_attachment_gap": sec["has_attachment_gap"],
                "violation_flag": sec["violation_flag"],
                "source_xml": row["xml_path"],
            })
        if not hit_any:
            no_content_hits.append(row["brandNm"])

    logger.info(f"브랜드 {n_brands}건 처리 -> 조항 {n_clauses}건 추출 (금액 {n_amounts}건 인식)")
    if no_content_hits:
        logger.warning(
            f"대상 섹션이 하나도 안 걸린 브랜드 {len(no_content_hits)}건 "
            f"(예: {no_content_hits[:5]})"
        )
    logger.info(f"결과: {OUT_PATH}")

    if args.limit is None and args.start == 0:
        # 전체를 한 번에(청크 없이) 돌렸을 때만 gzip 압축본을 자동으로 만든다.
        with open(OUT_PATH, "rb") as f_in, gzip.open(OUT_PATH_GZ, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        gz_mb = OUT_PATH_GZ.stat().st_size / 1024 / 1024
        logger.info(f"gzip 압축본 생성: {OUT_PATH_GZ} ({gz_mb:.1f} MB) — git에는 이 파일만 커밋")
    else:
        logger.info("(--limit 테스트 또는 --start 청크 실행이라 gzip 압축본은 자동으로 안 만듦 — "
                     "모든 청크가 끝난 뒤 따로 gzip 압축할 것)")


if __name__ == "__main__":
    main()
