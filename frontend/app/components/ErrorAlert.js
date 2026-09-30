"use client";

// card_02(Uiverse.io by seyed-mohsen-mousavi) 참고 — 다크 토스트 구조(아이콘 칩 + 메시지 +
// 닫기 버튼)를 저희 라이트 테마 토큰(--color-accent-orange 등)으로 바꿔 적용.
export default function ErrorAlert({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-hairline bg-surface px-4 py-3 mb-6 shadow-[var(--shadow-elevation-1)]">
      <div className="flex items-center gap-3 min-w-0">
        <span className="flex items-center justify-center w-8 h-8 rounded-md bg-accent-orange/10 text-accent-orange-deep shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
          </svg>
        </span>
        <p className="text-body-sm text-ink truncate">{message}</p>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="닫기"
          className="text-ink-faint hover:text-ink hover:bg-canvas-soft p-1 rounded-md transition-colors shrink-0"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}
