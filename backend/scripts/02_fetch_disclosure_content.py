"""
2단계: brand_unified.jsonl 의 각 브랜드를 1단계에서 만든 연도별 인덱스와
사업자등록번호(brno) 기준으로 매칭해서 jngIfrmpSn을 찾고, 본문(content) API를 호출한다.

- brno가 걸리는 연도 중 "가장 최신 연도"를 그 브랜드의 진짜 최신 정보공개서로 본다.
  brand_unified.jsonl의 latest_year는 참고만 하고 신뢰하지 않는다 (실측 결과 다른 시스템
  기준이라 실제 등록연도와 거의 안 맞았음 — 01_fetch_disclosure_lists.py가 2008~올해
  전체를 받아둬야 이 매칭이 제대로 된다).
- 목차(title) API는 호출하지 않는다 -> 본문 XML 안에 <h1 title="...">, <h2 title="...">
  형태로 섹션 제목이 이미 들어있기 때문 (03_extract_clauses.py 에서 이걸로 조항을 뽑는다).
- 브랜드당 API 호출 1회 (list는 1단계에서 이미 연도당 1회로 끝났음) -> 요청수 최소화.
- 원문은 XML 그대로 보관 + 브라우저에서 바로 열어볼 수 있는 .html 버전도 함께 저장.
  (본문 XML 내부가 이미 <table>/<tr>/<td>/<span style=...>/<p> 같은 HTML 태그라서
   최소한의 래핑만 하면 그대로 렌더링됨)

- 2026-09-11 (19): 출력에 `brandNm_matched` 필드 추가 — brand_unified.jsonl의 정적 `brandNm`이 아니라,
  실제로 그 연도 목록 API 항목(entry)에서 매칭된 영업표지명. needs_review=true(영업표지명 여러 개, 709건)
  브랜드는 이 값을 대표 표시명으로 쓰기로 함. NOT_FOUND_IN_LIST는 매칭된
  entry가 없어서 null.

이어하기(resume) 지원: disclosure_unified.jsonl 에 이미 있는 jngIfrmpSn은 건너뜀.
그래서 회사 노트북/집 데스크톱을 오가며 나눠 돌려도, git pull 받은 뒤 이어서 실행하면 된다.

사용법:
  python scripts/02_fetch_disclosure_content.py --limit 300          # 샘플 300개
  python scripts/02_fetch_disclosure_content.py --limit 300 --skip-review  # needs_review=true 브랜드는 제외하고 샘플링
  python scripts/02_fetch_disclosure_content.py                      # limit 생략 시 전체(주의: 수만 건)
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (BASE_URL, DATA_DIR, DISCLOSURE_LIST_SERVICE_KEY,
                    RateLimitedClient, append_jsonl, get_logger,
                    load_done_ids, read_jsonl)

logger = get_logger("02_fetch_content")

LIST_DIR = DATA_DIR / "disclosure" / "lists"
RAW_XML_DIR = DATA_DIR / "disclosure" / "raw_xml"
RAW_HTML_DIR = DATA_DIR / "disclosure" / "raw_html"
OUT_PATH = DATA_DIR / "disclosure" / "disclosure_unified.jsonl"

RAW_XML_DIR.mkdir(parents=True, exist_ok=True)
RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

HTML_WRAPPER = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{title}</title>
<style>body{{font-family:'Malgun Gothic',sans-serif;max-width:900px;margin:24px auto;padding:0 16px;line-height:1.5}}
table{{border-collapse:collapse;margin:8px 0}} td,th{{border:1px solid #ccc;padding:4px 8px}}</style>
</head><body>
<h1 style="font-size:18px;color:#555">{title}</h1>
{body}
</body></html>
"""


def load_all_year_indexes() -> Dict[int, dict]:
    """LIST_DIR에 캐시된 연도 인덱스를 전부 로드한다 (01_fetch_disclosure_lists.py가 만든 것).
    브랜드의 latest_year 목록에 없어도, 실제 정보공개서는 다른 연도에 등록되어 있는 경우가 많아서
    (두 시스템이 '연도'를 다르게 취급하는 것으로 보임 — brand_unified의 latest_year는
    FftcBrandRlsInfo2_Service 기준, 여기 목록 API의 yr은 franchise.ftc.go.kr 자체 등록연도 기준)
    가진 모든 연도를 다 뒤져서 찾는다."""
    indexes = {}
    if not LIST_DIR.exists():
        return indexes
    for path in LIST_DIR.glob("*_index.json"):
        try:
            yr = int(path.stem.replace("_index", ""))
        except ValueError:
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data:
            indexes[yr] = data
    return indexes


import re as _re


def normalize_name(s):
    """공백류(일반 공백/줄바꿈/NBSP) 차이를 무시하기 위한 정규화.
    (2026-09-14 수정: 브랜드 오매칭 버그 수정 -- ftc_match.py 로직을 이식)"""
    if s is None:
        return ""
    return _re.sub(r"\s+", "", s.replace("\xa0", " "))


def match_entry(brand_row: dict, all_indexes: Dict[int, dict]):
    """모든 연도의 brno 후보를 먼저 다 합친 뒤, 브랜드명이 정규화 기준으로 정확히
    일치하는 후보만 채택한다.
    (2026-09-14 수정: 기존 로직은 "그 해 후보가 1개뿐이면 브랜드명 대조 없이 채택"
    해서, brno 하나가 여러 브랜드를 가진 경우(1:N) 완전히 다른 브랜드 문서가 조용히
    붙는 버그가 있었음 -- 실측 결과 매칭 2,369건 중 135건(5.7%)에서 발생 확인됨.
    예: BRD_20090100099 "신마포갈매기"에 "염소해장국" 문서가, BRD_20140725
    "매머드커피"에 "매머드익스프레스" 문서가 붙어있었음.
    일치하는 후보가 없으면 억지로 아무거나 채택하지 않고 None을 반환한다.
    반환값: (entry, matched_year) 또는 (None, None)"""
    brno = brand_row.get("brno")
    if not brno:
        return None, None

    names_to_try = [brand_row.get("brandNm")] + (brand_row.get("brandNm_variants") or [])
    target_names = set(normalize_name(n) for n in names_to_try if n)
    if not target_names:
        return None, None

    all_candidates = []  # (entry, yr) 전체 연도 통합, 첫 매치에서 멈추지 않음
    for yr, index in all_indexes.items():
        for c in (index.get(brno) or []):
            all_candidates.append((c, yr))

    if not all_candidates:
        return None, None

    exact_matches = [
        (c, yr) for c, yr in all_candidates
        if normalize_name(c.get("brandNm")) in target_names
    ]
    if not exact_matches:
        return None, None

    exact_matches.sort(key=lambda pair: pair[1], reverse=True)  # 최신 연도 우선
    best_entry, best_year = exact_matches[0]
    return best_entry, best_year


def fetch_content(client: RateLimitedClient, jng_ifrmp_sn: str, logger=None) -> Optional[str]:
    params = {"type": "content", "jngIfrmpSn": jng_ifrmp_sn, "serviceKey": DISCLOSURE_LIST_SERVICE_KEY}
    resp = client.get(BASE_URL, params, url_type="content", logger=logger)
    if resp is None or resp.status_code != 200:
        if logger:
            status = resp.status_code if resp else "N/A"
            detail = client.last_error or (resp.text[:300] if resp is not None else "")
            logger.error(f"jngIfrmpSn={jng_ifrmp_sn} 본문 호출 실패 (status={status}) 원인: {detail}")
        return None
    return resp.text


def strip_xml_body(xml_text: str) -> str:
    """<?xml ...?> 선언만 제거하고 나머지(HTML 유사 태그)는 그대로 body에 넣는다."""
    idx = xml_text.find("?>")
    return xml_text[idx + 2:] if idx != -1 else xml_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="샘플로 처리할 브랜드 수 (미지정=전체)")
    ap.add_argument("--skip-review", action="store_true", help="needs_review=true 브랜드는 샘플에서 제외")
    ap.add_argument("--brand-file", default=str(DATA_DIR / "brand" / "brand_unified.jsonl"))
    ap.add_argument("--min-interval", type=float, default=0.35, help="요청 간 최소 간격(초)")
    ap.add_argument("--only-ids", default=None,
                     help="이 파일에 적힌 brandMnno만 처리(한 줄에 하나씩). 나머지 12,000여 건은 "
                          "아예 안 훑고 건너뛰어서 NOT_FOUND_IN_LIST 중복 기록도 안 생기고 빠름. "
                          "특정 브랜드만 재수집할 때 씀(예: 다른 컴퓨터엔 있는데 이 컴퓨터엔 파일이 "
                          "없는 경우 — 작업로그 (26) 참고).")
    args = ap.parse_args()

    only_ids = None
    if args.only_ids:
        only_ids = set(
            line.strip() for line in Path(args.only_ids).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        logger.info(f"--only-ids 지정됨: {len(only_ids)}개 brandMnno만 처리 (나머지는 건너뜀)")

    if not DISCLOSURE_LIST_SERVICE_KEY:
        logger.error("DISCLOSURE_LIST_SERVICE_KEY 가 .env에 없습니다.")
        return

    done_ids = load_done_ids(OUT_PATH, "jngIfrmpSn")
    logger.info(f"이미 완료된 항목: {len(done_ids)}건 (이어서 진행)")

    all_indexes = load_all_year_indexes()
    logger.info(f"로드된 연도 인덱스: {sorted(all_indexes.keys(), reverse=True)} "
                f"(브랜드 latest_year에 없어도 이 연도들 전체에서 brno를 찾습니다)")
    if not all_indexes:
        logger.error("캐시된 목록 인덱스가 없습니다. 먼저 01_fetch_disclosure_lists.py 를 실행하세요.")
        return

    client = RateLimitedClient(min_interval=args.min_interval)

    processed = 0
    matched = 0
    matched_diff_year = 0  # latest_year가 아닌 다른 연도에서 매칭된 건수 (연도 불일치 가설 검증용)
    not_found = 0
    fetched_ok = 0
    fetched_fail = 0
    t_start = time.time()

    for brand_row in read_jsonl(Path(args.brand_file)):
        if only_ids is not None and brand_row.get("brandMnno") not in only_ids:
            continue  # --only-ids 지정 시 나머지는 매칭 시도조차 안 함 (속도/로그 둘 다 절약)
        if args.limit is not None and processed >= args.limit:
            break
        if args.skip_review and brand_row.get("needs_review"):
            continue

        entry, matched_year = match_entry(brand_row, all_indexes)
        processed += 1

        if entry is None:
            not_found += 1
            append_jsonl(OUT_PATH, {
                "brandMnno": brand_row.get("brandMnno"),
                "brandNm": brand_row.get("brandNm"),
                "brno": brand_row.get("brno"),
                "jngIfrmpSn": None,
                "status": "NOT_FOUND_IN_LIST",
            })
            continue

        matched += 1
        brand_latest_year = brand_row.get("latest_year")
        if brand_latest_year and int(brand_latest_year) != matched_year:
            matched_diff_year += 1
        jng_sn = entry["jngIfrmpSn"]

        if jng_sn in done_ids:
            continue  # 이어하기: 이미 처리됨

        xml_text = fetch_content(client, jng_sn, logger=logger)
        if xml_text is None:
            fetched_fail += 1
            append_jsonl(OUT_PATH, {
                "brandMnno": brand_row.get("brandMnno"),
                "brandNm": brand_row.get("brandNm"),
                "brandNm_matched": entry.get("brandNm"),
                "brno": brand_row.get("brno"),
                "jngIfrmpSn": jng_sn,
                "jngIfrmpRgsno": entry.get("jngIfrmpRgsno"),
                "status": "FETCH_FAILED",
            })
            continue

        fetched_ok += 1
        brand_mnno = brand_row.get("brandMnno") or "UNKNOWN"
        xml_path = RAW_XML_DIR / f"{brand_mnno}_{jng_sn}.xml"
        html_path = RAW_HTML_DIR / f"{brand_mnno}_{jng_sn}.html"

        xml_path.write_text(xml_text, encoding="utf-8")
        title = f"{brand_row.get('brandNm')} ({brand_row.get('corpNm')}) - 정보공개서 {matched_year}"
        html_path.write_text(
            HTML_WRAPPER.format(title=title, body=strip_xml_body(xml_text)),
            encoding="utf-8",
        )

        append_jsonl(OUT_PATH, {
            "brandMnno": brand_mnno,
            "brandNm": brand_row.get("brandNm"),
            "brandNm_matched": entry.get("brandNm"),
            "corpNm": brand_row.get("corpNm"),
            "brno": brand_row.get("brno"),
            "latest_year_in_brand_data": brand_row.get("latest_year"),
            "matched_year": matched_year,
            "jngIfrmpSn": jng_sn,
            "jngIfrmpRgsno": entry.get("jngIfrmpRgsno"),
            "xml_path": xml_path.relative_to(DATA_DIR.parent).as_posix(),  # 항상 /로 저장 (윈도-리눅스 호환, 19번 로그)
            "html_path": html_path.relative_to(DATA_DIR.parent).as_posix(),
            "content_length": len(xml_text),
            "status": "OK",
        })
        done_ids.add(jng_sn)

        if processed % 20 == 0:
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            logger.info(
                f"진행 {processed}건 | 매칭 {matched}(연도다름 {matched_diff_year}) | 미매칭 {not_found} | "
                f"성공 {fetched_ok} | 실패 {fetched_fail} | {rate:.2f}건/초"
            )

    elapsed = time.time() - t_start
    logger.info("=" * 60)
    logger.info(f"처리 {processed}건 완료 (소요 {elapsed:.1f}초)")
    logger.info(f"매칭 성공 {matched} (그 중 brand_unified의 latest_year와 다른 연도에서 찾은 건 "
                f"{matched_diff_year}건) / 목록 내 미발견 {not_found}")
    logger.info(f"본문 수집 성공 {fetched_ok} / 실패 {fetched_fail}")
    if fetched_ok > 0:
        logger.info(f"브랜드당 평균 {elapsed / max(processed,1):.2f}초 "
                     f"-> 13,725건 전체 예상 소요: 약 {13725 * elapsed / max(processed,1) / 3600:.1f}시간")
    logger.info(f"결과: {OUT_PATH}")


if __name__ == "__main__":
    main()
