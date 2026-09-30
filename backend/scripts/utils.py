"""
공통 유틸: HTTP 클라이언트(재시도/백오프/레이트리밋), 로깅, 체크포인트 헬퍼.
모든 수집 스크립트가 이 모듈을 공유합니다.
"""
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

DISCLOSURE_LIST_SERVICE_KEY = os.environ.get("DISCLOSURE_LIST_SERVICE_KEY", "")
FTC_BRAND_SERVICE_KEY = os.environ.get("FTC_BRAND_SERVICE_KEY", "")
SANGKWON_SERVICE_KEY = os.environ.get("SANGKWON_SERVICE_KEY", "")

BASE_URL = "https://franchise.ftc.go.kr/api/search.do"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


class RateLimitedClient:
    """
    - 요청 간 최소 딜레이(min_interval) 보장
    - 429 / 5xx / 타임아웃 시 지수 백오프 재시도
    - 모든 호출의 소요시간을 timing_log(csv)에 기록 → 이후 대량 수집 시간 추정에 사용
    """

    def __init__(self, min_interval: float = 0.35, max_retries: int = 4, timeout: int = 15,
                 timing_log_path: Optional[Path] = None):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_call_ts = 0.0
        self.session = requests.Session()
        # 기본 User-Agent가 "python-requests/x.x"이면 franchise.ftc.go.kr의 WAF가
        # 봇으로 판단해 406 Access denied로 차단한다. 일반 브라우저처럼 보이게 헤더를 채운다.
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://franchise.ftc.go.kr/",
        })
        self.timing_log_path = timing_log_path or (LOG_DIR / "timing.csv")
        if not self.timing_log_path.exists():
            self.timing_log_path.write_text("ts,elapsed_sec,status,url_type,ok\n", encoding="utf-8")
        self.last_error: Optional[str] = None

    def _throttle(self):
        elapsed = time.time() - self._last_call_ts
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, params: dict, url_type: str = "unknown", logger: Optional[logging.Logger] = None) -> Optional[requests.Response]:
        self.last_error = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            t0 = time.time()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                self._last_call_ts = time.time()
                elapsed = self._last_call_ts - t0
                self._log_timing(elapsed, resp.status_code, url_type, resp.ok)
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429 or resp.status_code >= 500:
                    backoff = min(2 ** attempt, 30)
                    time.sleep(backoff)
                    continue
                # 4xx (429 제외) : 재시도해도 안 바뀔 가능성이 높음 -> 바로 반환해서 호출부에서 처리
                return resp
            except requests.exceptions.RequestException as e:
                self._last_call_ts = time.time()
                elapsed = self._last_call_ts - t0
                self._log_timing(elapsed, -1, url_type, False)
                self.last_error = f"{type(e).__name__}: {e}"
                if logger:
                    logger.warning(f"요청 예외 (시도 {attempt}/{self.max_retries}): {self.last_error}")
                backoff = min(2 ** attempt, 30)
                time.sleep(backoff)
        return None

    def _log_timing(self, elapsed, status, url_type, ok):
        with open(self.timing_log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.0f},{elapsed:.3f},{status},{url_type},{ok}\n")


def read_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def append_jsonl(path: Path, obj: dict):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_done_ids(path: Path, id_field: str) -> set:
    """이미 처리 완료된 항목의 id 집합을 읽어온다 (재실행/이어하기용)."""
    done = set()
    if path.exists():
        for row in read_jsonl(path):
            if row.get(id_field) is not None:
                done.add(str(row[id_field]))
    return done
