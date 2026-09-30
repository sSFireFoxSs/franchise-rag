// TOP20 목록의 브랜드 로고 한 칸: 로고 파일이 있으면 이미지, 없으면 색깔 첫 글자 아이콘.
import Image from "next/image";

const SIZE = 40; // 화면에 보이는 로고 크기(px). 파일은 128px라 고해상도 화면에서도 선명하다

// 로고가 없는 브랜드의 첫 글자 아이콘 색 (globals.css 디자인 토큰 12가지, 글자는 모두 흰색).
// Tailwind가 클래스를 찾을 수 있게 문자열 전체를 그대로 적어 둔다.
const PALETTE = [
  "bg-primary text-on-primary",
  "bg-secondary text-on-primary",
  "bg-accent-teal text-on-primary",
  "bg-accent-orange text-on-primary",
  "bg-accent-brown text-on-primary",
  "bg-accent-purple-deep text-on-primary",
  "bg-accent-orange-deep text-on-primary",
  "bg-accent-purple text-on-primary",
  "bg-accent-sky text-on-primary",
  "bg-accent-pink text-on-primary",
  "bg-accent-green text-on-primary",
  "bg-ink text-on-primary",
];

// 같은 브랜드는 항상 같은 색이 나오도록, 관리번호(또는 이름) 글자로 색 번호를 정한다.
function pickColor(key) {
  let hash = 0;
  for (const ch of key || "") hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

// 첫 글자: 앞의 괄호·기호는 건너뛰고 첫 글자/숫자를 쓴다. 예) "(주)한솥" → "주", "3030영어" → "3"
function initial(name) {
  return (name || "").match(/[\p{L}\p{N}]/u)?.[0]?.toUpperCase() || "?";
}

// 로고 파일이 있으면 이미지, 없으면 브랜드별 색이 들어간 첫 글자 아이콘.
export default function BrandLogo({ src, name, id }) {
  if (src) {
    return (
      <Image
        src={src}
        alt={`${name} 로고`}
        width={SIZE}
        height={SIZE}
        className="h-10 w-10 shrink-0 rounded-md border border-hairline bg-surface object-contain p-1"
      />
    );
  }
  return (
    <span
      aria-hidden
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-body-md font-semibold ${pickColor(id || name)}`}
    >
      {initial(name)}
    </span>
  );
}
