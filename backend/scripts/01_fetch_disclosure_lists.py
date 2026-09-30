"""
1단계: 정보공개서 "목록조회" API를 연도별로 1회씩만 호출해서 캐싱한다.

⚠️ 처음엔 brand_unified.jsonl의 latest_year(2025/2024)만 받으면 될 줄 알았는데,
실제로 해보니 2025년 목록엔 2,323건, 2024년엔 140건밖에 없었음 (브랜드는 12,498개).
즉 대부분 브랜드의 "진짜 최신 정보공개서"는 그보다 훨씬 이전 연도에 등록되어 있다는 뜻.
brand_unified.jsonl의 latest_year는 다른 시스템(FftcBrandRlsInfo2_Service) 기준이라
franchise.ftc.go.kr의 실제 등록연도와는 무관했음 (실측으로 확인됨).

그래서 기본 동작을 "브랜드 목록에서 뽑은 연도만" -> "전체 연도 범위(기본 2008~올해)"로 바꿈.
브랜드 코드(BRD_2008...)가 2008년부터 시작하는 걸 보고 시작연도를 2008로 잡음.

결과:
  data/disclosure/lists/{yr}.xml         - 원본 XML 그대로 보관 (감사/재파싱용)
  data/disclosure/lists/{yr}_index.json  - {brno: [ {jngIfrmpSn, corpNm, brandNm, jngIfrmpRgsno}, ... ]}

재실행해도 이미 받은 연도는 건너뛴다.
사용법:
  python scripts/01_fetch_disclosure_lists.py                      # 기본: 2008~올해 전체
  python scripts/01_fetch_disclosure_lists.py --start-year 2015     # 시작연도만 조정
  python scripts/01_fetch_disclosure_lists.py --years 2025 2024 2023  # 특정 연도만 수동 지정
"""
import argparse
import datetime
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (BASE_URL, DATA_DIR, DISCLOSURE_LIST_SERVICE_KEY,
                    RateLimitedClient, get_logger)

logger = get_logger("01_fetch_lists")

LIST_DIR = DATA_DIR / "disclosure" / "lists"
LIST_DIR.mkdir(parents=True, exist_ok=True)

NUM_OF_ROWS = 500  # 목록 API 페이지당 최대치 근처로 설정 (요청 수 최소화). 서버가 더 작게 자르면 자동 대응.


DEFAULT_START_YEAR = 2008  # 브랜드코드가 BRD_2008... 부터 시작하는 걸 근거로 잡음


def full_year_range(start_year: int) -> List[int]:
    current_year = datetime.date.today().year
    return list(range(current_year, start_year - 1, -1))  # 최신 연도부터 (사용자 체감상 최신 것부터 채워지는 게 좋음)


def fetch_year(client: RateLimitedClient, yr: int) -> dict:
    """해당 연도의 전체 목록을 페이지네이션으로 다 받아서 brno -> [items] 인덱스로 반환."""
    index = defaultdict(list)
    page_no = 1
    all_raw_items_xml = []
    total_count = None

    while True:
        params = {
            "type": "list",
            "yr": yr,
            "serviceKey": DISCLOSURE_LIST_SERVICE_KEY,
            "pageNo": page_no,
            "numOfRows": NUM_OF_ROWS,
        }
        resp = client.get(BASE_URL, params, url_type="list", logger=logger)
        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp else "N/A"
            detail = client.last_error or (resp.text[:300] if resp is not None else "")
            logger.error(f"[yr={yr}] page={page_no} 호출 실패 (status={status}) 원인: {detail}")
            break

        root = ET.fromstring(resp.text)
        if total_count is None:
            tc = root.findtext("totalCount")
            total_count = int(tc) if tc else 0
            logger.info(f"[yr={yr}] totalCount={total_count}")

        items = root.findall(".//item")
        if not items:
            break

        for item in items:
            brno = item.findtext("brno")
            entry = {
                "jngIfrmpSn": item.findtext("jngIfrmpSn"),
                "corpNm": item.findtext("corpNm"),
                "brandNm": item.findtext("brandNm"),
                "jngIfrmpRgsno": item.findtext("jngIfrmpRgsno"),
            }
            if brno:
                index[brno].append(entry)
            all_raw_items_xml.append(item)

        logger.info(f"[yr={yr}] page={page_no} -> {len(items)}건 수신 (누적 {sum(len(v) for v in index.values())})")

        if page_no * NUM_OF_ROWS >= total_count:
            break
        page_no += 1

    # 원본 보관 (감사/재파싱 대비)
    wrapper = ET.Element("root")
    tc_el = ET.SubElement(wrapper, "totalCount")
    tc_el.text = str(total_count or 0)
    items_el = ET.SubElement(wrapper, "items")
    for it in all_raw_items_xml:
        items_el.append(it)
    ET.ElementTree(wrapper).write(LIST_DIR / f"{yr}.xml", encoding="utf-8", xml_declaration=True)

    with open(LIST_DIR / f"{yr}_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=0)

    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=None,
                     help="수집할 연도를 직접 지정 (미지정 시 --start-year~올해 전체)")
    ap.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR,
                     help=f"전체 범위 수집 시 시작연도 (기본 {DEFAULT_START_YEAR})")
    args = ap.parse_args()

    if not DISCLOSURE_LIST_SERVICE_KEY:
        logger.error("DISCLOSURE_LIST_SERVICE_KEY 가 .env에 없습니다. .env.example을 참고해 .env를 만드세요.")
        return

    years = args.years or full_year_range(args.start_year)
    logger.info(f"수집 대상 연도: {years} ({len(years)}개 연도)")

    client = RateLimitedClient(min_interval=0.35)

    for yr in years:
        idx_path = LIST_DIR / f"{yr}_index.json"
        if idx_path.exists():
            # 이전 실행이 실패해서 빈 {} 로 저장된 캐시는 유효한 캐시로 치지 않고 다시 받는다.
            try:
                with open(idx_path, encoding="utf-8") as f:
                    cached = json.load(f)
            except (json.JSONDecodeError, OSError):
                cached = {}
            if cached:
                logger.info(f"[yr={yr}] 이미 캐시됨 ({len(cached)}개 brno) -> 건너뜀 (새로 받으려면 파일 삭제 후 재실행)")
                continue
            logger.warning(f"[yr={yr}] 캐시 파일이 비어있음(이전 실행 실패로 추정) -> 다시 받습니다")
        fetch_year(client, yr)

    logger.info("완료. data/disclosure/lists/ 에 연도별 인덱스가 생성되었습니다.")


if __name__ == "__main__":
    main()
