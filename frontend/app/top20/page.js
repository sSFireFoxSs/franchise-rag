"use client";

import { useEffect, useRef, useState } from "react";
import ErrorAlert from "../components/ErrorAlert";
import BrandLogo from "../components/BrandLogo";
import PageHeader from "../components/PageHeader";
import InfoTooltip from "../components/InfoTooltip";
import SlidingTabs from "../components/SlidingTabs";
import ListSkeleton from "../components/ListSkeleton";
import EmptyState from "../components/EmptyState";
import { getTop20, getTop20Categories } from "../../lib/api";

const TABS = [
  { key: "sales", label: "평균매출액" },
  { key: "store_count", label: "가맹점 수" },
  { key: "cost_efficiency", label: "창업비용 대비 매출" },
];

const ALL_CATEGORY = { key: "all", label: "전체" };

// "기타 외식"은 카운트 기준으로는 상위권이지만 구체적인 업종이 아니라서, 사용자가
// 명확한 업종(한식/커피/치킨/...)을 먼저 훑고 나서 보도록 "일식" 바로 뒤로 순서만 옮긴다.
// 어떤 카테고리가 몇 개 포함되는지(top_categories() 선정 기준)는 그대로 두고 표시 순서만 조정.
function reorderCategoryTabs(cats) {
  const etcIndex = cats.findIndex((c) => c.label === "기타 외식");
  const ilsikIndex = cats.findIndex((c) => c.label === "일식");
  if (etcIndex === -1 || ilsikIndex === -1 || etcIndex === ilsikIndex + 1) return cats;
  const next = [...cats];
  const [etc] = next.splice(etcIndex, 1);
  const insertAt = next.findIndex((c) => c.label === "일식") + 1;
  next.splice(insertAt, 0, etc);
  return next;
}

export default function Top20Page() {
  const [by, setBy] = useState("sales");
  const [category, setCategory] = useState(ALL_CATEGORY.key);
  const [categoryTabs, setCategoryTabs] = useState([ALL_CATEGORY]);
  // SlidingTabs와 같은 방식(실제 버튼 offsetLeft/offsetWidth 실측) — 카테고리 탭도
  // 색이 순간적으로 바뀌는 대신 인디케이터가 미끄러지듯 이동하게 함.
  const categoryTabRefs = useRef({});
  const [categoryIndicator, setCategoryIndicator] = useState({ left: 0, width: 0 });
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // 정렬/카테고리 탭을 바꿀 때마다 스켈레톤으로 화면이 확 바뀌는 대신, 이미 한 번
  // 로딩한 뒤로는 기존 목록을 그대로 두고 흐리게(opacity)만 낮췄다가 새 데이터가
  // 오면 부드럽게 되돌아오도록 함 — 첫 진입 시에만 스켈레톤을 보여줌.
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  useEffect(() => {
    getTop20Categories()
      .then((data) => {
        const cats = (data.categories || []).map((c) => ({ key: c.key, label: c.label }));
        setCategoryTabs([ALL_CATEGORY, ...reorderCategoryTabs(cats)]);
      })
      .catch(() => {
        // 카테고리 목록 로딩 실패는 조용히 무시 — "전체" 탭만으로도 기존 기능은 그대로 동작함
      });
  }, []);

  useEffect(() => {
    const el = categoryTabRefs.current[category];
    if (el) {
      setCategoryIndicator({ left: el.offsetLeft, width: el.offsetWidth });
    }
  }, [category, categoryTabs]);

  useEffect(() => {
    let cancelled = false;

    getTop20(by, category === ALL_CATEGORY.key ? null : category)
      .then((data) => {
        if (cancelled) return;
        setItems(data.items || []);
        setHasLoadedOnce(true);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(
          e.message?.includes("Failed to fetch") || e.message?.includes("fetch")
            ? "백엔드 서버에 연결하지 못했습니다. uvicorn이 실행 중인지 확인해 주세요."
            : e.message
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [by, category]);

  function handleByChange(nextBy) {
    setLoading(true);
    setError(null);
    setBy(nextBy);
  }

  function handleCategoryChange(nextCategory) {
    setLoading(true);
    setError(null);
    setCategory(nextCategory);
  }

  return (
    <div className="mx-auto w-full max-w-[1280px] flex-1 p-6">
      <PageHeader
        badge="TOP20"
        title={
          (category === ALL_CATEGORY.key ? "" : `${category} 브랜드 중 `) +
          (by === "sales"
            ? "평균매출액이 가장 높은 브랜드를 살펴보세요"
            : by === "store_count"
            ? "운영 중인 매장이 가장 많은 브랜드를 살펴보세요"
            : "창업비용 대비 매출이 가장 좋은 브랜드를 살펴보세요")
        }
        description={
          by === "sales" ? (
            <>
              공정거래위원회에 등록된 실제 매출 자료를 그대로 보여드려요{" "}
              <InfoTooltip>
                가맹점 수가 적으면 평균매출액이 소수 매장 실적에 쏠릴 수 있어서,
                가맹점 5개 이상인 브랜드만 표시돼요.
              </InfoTooltip>
            </>
          ) : by === "store_count" ? (
            "공정거래위원회에 등록된 실제 가맹점 수 자료를 그대로 보여드려요"
          ) : (
            <>
              연평균매출액을 총창업비용으로 나눈 값이에요(영업이익 기준 아님){" "}
              <InfoTooltip>
                정보공개서상 연평균매출액은 가맹점 평균값이라 소수 매장 실적에 쏠릴
                수 있어서, 가맹점 5개 이상인 브랜드만 표시돼요.
              </InfoTooltip>
            </>
          )
        }
      />

      <div className="mb-3">
        <SlidingTabs tabs={TABS} active={by} onChange={handleByChange} />
      </div>

      <div className="category-tabs relative mb-4 flex gap-2 overflow-x-auto pb-1">
        <span
          className="category-tab-indicator"
          style={{ transform: `translateX(${categoryIndicator.left}px)`, width: `${categoryIndicator.width}px` }}
          aria-hidden="true"
        />
        {categoryTabs.map((tab) => (
          <button
            key={tab.key}
            ref={(el) => {
              categoryTabRefs.current[tab.key] = el;
            }}
            type="button"
            aria-current={category === tab.key ? "page" : undefined}
            onClick={() => handleCategoryChange(tab.key)}
            className="category-tab shrink-0"
          >
            {tab.label}
          </button>
        ))}

        <style jsx>{`
          .category-tab {
            position: relative;
            z-index: 1;
            font: var(--text-button) / var(--text-button--line-height) var(--font-sans);
            font-weight: var(--text-button--font-weight);
            padding: 6px 16px;
            border-radius: var(--radius-full);
            border: 1px solid var(--color-hairline);
            background-color: var(--color-surface);
            color: var(--color-ink-secondary);
            transition: border-color 0.15s ease, color 0.2s ease;
          }
          .category-tab:hover {
            border-color: var(--color-primary);
          }
          .category-tab[aria-current="page"] {
            background-color: transparent;
            border-color: var(--color-primary);
            color: var(--color-on-primary);
          }
          .category-tab-indicator {
            position: absolute;
            z-index: 0;
            top: 0;
            left: 0;
            bottom: 0;
            border-radius: var(--radius-full);
            background-color: var(--color-primary);
            transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1), width 0.28s cubic-bezier(0.4, 0, 0.2, 1);
          }
        `}</style>
      </div>

      {error ? (
        <ErrorAlert message={error} onDismiss={() => setError(null)} />
      ) : loading && !hasLoadedOnce ? (
        <ListSkeleton rows={8} />
      ) : items.length === 0 ? (
        <EmptyState
          title="표시할 순위가 없습니다"
          description="집계 가능한 데이터를 가진 브랜드가 없습니다. 다른 정렬 기준을 선택해 보세요."
        />
      ) : (
        <>
        <ol
          className={`feature-card divide-y divide-hairline overflow-hidden transition-all duration-300 ease-out ${
            loading ? "opacity-20 blur-[2px] scale-[0.99]" : "opacity-100 blur-0 scale-100"
          }`}
        >
          {items.map((item) => (
            <li
              key={item.brandMnno ?? item.rank}
              className="top20-row grid grid-cols-[24px_48px_1fr_auto] items-center gap-3 py-3 px-2 -mx-2 rounded-lg"
            >
              {item.rank <= 3 ? (
                <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary text-on-primary text-caption font-bold">
                  {item.rank}
                </span>
              ) : (
                <span className="text-title text-ink-faint text-right">{item.rank}</span>
              )}
              <BrandLogo brandNm={item.brandNm} brandMnno={item.brandMnno} size={12} shape="square" />
              <div className="min-w-0">
                <p className="text-body-md text-ink font-semibold truncate">{item.brandNm}</p>
                {(by === "sales" || by === "cost_efficiency") && item.storeCount != null && (
                  <p className="text-caption text-ink-faint">
                    {`가맹점 ${item.storeCount.toLocaleString()}개`}
                  </p>
                )}
              </div>
              <span className="tabular-nums text-body-md text-ink font-medium text-right">
                {item.valueLabel || "데이터 없음"}
              </span>
            </li>
          ))}
        </ol>

        <style jsx>{`
          .top20-row {
            transition: background-color 0.15s ease, transform 0.15s ease;
          }
          .top20-row:hover {
            background-color: var(--color-canvas-soft);
            transform: translateX(2px);
          }
        `}</style>
        </>
      )}
    </div>
  );
}
