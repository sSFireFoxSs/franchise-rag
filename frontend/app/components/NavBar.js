"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getMe, logout } from "../../lib/api";

// 로그인/로그아웃은 별도 블록에서 렌더링(아래 참고)하므로 여기엔 페이지 링크만 둔다.
const PAGE_NAV_ITEMS = [
  { href: "/chat", label: "채팅" },
  { href: "/compare", label: "브랜드 비교" },
  { href: "/top20", label: "TOP20" },
];

// 홈 화면(/) 안에서만 보이는 섹션 앵커 — 다른 페이지엔 해당 섹션이 없어서 홈일 때만 노출
const HOME_ANCHOR_ITEMS = [
  { href: "#features", label: "기능" },
  { href: "#how-it-works", label: "이용 방법" },
  { href: "#security", label: "신뢰성" },
];

// "시작하기"는 #cta로 스크롤하는 대신, hover하면 실제 서비스 페이지 3개로 바로 갈 수
// 있는 드롭다운을 보여준다 — 홈 네비게이션에서 채팅/비교/TOP20 링크가 완전히 빠지면
// (특히 TOP20은 히어로 CTA에도 없어서) 접근성이 떨어진다는 판단으로 채택.
const START_DROPDOWN_ITEMS = [
  { href: "/chat", label: "채팅", description: "정보공개서 조항을 바로 질문" },
  { href: "/compare", label: "브랜드 비교", description: "가맹비·조건을 나란히" },
  { href: "/top20", label: "TOP20", description: "매출·효율 기준 순위" },
];

export default function NavBar() {
  const pathname = usePathname();

  const router = useRouter();
  const [user, setUser] = useState(null);

  // fixed 헤더 아래 spacer 높이를 실측해서 맞춘다(하드코딩된 68px는 nav 항목 줄바꿈
  // 등으로 헤더 실제 높이가 달라지면 본문과 겹치거나 뜨는 문제가 있었음 — 2026-09-23
  // sticky로 바꿨다가 이 프로젝트 레이아웃(h-dvh html + flex body)에서 sticky 자체가
  // 안 붙는 걸 다시 확인해서 fixed로 되돌리되, 원래 sticky로 바꾸려던 동기였던
  // "헤더 높이 불일치" 문제는 ResizeObserver로 같이 해결함).
  const headerRef = useRef(null);
  const [headerHeight, setHeaderHeight] = useState(0);

  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    // contentRect는 padding/border를 뺀 콘텐츠 박스만 준다(.nav-bar가 padding: 16px +
    // border-bottom: 1px라서 그만큼 spacer가 짧아짐) — offsetHeight(border-box 전체
    // 높이)를 써야 실제 헤더가 차지하는 높이와 맞는다.
    const observer = new ResizeObserver(() => {
      setHeaderHeight(el.offsetHeight);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      try {
        const currentUser = await getMe();

        if (!cancelled) {
          setUser(currentUser);
        }
      } catch {
        if (!cancelled) {
          setUser(null);
        }
      }
    }

    checkAuth();

    window.addEventListener("auth-changed", checkAuth);

    return () => {
      cancelled = true;
      window.removeEventListener("auth-changed", checkAuth);
    };
  }, [pathname]);

  async function handleLogout() {
    try {
      await logout();
      setUser(null);
      router.push("/");
      router.refresh();
    } catch (err) {
      console.error("로그아웃 실패:", err);
    }
  }


  return (
    <>
      <header ref={headerRef} className="nav-bar fixed top-0 left-0 right-0 z-20">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between gap-4">
        <Link href="/" className="text-title text-ink shrink-0">
          프차진단
        </Link>
        <nav className="flex flex-wrap items-center gap-2">
          {pathname === "/" && (
            <>
              {HOME_ANCHOR_ITEMS.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={(e) => {
                    e.preventDefault();
                    document.querySelector(item.href)?.scrollIntoView({ behavior: "smooth" });
                  }}
                  className="btn-utility"
                >
                  {item.label}
                </a>
              ))}
              <div className="nav-start-menu">
                <a
                  href="#cta"
                  onClick={(e) => {
                    e.preventDefault();
                    document.querySelector("#cta")?.scrollIntoView({ behavior: "smooth" });
                  }}
                  className="btn-utility"
                >
                  시작하기
                </a>
                <div className="nav-start-panel">
                  <div className="nav-start-panel-arrow" aria-hidden="true" />
                  <div className="nav-start-panel-card">
                    {START_DROPDOWN_ITEMS.map((item) => (
                      <Link key={item.href} href={item.href} className="nav-start-panel-link">
                        <span className="nav-start-panel-link-dot" aria-hidden="true" />
                        <span className="nav-start-panel-link-text">
                          <span className="nav-start-panel-link-label">{item.label}</span>
                          <span className="nav-start-panel-link-desc">{item.description}</span>
                        </span>
                        <span className="nav-start-panel-link-chevron" aria-hidden="true">
                          →
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
          {/* 홈에서는 채팅/브랜드비교/TOP20이 "시작하기" 드롭다운과 중복되므로 숨긴다.
              로그인/로그아웃 렌더링(바로 아래)과는 분리된 별도 블록 — 로그인 상태
              분기(연지님 담당)를 다른 조건으로 감싸지 않기 위해 일부러 나눠둠. */}
          {pathname !== "/" &&
            PAGE_NAV_ITEMS.map((item) => {
              const active =
                pathname === item.href ||
                pathname?.startsWith(item.href + "/");

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className="btn-utility"
                >
                  {item.label}
                </Link>
              );
            })}

          {user ? (
            <button type="button" onClick={handleLogout} className="btn-utility">
              로그아웃
            </button>
          ) : (
            <Link
              href="/login"
              aria-current={pathname === "/login" ? "page" : undefined}
              className="btn-utility"
            >
              로그인
            </Link>
          )}
        </nav>
        </div>
      </header>
      {/* fixed 헤더가 붕 떠서 본문을 가리는 걸 막는 자리차지용 — headerHeight는 위
          ResizeObserver 실측값(초기 렌더 시 0이면 잠깐 겹칠 수 있으나 레이아웃
          시프트보단 낫다고 판단, 마운트 직후 바로 갱신됨) */}
      <div style={{ height: headerHeight }} aria-hidden="true" />

      <style jsx>{`
        /* "시작하기" hover 드롭다운 — 모바일은 신경 안 씀(hover 전제), 데스크탑 전용 */
        .nav-start-menu {
          position: relative;
        }
        /* 트리거(시작하기)와 카드 사이에 투명한 padding-top으로 "다리"를 놓아서,
           마우스가 대각선으로 이동해도 이 브릿지 구간이 hover 영역에 포함되어
           패널이 끊기지 않게 한다 — 실제 카드(border/그림자)는 안쪽 -card에만 적용. */
        .nav-start-panel {
          position: absolute;
          top: 100%;
          right: 0;
          padding-top: 12px;
          opacity: 0;
          visibility: hidden;
          pointer-events: none;
          transform: translateY(2px);
          transition: opacity 0.18s ease, visibility 0.18s ease, transform 0.18s ease;
        }
        .nav-start-menu:hover .nav-start-panel {
          opacity: 1;
          visibility: visible;
          pointer-events: auto;
          transform: translateY(0);
        }
        .nav-start-panel-arrow {
          position: absolute;
          top: 6px;
          right: 22px;
          width: 10px;
          height: 10px;
          background-color: var(--color-surface);
          border-left: 1px solid var(--color-hairline);
          border-top: 1px solid var(--color-hairline);
          transform: rotate(45deg);
        }
        .nav-start-panel-card {
          position: relative;
          display: flex;
          flex-direction: column;
          gap: 2px;
          min-width: 230px;
          padding: 8px;
          border-radius: var(--radius-lg);
          border: 1px solid var(--color-hairline);
          background-color: var(--color-surface);
          box-shadow: var(--shadow-elevation-2);
          transform: scale(0.97);
          transform-origin: top right;
          transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .nav-start-menu:hover .nav-start-panel-card {
          transform: scale(1);
        }
        .nav-start-panel-link {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 9px 10px;
          border-radius: var(--radius-md);
          color: var(--color-ink);
          white-space: nowrap;
          transition: background-color 0.15s ease;
        }
        .nav-start-panel-link:hover {
          background-color: var(--color-canvas-soft);
        }
        .nav-start-panel-link-dot {
          flex-shrink: 0;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background-color: var(--color-ink-faint);
          transition: background-color 0.15s ease, transform 0.15s ease;
        }
        .nav-start-panel-link:hover .nav-start-panel-link-dot {
          background-color: var(--color-primary);
          transform: scale(1.2);
        }
        .nav-start-panel-link-text {
          display: flex;
          flex-direction: column;
          gap: 1px;
          min-width: 0;
        }
        .nav-start-panel-link-label {
          font: var(--text-button) / var(--text-button--line-height) var(--font-sans);
          font-weight: var(--text-button--font-weight);
        }
        .nav-start-panel-link-desc {
          font: var(--text-caption) / var(--text-caption--line-height) var(--font-sans);
          color: var(--color-ink-faint);
        }
        .nav-start-panel-link-chevron {
          margin-left: auto;
          flex-shrink: 0;
          color: var(--color-ink-faint);
          opacity: 0;
          transform: translateX(-4px);
          transition: opacity 0.15s ease, transform 0.15s ease;
        }
        .nav-start-panel-link:hover .nav-start-panel-link-chevron {
          opacity: 1;
          transform: translateX(0);
        }
      `}</style>
    </>
  );
}
