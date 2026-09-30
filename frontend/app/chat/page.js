"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ChatBubble from "../components/ChatBubble";
import SourcePanel from "../components/SourcePanel";
import {
  getConversation,
  getConversations,
  getMe,
  postChat,
} from "../../lib/api";
import { EXAMPLE_QUESTIONS } from "../../lib/exampleQuestions";

let nextId = 1;

function ChatPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedMessageId, setSelectedMessageId] = useState(null);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const scrollRef = useRef(null);
  const activeRequestRef = useRef(null);
  const lastStopAtRef = useRef(0);
  const STOP_SUBMIT_GUARD_MS = 300;

  // 비로그인 사용자는 채팅 UI 자체를 렌더링하지 않고 로그인 페이지로 보낸다
  // (백엔드 /api/chat은 이미 인증을 강제하고 있지만, 프론트에서도 진입 시점에 막아야
  // 메시지를 실제로 보내기 전까지 채팅 화면이 그대로 보이는 문제가 없다).
  useEffect(() => {
    async function checkAuth() {
      try {
        const currentUser = await getMe();
        if (!currentUser) {
          router.push("/login");
          return;
        }
        setAuthChecked(true);
      } catch (err) {
        console.error("로그인 상태를 확인하지 못했습니다:", err);
        router.push("/login");
      }
    }

    checkAuth();
  }, [router]);

  // 홈 화면 예시 질문 칩(/chat?q=...)으로 들어온 경우, 입력창에 채워만 주고 자동 전송은 하지 않는다.
  useEffect(() => {
    const q = searchParams.get("q");
    if (q) setInput(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!authChecked) return;
    refreshConversations().catch((err) => {
      console.error("Conversation 목록을 불러오지 못했습니다:", err);
    });
  }, [authChecked]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function refreshConversations() {
    const data = await getConversations();
    setConversations(data);
  }

  const selectedMessage = messages.find((m) => m.id === selectedMessageId);

  async function handleSelectConversation(conversationId) {
    if (loading) return;

    setLoading(true);

    try {
      const data = await getConversation(conversationId);

      const restoredMessages = data.messages.map((message) => ({
        id: `history-${message.id}`,
        role: message.role,
        content: message.content,
      }));

      setMessages(restoredMessages);
      setActiveConversationId(data.id);
      setSelectedMessageId(null);
    } catch (err) {
      console.error("Conversation을 불러오지 못했습니다:", err);
    } finally {
      setLoading(false);
    }
  }

  function handleNewChat() {
    if (loading) return;

    setMessages([]);
    setActiveConversationId(null);
    setSelectedMessageId(null);
    setInput("");
  }


  async function sendQuestion(question, brandMnno) {
    if (!question || loading) return;

    const userMsg = { id: nextId++, role: "user", content: question };
    const pendingId = nextId++;
    // originalQuestion을 pending 메시지에 저장해둬서, 이 답변에 달리는 브랜드 후보 버튼을
    // 클릭했을 때 원래 질문 문장에서 브랜드 부분만 치환해 재질문할 수 있게 한다(카테고리
    // 문맥이 있는 문장 전체를 다시 보내는 쪽이, 브랜드명만 단독으로 보내는 것보다 NLU가
    // 의도를 안정적으로 파악함 — 순수 브랜드명만 있는 질문은 "커버불가"로 오분류되는
    // 경우가 실측됨).
    const pendingMsg = { id: pendingId, role: "assistant", content: "", pending: true, originalQuestion: question };
    setMessages((prev) => [...prev, userMsg, pendingMsg]);
    setInput("");
    const controller = new AbortController();
    activeRequestRef.current = { controller, pendingId };

    setLoading(true);

    try {
      const data = await postChat(
        question,
        brandMnno,
        activeConversationId,
        controller.signal
      );
      if (data.conversation_id !== null && data.conversation_id !== undefined) {
        setActiveConversationId(data.conversation_id);
      }
      try {
        await refreshConversations();
      } catch (err) {
        console.error("Conversation 목록을 갱신하지 못했습니다:", err);
      }
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingId
            ? {
                ...m,
                content: data.answer,
                sources: data.sources || [],
                brandSuggestions: data.brand_suggestions || [],
                pending: false,
              }
            : m
        )
      );
      setSelectedMessageId(pendingId);
    } catch (err) {
      if (err.name === "AbortError") {
        return;
      }
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingId
            ? {
                ...m,
                content: `답변을 가져오지 못했습니다: ${err.message}. 백엔드(uvicorn)가 실행 중인지 확인해 주세요.`,
                error: true,
                pending: false,
              }
            : m
        )
      );
    } finally {
      if (activeRequestRef.current?.pendingId === pendingId) {
        setLoading(false);
        activeRequestRef.current = null;
      }
    }
  }

  function handleSubmit(e) {
    e.preventDefault();

    if (loading) return;
    if (Date.now() - lastStopAtRef.current < STOP_SUBMIT_GUARD_MS) return;

    sendQuestion(input.trim());
  }

  function handleStop() {
    const active = activeRequestRef.current;

    if (!active) return;

    active.controller.abort();

    setMessages((prev) =>
      prev.filter((message) => message.id !== active.pendingId)
    );

    setLoading(false);
    activeRequestRef.current = null;
    lastStopAtRef.current = Date.now();
  }

  function handlePickBrandSuggestion(originalQuestion, brandText, candidate) {
    // 2026-09-19(라운드3 작업지시 0번): candidate.source === "ambiguous"(동명이인 —
    // "피자스쿨"처럼 이름이 완전히 같은 서로 다른 법인)는 표시 텍스트에 구분용 법인명/
    // 개시연도 라벨이 붙어있어서("피자스쿨((주)씨에이치컴퍼니, 2012년 개시)") 기존 방식
    // (질문 문장의 브랜드 텍스트를 그 표시 텍스트로 치환해 재질문)을 쓰면 그 라벨이
    // 브랜드 별칭으로 등록돼 있지 않아 다시 매칭에 실패하거나, 라벨 없이 원래 이름
    // 그대로 재질문하면 여전히 같은 동명이인 후보가 나와 무한 반복된다 — 원래 질문
    // 문장은 그대로 두고 brandMnno를 강제 지정해서 재질문한다(scripts/rag/pipeline.py
    // forced_brand_mnno). 그 외(fuzzy 추천 등)는 기존 방식 그대로 유지.
    if (candidate.source === "ambiguous") {
      sendQuestion(originalQuestion, candidate.brandMnno);
      return;
    }
    // 원래 질문 문장에서 매칭 실패했던 브랜드 텍스트(brandText, 예: "bhc")를 후보의
    // display_name으로 치환해 다시 질문한다. 원본 문장이 없거나 brandText가 그 문장
    // 안에 그대로 없으면(안전장치) display_name 단독 질문으로 폴백한다.
    const displayName = candidate.display_name;
    if (originalQuestion && brandText && originalQuestion.includes(brandText)) {
      sendQuestion(originalQuestion.replace(brandText, displayName));
    } else {
      sendQuestion(displayName);
    }
  }
  const chatRequestActive =
    loading && activeRequestRef.current !== null;

  if (!authChecked) {
    // 비로그인 사용자에게는 "로그인 확인 중" 같은 문구조차 보이지 않고 곧장 /login으로
    // 넘어가는 것처럼 느껴져야 해서, 이 화면엔 텍스트를 전혀 두지 않는다 — 실제로 채팅
    // 화면이 뜨는(로그인된) 경우에도 이 최소 스피너를 아주 짧게 거치고 지나간다.
    return (
      <div className="mx-auto w-full max-w-[1280px] flex-1 flex items-center justify-center p-6">
        <div className="chat-auth-spinner" role="status" aria-label="불러오는 중" />
      </div>
    );
  }

  return (
    <div
      className={`mx-auto w-full max-w-[1600px] flex-1 flex flex-col md:flex-row gap-6 p-6 min-h-0 relative ${
        messages.length === 0 ? "chat-hero-page-bg" : ""
      }`}
    >
      {/* 사이드바 토글 + 대화 기록 */}
      <div
        className={`flex md:flex-col gap-2 min-h-0 ${
          messages.length === 0 ? "md:absolute md:top-6 md:left-6 md:z-20" : ""
        }`}
      >
        <div className="chat-sidebar-toggle shrink-0 self-start">
          <input
            id="chat-sidebar-toggle-checkbox"
            type="checkbox"
            checked={sidebarOpen}
            onChange={() => setSidebarOpen((v) => !v)}
            aria-label={sidebarOpen ? "대화 기록 접기" : "대화 기록 펼치기"}
          />
          <label className="toggle" htmlFor="chat-sidebar-toggle-checkbox">
            <div className="bar bar--top" />
            <div className="bar bar--middle" />
            <div className="bar bar--bottom" />
          </label>
        </div>

        <aside
          className={`flex flex-col min-h-0 overflow-hidden shrink-0 transition-[width] duration-300 ease-in-out ${
            sidebarOpen ? "w-56" : "w-0"
          }`}
        >
          <div
            className={`flex flex-col gap-3 min-h-0 w-56 transition-opacity duration-150 ${
              sidebarOpen ? "opacity-100" : "opacity-0"
            }`}
          >
            <button
              type="button"
              onClick={handleNewChat}
              className="btn-primary w-full"
              disabled={loading}
            >
              + 새 채팅
            </button>

            <div className="feature-card-elevated flex flex-col gap-2 p-3 min-h-0">
              <h2 className="text-sm font-semibold text-ink">
                대화 기록
              </h2>

              <div className="flex flex-col gap-1 overflow-y-auto">
                {conversations.length === 0 && (
                  <p className="px-2 py-3 text-sm text-ink-secondary">
                    아직 저장된 대화가 없습니다.
                  </p>
                )}

                {conversations.map((conversation) => (
                  <button
                    key={conversation.id}
                    type="button"
                    onClick={() => handleSelectConversation(conversation.id)}
                    className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                      conversation.id === activeConversationId
                        ? "border-blue-500 bg-blue-50 text-blue-700"
                        : "border-hairline bg-white text-ink hover:bg-canvas-soft hover:border-primary/40"
                    }`}
                    disabled={loading}
                    title={conversation.title}
                  >
                    <span className="block truncate">
                      {conversation.title}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </aside>
      </div>
      {messages.length === 0 ? (
        <div key="hero" className="flex flex-1 flex-col items-center justify-start pt-24 md:pt-32 gap-16 md:gap-20 min-h-0 px-4 chat-hero-appear">
          <div className="text-center chat-hero-heading">
            <span className="badge-pill">AI 정보공개서 도우미</span>
            <h2 className="text-heading-1 text-ink mt-4 mb-4">무엇이 궁금하신가요?</h2>
            <p className="text-[18px] leading-relaxed text-ink-secondary max-w-lg mx-auto">
              궁금한 브랜드의 가맹비, 보증금, 계약해지 조건, 필수구입물품 등을 자연어로
              물어보세요. 답변의 근거가 된 정보공개서 원문은 전송 후 오른쪽 패널에서 바로
              확인할 수 있습니다.
            </p>
          </div>

          <div className="flex flex-col items-center gap-8 w-full max-w-4xl">
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setInput(q)}
                  className="btn-utility chat-example-chip"
                >
                  {q}
                </button>
              ))}
            </div>

            <form onSubmit={handleSubmit} className="chat-hero-input flex items-center gap-2 w-full">
              <div className="nebula" aria-hidden="true" />
              <div className="starfield" aria-hidden="true" />
              <div className="stardust" aria-hidden="true" />
              <div className="cosmic-ring" aria-hidden="true" />
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="예: GS25 보증금 얼마야?"
                className="text-input flex-1"
              />

              <button
                type={chatRequestActive ? "button" : "submit"}
                onClick={chatRequestActive ? handleStop : undefined}
                className="btn-primary chat-send-btn"
                disabled={loading ? !chatRequestActive : !input.trim()}
              >
                <span>
                  {chatRequestActive
                    ? "중지"
                    : loading
                      ? "불러오는 중…"
                      : "전송"}
                </span>
              </button>
            </form>
          </div>
        </div>
      ) : (
        <div key="active" className="flex flex-1 flex-col md:flex-row gap-6 min-h-0 chat-active-appear">
          {/* 좌측: 대화 */}
          <section className="flex flex-col flex-1 min-h-0 md:min-w-0">
            <div ref={scrollRef} className="flex-1 overflow-y-auto flex flex-col gap-3 py-2">
              {messages.map((m) => (
                <ChatBubble
                  key={m.id}
                  message={m}
                  isSelected={m.id === selectedMessageId}
                  onSelectSources={setSelectedMessageId}
                  onPickBrandSuggestion={handlePickBrandSuggestion}
                />
              ))}
            </div>

            <form onSubmit={handleSubmit} className="chat-active-input flex items-center gap-2 pt-4 border-t border-hairline">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="예: GS25 보증금 얼마야?"
                className="text-input flex-1"
              />

              <button
                type={chatRequestActive ? "button" : "submit"}
                onClick={chatRequestActive ? handleStop : undefined}
                className="btn-primary chat-active-send-btn"
                disabled={loading ? !chatRequestActive : !input.trim()}
              >
                {chatRequestActive
                  ? "중지"
                  : loading
                    ? "불러오는 중…"
                    : "전송"}
              </button>
            </form>
          </section>

          {/* 우측: 근거 원문 패널 */}
          <section className="flex flex-col min-h-[40vh] md:min-h-0 md:w-[420px] md:shrink-0">
            <SourcePanel key={selectedMessageId ?? "none"} sources={selectedMessage?.sources} />
          </section>
        </div>
      )}

      <style jsx>{`
        .chat-send-btn:not(:disabled):hover {
          box-shadow: 0 0 16px rgba(0, 117, 222, 0.35);
          transform: scale(1.06);
        }
        .chat-send-btn:not(:disabled):active {
          transform: scale(0.96);
          box-shadow: none;
        }
        /* 채팅방(active 상태) 하단 전송 버튼 전용 — 히어로의 글로시 그라데이션과 같은
           색상 계열(primary→secondary)을 쓰되, 반짝임/글로우 애니메이션 없이 hover/active
           시 밝기만 살짝 바뀌는 톤다운 버전. 히어로 버튼(.chat-send-btn)과는 별개 클래스라
           히어로 쪽 글로우 효과에는 영향이 없다. */
        .chat-active-send-btn {
          background-image: linear-gradient(
            135deg,
            var(--color-primary) 0%,
            var(--color-secondary) 100%
          );
          transition: filter 0.15s ease-out;
        }
        .chat-active-send-btn:not(:disabled):hover {
          filter: brightness(1.1);
        }
        .chat-active-send-btn:not(:disabled):active {
          filter: brightness(0.92);
        }
        .chat-active-send-btn:disabled {
          /* globals.css의 .btn-primary:disabled(무채색 회색)가 그대로 드러나면 활성
             상태(그라데이션)와 너무 딴판으로 보여서, 기존 그라데이션 위에 옅은 회백색
             오버레이(--color-ink-faint, 반투명)를 얹어 톤은 이어지되 "비활성"임이
             드러나는 버튼으로 만든다. 텍스트/보더는 그대로 두고 배경만 옅게 한다. */
          background-image:
            linear-gradient(
              color-mix(in srgb, var(--color-ink-faint) 55%, transparent),
              color-mix(in srgb, var(--color-ink-faint) 55%, transparent)
            ),
            linear-gradient(
              135deg,
              var(--color-primary) 0%,
              var(--color-secondary) 100%
            );
        }
        .chat-example-chip {
          background-color: var(--color-canvas-soft);
          border-color: var(--color-hairline);
          color: var(--color-ink-muted);
          transition:
            transform 0.15s ease-out,
            border-color 0.15s ease-out,
            box-shadow 0.15s ease-out,
            background-color 0.15s ease-out,
            color 0.15s ease-out;
        }
        .chat-example-chip:hover {
          transform: translateY(-2px);
          background-color: var(--color-surface);
          border-color: var(--color-primary);
          color: var(--color-ink);
          box-shadow: var(--shadow-elevation-1);
        }
        .chat-example-chip:active {
          transform: scale(0.95);
        }
        .chat-hero-appear,
        .chat-active-appear {
          opacity: 0;
          animation: chat-state-fade-in 0.35s ease-out forwards;
        }
        @keyframes chat-state-fade-in {
          from {
            opacity: 0;
            transform: translateY(6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        /* 히어로 배경 — 정적인 radial-gradient(애니메이션 없음), 낮은 opacity라서
           텍스트/배지/전송 버튼 글로우와 부딪히지 않는다. */
        .chat-hero-page-bg {
          background-image: radial-gradient(
            circle at 50% 20%,
            color-mix(in srgb, var(--color-accent-sky) 14%, transparent) 0%,
            color-mix(in srgb, var(--color-secondary) 8%, transparent) 45%,
            transparent 75%
          );
        }
        .chat-auth-spinner {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          border: 3px solid var(--color-hairline);
          border-top-color: var(--color-primary);
          animation: chat-auth-spin 0.7s linear infinite;
        }
        @keyframes chat-auth-spin {
          to {
            transform: rotate(360deg);
          }
        }
        .chat-hero-heading .badge-pill {
          font-size: 13px;
        }
        .chat-hero-heading h2 {
          font-size: 44px;
        }
        .chat-hero-heading p {
          font-size: 20px;
        }
        .chat-active-input .text-input {
          border-radius: var(--radius-full);
          padding: 12px 16px;
        }
        .chat-sidebar-toggle input[type="checkbox"] {
          display: none;
        }
        .chat-sidebar-toggle .toggle {
          position: relative;
          width: 34px;
          cursor: pointer;
          margin: 0;
          display: block;
          height: calc(5px * 3 + 9px * 2);
        }
        .chat-sidebar-toggle .bar {
          position: absolute;
          left: 0;
          right: 0;
          height: 5px;
          border-radius: calc(5px / 2);
          background: var(--color-primary);
          opacity: 1;
          transition: none 0.35s cubic-bezier(0.5, -0.35, 0.35, 1.5) 0s;
        }
        .chat-sidebar-toggle .bar--top {
          bottom: calc(50% + 9px + 5px / 2);
          transition-property: bottom, transform;
          transition-delay: calc((0s + 0.35s) * 0.6);
        }
        .chat-sidebar-toggle .bar--middle {
          top: calc(50% - 5px / 2);
          transition-property: opacity, transform;
          transition-delay: calc(0s + 0.35s * 0.3);
        }
        .chat-sidebar-toggle .bar--bottom {
          top: calc(50% + 9px + 5px / 2);
          transition-property: top, transform;
          transition-delay: 0s;
        }
        .chat-sidebar-toggle input:checked + .toggle .bar--top {
          transform: rotate(-135deg);
          transition-delay: 0s;
          bottom: calc(50% - 5px / 2);
        }
        .chat-sidebar-toggle input:checked + .toggle .bar--middle {
          opacity: 0;
          transform: rotate(-135deg);
          transition-delay: calc(0s + 0.35s * 0.3);
        }
        .chat-sidebar-toggle input:checked + .toggle .bar--bottom {
          top: calc(50% - 5px / 2);
          transform: rotate(-225deg);
          transition-delay: calc(0s + 0.35s * 0.6);
        }
        .chat-hero-input {
          position: relative;
          z-index: 0;
          isolation: isolate;
        }
        .chat-hero-input .text-input {
          padding: 14px 20px;
          font-size: 17px;
          border-radius: var(--radius-full);
        }
        .chat-hero-input .chat-send-btn {
          position: relative;
          z-index: 1;
          overflow: hidden;
          padding: 0;
          font-size: 16px;
          background-image: linear-gradient(
            to bottom,
            #2b8fe6 0%,
            var(--color-primary) 50%,
            var(--color-primary-active) 100%
          );
          box-shadow:
            0 4px 14px rgba(0, 90, 200, 0.22),
            0 2px 8px rgba(0, 90, 200, 0.14),
            inset 0 1px 1px rgba(234, 244, 255, 0.5),
            inset 0 -1px 3px rgba(0, 130, 255, 0.3);
        }
        .chat-hero-input .chat-send-btn:disabled {
          background-image: none;
          box-shadow: none;
        }
        .chat-hero-input .chat-send-btn::before {
          content: "";
          position: absolute;
          left: 50%;
          top: -3px;
          transform: translateX(-50%);
          width: 60px;
          height: 6px;
          background-color: #eaf4ff;
          opacity: 0.6;
          filter: blur(6px);
          pointer-events: none;
        }
        .chat-hero-input .chat-send-btn span {
          display: block;
          position: relative;
          padding: 14px 28px;
          background-image: linear-gradient(to bottom, #eaf4ff, transparent 8px);
          background-position: 0 -6px;
          background-repeat: no-repeat;
        }
        .chat-hero-input .chat-send-btn span::before,
        .chat-hero-input .chat-send-btn span::after {
          content: "";
          position: absolute;
          left: 50%;
          transform: translateX(-50%);
          border-radius: 50%;
          background-color: #bfe3ff;
          transition:
            opacity 0.25s,
            transform 0.25s;
          pointer-events: none;
        }
        .chat-hero-input .chat-send-btn span::before {
          width: 56px;
          height: 8px;
          bottom: -4px;
          opacity: 0.7;
          filter: blur(6px);
        }
        .chat-hero-input .chat-send-btn span::after {
          width: 68px;
          height: 1px;
          bottom: 0;
          opacity: 0.85;
          filter: blur(1px);
        }
        .chat-hero-input .chat-send-btn:not(:disabled):hover span::before {
          opacity: 0.85;
          transform: translateX(-50%) scale(1.25);
        }
        .chat-hero-input .chat-send-btn:not(:disabled):hover span::after {
          opacity: 1;
        }
        .chat-hero-input .nebula,
        .chat-hero-input .starfield,
        .chat-hero-input .stardust,
        .chat-hero-input .cosmic-ring {
          position: absolute;
          z-index: -1;
          overflow: hidden;
          pointer-events: none;
          border-radius: var(--radius-full);
        }
        .chat-hero-input .nebula {
          inset: -20px;
          filter: blur(24px);
          opacity: 0.35;
        }
        .chat-hero-input .starfield {
          inset: -10px;
          filter: blur(2px);
        }
        .chat-hero-input .stardust {
          inset: -5px;
          filter: blur(1.5px);
        }
        .chat-hero-input .cosmic-ring {
          inset: -2px;
          filter: blur(0.5px);
        }
        .chat-hero-input .nebula::before,
        .chat-hero-input .starfield::before,
        .chat-hero-input .stardust::before,
        .chat-hero-input .cosmic-ring::before {
          content: "";
          position: absolute;
          top: 50%;
          left: 50%;
          width: 600px;
          height: 600px;
          background-repeat: no-repeat;
          background-position: 0 0;
          animation-timing-function: linear;
          animation-iteration-count: infinite;
        }
        .chat-hero-input .nebula::before {
          background-image: conic-gradient(
            transparent,
            var(--color-primary) 5%,
            transparent 38%,
            transparent 50%,
            var(--color-primary-active) 60%,
            transparent 87%
          );
          animation-name: chat-hero-ring-spin-nebula;
          animation-duration: 14s;
        }
        .chat-hero-input .starfield::before {
          background-image: conic-gradient(
            transparent,
            var(--color-primary-active) 8%,
            transparent 16%,
            transparent 50%,
            var(--color-primary) 58%,
            transparent 66%
          );
          animation-name: chat-hero-ring-spin-starfield;
          animation-duration: 10s;
        }
        .chat-hero-input .stardust::before {
          filter: brightness(1.4);
          background-image: conic-gradient(
            transparent,
            var(--color-primary) 8%,
            transparent 16%,
            transparent 50%,
            var(--color-primary-active) 58%,
            transparent 66%
          );
          animation-name: chat-hero-ring-spin-stardust;
          animation-duration: 8s;
        }
        .chat-hero-input .cosmic-ring::before {
          filter: brightness(1.2);
          background-image: conic-gradient(
            var(--color-surface),
            var(--color-primary) 5%,
            var(--color-surface) 14%,
            var(--color-surface) 50%,
            var(--color-primary-active) 60%,
            var(--color-surface) 64%
          );
          animation-name: chat-hero-ring-spin-cosmic-ring;
          animation-duration: 6s;
        }
        @keyframes chat-hero-ring-spin-nebula {
          from {
            transform: translate(-50%, -50%) rotate(60deg);
          }
          to {
            transform: translate(-50%, -50%) rotate(420deg);
          }
        }
        @keyframes chat-hero-ring-spin-starfield {
          from {
            transform: translate(-50%, -50%) rotate(82deg);
          }
          to {
            transform: translate(-50%, -50%) rotate(442deg);
          }
        }
        @keyframes chat-hero-ring-spin-stardust {
          from {
            transform: translate(-50%, -50%) rotate(83deg);
          }
          to {
            transform: translate(-50%, -50%) rotate(443deg);
          }
        }
        @keyframes chat-hero-ring-spin-cosmic-ring {
          from {
            transform: translate(-50%, -50%) rotate(70deg);
          }
          to {
            transform: translate(-50%, -50%) rotate(430deg);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .chat-send-btn:not(:disabled):hover,
          .chat-send-btn:not(:disabled):active,
          .chat-example-chip:hover,
          .chat-example-chip:active {
            transform: none;
          }
          .chat-hero-appear,
          .chat-active-appear {
            animation: none;
            opacity: 1;
          }
          .chat-hero-input .nebula::before,
          .chat-hero-input .starfield::before,
          .chat-hero-input .stardust::before,
          .chat-hero-input .cosmic-ring::before {
            animation: none;
          }
          .chat-hero-input .chat-send-btn:not(:disabled):hover span::before,
          .chat-hero-input .chat-send-btn:not(:disabled):hover span::after {
            transition: none;
          }
          .chat-auth-spinner {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatPageInner />
    </Suspense>
  );
}
