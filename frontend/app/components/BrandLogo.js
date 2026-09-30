"use client";

import { useState } from "react";
import Image from "next/image";

// 팀원이 backend/data/disclosure XML에서 추출한 로고 993장(public/logos/)을 씀 —
// 파일명은 brandMnno.png. 로고 없거나 로드 실패하면 이니셜 플레이스홀더로 자동 폴백.
// (팀원이 만든 top20/BrandLogo.js·logos.js는 node:fs 기반 서버 전용이라
// "use client"인 이 페이지들(top20/compare)에선 못 써서, 이 컴포넌트에 직접 이식함 —
// 디렉터리 스캔 대신 파일 경로를 바로 시도하고 onError로 폴백하는 방식.)
//
// shape="circle"(기본, TOP3 글로우 링 있는 자리)은 로고를 꽉 채워 자르고(object-cover),
// shape="square"(로고 원본 비율 그대로 보여줘야 하는 자리)는 안 잘리게(object-contain).
export default function BrandLogo({ brandNm, brandMnno, size = 10, highlight = false, shape = "circle" }) {
  const [imgFailed, setImgFailed] = useState(false);
  const initial = (brandNm || "?").trim().charAt(0);
  const sizeClass = size === 8 ? "w-8 h-8" : size === 12 ? "w-12 h-12" : "w-10 h-10";
  const shapeClass = shape === "square" ? "rounded-md" : "rounded-full";
  const showImage = brandMnno && !imgFailed;

  return (
    <span className={`brand-logo-wrap relative inline-flex shrink-0 ${highlight ? "brand-logo-wrap--glow" : ""}`}>
      {showImage ? (
        <Image
          src={`/logos/${encodeURIComponent(brandMnno)}.png`}
          alt={`${brandNm || "브랜드"} 로고`}
          width={64}
          height={64}
          onError={() => setImgFailed(true)}
          className={`relative z-10 ${sizeClass} ${shapeClass} border border-hairline bg-surface ${
            shape === "square" ? "object-contain p-1" : "object-cover"
          }`}
        />
      ) : (
        <span
          className={`relative z-10 flex items-center justify-center ${sizeClass} ${shapeClass} bg-canvas-soft border border-hairline text-body-sm text-ink-secondary font-medium`}
          aria-hidden="true"
        >
          {initial}
        </span>
      )}

      <style jsx>{`
        /* BorderGlow(react-bits)의 conic-gradient 마스킹 기법을 얇은 원형 링 하나로
           단순화 — 포인터 추적/다색 메시는 제거하고 TOP3에서 항상 보이는 은은한
           단색(primary) 회전 링만 남김. */
        .brand-logo-wrap--glow::before {
          content: "";
          position: absolute;
          inset: -3px;
          border-radius: 9999px;
          background: conic-gradient(
            from 0deg,
            transparent 0deg,
            var(--color-primary) 60deg,
            transparent 150deg,
            transparent 210deg,
            var(--color-primary) 300deg,
            transparent 360deg
          );
          -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 2px));
          mask: radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 2px));
          opacity: 0.55;
          animation: brand-logo-glow-spin 6s linear infinite;
        }

        @keyframes brand-logo-glow-spin {
          to {
            transform: rotate(360deg);
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .brand-logo-wrap--glow::before {
            animation: none;
          }
        }
      `}</style>
    </span>
  );
}
