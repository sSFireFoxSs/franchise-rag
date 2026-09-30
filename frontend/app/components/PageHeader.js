"use client";

// header_06(GitHub/AmmarrBN, "Minimal Hero Badge + Heading") 참고 — 배지 안의 작은 점만
// 은은하게 pulse하고, 제목/설명은 짧게 fade-up 된다. 세 후보(header_04/05/06) 중
// 애니메이션이 가장 절제되어 있어 barely-there 톤에 맞다고 판단해 채택.
export default function PageHeader({ badge, title, description, action }) {
  return (
    <header className="page-header mb-6">
      <div className="page-header__row">
        <div className="min-w-0">
          <span className="page-header__badge">
            <span className="page-header__dot" aria-hidden="true" />
            {badge}
          </span>
          <h1 className="page-header__title text-heading-2 text-ink">{title}</h1>
          <p className="page-header__description text-body-md text-ink-muted">{description}</p>
        </div>
        {action && <div className="page-header__action">{action}</div>}
      </div>

      <style jsx>{`
        .page-header__row {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
        }
        .page-header__action {
          flex-shrink: 0;
          margin-top: 4px;
        }
        .page-header__badge {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 4px 10px;
          border-radius: var(--radius-full);
          background-color: var(--color-canvas-soft);
          color: var(--color-ink-muted);
          font: var(--text-caption) / var(--text-caption--line-height) var(--font-sans);
          font-weight: 600;
        }
        .page-header__dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background-color: var(--color-primary);
          animation: dot-pulse 2s ease-in-out infinite;
        }
        .page-header__title {
          margin: 12px 0 8px;
          opacity: 0;
          animation: fade-up 0.4s ease-out 0.05s forwards;
        }
        .page-header__description {
          opacity: 0;
          animation: fade-up 0.4s ease-out 0.1s forwards;
        }
        @keyframes dot-pulse {
          0%, 100% { opacity: 0.45; transform: scale(0.85); }
          50% { opacity: 1; transform: scale(1); }
        }
        @keyframes fade-up {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .page-header__dot,
          .page-header__title,
          .page-header__description {
            animation: none;
            opacity: 1;
          }
        }
      `}</style>
    </header>
  );
}
