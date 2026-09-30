"use client";

import { useEffect, useRef, useState } from "react";
import { searchBrands } from "../../lib/api";

/**
 * 브랜드 다중 선택 콤보박스. 선택된 브랜드는 입력창 안에 칩으로 쌓이고, 그 옆에서 계속
 * 타이핑해서 다음 브랜드를 검색/추가할 수 있다(원본 BrandAutocomplete의 디바운스 검색·
 * 키보드 네비게이션 로직을 그대로 가져오되, "슬롯 여러 개"가 아니라 "칩 여러 개 + 인풋
 * 하나"로 렌더링만 바꿈). value/onChange로 선택된 배열({brandNm, brandMnno})을 부모가
 * 들고 있고, max에 도달하면 입력창이 사라진다.
 */
export default function BrandMultiSelect({ value, onChange, max, placeholder, disabled }) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [focused, setFocused] = useState(false);
  const debounceRef = useRef(null);
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedMnnos = new Set(value.map((v) => v.brandMnno).filter(Boolean));
  const atMax = value.length >= max;

  function handleQueryChange(e) {
    const q = e.target.value;
    setQuery(q);
    setActiveIndex(-1);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    const trimmed = q.trim();
    if (!trimmed) {
      setItems([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await searchBrands(trimmed);
        setItems((data.items || []).filter((it) => !selectedMnnos.has(it.brandMnno)));
        setOpen(true);
      } catch {
        setItems([]);
      }
    }, 200);
  }

  function addBrand(item) {
    if (value.length >= max) return;
    onChange([...value, { brandNm: item.brandNm, brandMnno: item.brandMnno }]);
    setQuery("");
    setItems([]);
    setOpen(false);
    inputRef.current?.focus();
  }

  function removeAt(idx) {
    onChange(value.filter((_, i) => i !== idx));
    inputRef.current?.focus();
  }

  function handleKeyDown(e) {
    if (e.key === "ArrowDown" && open && items.length > 0) {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, items.length - 1));
    } else if (e.key === "ArrowUp" && open && items.length > 0) {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && items[activeIndex]) {
        addBrand(items[activeIndex]);
      } else if (query.trim()) {
        // 후보를 고르지 않고 그냥 엔터 — 검색 결과가 아직 없거나 마음에 드는 게 없어도
        // 이름만으로 우선 칩을 만든다(brandMnno 없이). 이전 슬롯 방식에서도 자동완성 없이
        // 이름만 입력해서 제출할 수 있었던 걸 그대로 유지.
        onChange([...value, { brandNm: query.trim(), brandMnno: undefined }]);
        setQuery("");
        setItems([]);
        setOpen(false);
      }
    } else if (e.key === "Backspace" && !query && value.length > 0) {
      removeAt(value.length - 1);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative flex-1 min-w-[240px]">
      {/* input_04(Uiverse.io by alexruix) 참고 — 왼쪽 돋보기 아이콘 + 연한 회색 배경,
          포커스 시 테두리색과 은은한 glow(box-shadow)로 바뀌는 검색창 스타일. 원본 핑크
          포인트 컬러는 프로젝트 primary 토큰으로 교체. */}
      <div className={`chip-shell ${focused ? "focused" : ""}`} onClick={() => inputRef.current?.focus()}>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="chip-shell-icon" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path strokeLinecap="round" d="m20 20-3.5-3.5" />
        </svg>
        {value.map((v, i) => (
          <span key={`${v.brandMnno || v.brandNm}-${i}`} className="chip">
            <span className="chip-label">{v.brandNm}</span>
            <button
              type="button"
              className="chip-remove"
              onClick={(e) => {
                e.stopPropagation();
                removeAt(i);
              }}
              aria-label={`${v.brandNm} 삭제`}
              disabled={disabled}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" strokeWidth="2.5" stroke="currentColor" fill="none" className="w-3 h-3">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </span>
        ))}
        {!atMax && (
          // 드롭다운을 이 span 기준(relative)으로 앵커링한다 — 이전엔 전체 콤보박스
          // 왼쪽에 고정되어 있어서 칩이 쌓여 인풋이 오른쪽으로 밀려도 드롭다운은 안 따라
          //왔었다. 인풋 바로 아래에서 열리도록 인풋을 감싸는 요소에 dropdown을 둔다.
          <span className="chip-input-wrap">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={handleQueryChange}
              onKeyDown={handleKeyDown}
              onFocus={() => {
                setFocused(true);
                items.length > 0 && setOpen(true);
              }}
              onBlur={() => setFocused(false)}
              placeholder={value.length === 0 ? placeholder : ""}
              className="chip-input"
              disabled={disabled}
              autoComplete="off"
            />
            {open && items.length > 0 && (
              <ul className="absolute left-0 top-full z-10 mt-1 min-w-[280px] max-h-72 overflow-y-auto feature-card-elevated p-1 flex flex-col gap-1">
                {items.map((item, i) => (
                  <li key={item.brandMnno}>
                    <button
                      type="button"
                      onClick={() => addBrand(item)}
                      className={`w-full flex items-center justify-between gap-3 px-3 py-2 rounded-md text-left text-body-sm transition-colors duration-150 ${
                        i === activeIndex ? "bg-primary text-on-primary" : "text-ink"
                      }`}
                      onMouseEnter={() => setActiveIndex(i)}
                    >
                      <span className="whitespace-nowrap">{item.brandNm}</span>
                      <span className={`text-caption shrink-0 ${i === activeIndex ? "text-on-primary/80" : "text-ink-faint"}`}>
                        {item.storeCount != null ? `가맹점 ${item.storeCount.toLocaleString()}개` : "-"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </span>
        )}
      </div>

      <style jsx>{`
        .chip-shell {
          position: relative;
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px;
          width: 100%;
          min-height: 44px;
          padding: 6px 10px 6px 2.25rem;
          border: 2px solid var(--color-hairline);
          border-radius: var(--radius-md);
          background-color: var(--color-surface);
          cursor: text;
          transition: 0.2s ease;
        }
        .chip-shell:hover {
          border-color: color-mix(in srgb, var(--color-primary) 25%, var(--color-hairline));
        }
        .chip-shell.focused {
          border-color: color-mix(in srgb, var(--color-primary) 40%, transparent);
          background-color: var(--color-surface);
          box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-primary) 10%, transparent);
        }
        .chip-shell-icon {
          position: absolute;
          left: 0.7rem;
          width: 1rem;
          height: 1rem;
          color: var(--color-ink-faint);
        }
        .chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 5px 6px 5px 12px;
          background-color: var(--color-primary);
          color: var(--color-on-primary);
          border-radius: var(--radius-full);
          font: var(--text-body-sm) / var(--text-body-sm--line-height) var(--font-sans);
          max-width: 220px;
        }
        .chip-label {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .chip-remove {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          color: var(--color-on-primary);
          background-color: rgba(255, 255, 255, 0.2);
          transition: background-color 0.15s ease;
          shrink: 0;
        }
        .chip-remove:hover:not(:disabled) {
          background-color: rgba(255, 255, 255, 0.4);
        }
        .chip-input-wrap {
          position: relative;
          flex: 1;
          min-width: 120px;
          display: flex;
        }
        .chip-input {
          flex: 1;
          min-width: 120px;
          border: none;
          outline: none;
          background: transparent;
          font: var(--text-body-sm) / var(--text-body-sm--line-height) var(--font-sans);
          color: var(--color-ink);
          padding: 4px 2px;
        }
        .chip-input:disabled {
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}
