"use client";

import { useEffect, useState } from "react";
import BrandLogo from "./BrandLogo";

// 마이프차 비교 차트 참고 — 브랜드별로 막대 색을 다르게 주고, 막대 하나하나에 개별
// 툴팁을 붙이는 대신 차트 전체에 마우스를 올리면 모든 브랜드의 값이 한 번에 나열된
// 통합 툴팁이 뜬다. shadcn/ui "Bar Chart - Multiple"의 그리드선 느낌은 유지하되
// recharts는 안 쓰고(팀 공지 없이 package.json 안 건드리기로 함) 순수 CSS로 구현.
const MIN_BAR_PX = 4;
// 데이터 없는 브랜드는 막대 높이를 실제 값(0에 가까운 값)처럼 비례 계산하지 않고 고정
// 높이의 "빗금" 표시로 그린다 — 4px짜리 실선 막대는 "값이 아주 작다"와 구분이 안 돼서
// 사실상 안 보이는 것처럼 느껴지는 문제가 있었음(사용자 피드백). 빗금+점선 테두리로
// "이건 값이 아니라 데이터 없음 표시"라는 의도를 명확히 한다.
const EMPTY_BAR_PX = 22;
// BrandLogo(size=8 → 32px) + 로고-막대 간격(6px). chart-row 자체의 CSS height는 이만큼
// 더 크게 잡아야, "로고+막대" 합산 높이가 항목 최댓값(height)만큼 커져도 justify-end로
// 쌓인 내용이 위로 넘쳐서 카테고리 제목을 가리는 일이 없다.
const LOGO_RESERVED_PX = 32 + 6;

// 프로젝트 디자인 토큰 중 서로 구분되는 4색 — 브랜드 최대 개수(4개)에 맞춤. 같은 브랜드는
// 이 차트, 저 차트에서 항상 같은 색을 쓰도록 브랜드 배열의 인덱스로 고정 매핑한다.
const BAR_COLORS = [
  "var(--color-primary)",
  "var(--color-accent-teal)",
  "var(--color-accent-orange)",
  "var(--color-accent-purple-deep)",
];

export default function MetricBarChart({ label, bars, height = 140 }) {
  const [hovered, setHovered] = useState(false);
  const [grown, setGrown] = useState(false);
  const max = Math.max(0, ...bars.map((b) => (b.value == null ? 0 : b.value)));

  // 마운트 시 0에서 목표 높이로 차오르는 진입 애니메이션 — rAF로 한 프레임 뒤에 값을
  // 바꿔야 브라우저가 0px 상태를 먼저 페인트하고 그 다음 transition을 잡음
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div>
      <span className="text-title text-primary">{label}</span>
      <div
        className="chart-row mt-4"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {hovered && (
          <div className="chart-tooltip">
            {bars.map((b, i) => (
              <div key={b.brandMnno} className="chart-tooltip__row">
                <span className="chart-tooltip__dot" style={{ backgroundColor: BAR_COLORS[i % BAR_COLORS.length] }} />
                <span className="chart-tooltip__name" title={b.brandNm}>
                  {b.brandNm}
                </span>
                <span className="chart-tooltip__value">{b.formatted || "데이터 없음"}</span>
              </div>
            ))}
          </div>
        )}
        {bars.map((b, i) => {
          const hasValue = b.value != null && max > 0;
          const targetPx = hasValue ? Math.max(MIN_BAR_PX, Math.round((b.value / max) * height)) : EMPTY_BAR_PX;
          const px = grown ? targetPx : 0;
          const color = BAR_COLORS[i % BAR_COLORS.length];
          return (
            <div key={b.brandMnno} className="chart-col">
              <BrandLogo brandNm={b.brandNm} brandMnno={b.brandMnno} size={8} shape="square" />
              <div className="chart-track">
                <div
                  className={`chart-bar ${hasValue ? "" : "empty"}`}
                  style={{
                    height: `${px}px`,
                    backgroundColor: hasValue ? color : undefined,
                    backgroundImage: hasValue
                      ? `linear-gradient(180deg, color-mix(in srgb, ${color} 75%, white) 0%, ${color} 60%)`
                      : undefined,
                    transitionDelay: `${i * 40}ms`,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <style jsx>{`
        .chart-row {
          position: relative;
          display: flex;
          align-items: flex-end;
          gap: 6px;
          height: ${height + LOGO_RESERVED_PX}px;
          padding: 0 4px;
          /* shadcn Bar Chart 참고 — CartesianGrid(vertical=false)처럼 가로 그리드선만 은은하게 */
          background-image: linear-gradient(var(--color-hairline) 1px, transparent 1px);
          background-size: 100% 33.33%;
          background-position: top;
          border-bottom: 1.5px solid var(--color-hairline);
        }
        .chart-col {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: flex-end;
          gap: 6px;
          height: 100%;
        }
        .chart-track {
          width: 100%;
          display: flex;
          justify-content: center;
        }
        .chart-bar {
          width: 40%;
          min-width: 10px;
          max-width: 22px;
          background-color: var(--color-hairline);
          border-radius: var(--radius-sm) var(--radius-sm) 0 0;
          transition: height 0.5s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.15s ease, transform 0.15s ease;
        }
        .chart-col:hover .chart-bar:not(.empty) {
          transform: scaleX(1.15);
        }
        .chart-bar.empty {
          background-color: var(--color-canvas-soft);
          background-image: repeating-linear-gradient(
            45deg,
            var(--color-hairline),
            var(--color-hairline) 3px,
            transparent 3px,
            transparent 6px
          );
          border: 1px dashed var(--color-hairline);
          border-radius: var(--radius-xs);
        }
        .chart-row:hover .chart-bar {
          opacity: 0.55;
        }
        .chart-col:hover .chart-bar {
          opacity: 1;
        }
        .chart-tooltip {
          position: absolute;
          left: 50%;
          top: 0;
          transform: translate(-50%, -100%);
          margin-top: -8px;
          background-color: var(--color-ink);
          color: white;
          font: var(--text-caption) / var(--text-caption--line-height) var(--font-sans);
          padding: 8px 10px;
          border-radius: var(--radius-sm);
          white-space: nowrap;
          z-index: 5;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .chart-tooltip__row {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .chart-tooltip__dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .chart-tooltip__name {
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 120px;
        }
        .chart-tooltip__value {
          margin-left: auto;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
