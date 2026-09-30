import { readdirSync } from "node:fs";
import path from "node:path";

const LOGO_DIR = path.join(process.cwd(), "public", "logos");
const IMAGE_EXT = /\.(png|jpe?g|webp|svg)$/i;

// public/logos/ 의 이미지 파일을 "파일명(확장자 제외) → /logos/파일" 맵으로 만든다.
// 파일명은 brandMnno 또는 brandNm. 서버 컴포넌트에서만 호출(요청마다 읽으니 파일 추가 즉시 반영).
export function loadLogoMap() {
  try {
    return Object.fromEntries(
      readdirSync(LOGO_DIR)
        .filter((f) => IMAGE_EXT.test(f))
        .map((f) => [path.parse(f).name.normalize("NFC"), `/logos/${encodeURIComponent(f)}`]),
    );
  } catch {
    return {};
  }
}

export function findLogo(logoMap, item) {
  return logoMap[item.brandMnno] || logoMap[(item.brandNm || "").normalize("NFC")] || null;
}
