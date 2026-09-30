"""TOP20 화면용 브랜드 로고 만들기 — 정보공개서 원문(XML)에서 로고를 꺼내고, 규격(128px 정사각형)을 맞춰
frontend/public/logos/ 에 넣는다.

필요: Pillow, 백엔드 실행 환경(fastapi) — 로고를 만들 브랜드 목록을 top20 코드에서 가져오기 때문
사용법 (franchise-web 폴더에서):
    python tools/logos/logos.py               # 원문에서 추출 → 규격 맞추기까지 한 번에
    python tools/logos/logos.py --normalize   # 규격 맞추기만 (직접 넣은 로고를 정리할 때)
    python tools/logos/logos.py --seconds 600 # 600초만 추출하고 멈춤. 다시 실행하면 이어서 진행

[1단계] 추출 — 원문 XML에서 로고 고르기
    1. 대상: TOP20 화면에 나올 수 있는 브랜드(가맹점 5곳 이상)만. 전체를 넣으면 git 용량만 커진다.
    2. 원문 XML에서 이미지를 장(섹션)별로 모은다. 로고 후보 순서:
         4장 '가맹희망자가 앞으로 경영할 가맹사업의 내용' → 9장 '사용을 허용하는 지식재산권'
       (계열사 로고, 재무제표·표 캡처가 있는 다른 장은 제외)
    3. 기본은 후보 0번. logo_overrides.json 에 보정값이 있으면 그 번호를 쓴다.
       (형식과 예시는 logo_overrides.json 맨 위 "_설명" 참고, 후보 번호는 logo_preview.py 로 확인)
    4. 사람이 직접 넣은 로고는 건드리지 않는다. 보정값이 있을 때만 바꾼다.
    5. 고른 원본은 _work/raw/ 에 저장하고, 결과표를 _work/logo_extract_report.csv 로 남긴다.
       결과표의 '확인필요' 열(가로로 김 / 작음 / 9장에서 가져옴)은 로고가 아닐 수 있으니 미리보기로 확인.
    추출이 끝까지 완료됐을 때만 2단계로 넘어간다.

[2단계] 규격 맞추기 — 흰 배경 투명 처리 → 여백 자르기 → 정사각형 가운데 정렬 → 128px 투명 PNG
    1. public/logos/ 에 있는데 _work/raw/ 에 원본이 없는 파일(직접 넣은 로고)은 원본으로 복사해 둔다.
    2. public/logos/ 의 로고 전체를 항상 _work/raw/ 의 원본에서 다시 가공한다 → 여러 번 실행해도 화질이 나빠지지 않는다.
    3. 결과를 public/logos/ 에 png로 덮어쓴다. jpg·webp를 넣었으면 png로 바뀌고 원래 파일은 지워진다.

로고를 직접 넣을 때:
    - 파일 이름은 반드시 브랜드 관리번호로 한다. 예) GS25.png → BRD_20080100032.png
      (브랜드명 이름도 화면에 나오긴 하지만, 같은 브랜드의 자동 추출 로고가 있으면 그쪽이 우선이라 가려진다)
    - 파일을 public/logos/ 에 넣고 --normalize 로 실행한다.
    - 같은 이름으로 교체할 때는 _work/raw/ 의 예전 원본을 먼저 지운다 (안 지우면 예전 그림이 다시 나온다).
    - 바꿨는데 화면에 예전 그림이 보이면 frontend/.next/dev/cache/images 안의 캐시를 지운다.

_work/ 폴더(원본, 결과표, 미리보기, 진행 기록)는 로컬 작업용이라 git에 올리지 않는다.
"""
import argparse
import base64
import csv
import io
import json
import re
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                               # franchise-web 폴더 (tools/logos/ 두 단계 위)
XML_DIR = ROOT / "backend/data/disclosure/raw_xml"   # 정보공개서 원문 XML
LOGO_DIR = ROOT / "frontend/public/logos"            # 화면이 쓰는 최종 로고 (git에 올라감)
WORK_DIR = HERE / "_work"                            # 로컬 작업용 (git 제외)
RAW_DIR = WORK_DIR / "raw"                           # 가공 전 원본 로고
REPORT = WORK_DIR / "logo_extract_report.csv"        # 추출 결과표
PROGRESS = RAW_DIR / "_extract_progress.json"        # 추출 중간 저장. 처음부터 다시 하려면 이 파일을 지운다
OVERRIDES = HERE / "logo_overrides.json"             # 자동으로 고른 로고가 틀렸을 때의 보정값

# 추출 설정
LOGO_SECTIONS = ["JNGCDIDT_JNG_BIZ_INFO", "JNGHDQRTRS_IPRS_INFO"]  # 4장 → 9장 순서
SECTION_NAME = {"JNGCDIDT_JNG_BIZ_INFO": "4장", "JNGHDQRTRS_IPRS_INFO": "9장"}
HEAD_RE = re.compile(r'<h\d[^>]*\battr="([A-Z_]+)"')              # 장 제목 태그
IMG_RE = re.compile(r"data:image/\w+;base64,([A-Za-z0-9+/=]+)")   # 본문에 글자로 박힌 이미지

# 규격 맞추기 설정
SIZE = 128          # 최종 정사각형 한 변(px). 화면 표시는 40px라 선명도에 충분
MARGIN = 0.06       # 로고 주변에 남길 여백 비율
BG_TOLERANCE = 12   # 흰 배경으로 볼 밝기 허용치
BG_THRESH = 40      # 투명 처리할 때 배경과 같은 색으로 볼 색 차이 허용치 (클수록 로고 가장자리까지 지워짐)
WORK_SIZE = 512     # 투명 처리 전에 이 크기로 줄여 둔다 (큰 원본은 느리므로)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


# ───────────────────────── 1단계: 추출 ─────────────────────────

def load_overrides() -> dict:
    """logo_overrides.json 읽기 → {관리번호: 후보번호 또는 None}
    값은 숫자/null 이거나 {"후보": 번호, "브랜드": …, "메모": …} 형태. '_'로 시작하는 키는 설명이라 무시."""
    if not OVERRIDES.exists():
        return {}
    raw = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    return {k: (v.get("후보") if isinstance(v, dict) else v)
            for k, v in raw.items() if not k.startswith("_")}


def rankable_brands() -> dict:
    """TOP20에 나올 수 있는 브랜드 {관리번호: 브랜드명} (가맹점 5곳 이상, brand_data.py 계산을 그대로 사용)"""
    sys.path[:0] = [str(ROOT / "backend/scripts"), str(ROOT / "backend")]
    from app import brand_data
    return {s["brandMnno"]: s["brandNm"] for s in brand_data.all_brand_avg_sales()
            if (s["storeCount"] or 0) >= 5}


def latest_xml_per_brand() -> dict:
    """브랜드별 가장 최근 정보공개서 XML (파일명: 관리번호_문서번호.xml, 문서번호가 클수록 최신)"""
    found = {}
    for p in XML_DIR.glob("BRD_*.xml"):
        mnno, _, sn = p.stem.rpartition("_")
        if mnno not in found or int(sn) > int(found[mnno].stem.rpartition("_")[2]):
            found[mnno] = p
    return found


def candidates(xml_path: Path) -> list:
    """로고 후보 이미지 목록 [(장, PIL 이미지), ...] — 4장 이미지 먼저, 그다음 9장"""
    text = xml_path.read_text(encoding="utf-8", errors="ignore")
    heads = [(m.start(), m.group(1)) for m in HEAD_RE.finditer(text)]
    by_section = {s: [] for s in LOGO_SECTIONS}
    for m in IMG_RE.finditer(text):
        section = next((a for pos, a in reversed(heads) if pos < m.start()), None)
        if section not in by_section:
            continue
        try:
            im = Image.open(io.BytesIO(base64.b64decode(m.group(1))))
            im.load()
        except Exception:
            continue
        if min(im.size) >= 16:  # 점·선 같은 장식 이미지 제외
            by_section[section].append(im)
    return [(SECTION_NAME[s], im) for s in LOGO_SECTIONS for im in by_section[s]]


def warn_flags(section: str, im: Image.Image) -> str:
    """로고가 아닐 수도 있는 후보 표시 (결과표 '확인필요' 열): 가로로 김 / 작음 / 9장에서 가져옴"""
    w, h = im.size
    flags = []
    if max(w, h) / min(w, h) > 5:
        flags.append("가로로 김")
    if max(w, h) < 80:
        flags.append("작음")
    if section == "9장":
        flags.append("9장에서 가져옴")
    return ", ".join(flags)


def remove_logo(mnno: str) -> None:
    """로고 파일을 지운다 → 화면은 색깔 첫 글자 아이콘으로 대체 (파일이 남아 있으면 예전 그림이 계속 나온다)"""
    for folder in (LOGO_DIR, RAW_DIR):
        for p in folder.glob(f"{mnno}.*"):
            p.unlink()


def extract(seconds: int = 0) -> bool:
    """원문에서 로고를 골라 _work/raw/ 에 저장. 끝까지 완료하면 True, 시간 제한으로 멈추면 False"""
    started = time.time()
    overrides = load_overrides()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if PROGRESS.exists():
        prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
    else:
        # 처음 실행할 때 이미 있던 로고 = 사람이 직접 넣은 것 → 보정값 없으면 건드리지 않음
        prog = {"brands": rankable_brands(),
                "manual": sorted(p.stem for p in LOGO_DIR.glob("BRD_*.png")),
                "rows": {}}
    xmls = latest_xml_per_brand()
    manual = set(prog["manual"])

    for mnno, name in sorted(prog["brands"].items()):
        if mnno in prog["rows"] and mnno not in overrides:
            continue
        if seconds and time.time() - started > seconds:
            break
        row = {"관리번호": mnno, "브랜드명": name, "후보수": 0, "사용후보": "", "장": "",
               "크기": "", "확인필요": "", "상태": ""}
        if mnno in manual and mnno not in overrides:
            row["상태"] = "직접 넣은 로고 유지"
        elif mnno not in xmls:
            row["상태"] = "원문 없음"
        else:
            cands = candidates(xmls[mnno])
            pick = overrides.get(mnno, 0)
            row["후보수"] = len(cands)
            if pick is None or not cands:
                row["상태"] = "로고 없음"
                remove_logo(mnno)
            elif pick >= len(cands):
                row["상태"] = "보정값 범위 초과"
            else:
                section, im = cands[pick]
                im.convert("RGBA").save(RAW_DIR / f"{mnno}.png")    # 원본 → 2단계가 여기서 가공
                im.convert("RGBA").save(LOGO_DIR / f"{mnno}.png")   # 2단계가 규격 맞춘 것으로 덮어씀
                row.update({"사용후보": pick, "장": section, "크기": f"{im.size[0]}x{im.size[1]}",
                            "확인필요": warn_flags(section, im), "상태": "추출"})
        prog["rows"][mnno] = row
        PROGRESS.write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")

    rows = list(prog["rows"].values())
    if len(rows) < len(prog["brands"]):
        print(f"진행 {len(rows)}/{len(prog['brands'])} — 다시 실행하면 이어서 진행")
        return False
    with open(REPORT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["관리번호"]))
    done = sum(1 for r in rows if r["상태"] == "추출")
    print(f"추출 완료: 대상 {len(rows)}개 / 추출 {done}개 / 결과표: _work/{REPORT.name}")
    return True


# ───────────────────────── 2단계: 규격 맞추기 ─────────────────────────

def clear_background(im: Image.Image) -> Image.Image:
    """테두리에 닿아 있는 흰 배경을 투명으로 바꾼다.
    테두리와 이어지지 않은 흰색(글자 속, 흰 원형 배지 등)은 로고의 일부라 그대로 둔다."""
    im = im.convert("RGBA")
    im.thumbnail((WORK_SIZE, WORK_SIZE), Image.LANCZOS)
    w, h = im.size
    border = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for x in (0, w - 1) for y in range(h)]
    for xy in border:
        r, g, b, a = im.getpixel(xy)
        if a and min(r, g, b) >= 255 - BG_TOLERANCE:     # 아직 안 지운 흰 픽셀에서만 시작
            ImageDraw.floodfill(im, xy, (255, 255, 255, 0), thresh=BG_THRESH)
    return im


def trim(im: Image.Image) -> Image.Image:
    """투명 여백은 알파로, 단색(흰) 여백은 모서리 색과 비교해서 잘라낸다."""
    im = im.convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if bbox and bbox != (0, 0, *im.size):     # 투명 배경이면 알파 기준으로 충분
        return im.crop(bbox)
    rgb = im.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 * (v > BG_TOLERANCE))
    return im.crop(diff.getbbox() or (0, 0, *im.size))


def normalize_one(src: Path, dest: Path) -> None:
    """원본 한 장을 SIZE x SIZE 투명 PNG로 만들어 dest 에 저장"""
    im = trim(clear_background(Image.open(src)))
    inner = round(SIZE * (1 - MARGIN * 2))
    im.thumbnail((inner, inner), Image.LANCZOS)           # 비율 유지 축소
    ImageOps.pad(im, (SIZE, SIZE), color=(0, 0, 0, 0), centering=(0.5, 0.5)).save(dest, optimize=True)


def normalize() -> None:
    """public/logos/ 의 로고 전체를 _work/raw/ 의 원본에서 다시 가공해 덮어쓴다.
    원본이 없는 파일(직접 넣은 로고)은 먼저 원본으로 보관한다."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(LOGO_DIR.iterdir()):
        if path.suffix.lower() not in IMAGE_EXT:
            continue
        # 원본은 확장자와 상관없이 같은 이름으로 찾는다 (jpg로 넣은 로고는 원본이 .jpg로 남아 있음)
        raw = next((r for r in RAW_DIR.glob(f"{path.stem}.*") if r.suffix.lower() in IMAGE_EXT), None)
        if raw is None:
            raw = RAW_DIR / path.name
            shutil.copy2(path, raw)
        normalize_one(raw, path.with_suffix(".png"))
        if path.suffix.lower() != ".png":                  # jpg·webp를 넣었던 경우 png만 남긴다
            path.unlink()
        count += 1
    print(f"규격 맞추기 완료: {count}개 → {SIZE}x{SIZE}px")


def main():
    ap = argparse.ArgumentParser(description="TOP20 브랜드 로고 추출 + 규격 맞추기")
    ap.add_argument("--normalize", action="store_true", help="추출 없이 규격 맞추기만")
    ap.add_argument("--seconds", type=int, default=0, help="추출을 이 시간(초)만 하고 멈춤. 0이면 끝까지")
    args = ap.parse_args()
    if args.normalize or extract(args.seconds):
        normalize()


if __name__ == "__main__":
    main()
