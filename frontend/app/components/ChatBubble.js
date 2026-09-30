"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const markdownComponents = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  table: ({ children }) => (
    <div className="mt-2 mb-2 overflow-x-auto">
      <table className="w-full text-caption border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-canvas-soft text-eyebrow uppercase text-ink-muted">{children}</thead>
  ),
  tr: ({ children }) => <tr className="border-b border-hairline last:border-0">{children}</tr>,
  th: ({ children }) => <th className="text-left px-2 py-1">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1 text-ink-secondary">{children}</td>,
};

export default function ChatBubble({ message, isSelected, onSelectSources, onPickBrandSuggestion }) {
  const isUser = message.role === "user";
  const hasSources = (message.sources || []).length > 0;
  const hasBrandSuggestions = (message.brandSuggestions || []).length > 0;

  return (
    <div className={`flex min-w-0 chat-bubble-appear ${isUser ? "justify-end" : "justify-start"}`}>
      {message.pending ? (
        <div
          key="pending"
          className="max-w-[85%] min-w-0 px-4 py-3 flex items-center gap-2"
          role="status"
          aria-label="답변을 생각하는 중입니다"
        >
          <div className="ping" aria-hidden="true" />
          <span className="text-body-sm text-ink-faint">생각중...</span>
        </div>
      ) : (
        <div
          key="answered"
          className={`max-w-[85%] min-w-0 px-4 py-3 text-body-sm whitespace-pre-wrap break-words chat-answer-reveal chat-bubble-box ${
            isUser
              ? "chat-bubble-box--user text-on-primary"
              : !isUser && isSelected
                ? "chat-bubble-box--assistant bg-surface border-2 border-primary/40 text-ink"
                : "chat-bubble-box--assistant bg-surface border border-hairline text-ink"
          }`}
        >
          {message.error ? (
            <span className="text-accent-orange-deep">{message.content}</span>
          ) : isUser ? (
            <span>{message.content}</span>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {message.content}
            </ReactMarkdown>
          )}

          {!isUser && hasSources && (
            <div className="mt-3 flex flex-wrap gap-2">
              {message.sources.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => onSelectSources(message.id)}
                  className="badge-pill cursor-pointer hover:bg-canvas-soft"
                >
                  {s.brandNm} · {s.category}
                </button>
              ))}
            </div>
          )}

          {!isUser && hasBrandSuggestions && (
            <div className="mt-3 flex flex-col gap-2">
              {message.brandSuggestions.map((group, gi) => {
                // "ambiguous"(동명이인)는 유사도 추측이 아니라 이름이 이미 정확히 일치하는
                // 실제 후보들이라 안내 문구를 다르게 한다(라운드3 작업지시 0번).
                const isAmbiguous = group.candidates[0]?.source === "ambiguous";
                return (
                  <div key={gi} className="flex flex-col gap-1">
                    <span className="text-caption text-ink-muted">
                      {isAmbiguous ? "같은 이름의 브랜드가 여러 개 있어요. 하나를 선택해 주세요." : "혹시 이 중 하나였나요?"}
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {group.candidates.map((c) => (
                        <button
                          key={c.brandMnno}
                          type="button"
                          onClick={() => onPickBrandSuggestion?.(message.originalQuestion, group.text, c)}
                          className="badge-pill cursor-pointer border border-primary/40 bg-canvas-soft hover:bg-primary/10"
                        >
                          {c.display_name}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      <style jsx>{`
        .chat-bubble-appear {
          opacity: 0;
          animation: chat-bubble-fade-up 0.35s ease-out forwards;
        }
        @keyframes chat-bubble-fade-up {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
        .chat-bubble-box {
          border-radius: 16px;
          box-shadow: var(--shadow-elevation-1);
        }
        .chat-bubble-box--user {
          border-top-right-radius: 4px;
          background-image: linear-gradient(
            135deg,
            var(--color-primary) 0%,
            var(--color-primary-active) 100%
          );
        }
        .chat-bubble-box--assistant {
          border-top-left-radius: 4px;
        }
        .chat-answer-reveal {
          opacity: 0;
          animation: chat-answer-fade-in 0.5s ease-out forwards;
        }
        @keyframes chat-answer-fade-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
        .ping {
          --uib-size: 35px;
          --uib-speed: 1s;
          --uib-color: #0075de;
          position: relative;
          height: var(--uib-size);
          width: var(--uib-size);
        }
        .ping::before,
        .ping::after {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          height: 100%;
          width: 100%;
          border-radius: 50%;
          background-color: var(--uib-color);
          animation: chat-ping-pulse var(--uib-speed) linear infinite;
          transform: scale(0);
          opacity: 0;
        }
        .ping::after {
          animation-delay: calc(var(--uib-speed) / -2);
        }
        @keyframes chat-ping-pulse {
          0% {
            transform: scale(0);
            opacity: 1;
          }
          100% {
            transform: scale(1);
            opacity: 0;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .chat-bubble-appear,
          .chat-answer-reveal {
            animation: none;
            opacity: 1;
          }
          .ping::before,
          .ping::after {
            animation: none;
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
}
