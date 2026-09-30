"use client";

function AmountsTable({ amounts }) {
  if (!amounts || amounts.length === 0) return null;
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="w-full text-caption border-collapse">
        <thead>
          <tr className="bg-canvas-soft text-eyebrow uppercase text-ink-muted">
            <th className="text-left px-2 py-1">항목</th>
            <th className="text-right px-2 py-1">금액</th>
          </tr>
        </thead>
        <tbody>
          {amounts.slice(0, 12).map((a, i) => (
            <tr key={i} className="border-b border-hairline last:border-0">
              <td className="px-2 py-1 text-ink-secondary">
                {a.label}
                {a.column ? ` (${a.column})` : ""}
              </td>
              <td className="px-2 py-1 text-right text-ink">
                {a.amount_won != null ? `${a.amount_won.toLocaleString("ko-KR")}원` : a.raw || "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceCard({ source }) {
  return (
    <div className="feature-card">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="badge-pill">{source.category}</span>
        {source.violation_flag != null && (
          <span className="text-caption text-ink-muted">위반이력: {String(source.violation_flag)}</span>
        )}
      </div>
      <h3 className="text-title text-ink">{source.brandNm}</h3>
      <p className="text-caption text-ink-muted mb-2">{source.canonical_title}</p>
      {source.text && <p className="text-body-sm text-ink-secondary">{source.text}</p>}
      <AmountsTable amounts={source.amounts} />
    </div>
  );
}

export default function SourcePanel({ sources }) {
  const hasSources = sources && sources.length > 0;

  return (
    <div className="feature-card-elevated flex flex-col gap-4 h-full min-h-0 source-panel-appear">
      <h2 className="text-heading-3 text-ink shrink-0">근거원문</h2>
      {hasSources ? (
        <div className="flex-1 flex flex-col gap-3 overflow-y-auto min-h-0">
          {sources.map((s, i) => (
            <SourceCard key={i} source={s} />
          ))}
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center text-center gap-2">
          <p className="text-body-md text-ink-muted">
            질문을 보내면 답변의 근거가 된 정보공개서 원문이 여기에 표시됩니다.
          </p>
        </div>
      )}
      <style jsx>{`
        .source-panel-appear {
          opacity: 0;
          animation: source-panel-fade-in 0.3s ease-out forwards;
        }
        @keyframes source-panel-fade-in {
          from {
            opacity: 0;
            transform: translateY(4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .source-panel-appear {
            animation: none;
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
