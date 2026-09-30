"use client";

// 브라우저 기본 title 툴팁(각지고 느리고 스타일링 안 됨) 대신, NavBar.js의
// "시작하기" hover 패널과 같은 패턴(카드 + fade/translateY)으로 통일한 작은 정보
// 아이콘. hover/focus 둘 다에서 뜨도록 해서 키보드 접근성도 챙김.
export default function InfoTooltip({ children }) {
  return (
    <span className="info-tooltip" tabIndex={0}>
      <span className="info-tooltip__icon" aria-hidden="true">
        i
      </span>
      <span className="info-tooltip__panel" role="tooltip">
        <span className="info-tooltip__arrow" aria-hidden="true" />
        <span className="info-tooltip__card">{children}</span>
      </span>

      <style jsx>{`
        .info-tooltip {
          position: relative;
          display: inline-flex;
          vertical-align: middle;
          outline: none;
        }
        .info-tooltip__icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 15px;
          height: 15px;
          border-radius: 50%;
          background-color: var(--color-ink-faint);
          color: var(--color-surface);
          font-size: 10px;
          font-weight: 700;
          font-style: italic;
          font-family: Georgia, "Times New Roman", serif;
          cursor: help;
          transition: background-color 0.15s ease;
        }
        .info-tooltip:hover .info-tooltip__icon,
        .info-tooltip:focus-visible .info-tooltip__icon {
          background-color: var(--color-primary);
        }
        .info-tooltip__panel {
          position: absolute;
          left: 50%;
          bottom: calc(100% + 9px);
          transform: translate(-50%, 4px);
          width: max-content;
          max-width: 240px;
          opacity: 0;
          visibility: hidden;
          pointer-events: none;
          transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s ease;
          z-index: 30;
        }
        .info-tooltip:hover .info-tooltip__panel,
        .info-tooltip:focus-visible .info-tooltip__panel {
          opacity: 1;
          visibility: visible;
          transform: translate(-50%, 0);
        }
        .info-tooltip__card {
          display: block;
          padding: 10px 12px;
          border-radius: var(--radius-md);
          border: 1px solid var(--color-hairline);
          background-color: var(--color-surface);
          box-shadow: var(--shadow-elevation-2);
          color: var(--color-ink-secondary);
          font: var(--text-caption) / var(--text-caption--line-height) var(--font-sans);
          text-align: left;
        }
        .info-tooltip__arrow {
          position: absolute;
          left: 50%;
          bottom: -5px;
          transform: translateX(-50%) rotate(45deg);
          width: 9px;
          height: 9px;
          background-color: var(--color-surface);
          border-right: 1px solid var(--color-hairline);
          border-bottom: 1px solid var(--color-hairline);
        }
      `}</style>
    </span>
  );
}
