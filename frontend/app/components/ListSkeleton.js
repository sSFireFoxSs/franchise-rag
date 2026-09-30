"use client";

// badge_01(Uiverse.io by mrhyddenn) 참고 — 회색 블록에 그라데이션이 좌우로 흐르는
// shimmer 애니메이션. 로딩 중 "불러오는 중…" 텍스트 한 줄 대신, 실제 리스트 행과
//비슷한 모양의 스켈레톤을 보여줘서 레이아웃이 갑자기 안 바뀌게 한다.
export default function ListSkeleton({ rows = 6 }) {
  return (
    <div className="feature-card divide-y divide-hairline overflow-hidden">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
          <span className="skeleton-block w-5 h-5 rounded shrink-0" />
          <span className="skeleton-block w-10 h-10 rounded-full shrink-0" />
          <div className="flex-1 min-w-0 flex flex-col gap-2">
            <span className="skeleton-block h-4 rounded" style={{ width: "40%" }} />
            <span className="skeleton-block h-3 rounded" style={{ width: "25%" }} />
          </div>
          <span className="skeleton-block h-5 w-24 rounded shrink-0" />
        </div>
      ))}

      <style jsx>{`
        .skeleton-block {
          display: inline-block;
          background: linear-gradient(
            120deg,
            var(--color-hairline) 30%,
            var(--color-canvas-soft) 38%,
            var(--color-canvas-soft) 40%,
            var(--color-hairline) 48%
          );
          background-size: 200% 100%;
          background-position: 100% 0;
          animation: skeleton-shimmer 1.6s ease-in-out infinite;
        }
        @keyframes skeleton-shimmer {
          100% {
            background-position: -100% 0;
          }
        }
      `}</style>
    </div>
  );
}
