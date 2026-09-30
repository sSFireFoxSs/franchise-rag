"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getHomeStats } from "../lib/api";
import LogoLoop from "./components/LogoLoop";

/* ─────────────────────────────────────────────────────────────────────────
   experiment/optimus-home 브랜치에서 만든 Optimus 템플릿 기반 실험을, 새 패키지
   설치 없이(TypeScript/shadcn/lucide 없이) 우리 기존 디자인 토큰 + 순수 JS로
   재현한 버전. 시각적 결과물은 최대한 동일하게, 기술 스택만 기존 프로젝트에 맞춤.
   ───────────────────────────────────────────────────────────────────────── */

const WORDS = ["확인하고", "비교하고", "검토하고", "정리하고"];

// 히어로 로고 루프에 고정 노출할 브랜드 20개(2026-09-23 사용자 직접 선정).
const LOOP_BRANDS = [
  { brandMnno: "BRD_20090100502", brandNm: "빽다방" },
  { brandMnno: "BRD_20161159", brandNm: "매머드익스프레스" },
  { brandMnno: "BRD_20231305", brandNm: "셀렉커피랩" },
  { brandMnno: "BRD_20230178", brandNm: "카페만월경" },
  { brandMnno: "BRD_20080100373", brandNm: "탐앤탐스커피" },
  { brandMnno: "BRD_20080200106", brandNm: "처갓집양념치킨" },
  { brandMnno: "BRD_20161241", brandNm: "비비큐(BBQ)" },
  { brandMnno: "BRD_20160798", brandNm: "가마치통닭" },
  { brandMnno: "BRD_20080100262", brandNm: "멕시카나" },
  { brandMnno: "BRD_20170439", brandNm: "후라이드 참 잘하는집" },
  { brandMnno: "BRD_20141221", brandNm: "본죽&비빔밥" },
  { brandMnno: "BRD_20151296", brandNm: "백채" },
  { brandMnno: "BRD_20080100111", brandNm: "채선당" },
  { brandMnno: "BRD_20160803", brandNm: "뉴욕야시장" },
  { brandMnno: "BRD_20150385", brandNm: "두끼" },
  { brandMnno: "BRD_20141237", brandNm: "와플대학" },
  { brandMnno: "BRD_20110100614", brandNm: "알파" },
  { brandMnno: "BRD_20130100025", brandNm: "준오헤어" },
  { brandMnno: "BRD_20080100032", brandNm: "GS25" },
  { brandMnno: "BRD_20201211", brandNm: "Uber Taxi" },
];

const FEATURES = [
  {
    number: "01",
    title: "채팅으로 질문",
    description: "브랜드명이나 항목명을 몰라도 자연어로 질문할 수 있습니다.",
  },
  {
    number: "02",
    title: "브랜드 비교",
    description: "관심 브랜드의 가맹비, 보증금, 계약 조건을 항목별로 나란히 비교합니다.",
  },
  {
    number: "03",
    title: "TOP20 순위",
    description: "매출, 가맹점 수 등 주요 기준별 상위 20개 브랜드를 확인합니다.",
  },
  {
    number: "04",
    title: "근거 기반 답변",
    description: "답변에 사용된 정보공개서 항목과 원문 위치를 함께 제공합니다.",
  },
];

const STEPS = [
  {
    number: "I",
    title: "질문하기",
    description: "궁금한 브랜드나 조건을 평소 말하듯 입력하세요.",
    code: `질문("GS25 가맹비와 보증금 알려줘")`,
    status: "검색 준비 완료",
  },
  {
    number: "II",
    title: "출처 보기",
    description: "답변에 사용된 정보공개서 항목, 연도, 원문 내용을 확인합니다.",
    code: `근거 = 정보공개서["가맹금"]["보증금"]\n출처: 공정거래위원회`,
    status: "원문 출처 표시",
  },
  {
    number: "III",
    title: "브랜드 비교",
    description: "여러 브랜드를 선택해 비용과 계약 조건의 차이를 비교합니다.",
    code: `비교(["GS25", "CU", "세븐일레븐"])\n\n// 3개 브랜드 가맹금 비교 완료`,
    status: "비교 항목 정리",
  },
];

const SECURITY_FEATURES = [
  {
    icon: "shield",
    title: "공정거래위원회 정보공개서 기반",
    description: "등록된 정보공개서 데이터를 기준으로 답변합니다.",
  },
  {
    icon: "doc",
    title: "원문 항목 표시",
    description: "답변마다 연도, 항목, 원문 내용을 함께 보여줍니다.",
  },
  {
    icon: "eye",
    title: "임의 수치 없음",
    description: "데이터가 없는 브랜드나 항목은 '데이터 없음'으로 표시합니다.",
  },
  {
    icon: "lock",
    title: "계산값 별도 처리",
    description: "합산, 정렬, 순위 계산은 별도 로직으로 처리해 추정값이 섞이지 않도록 합니다.",
  },
];

const CERTIFICATIONS = [
  "공정거래위원회",
  "2024~2025 정보공개서",
  "89,969건 데이터",
  "2,427개 브랜드",
  "TOP20 분석 대상 1,336개",
  "답변 수치 자동 검증",
  "AI 검색 서비스",
];

const HERO_STAT_LABELS = [
  { key: "brandCount", label: "정보공개서 보유 브랜드 수" },
  { key: "disclosureItemCount", label: "정보공개서 데이터 항목" },
  { key: "rankableBrandCount", label: "TOP20 분석 대상 브랜드" },
];

/* 코드 스니펫에 최소한의 신택스 하이라이팅을 입히는 간단한 토크나이저.
   실제 파서가 아니라 " "문자열, ()안 함수명, // 주석, 숫자만 구분하는 수준. */
function highlightLine(line) {
  if (line.trim().startsWith("//")) {
    return line.split("").map((char) => ({ char, color: "rgba(255,255,255,0.35)", italic: true }));
  }
  const result = [];
  let i = 0;
  let inString = false;
  while (i < line.length) {
    const ch = line[i];
    if (ch === '"') {
      inString = !inString;
      result.push({ char: ch, color: "#e3a86b" });
      i++;
      continue;
    }
    if (inString) {
      result.push({ char: ch, color: "#e3a86b" });
      i++;
      continue;
    }
    if ("[](){}".includes(ch)) {
      result.push({ char: ch, color: "rgba(255,255,255,0.45)" });
      i++;
      continue;
    }
    if (/[A-Za-z0-9가-힣_]/.test(ch)) {
      let j = i;
      while (j < line.length && /[A-Za-z0-9가-힣_]/.test(line[j])) j++;
      const word = line.slice(i, j);
      const isNumber = /^[0-9]+$/.test(word);
      const isCall = line[j] === "(";
      const color = isCall ? "#8fc7ef" : isNumber ? "#9fd88f" : "rgba(255,255,255,0.75)";
      for (const c of word) result.push({ char: c, color });
      i = j;
      continue;
    }
    result.push({ char: ch, color: "rgba(255,255,255,0.5)" });
    i++;
  }
  return result;
}

/* lucide-react 없이 순수 SVG로 그린 4개 아이콘 — 새 패키지 안 씀 */
function SecurityIcon({ type }) {
  const common = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8 };
  switch (type) {
    case "shield":
      return (
        <svg {...common}>
          <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
        </svg>
      );
    case "doc":
      return (
        <svg {...common}>
          <path d="M6 3h9l5 5v13H6z" />
          <path d="M9 12l2 2 4-4" />
        </svg>
      );
    case "eye":
      return (
        <svg {...common}>
          <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z" />
          <circle cx="12" cy="12" r="2.5" />
        </svg>
      );
    case "lock":
      return (
        <svg {...common}>
          <rect x="5" y="11" width="14" height="9" rx="1.5" />
          <path d="M8 11V7a4 4 0 018 0v4" />
        </svg>
      );
    default:
      return null;
  }
}

/* 스크롤(또는 마운트 시 이미 보이는 경우 즉시) 등장 페이드업 애니메이션.
   새 keyframe 없이 opacity/translate transition만 써서 globals.css 안 건드림. */
function RevealBlock({ children, className = "", delay = 0, as: Tag = "div", style: extraStyle, ...rest }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`transition-all duration-700 ease-out ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
      } ${className}`}
      style={{ transitionDelay: `${delay}ms`, ...extraStyle }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/* 순환 단어 — 바뀔 때 블러+슬라이드로 살짝 사라졌다 나타남(keyframe 없이 transition만) */
function CyclingWord({ words, intervalMs = 2500 }) {
  const [index, setIndex] = useState(0);
  const [shown, setShown] = useState(true);

  useEffect(() => {
    const timer = setInterval(() => {
      setShown(false);
      setTimeout(() => {
        setIndex((i) => (i + 1) % words.length);
        setShown(true);
      }, 250);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [words, intervalMs]);

  return (
    <span
      className="inline-block transition-all duration-300 ease-out"
      style={{
        opacity: shown ? 1 : 0,
        filter: shown ? "blur(0px)" : "blur(6px)",
        transform: shown ? "translateY(0)" : "translateY(6px)",
      }}
    >
      {words[index]}
    </span>
  );
}

export default function Home() {
  const [stats, setStats] = useState(null);
  const [activeStep, setActiveStep] = useState(0);
  const [logoItems, setLogoItems] = useState([]);

  useEffect(() => {
    let cancelled = false;
    getHomeStats()
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch(() => {
        if (!cancelled) setStats(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 히어로 로고 루프 — TOP20 API에서 동적으로 가져오던 것을, 2026-09-23 사용자가
  // 직접 고른 브랜드 20개로 고정함(무작위/자동 선정 대신 사람이 확인한 목록만 노출
  // — 핵심 원칙: 임의 데이터 노출 금지와 같은 취지). 파일이 실제로 로드되는지는
  // 여전히 <img>로 검증해서, 깨진 이미지는 목록에서 뺌.
  useEffect(() => {
    let cancelled = false;

    async function loadLogos() {
      const checked = await Promise.all(
        LOOP_BRANDS.map(
          (b) =>
            new Promise((resolve) => {
              const src = `/logos/${encodeURIComponent(b.brandMnno)}.png`;
              const img = new window.Image();
              img.onload = () => resolve({ src, alt: `${b.brandNm} 로고` });
              img.onerror = () => resolve(null);
              img.src = src;
            })
        )
      );

      if (!cancelled) setLogoItems(checked.filter(Boolean));
    }

    loadLogos();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const interval = setInterval(() => setActiveStep((i) => (i + 1) % STEPS.length), 5000);
    return () => clearInterval(interval);
  }, []);

  const scrollToId = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

  return (
    <div className="flex-1 flex flex-col">
      {/* 히어로 */}
      <section className="relative min-h-[85vh] flex flex-col justify-center overflow-hidden">
        <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-30">
          {[...Array(8)].map((_, i) => (
            <div key={`h-${i}`} className="absolute h-px bg-ink/10" style={{ top: `${12.5 * (i + 1)}%`, left: 0, right: 0 }} />
          ))}
          {[...Array(12)].map((_, i) => (
            <div key={`v-${i}`} className="absolute w-px bg-ink/10" style={{ left: `${8.33 * (i + 1)}%`, top: 0, bottom: 0 }} />
          ))}
        </div>

        <div className="relative z-10 max-w-[1280px] w-full mx-auto px-6 lg:px-12 py-24">
          <RevealBlock className="mb-8">
            <span className="hero-eyebrow">
              <span className="hero-eyebrow-line" aria-hidden="true" />
              정보공개서 기반 AI 검색
            </span>
          </RevealBlock>

          <RevealBlock delay={100} as="h1" className="text-[clamp(2.75rem,8vw,6.5rem)] font-bold leading-[1.05] tracking-tight text-ink mb-12 break-keep">
            <span className="block">프랜차이즈 계약,</span>
            <span className="block">
              조항까지{" "}
              <span className="relative inline-block">
                <CyclingWord words={WORDS} />
                <span className="absolute -bottom-2 left-0 right-0 h-3 bg-primary/10" />
              </span>
            </span>
            <span className="block">시작하세요</span>
          </RevealBlock>

          <RevealBlock delay={200} className="grid lg:grid-cols-2 gap-12 lg:gap-24 items-end mb-16">
            <p className="text-xl lg:text-2xl text-ink-muted leading-relaxed max-w-xl break-keep">
              가맹비, 보증금, 계약 조건을 정보공개서 기준으로 찾아드립니다.
            </p>
            <div className="flex flex-col sm:flex-row items-start gap-4">
              <Link href="/chat" className="btn-hero-primary">
                지금 물어보기
                <span className="hero-cta-arrow" aria-hidden="true">→</span>
              </Link>
              <button type="button" onClick={() => scrollToId("features")} className="btn-hero-outline">
                주요 기능 보기
              </button>
            </div>
          </RevealBlock>

          {logoItems.length > 0 && (
            <RevealBlock delay={300} className="pt-8 border-t border-hairline">
              <LogoLoop logos={logoItems} speed={50} logoHeight={56} gap={56} pauseOnHover />
            </RevealBlock>
          )}
        </div>
      </section>

      {/* 기능 */}
      <section id="features" className="relative h-screen flex flex-col justify-center overflow-hidden">
        <div className="max-w-[1280px] mx-auto px-6 lg:px-12">
          <RevealBlock className="mb-10">
            <span className="hero-eyebrow mb-3">
              <span className="hero-eyebrow-line" aria-hidden="true" />
              기능
            </span>
            <h2 className="text-3xl lg:text-5xl font-bold tracking-tight text-ink break-keep">
              창업 검토에 필요한 정보만 <span className="text-primary">정확하게 확인하세요</span>
            </h2>
          </RevealBlock>

          <div className="grid sm:grid-cols-2 gap-4 lg:gap-6">
            {FEATURES.map((f, i) => (
              <RevealBlock
                key={f.number}
                delay={i * 100}
                className="feature-card border-0 ring-4 ring-white/70 transition-all duration-300 hover:shadow-[var(--shadow-elevation-2)] hover:-translate-y-1"
              >
                <span className="text-caption text-primary font-semibold block mb-2">{f.number}</span>
                <h3 className="text-title text-ink mb-2">{f.title}</h3>
                <p className="text-body-sm text-ink-muted break-keep">{f.description}</p>
              </RevealBlock>
            ))}
          </div>
        </div>
      </section>

      {/* 이용 방법 (다크 섹션) */}
      <section id="how-it-works" className="relative h-screen flex flex-col justify-center bg-ink text-canvas overflow-hidden">
        {/* 대각선 줄무늬 배경 패턴 */}
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage:
                "repeating-linear-gradient(-45deg, transparent, transparent 40px, currentColor 40px, currentColor 41px)",
            }}
          />
        </div>

        <div className="relative z-10 max-w-[1280px] mx-auto px-6 lg:px-12">
          <RevealBlock className="mb-10">
            <span className="inline-flex items-center gap-3 text-sm text-canvas/50 mb-3">
              <span className="w-8 h-px bg-canvas/30" />
              이용 방법
            </span>
            <h2 className="text-3xl lg:text-5xl font-bold tracking-tight break-keep">
              질문부터 비교까지, <span className="text-canvas/50">세 단계로 진행됩니다</span>
            </h2>
          </RevealBlock>

          <div className="grid lg:grid-cols-2 gap-10 lg:gap-16">
            <div>
              {STEPS.map((step, index) => (
                <button
                  key={step.number}
                  type="button"
                  onClick={() => setActiveStep(index)}
                  className={`w-full text-left py-5 border-b border-canvas/10 transition-opacity duration-500 ${
                    activeStep === index ? "opacity-100" : "opacity-40 hover:opacity-70"
                  }`}
                >
                  <div className="flex items-start gap-6">
                    <span className="text-3xl font-bold text-canvas/30">{step.number}</span>
                    <div className="flex-1">
                      <h3 className="text-2xl font-bold mb-3">{step.title}</h3>
                      <p className="text-canvas/60 leading-relaxed break-keep">{step.description}</p>
                      {activeStep === index && (
                        <div className="mt-4 h-px bg-canvas/20 overflow-hidden">
                          <div key={activeStep} className="h-full bg-canvas w-0 step-progress" />
                        </div>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>

            <div className="lg:sticky lg:top-8 self-start">
              <div className="border border-canvas/10 overflow-hidden">
                <div className="px-6 py-4 border-b border-canvas/10 flex items-center justify-between">
                  <div className="flex gap-2">
                    <div className="w-3 h-3 rounded-full bg-canvas/20" />
                    <div className="w-3 h-3 rounded-full bg-canvas/20" />
                    <div className="w-3 h-3 rounded-full bg-canvas/20" />
                  </div>
                  <span className="text-xs font-mono text-canvas/40">query.js</span>
                </div>
                <div className="p-6 font-mono text-sm min-h-[140px]">
                  <pre>
                    {(() => {
                      const codeLines = STEPS[activeStep].code.split("\n").map((line) => highlightLine(line));
                      const linePause = 150;
                      let cursor = 0;
                      const lineStartDelays = codeLines.map((chars) => {
                        const start = cursor;
                        cursor += chars.length * 28 + linePause;
                        return start;
                      });
                      const lastLineIndex = codeLines.length - 1;
                      const lastLineEndDelay =
                        lineStartDelays[lastLineIndex] + codeLines[lastLineIndex].length * 28 + 100;
                      return codeLines.map((chars, lineIndex) => (
                        <div
                          key={`${activeStep}-${lineIndex}`}
                          className="leading-loose code-line-reveal"
                          style={{ animationDelay: `${lineStartDelays[lineIndex]}ms` }}
                        >
                          <span className="text-canvas/20 select-none w-8 inline-block">{lineIndex + 1}</span>
                          {chars.map(({ char, color, italic }, charIndex) => (
                            <span
                              key={charIndex}
                              className="code-char-reveal"
                              style={{
                                color,
                                fontStyle: italic ? "italic" : "normal",
                                animationDelay: `${lineStartDelays[lineIndex] + charIndex * 28}ms`,
                              }}
                            >
                              {char === " " ? " " : char}
                            </span>
                          ))}
                          {lineIndex === lastLineIndex && (
                            <span
                              className="code-typing-cursor"
                              style={{ animationDelay: `${lastLineEndDelay}ms` }}
                              aria-hidden="true"
                            >
                              |
                            </span>
                          )}
                        </div>
                      ));
                    })()}
                  </pre>
                </div>
                <div className="px-6 py-4 border-t border-canvas/10 flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
                  <span className="text-xs font-mono text-canvas/40">{STEPS[activeStep].status}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* globals.css 안 건드리고 이 섹션에만 스코프된 keyframe — styled-jsx는 Next.js
            내장 기능이라 새 패키지 설치 없이 씀 */}
        <style jsx>{`
          .code-line-reveal {
            opacity: 0;
            transform: translateX(-8px);
            animation: lineReveal 0.4s cubic-bezier(0.22, 1, 0.36, 1) forwards;
          }
          @keyframes lineReveal {
            to {
              opacity: 1;
              transform: translateX(0);
            }
          }
          .code-char-reveal {
            /* 블러로 서서히 떠오르는 대신, 타자기처럼 순간적으로 툭 찍히게 —
               reactbits TextType 컴포넌트 검토 후 채택한 방식(gsap 등 새 패키지는
               안 쓰고, 이 프로젝트 기존 staggered-delay 구조에 순수 CSS로만 반영) */
            opacity: 0;
            animation: charReveal 0.05s steps(1) forwards;
          }
          @keyframes charReveal {
            to {
              opacity: 1;
            }
          }
          .code-typing-cursor {
            display: inline-block;
            opacity: 0;
            color: rgba(255, 255, 255, 0.75);
            animation: cursorAppear 0.05s steps(1) forwards, cursorBlink 0.9s steps(1) infinite;
          }
          @keyframes cursorAppear {
            to {
              opacity: 1;
            }
          }
          @keyframes cursorBlink {
            0%,
            49% {
              opacity: 1;
            }
            50%,
            100% {
              opacity: 0;
            }
          }
          .step-progress {
            animation: stepProgress 5s linear forwards;
          }
          @keyframes stepProgress {
            from {
              width: 0%;
            }
            to {
              width: 100%;
            }
          }
        `}</style>
      </section>

      {/* 신뢰성 */}
      <section id="security" className="relative py-24 lg:py-32 bg-canvas-soft">
        {/* 히어로와 같은 격자선 배경 — 신뢰성 섹션에만 적용. 히어로는 min-h-[85vh]를
            8등분(칸 높이 85/8 = 10.625vh)한 것과 정확히 같은 칸 크기를 쓰도록, %가
            아니라 vh 고정값으로 줄을 긋고 섹션 높이를 넘는 건 overflow-hidden으로
            자름 — 섹션 자체 높이가 달라도(반응형/콘텐츠 가변) 칸 크기는 항상 동일. */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-30">
          {[...Array(20)].map((_, i) => (
            <div key={`sec-h-${i}`} className="absolute h-px bg-ink/10" style={{ top: `${10.625 * (i + 1)}vh`, left: 0, right: 0 }} />
          ))}
          {[...Array(12)].map((_, i) => (
            <div key={`sec-v-${i}`} className="absolute w-px bg-ink/10" style={{ left: `${8.33 * (i + 1)}%`, top: 0, bottom: 0 }} />
          ))}
        </div>
        <div className="relative z-10 max-w-[1280px] mx-auto px-6 lg:px-12">
          <div className="grid lg:grid-cols-2 gap-16 lg:gap-24">
            <RevealBlock>
              <span className="hero-eyebrow mb-6">
                <span className="hero-eyebrow-line" aria-hidden="true" />
                신뢰성
              </span>
              <h2 className="text-3xl lg:text-5xl font-bold tracking-tight text-ink mb-8 break-keep">
                출처가 확인되는
                <br />
                답변을 제공합니다
              </h2>
              <p className="text-lg text-ink-muted leading-relaxed mb-10 break-keep">
                창업 판단에 쓰이는 정보인 만큼, 수치와 조건을 임의로 보완하지 않습니다.
                답변은 등록된 정보공개서 데이터와 원문 항목을 기준으로 구성됩니다.
              </p>
              <div className="flex flex-wrap gap-3">
                {CERTIFICATIONS.map((cert) => (
                  <span
                    key={cert}
                    className="relative px-4 py-2 border border-hairline bg-surface text-sm font-mono text-ink-muted transition-[color,border-color,transform,box-shadow] duration-200 hover:border-primary hover:text-ink hover:-translate-y-0.5 hover:shadow-[0_10px_20px_rgba(0,0,0,0.12)] after:content-[''] after:absolute after:inset-0 after:bg-surface after:-z-10 after:transition-all after:duration-500 hover:after:scale-x-125 hover:after:scale-y-150 hover:after:opacity-0"
                  >
                    {cert}
                  </span>
                ))}
              </div>
            </RevealBlock>

            <div className="grid gap-4">
              {SECURITY_FEATURES.map((f, i) => (
                <RevealBlock
                  key={f.title}
                  delay={i * 100}
                  className="relative p-5 border border-hairline bg-surface flex items-start gap-4 transition-[color,border-color,transform,box-shadow] duration-200 hover:border-primary hover:-translate-y-1 hover:shadow-[0_10px_20px_rgba(0,0,0,0.12)] group after:content-[''] after:absolute after:inset-0 after:bg-surface after:-z-10 after:transition-all after:duration-500 hover:after:scale-x-110 hover:after:scale-y-125 hover:after:opacity-0"
                >
                  <div className="shrink-0 w-10 h-10 flex items-center justify-center border border-hairline text-ink-muted transition-colors group-hover:bg-primary group-hover:text-on-primary">
                    <SecurityIcon type={f.icon} />
                  </div>
                  <div>
                    <h3 className="text-body-md font-semibold text-ink mb-1">{f.title}</h3>
                    <p className="text-body-sm text-ink-muted break-keep">{f.description}</p>
                  </div>
                </RevealBlock>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 통계 마퀴 — 원래 히어로 밑에 있던 걸 신뢰성/시작하기 사이로 이동(사용자 지시) */}
      <section className="relative py-12 overflow-hidden">
        <RevealBlock className="stats-marquee">
          <div className="stats-marquee-track">
            {[0, 1].map((rep) =>
              HERO_STAT_LABELS.map(({ key, label }) => (
                <div key={`${rep}-${key}`} className="flex items-baseline gap-3 shrink-0">
                  <span className="text-heading-1 font-bold text-ink tabular-nums">
                    {stats ? `${stats[key].toLocaleString("ko-KR")}개` : "…"}
                  </span>
                  <span className="text-caption text-ink-muted whitespace-nowrap">{label}</span>
                </div>
              ))
            )}
          </div>
        </RevealBlock>
      </section>

      {/* CTA */}
      <section id="cta" className="relative py-24 lg:py-32">
        <div className="max-w-[1280px] mx-auto px-6 lg:px-12">
          <RevealBlock
            className="relative border-2 border-ink rounded-2xl px-8 lg:px-16 py-16 lg:py-24 overflow-hidden"
            onMouseMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect();
              e.currentTarget.style.setProperty("--spot-x", `${((e.clientX - rect.left) / rect.width) * 100}%`);
              e.currentTarget.style.setProperty("--spot-y", `${((e.clientY - rect.top) / rect.height) * 100}%`);
            }}
          >
            {/* 마우스 따라다니는 스포트라이트 — CSS 변수만 JS로 갱신, 렌더는 순수 CSS */}
            <div
              className="absolute inset-0 opacity-10 pointer-events-none transition-opacity duration-300"
              style={{
                background:
                  "radial-gradient(600px circle at var(--spot-x, 50%) var(--spot-y, 50%), rgba(0,0,0,0.2), transparent 40%)",
              }}
            />

            <h2 className="relative text-4xl lg:text-6xl font-bold tracking-tight text-ink mb-8 leading-[0.95] break-keep">
              검토 중인 브랜드를
              <br />
              지금 확인해보세요
            </h2>
            <p className="text-xl text-ink-muted mb-12 leading-relaxed max-w-xl break-keep">
              가맹비, 보증금, 계약해지 조건을 정보공개서 기준으로 빠르게 찾아볼 수 있습니다.
            </p>
            <div className="flex flex-col sm:flex-row items-start gap-4">
              <Link href="/chat" className="btn-hero-primary">
                질문 시작하기
                <span className="hero-cta-arrow" aria-hidden="true">→</span>
              </Link>
              <Link href="/compare" className="btn-hero-outline">
                브랜드 비교하기
              </Link>
            </div>
            <p className="text-body-sm text-ink-muted mt-8">회원가입 없이 이용할 수 있습니다</p>
          </RevealBlock>
        </div>
      </section>

      {/* 푸터 */}
      <footer className="border-t border-hairline py-12">
        <div className="max-w-[1280px] mx-auto px-6 lg:px-12 flex flex-col md:flex-row md:items-start justify-between gap-10">
          <p className="text-body-sm text-ink-muted max-w-xs break-keep">
            프차진단은 프랜차이즈 정보공개서를 바탕으로 비용, 계약 조건, 브랜드 비교 정보를
            찾아주는 AI 검색 서비스입니다.
          </p>
          <div className="flex gap-16">
            <div>
              <h3 className="text-caption font-semibold text-ink mb-4">기능</h3>
              <ul className="space-y-2">
                {[
                  { name: "채팅", href: "/chat" },
                  { name: "브랜드 비교", href: "/compare" },
                  { name: "TOP20", href: "/top20" },
                ].map((l) => (
                  <li key={l.name}>
                    <Link href={l.href} className="text-body-sm text-ink-muted hover:text-ink transition-colors">
                      {l.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-caption font-semibold text-ink mb-4">정보</h3>
              <ul className="space-y-2">
                <li>
                  <button type="button" onClick={() => scrollToId("how-it-works")} className="text-body-sm text-ink-muted hover:text-ink transition-colors">
                    이용 방법
                  </button>
                </li>
                <li>
                  <button type="button" onClick={() => scrollToId("security")} className="text-body-sm text-ink-muted hover:text-ink transition-colors">
                    신뢰성
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
