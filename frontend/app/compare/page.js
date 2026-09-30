"use client";

import { useState } from "react";
import BrandMultiSelect from "../components/BrandMultiSelect";
import ErrorAlert from "../components/ErrorAlert";
import BrandLogo from "../components/BrandLogo";
import MetricBarChart from "../components/MetricBarChart";
import CompareSourceDrawer from "../components/CompareSourceDrawer";
import PageHeader from "../components/PageHeader";
import SlidingTabs from "../components/SlidingTabs";
import { getCompare } from "../../lib/api";

// ============================================================
// 1. 설정값
// ============================================================
const MIN_BRANDS = 2;
const MAX_BRANDS = 4;

// ============================================================
// 2. 브랜드명 표시 유틸 — 괄호 부기명 분리
// ============================================================
function splitBrandName(brandNm) {
  const m = /^(.*?)\s*\(([^)]*)\)\s*$/su.exec(brandNm || "");
  if (!m) return { main: brandNm || "", paren: null };
  return { main: m[1], paren: m[2] };
}

function BrandNameLabel({ brandNm, className = "" }) {
  const { main, paren } = splitBrandName(brandNm);
  return (
    <span className={`block ${className}`}>
      <span className="block">{main}</span>
      {paren && <span className="block text-caption text-ink-faint font-normal">({paren})</span>}
    </span>
  );
}

// ============================================================
// 3. 상단 숫자 비교표 — 항목 정의 · 금액 포맷 · 값 렌더링
// ============================================================
const ROWS = [
  { key: "storeCount", label: "가맹점 수", format: (v) => `${v.toLocaleString()}개` },
  { key: "avgSalesAnnual", label: "연평균 매출액(전체)", format: formatWonKR },
  { key: "avgSalesPer33", label: "3.3㎡당 평균매출액", format: formatWonKR },
  { key: "franchiseFee", label: "가맹비(최초 가맹금)", format: formatWonKR },
  { key: "deposit", label: "보증금", format: formatWonKR },
  { key: "totalStartupCost", label: "총창업비용", format: formatWonKR },
];

function formatWonKR(won) {
  if (won == null) return "";
  const neg = won < 0 ? "-" : "";
  won = Math.abs(won);
  const eok = Math.floor(won / 100_000_000);
  const rem = won % 100_000_000;
  const man = Math.round(rem / 10_000);
  if (eok && man) return `${neg}${eok}억 ${man.toLocaleString()}만원`;
  if (eok) return `${neg}${eok}억원`;
  if (man) return `${neg}${man.toLocaleString()}만원`;
  return `${neg}${won.toLocaleString()}원`;
}

function CellValue({ brand, row }) {
  if (!brand) return <span className="text-ink-faint">-</span>;
  const value = brand[row.key];
  const note = brand.notes?.[row.key];
  if (value == null) {
    // 값이 있는 항목과 폰트 굵기·크기를 다르게 둬서, 실제 숫자와 "비교값 없음"이
    // 한눈에 구분되게 한다. "정규화된 비교 수치가 없다"는 뜻이 더 분명한 "비교값
    // 없음"으로 표현한다 (원문엔 세부 금액이 있는 경우도 있어서 "데이터 없음"이라고
    // 하면 오해가 생김).
    return (
      <span className="text-caption font-normal text-ink-faint">
        비교값 없음
        {note ? <span className="block">({note})</span> : null}
      </span>
    );
  }
  return <span className="text-ink font-medium">{row.format(value)}</span>;
}

// ============================================================
// 4. 정보공개서 원문 섹션 — 카테고리 설정
// ============================================================
const SOURCE_GROUP_ORDER = ["평균매출액", "가맹비/가맹금", "보증금"];
const SOURCE_GROUP_LABEL = { "평균매출액": "평균매출액", "가맹비/가맹금": "가맹비", "보증금": "보증금" };
const SOURCE_GROUP_SUBTITLE = {
  "평균매출액": "가맹점 수 · 연평균 매출액 · 3.3㎡당 평균매출액",
  "가맹비/가맹금": "가맹비 · 총창업비용",
  "보증금": "보증금",
};
const CATEGORY_PRIMARY_METRIC = {
  "평균매출액": "avgSalesAnnual",
  "가맹비/가맹금": "franchiseFee",
  "보증금": "deposit",
};
const ROWS_BY_KEY = Object.fromEntries(ROWS.map((r) => [r.key, r]));

// ============================================================
// 5. 정보공개서 원문 섹션 — 데이터 가공 · 표/텍스트 렌더링
// ============================================================
function groupSourcesByCategory(sources) {
  const byCategory = {};
  for (const s of sources || []) {
    (byCategory[s.category] ||= []).push(s);
  }
  return byCategory;
}

function SourceText({ text }) {
  return (
    <p className="text-body-sm text-ink-secondary whitespace-pre-line break-keep [overflow-wrap:anywhere] leading-[1.75]">
      {text}
    </p>
  );
}

function AmountsTable({ amounts }) {
  if (!amounts || amounts.length === 0) return null;
  return (
    <table className="w-full text-caption mb-2">
      <thead>
        <tr className="text-eyebrow uppercase text-ink-faint">
          <th className="text-left font-normal pb-1">항목</th>
          <th className="text-right font-normal pb-1">금액</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-hairline">
        {amounts.slice(0, 12).map((a, i) => (
          <tr key={i}>
            <td className="py-1 pr-3 text-ink-muted">
              {a.label}
              {a.column ? ` · ${a.column}` : ""}
            </td>
            <td className="py-1 text-ink font-medium text-right tabular-nums whitespace-nowrap">
              {a.amountWon != null ? formatWonKR(a.amountWon) : a.raw || "-"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// 원문 셀의 짧은 미리보기 — 우측 패널을 열지 않아도 "대략 이런 내용이다"를 알 수 있게.
function previewText(items) {
  const text = items?.[0]?.text;
  if (!text) return null;
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

// card_04(Uiverse.io by gharsh11032000) 참고 — 테두리 대신 은은한 흰색 ring으로 카드를
// 배경에서 분리하고, hover 시 그림자만 살짝 깊어지게.
const SOURCE_CARD_CLASS =
  "feature-card border-0 ring-4 ring-white/70 transition-shadow duration-300 hover:shadow-[var(--shadow-elevation-2)]";

// 브랜드 하나의 원문 미리보기 행 — 예전엔 여기서 바로 펼쳐서 전체 원문을 보여줬는데,
// 브랜드마다 원문 길이가 달라 아코디언을 펼칠 때마다 페이지가 들쭉날쭉 길어지는 문제가
// 있었다. 이제는 미리보기 한두 줄만 보여주고, "원문 보기"를 누르면 우측 슬라이드
// 패널에서 전체 원문 + 구조화 금액표를 보여준다(패널은 브랜드/카테고리를 바꿔가며
// 계속 열어둘 수 있음 — SourcePanel 참고).
function SourceRow({ brand, items, primaryRow, onOpen }) {
  const preview = previewText(items);
  return (
    <div className="flex items-start gap-3 py-5 last:pb-0">
      <BrandLogo brandNm={brand.brandNm} brandMnno={brand.brandMnno} size={8} shape="square" />
      {/* 브랜드명(부기명 유무로 1~2줄)·대표 수치·미리보기·버튼을 ad-hoc margin 대신
          flex-col gap으로 묶어서, 브랜드마다 줄 수가 달라도 각 줄 사이 간격이 항상
          같게 유지되도록 한다. */}
      <div className="min-w-0 flex-1 flex flex-col gap-1.5">
        <BrandNameLabel brandNm={brand.brandNm} className="text-body-md text-ink font-medium" />
        {primaryRow ? (
          <span className="block text-caption text-ink-faint">
            {primaryRow.label} · <CellValue brand={brand} row={primaryRow} />
          </span>
        ) : null}
        {!items || items.length === 0 ? (
          <span className="text-caption text-ink-faint">원문 없음</span>
        ) : (
          <>
            {preview && <p className="text-caption text-ink-muted leading-[1.6]">{preview}</p>}
            <button
              type="button"
              onClick={onOpen}
              className="group text-caption text-primary font-medium self-start inline-flex items-center gap-0.5"
            >
              원문 보기
              <span className="transition-transform duration-150 group-hover:translate-x-0.5" aria-hidden="true">
                →
              </span>
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// 카테고리 토글을 펼치면 브랜드별 미리보기 행이 나온다. 대표 수치 1개만 미리보기에
// 남겨서 "이 숫자의 근거가 여기 있다"는 연결만 보여준다(상단 비교표/차트와 같은
// 숫자를 또 리스트로 반복하지 않음).
function SourceCategorySection({ cat, result, groupsList, onOpenSource }) {
  const [open, setOpen] = useState(false);
  const hasAny = groupsList.some((g) => g[cat]?.length);
  if (!hasAny) return null;
  const primaryRow = ROWS_BY_KEY[CATEGORY_PRIMARY_METRIC[cat]];

  return (
    <div className={`${SOURCE_CARD_CLASS} mb-4`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="group w-full flex items-center justify-between gap-3 text-left"
      >
        <span>
          <span className="text-title text-primary block">{SOURCE_GROUP_LABEL[cat] || cat}</span>
          <span className="text-caption text-ink-faint">{SOURCE_GROUP_SUBTITLE[cat]}</span>
        </span>
        {/* TOP20 카테고리 탭(category-tab)과 같은 "선택되면 필이 꽉 찬다" 패턴 재사용 —
            펼쳐진 상태(접기)를 primary 배경 필로, 접힌 상태(펼쳐보기)를 outline으로 표현 */}
        <span
          className={`shrink-0 px-3 py-1 rounded-full text-caption font-medium border transition-colors duration-150 ${
            open
              ? "bg-primary border-primary text-on-primary group-hover:bg-primary-active group-hover:border-primary-active"
              : "border-hairline text-primary group-hover:border-primary group-hover:bg-primary/5"
          }`}
        >
          {open ? "접기" : "펼쳐보기"}
        </span>
      </button>
      {open && (
        <div className="mt-4">
          <p className="mb-4 text-caption text-ink-faint">
            위 비교표·차트의 수치는 아래 정보공개서 원문을 근거로 합니다.
          </p>
          <div className="border-t border-hairline divide-y divide-hairline">
            {result.map((b, i) => (
              <SourceRow
                key={b.brandMnno}
                brand={b}
                items={groupsList[i][cat]}
                primaryRow={primaryRow}
                onOpen={() => onOpenSource({ category: cat, brandIndex: i })}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// 6. 페이지 컴포넌트 — 브랜드 선택 폼 · 숫자 비교표 · 차트 · 원문 섹션
// ============================================================
export default function ComparePage() {
  const [selected, setSelected] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // 우측 원문 패널 상태 — { category, brandIndex } | null. 패널이 열린 채로 다른
  // 브랜드/항목의 "원문 보기"를 누르면 패널을 닫았다 열지 않고 이 값만 바꿔서
  // 패널 내부 content만 교체되게 한다(패널 안 브랜드 칩으로도 전환 가능).
  const [panel, setPanel] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (loading || selected.length < MIN_BRANDS) return;

    setLoading(true);
    setError(null);
    try {
      const data = await getCompare(selected.map((s) => ({ name: s.brandNm, mnno: s.brandMnno })));
      setResult(data.brands);
      setPanel(null);
    } catch (err) {
      setResult(null);
      setError(err.message || "비교 결과를 가져오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  const canSubmit = !loading && selected.length >= MIN_BRANDS;

  function resetAll() {
    setSelected([]);
    setResult(null);
    setError(null);
    setPanel(null);
  }

  const groupsList = result ? result.map((b) => groupSourcesByCategory(b.sources)) : [];
  const panelBrand = panel ? result[panel.brandIndex] : null;
  const panelItems = panel ? groupsList[panel.brandIndex]?.[panel.category] : null;

  return (
    <div className="mx-auto w-full max-w-[1280px] flex-1 p-6">
      <PageHeader
        badge="브랜드 비교"
        title="궁금한 브랜드끼리 나란히 비교해보세요"
        description="최대 4개 브랜드, 숫자와 원문으로 직접 비교해보세요"
        action={
          (selected.length > 0 || result) && (
            <button type="button" onClick={resetAll} className="btn-utility reset-btn">
              초기화
            </button>
          )
        }
      />

      <form onSubmit={handleSubmit} className="mb-6">
        <div className="flex flex-wrap items-start gap-3">
          <BrandMultiSelect
            value={selected}
            onChange={setSelected}
            max={MAX_BRANDS}
            placeholder="비교할 브랜드를 검색하세요 (2~4개)"
            disabled={loading}
          />
          {/* button_05(Uiverse.io by adamgiebl) 원본 그대로 이식 — hover 시 아이콘이
              날아가듯 위아래로 흔들리며(fly-1) 오른쪽으로 이동+회전하고, 글자는 옆으로
              슬라이드되어 사라진다. 로딩 중엔 같은 자리에서 스피너로 바뀐다. */}
          <button type="submit" className="send-btn" disabled={!canSubmit}>
            {loading ? (
              <span className="w-5 h-5 rounded-full border-2 border-white/40 border-t-white animate-spin" aria-hidden="true" />
            ) : (
              <span className="svg-wrapper">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white" width="20">
                  <path d="M1.101 21.757 23.8 12.028 1.101 2.3l.011 7.912 13.623 1.816-13.623 1.817-.011 7.912Z" />
                </svg>
              </span>
            )}
            <span>{loading ? "비교 중…" : "비교하기"}</span>
          </button>
        </div>
        <p className="text-caption text-ink-faint mt-2">{selected.length}/{MAX_BRANDS}개 선택됨 (최소 {MIN_BRANDS}개)</p>
      </form>

      <style jsx>{`
        .reset-btn {
          transition: transform 0.15s ease, border-color 0.15s ease, color 0.15s ease;
        }
        .reset-btn:hover {
          transform: translateY(-2px);
          border-color: var(--color-primary);
          color: var(--color-primary);
        }
        .send-btn {
          font-family: inherit;
          font-size: var(--text-button-font-size, 15px);
          font-weight: var(--text-button--font-weight);
          background: var(--color-primary);
          color: var(--color-on-primary);
          padding: 12px 20px;
          display: flex;
          align-items: center;
          gap: 0.4em;
          border: none;
          border-radius: var(--radius-full);
          overflow: hidden;
          transition: all 0.2s;
          cursor: pointer;
        }
        .send-btn:hover:not(:disabled) {
          background-color: var(--color-primary-active);
        }
        .send-btn span {
          display: block;
          transition: all 0.3s ease-in-out;
        }
        .send-btn svg {
          display: block;
          transform-origin: center center;
          transition: transform 0.3s ease-in-out;
        }
        .send-btn:hover:not(:disabled) .svg-wrapper {
          animation: fly-1 0.6s ease-in-out infinite alternate;
        }
        .send-btn:hover:not(:disabled) svg {
          transform: translateX(0.3em) scale(1.1);
        }
        .send-btn:hover:not(:disabled) span:last-child {
          transform: translateX(3em);
          opacity: 0;
        }
        .send-btn:active:not(:disabled) {
          transform: scale(0.95);
        }
        .send-btn:disabled {
          background-color: var(--color-ink-faint);
          cursor: not-allowed;
        }
        @keyframes fly-1 {
          from {
            transform: translateY(0.1em);
          }
          to {
            transform: translateY(-0.1em);
          }
        }
      `}</style>

      <ErrorAlert message={error} onDismiss={() => setError(null)} />

      {result ? (
        <>
          {/* --- 숫자 비교표: 항목(행) × 브랜드(열) --- */}
          <div className={`${SOURCE_CARD_CLASS} overflow-x-auto mb-6`}>
            <table className="w-full text-body-sm table-fixed">
              <thead>
                <tr className="border-b border-hairline">
                  <th className="py-2 pr-4 text-ink-faint font-normal text-center w-32 sm:w-40">항목</th>
                  {result.map((b) => (
                    <th key={b.brandMnno} className="py-2 px-4 text-ink font-medium text-center">
                      <BrandNameLabel brandNm={b.brandNm} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {ROWS.map((row) => (
                  <tr key={row.key}>
                    <td className="py-3 pr-4 text-ink-muted text-center">{row.label}</td>
                    {result.map((b) => (
                      <td key={b.brandMnno} className="py-3 px-4 text-center">
                        <CellValue brand={b} row={row} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* --- 항목별 막대 차트 (6개) ---
              항목마다 단위(개 vs 원)가 달라서 한 차트에 다 넣으면 매출액 막대에 가맹점수
              막대가 묻힌다 — 항목 하나당 차트를 따로 두고, 6개를 압축 그리드로 배치한다.
              선택된 브랜드 전부 값이 없는 항목도 스킵하지 않고 그린다 — 6칸 그리드
              레이아웃이 항목 조합에 따라 들쭉날쭉해지는 것을 막기 위해, 데이터 없음은
              MetricBarChart의 빗금 표시로 보여준다. */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            {ROWS.map((row) => (
              <div key={row.key} className={SOURCE_CARD_CLASS}>
                <MetricBarChart
                  label={row.label}
                  height={110}
                  bars={result.map((b) => ({
                    brandMnno: b.brandMnno,
                    brandNm: b.brandNm,
                    value: b[row.key],
                    formatted: b[row.key] != null ? row.format(b[row.key]) : null,
                  }))}
                />
              </div>
            ))}
          </div>

          {/* --- 정보공개서 원문 (카테고리별 아코디언 → 브랜드별 미리보기 + 우측 패널) --- */}
          <h2 className="text-heading-3 text-ink mt-16 mb-4">정보공개서 원문</h2>
          {(() => {
            const anyData = SOURCE_GROUP_ORDER.some((cat) => groupsList.some((g) => g[cat]?.length));
            if (!anyData) {
              return <div className={`${SOURCE_CARD_CLASS} text-ink-faint text-body-sm`}>원문을 찾지 못했습니다.</div>;
            }
            return (
              <div>
                {SOURCE_GROUP_ORDER.map((cat) => (
                  <SourceCategorySection
                    key={cat}
                    cat={cat}
                    result={result}
                    groupsList={groupsList}
                    onOpenSource={setPanel}
                  />
                ))}
              </div>
            );
          })()}
        </>
      ) : !error && !loading ? (
        <div className={`${SOURCE_CARD_CLASS} text-ink-muted text-body-sm`}>
          비교할 브랜드를 2개 이상 입력하고 &quot;비교하기&quot;를 눌러 주세요.
        </div>
      ) : null}

      <CompareSourceDrawer
        open={!!panel}
        onClose={() => setPanel(null)}
        title={
          panelBrand && (
            <div className="flex items-center gap-2 min-w-0">
              <BrandLogo brandNm={panelBrand.brandNm} brandMnno={panelBrand.brandMnno} size={8} shape="square" />
              <span className="min-w-0">
                <BrandNameLabel brandNm={panelBrand.brandNm} className="truncate text-body-md text-ink font-medium" />
                <span className="block text-caption text-ink-faint">{panel && SOURCE_GROUP_LABEL[panel.category]} 원문</span>
              </span>
            </div>
          )
        }
      >
        {/* 같은 항목 안에서 다른 브랜드로 바로 전환할 수 있게, 패널 안에도 브랜드
            탭을 둔다 — 패널을 닫았다 다시 열 필요 없이 내용만 바뀐다. SlidingTabs를
            compact 모드로 써서, 패널 폭(420px)에 4개가 안 들어가도 가로 스크롤 대신
            pill이 줄어들며 라벨이 2줄까지 접히게 둔다(SlidingTabs.js의 compact 참고). */}
        {result && panel && (
          <div className="mb-5">
            <SlidingTabs
              compact
              tabs={result.map((b) => ({ key: b.brandMnno, label: b.brandNm }))}
              active={panelBrand?.brandMnno}
              onChange={(key) => {
                const idx = result.findIndex((b) => b.brandMnno === key);
                if (idx >= 0) setPanel({ category: panel.category, brandIndex: idx });
              }}
            />
          </div>
        )}
        {panelItems && panelItems.length > 0 ? (
          // key로 브랜드/카테고리 조합을 줘서, 전환할 때마다 카드가 다시 마운트되며
          // fade-up 애니메이션이 처음부터 재생되게 한다(전환도 "새로 등장"처럼 보이게).
          <div key={`${panel.category}-${panel.brandIndex}`}>
            {panelItems.map((s, j) => (
              <div key={j} className={j > 0 ? "mt-5" : ""}>
                {panelItems.length > 1 && <p className="text-caption text-ink-muted mb-2">{s.canonicalTitle}</p>}
                {/* 표 항목(구조화 금액)과 원문(전문 텍스트)을 각각 독립된 카드로 나누고,
                    fade-up 진입 애니메이션(PageHeader와 같은 패턴)을 시차를 둬서 적용 —
                    두 파트가 시각적으로 분리된 콘텐츠라는 걸 애니메이션으로도 드러낸다. */}
                {s.amounts?.length > 0 && (
                  <div className="drawer-card" style={{ animationDelay: "0ms" }}>
                    <p className="text-caption font-medium text-ink-faint mb-2">표 항목</p>
                    <AmountsTable amounts={s.amounts} />
                  </div>
                )}
                {s.text && (
                  <div className="drawer-card mt-3" style={{ animationDelay: "80ms" }}>
                    <p className="text-caption font-medium text-ink-faint mb-2">원문</p>
                    <SourceText text={s.text} />
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-caption text-ink-faint">원문이 없습니다.</p>
        )}
      </CompareSourceDrawer>

      <style jsx>{`
        .drawer-card {
          background-color: var(--color-canvas-soft);
          border-radius: var(--radius-md);
          padding: 14px;
          opacity: 0;
          animation: drawer-card-fade-up 0.35s ease-out forwards;
        }
        @keyframes drawer-card-fade-up {
          from {
            opacity: 0;
            transform: translateY(6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .drawer-card {
            animation: none;
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
