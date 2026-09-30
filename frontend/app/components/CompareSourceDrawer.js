"use client";

import { useEffect, useRef } from "react";

// compare 페이지 전용 우측 슬라이드 패널 — "원문 보기"를 누르면 뜬다. 표/차트는 그대로
// 두고 원문(가변 길이 텍스트 + 세부 금액표)만 이 패널로 분리해서, 브랜드마다 원문
// 길이가 달라도 카테고리 아코디언이 브랜드별로 들쭉날쭉 길어지지 않게 한다.
//
// 이름을 SourcePanel이 아니라 CompareSourceDrawer로 둔 이유: frontend/app/components/
// SourcePanel.js는 이미 /chat 페이지가 답변 근거 사이드바(sources 배열을 받는 다른
// 컴포넌트)로 쓰고 있던 파일이라 겹치면 안 됨.
//
// 패널이 열려 있는 상태에서 다른 브랜드/항목의 "원문 보기"를 다시 누르면 패널을
// 닫았다 새로 열지 않고 content(title/children)만 교체한다 — 호출부(compare/page.js)가
// open을 유지한 채 title/children props만 바꿔서 리렌더시키면 됨.
export default function CompareSourceDrawer({ open, onClose, title, children }) {
  const closeBtnRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    closeBtnRef.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  return (
    <>
      <div
        className="source-drawer-backdrop"
        style={{ opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none" }}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className="source-drawer"
        style={{ transform: open ? "translateX(0)" : "translateX(100%)" }}
        role="dialog"
        aria-modal="true"
        aria-hidden={!open}
      >
        <div className="source-drawer__header">
          <div className="min-w-0 flex-1">{title}</div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            className="source-drawer__close"
            aria-label="닫기"
            tabIndex={open ? 0 : -1}
          >
            ✕
          </button>
        </div>
        <div className="source-drawer__body">{children}</div>
      </aside>

      <style jsx>{`
        .source-drawer-backdrop {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.25);
          z-index: 30;
          transition: opacity 0.25s ease;
        }
        .source-drawer {
          position: fixed;
          top: 0;
          right: 0;
          bottom: 0;
          width: min(420px, 100vw);
          background: var(--color-canvas);
          box-shadow: var(--shadow-elevation-2);
          z-index: 31;
          display: flex;
          flex-direction: column;
          transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .source-drawer__header {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 20px;
          border-bottom: 1px solid var(--color-hairline);
        }
        .source-drawer__close {
          flex-shrink: 0;
          width: 32px;
          height: 32px;
          border-radius: var(--radius-full);
          color: var(--color-ink-muted);
          transition: background-color 0.15s ease, color 0.15s ease;
        }
        .source-drawer__close:hover {
          background-color: var(--color-canvas-soft);
          color: var(--color-ink);
        }
        .source-drawer__body {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
        }
        @media (prefers-reduced-motion: reduce) {
          .source-drawer,
          .source-drawer-backdrop {
            transition: none;
          }
        }
      `}</style>
    </>
  );
}
