"use client";

// "데이터 없음" 한 줄 텍스트 대신 아이콘 + 제목 + (선택) 설명을 갖춘 빈 상태 화면.
export default function EmptyState({ title = "데이터 없음", description }) {
  return (
    <div className="feature-card flex flex-col items-center text-center py-12">
      <span className="flex items-center justify-center w-12 h-12 rounded-full bg-canvas-soft text-ink-faint mb-3" aria-hidden="true">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-6 h-6">
          <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 7.5v9a2.25 2.25 0 0 1-2.25 2.25h-12a2.25 2.25 0 0 1-2.25-2.25v-9m16.5 0a2.25 2.25 0 0 0-2.25-2.25h-12a2.25 2.25 0 0 0-2.25 2.25m16.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 9.66a2.25 2.25 0 0 1-1.07-1.916V7.5" />
        </svg>
      </span>
      <p className="text-body-md text-ink font-medium">{title}</p>
      {description && <p className="text-body-sm text-ink-faint mt-1 max-w-sm">{description}</p>}
    </div>
  );
}
