"""로고 후보 미리보기 이미지 만들기 — 틀린 로고만 골라 logo_overrides.json 에 보정값을 적기 위한 용도.

사용법 (franchise-web 폴더에서):
    python tools/logos/logo_preview.py top       # TOP20 화면 상위권(전체 TOP20 + 대분류별 상위 5위)
    python tools/logos/logo_preview.py flagged   # 결과표(_work/logo_extract_report.csv)에서 '확인필요' 표시된 브랜드
결과: tools/logos/_work/preview/ 폴더에 한 장당 25개 브랜드씩 PNG로 저장 (git에 올리지 않음)

읽는 법: 한 줄 = 브랜드 하나. 왼쪽부터 후보 0, 1, 2 … 빨간 테두리가 지금 쓰는 후보.
틀렸으면 logo_overrides.json 에 {"관리번호": 후보번호} 또는 {"관리번호": null}(로고 없음)을 적고
python tools/logos/logos.py 를 다시 실행한다.
"""
import csv
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import logos as ex  # noqa: E402  (경로·후보 찾기 함수를 logos.py와 함께 씀)

OUT_DIR = ex.WORK_DIR / "preview"   # _work/preview (git 제외)
PER_SHEET, MAX_CANDS = 25, 6
CELL_W, CELL_H, NAME_W = 170, 90, 260


def font(size):
    for f in ["C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def screen_brands() -> list:
    """TOP20 화면에 실제로 보이는 브랜드: 전체 TOP20 + 대분류별 상위 5위 (정렬 2가지)"""
    sys.path[:0] = [str(ex.ROOT / "backend/scripts"), str(ex.ROOT / "backend")]
    from app.routers import top20
    seen = []
    for by in ("sales", "stores"):
        lists = [top20.brands_top20(by, 20, 5, None, None)["items"]]
        lists += [top20.brands_top20(by, 5, 5, big, None)["items"] for big in top20._industry_options()]
        for items in lists:
            seen += [i["brandMnno"] for i in items if i["brandMnno"] not in seen]
    return seen


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "top"
    report = {r["관리번호"]: r for r in csv.DictReader(open(ex.REPORT, encoding="utf-8-sig"))}
    if mode == "flagged":
        targets = [m for m, r in report.items() if r["확인필요"]]
    else:
        targets = screen_brands()
    xmls = ex.latest_xml_per_brand()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    f_name, f_small = font(16), font(13)

    for page in range(0, len(targets), PER_SHEET):
        chunk = targets[page:page + PER_SHEET]
        sheet = Image.new("RGB", (NAME_W + CELL_W * MAX_CANDS, CELL_H * len(chunk)), "white")
        d = ImageDraw.Draw(sheet)
        for row, mnno in enumerate(chunk):
            y = row * CELL_H
            r = report.get(mnno, {})
            d.text((8, y + 10), r.get("브랜드명", mnno)[:16], fill="black", font=f_name)
            d.text((8, y + 34), mnno, fill="gray", font=f_small)
            d.text((8, y + 54), (r.get("상태", "") + " " + r.get("확인필요", ""))[:28], fill="red", font=f_small)
            cands = ex.candidates(xmls[mnno]) if mnno in xmls else []
            chosen = r.get("사용후보")
            for i, (section, im) in enumerate(cands[:MAX_CANDS]):
                x = NAME_W + i * CELL_W
                thumb = im.convert("RGBA")
                thumb.thumbnail((CELL_W - 16, CELL_H - 26))
                bg = Image.new("RGBA", thumb.size, "white")
                bg.alpha_composite(thumb)
                sheet.paste(bg.convert("RGB"), (x + 8, y + 20))
                d.text((x + 8, y + 3), f"{i} ({section})", fill="gray", font=f_small)
                if str(i) == str(chosen):
                    d.rectangle([x + 2, y + 2, x + CELL_W - 3, y + CELL_H - 3], outline="red", width=3)
            d.line([(0, y + CELL_H - 1), (sheet.width, y + CELL_H - 1)], fill="#ddd")
        out = OUT_DIR / f"{mode}_{page // PER_SHEET + 1:02d}.png"
        sheet.save(out)
        print(out.name, len(chunk), "개")


if __name__ == "__main__":
    main()
