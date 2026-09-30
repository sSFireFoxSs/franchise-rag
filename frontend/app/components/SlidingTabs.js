"use client";

import { useEffect, useRef, useState } from "react";

// toggle_07(CodePen/o3owo, "Sliding Pill Tabs") 참고 — 흰 pill이 선택된 탭 밑에서
// 미끄러지듯 이동한다. 원본은 indicator 너비를 110px로 고정했지만, 탭 라벨 길이가
// 서로 다르면(예: "평균매출액" vs "가맹점 수") 고정폭이 안 맞아서 각 탭 버튼의
// offsetLeft/offsetWidth를 실측해 옮기는 방식으로 바꿨다(원본 코드의 메모에서도
// React로 옮기면 이렇게 하라고 되어 있었음).
// compact — 브랜드 비교 우측 패널처럼 폭이 좁고 라벨 길이가 들쭉날쭉한 자리에서 쓰는
// 축소 모드. 한 줄 고정(white-space: nowrap) 대신 폭이 부족하면 pill이 줄어들면서
// 라벨이 자체적으로 2줄까지 접히게 둔다 — 가로 스크롤보다 이쪽이 훨씬 자연스러움.
export default function SlidingTabs({ tabs, active, onChange, compact = false }) {
  const containerRef = useRef(null);
  const tabRefs = useRef({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  useEffect(() => {
    const el = tabRefs.current[active];
    if (el) {
      setIndicator({ left: el.offsetLeft, width: el.offsetWidth });
    }
  }, [active, tabs]);

  return (
    <div ref={containerRef} className={`sliding-tabs ${compact ? "sliding-tabs--compact" : ""}`}>
      <span
        className="sliding-tabs__indicator"
        style={{ transform: `translateX(${indicator.left}px)`, width: `${indicator.width}px` }}
        aria-hidden="true"
      />
      {tabs.map((tab) => (
        <button
          key={tab.key}
          ref={(el) => {
            tabRefs.current[tab.key] = el;
          }}
          type="button"
          aria-current={active === tab.key ? "page" : undefined}
          onClick={() => onChange(tab.key)}
          className={`sliding-tabs__tab ${active === tab.key ? "active" : ""}`}
        >
          {tab.label}
        </button>
      ))}

      <style jsx>{`
        .sliding-tabs {
          position: relative;
          display: inline-flex;
          width: fit-content;
          padding: 4px;
          border-radius: var(--radius-full);
          background-color: var(--color-canvas-soft);
        }
        .sliding-tabs__tab {
          position: relative;
          z-index: 2;
          padding: 8px 16px;
          border: none;
          background: transparent;
          border-radius: var(--radius-full);
          font: var(--text-button) / var(--text-button--line-height) var(--font-sans);
          font-weight: var(--text-button--font-weight);
          color: var(--color-ink-secondary);
          cursor: pointer;
          transition: color 0.18s ease;
        }
        .sliding-tabs--compact .sliding-tabs__tab {
          padding: 6px 12px;
          text-align: center;
          font: var(--text-caption) / var(--text-caption--line-height) var(--font-sans);
          font-weight: 600;
        }
        .sliding-tabs__tab.active {
          color: var(--color-on-primary);
        }
        .sliding-tabs__indicator {
          position: absolute;
          z-index: 1;
          top: 4px;
          left: 0;
          bottom: 4px;
          border-radius: var(--radius-full);
          background-color: var(--color-primary);
          transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1), width 0.28s cubic-bezier(0.4, 0, 0.2, 1);
        }
      `}</style>
    </div>
  );
}
