"""
정보공개서 표준서식의 "공식 섹션 코드" 참조표.

원문 XML의 헤딩 태그에는 <hN attrb_sn="AF_0401010000" attr="FRCS_BZMN_FRST_JNNT_INFO"
title="1) 최초 가맹금" ...> 처럼 공정위 쪽에서 붙여놓은 고정 필드 코드(attrb_sn/attr)가
브랜드 상관없이 항상 동일하게 박혀있다 (2026-09-11, 전체 2,256개 브랜드・243,162개 헤딩
전수조사로 확인: 예외 0건, 고유 코드 110개). 제목 문구나 앞 번호는 브랜드마다 미묘하게
다를 수 있지만(예: "11. 가맹금 예치" vs "가맹금 예치 기관") attr 코드는 절대 안 바뀐다.

그래서 섹션을 "제목 키워드"가 아니라 이 attr 코드로 식별한다. 03_extract_clauses.py가
이 표를 갖고: (1) 어떤 섹션을 뽑을지(SELECTED_SECTIONS에 있는 것만), (2) 그 섹션의
카테고리가 뭔지를 결정한다.

전체 110개 코드 중 "가맹 희망자가 여러 브랜드를 비교할 때 실제로 보고 싶어할 내용"
위주로 골랐다(나머지는 회사 연혁/임원명단/재무제표 등 비교 목적과 거리가 먼 항목,
또는 순수 안내문 성격이라 제외). 최초 선별 시 37개였고, 2026-09-14에 누락됐던 Ⅱ장
"평균매출액" 코드 1개를 추가해서 현재 38개. 자세한 판단 근거는 docs/DESIGN.md 개발 기록 참고.
"""

# attr 코드 -> (카테고리, 참고용 대표 제목, 소속 장)
# 대표 제목/장은 전수조사에서 가장 흔했던(top_title) 표기를 그대로 씀 — 브랜드별 실제 제목은
# 조항 데이터의 section_title 필드에 원문 그대로 따로 저장되니 여기 있는 건 참고용.
SECTION_SCHEMA = {
    # --- 평균매출액 (Ⅱ장, 2026-09-14 추가) ---
    # 기획서에 필수 구조화 항목으로 명시돼 있었는데 최초 37개 코드 선별 때 누락됐던 걸 뒤늦게
    # 발견함. "매출액"이 들어간 헤딩이 여러 장(Ⅰ/Ⅱ/Ⅴ/Ⅸ)에 흩어져 있는데, 그 중 예비 창업자가
    # 브랜드 비교에 실제로 쓸 "가맹점당 평균매출액"은 이 코드 하나뿐이다(전수조사로 확인 —
    # Ⅰ장 것은 회사 전체 가맹사업 매출, Ⅴ장 것은 온/오프라인 매출 비중, Ⅸ장 것은 직영점 매출이라
    # 성격이 다름). 400개 브랜드 샘플 기준 커버리지 97.8%(2,443/2,498, 나머지는 이 섹션 자체가
    # 없는 극소수 브랜드).
    "RB_BIZ_YR_FYER_AVRG_SLS_AMT": ("평균매출액", "바로 전 사업연도 가맹점사업자의 연간 평균 매출액(직영점 매출은 제외)과 그 산정기준", "Ⅱ"),

    # --- 위약금/손해배상 ---
    "JNG_CTRT_VIOLT_REPRATN_INFO": ("위약금/손해배상", "가맹계약 위반 시 손해배상에 관한 사항", "Ⅴ"),

    # --- 필수구입물품 ---
    "THNG_PURCHS_HIRE_STUS": ("필수구입물품", "물품 구입 및 임차 현황", "Ⅴ"),
    "RB_BIZ_YR_SPLY_PRC": ("필수구입물품", "주요 품목별 직전 사업연도 공급가격의 상ㆍ하한", "Ⅴ"),
    "BRAND_DLNG_PRDLST_INFO": ("필수구입물품", "구입ㆍ임차 품목 안내", "Ⅴ"),
    "SPCL_PRTCT_PROFIT_INFO": ("필수구입물품", "특수관계인의 경제적 이익", "Ⅴ"),
    "JNGHDQRTRS_DLNG_ENFRC_PROFIT": ("필수구입물품", "거래 강제/권장의 대가", "Ⅴ"),
    "SPCL_PRTCT_DLNG_ENFRC_PROFIT": ("필수구입물품", "특수관계인의 거래 강제 대가", "Ⅴ"),
    "PRDLST_CRTRA_JNNT_GIVE_INFO": ("필수구입물품", "구입요구 품목 구입을 통한 가맹금 지급(차액가맹금)", "Ⅳ"),
    "FRCS_OPER_THNG_SPLY_ENTRPS": ("필수구입물품", "가맹점 운영에 필요한 설비 등 공급업체", "Ⅳ"),

    # --- 가맹비/가맹금 (실제 금액. "가맹금 예치기관" 안내문과는 다름 — 그건 일부러 제외) ---
    "FRCS_BZMN_FRST_JNNT_INFO": ("가맹비/가맹금", "최초 가맹금", "Ⅳ"),
    "FRCS_BZMN_DEPO_JNNT_INFO": ("가맹비/가맹금", "예치가맹금의 범위와 그 금액", "Ⅳ"),
    "FRCS_BZMN_ADDM_CT_INFO": ("가맹비/가맹금", "그 밖에 지급하여야 하는 비용", "Ⅳ"),
    "JNNT_PAY_PROCSS_INFO": ("가맹비/가맹금", "가맹금 분할 납부 절차", "Ⅳ"),

    # --- 보증금 ---
    "FRCS_BZMN_ASSRNC_AMT_INFO": ("보증금", "보증금", "Ⅳ"),

    # --- 로열티 (영업 중 비용부담 표 안에 로열티 행이 포함됨 — 실측 확인함) ---
    "FRCS_BZMN_CT_BND_INFO": ("로열티", "영업 중의 비용 부담(로열티 등)", "Ⅳ"),

    # --- 영업지역 ---
    "MNPLY_ECL_BSN_AREA_STNG_CN": ("영업지역", "독점적ㆍ배타적 영업지역 설정", "Ⅴ"),
    "BSN_AREA_STNG_CRTRA_INFO": ("영업지역", "영업지역 설정기준", "Ⅴ"),
    "BSN_AREA_READJST_RSN": ("영업지역", "영업지역 재조정 사유 및 절차", "Ⅴ"),
    "BSN_CUST_NTSL_LMTT_INFO": ("영업지역", "영업지역 밖 판매 제한", "Ⅴ"),
    "AGENCY_DISTB_CHNNL_SPLY_YN": ("영업지역", "대리점 등 유통채널 공급 여부", "Ⅴ"),
    "ONLINE_DISTB_CHNNL_SPLY_YN": ("영업지역", "온라인 등 유통채널 공급 여부", "Ⅴ"),
    "ETC_BSN_AREA_INFO": ("영업지역", "그 밖의 영업지역 관련 내용", "Ⅴ"),

    # --- 계약해지 ---
    "JNG_CTRT_UPDT_PD": ("계약해지", "가맹계약 및 갱신 기간", "Ⅴ"),
    "CTRT_ET_END_PROCSS": ("계약해지", "계약 연장ㆍ재계약ㆍ종료 절차", "Ⅴ"),
    "CTRT_UPDT_REJECT_RSN": ("계약해지", "계약 갱신 거절(종료) 사유", "Ⅴ"),
    "CTRT_CNCLTN_RSN_PROCSS": ("계약해지", "계약 해지 사유 및 절차", "Ⅴ"),
    "CTRT_MDFCN_RSN_INFO": ("계약해지", "계약 수정 사유 및 절차", "Ⅴ"),
    "CTRT_ET_BND_INFO": ("계약해지", "계약 연장/재계약 과정의 추가 부담", "Ⅳ"),
    "JNGHDQRTRS_CTRT_END_ACTN_CN": ("계약해지", "가맹본부 사정에 의한 계약종료 시 조치사항", "Ⅳ"),
    "CTRT_END_ACTN_INFO": ("계약해지", "계약 종료 후 조치사항", "Ⅳ"),

    # --- 행정처분 ---
    "COREC_ACTN_INFO": ("행정처분", "공정거래위원회 또는 시ㆍ도 지사의 시정조치 등", "Ⅲ"),

    # --- 소송/법위반 ---
    "CVLST_INFO": ("소송/법위반", "민사소송 및 민사상 화해", "Ⅲ"),
    "PETY_ADJU_INFO": ("소송/법위반", "형(刑)의 선고", "Ⅲ"),

    # --- 교육비 ---
    "EDU_TRAING_MAJR_CN": ("교육비", "교육ㆍ훈련의 주요내용", "Ⅷ"),
    "EDU_TRAING_MUMM_HR_CT": ("교육비", "교육ㆍ훈련의 최소시간 및 비용", "Ⅷ"),
    "EDU_TRAING_MBY_INFO": ("교육비", "교육ㆍ훈련의 주체", "Ⅷ"),
    "EDU_TRAING_DSDVNT_INFO": ("교육비", "교육ㆍ훈련 불참 시 불이익", "Ⅷ"),
}

CATEGORY_NAMES = sorted(set(v[0] for v in SECTION_SCHEMA.values()))

# 2026-09-14: RAG 검색 전략 분기용 (scripts/rag/ 참고) — 어떤 카테고리는 amounts 필드를
# 직접 조회하는 게 벡터검색보다 정확하고(숫자는 근사검색에 안 맞음), 어떤 카테고리는 서술형이라
# 벡터검색이 필요하다. docs/DESIGN.md "RAG 질의응답 아키텍처 설계" 2단계 분기 기준을 그대로 상수화함 —
# 재논의 없이 확정된 분류이므로 여기서 코드로 고정해서 rag_core와 임베딩 빌드 스크립트가 같은
# 기준을 공유하게 한다(따로따로 하드코딩하면 어긋날 위험).
STRUCTURED_CATEGORIES = {"가맹비/가맹금", "보증금", "교육비", "로열티", "평균매출액", "행정처분"}
VECTOR_CATEGORIES = {"계약해지", "필수구입물품", "영업지역", "소송/법위반", "위약금/손해배상"}

# 2026-09-17 (작업로그 (41)): 위 두 집합은 SECTION_SCHEMA(원문 attr 코드)에서 그대로
# 나온 "실제 장(章) 카테고리"인데, 이건 그런 게 아니라 scripts/rag/total_cost.py가 여러
# 카테고리(최초 가맹금/그 밖의 비용/보증금 또는 예치가맹금)의 합계를 모아 계산해서 보여주는
# 합성 카테고리다. nlu.py가 intent="금액조회"로 분류하되 canonical_title 없이 이 카테고리
# 이름 하나로만 라우팅한다.
TOTAL_COST_CATEGORY = "총창업비용"

assert STRUCTURED_CATEGORIES | VECTOR_CATEGORIES == set(CATEGORY_NAMES), (
    "STRUCTURED_CATEGORIES/VECTOR_CATEGORIES가 CATEGORY_NAMES 전체를 안 덮음 — "
    "새 카테고리를 SECTION_SCHEMA에 추가했으면 이 두 집합 중 하나에도 분류해줄 것."
)
assert not (STRUCTURED_CATEGORIES & VECTOR_CATEGORIES), "구조화/벡터 카테고리가 겹치면 안 됨"


def lookup(attr: str):
    """attr 코드 -> (category, canonical_title, chapter). 스키마에 없으면(=제외 대상) None."""
    return SECTION_SCHEMA.get(attr)


def pick_display_name(brand_nm, brand_nm_matched):
    """brandNm_matched를 우선하되, "?"가 섞여있고 정적 brandNm에는 없으면 brandNm으로 폴백한다
    (franchise.ftc.go.kr 응답 자체가 드물게 깨진 문자를 "?"로 반환하는 경우 대응, 2026-09-15
    실측: 2,441개 중 5건, 그 중 3건은 brandNm이 깨끗함)."""
    if isinstance(brand_nm_matched, str) and brand_nm_matched.strip():
        if "?" in brand_nm_matched and brand_nm and "?" not in brand_nm:
            return brand_nm
        return brand_nm_matched
    return brand_nm
