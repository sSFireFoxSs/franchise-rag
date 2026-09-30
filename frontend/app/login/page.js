"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, login, signup } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");

  const [checkingSession, setCheckingSession] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function restoreSession() {
      try {
        const currentUser = await getMe();
        if (currentUser) {
          // 이미 로그인된 사용자는 확인 화면 없이 바로 홈으로 보낸다 — checkingSession을
          // false로 바꾸지 않아서, 라우팅이 끝날 때까지 로그인 폼이 잠깐 보이지 않는다.
          router.push("/");
          return;
        }
      } catch (err) {
        setError(err.message);
      }

      setCheckingSession(false);
    }

    restoreSession();
  }, [router]);

  function resetForm() {
    setEmail("");
    setPassword("");
    setPasswordConfirm("");
    setError("");
  }

  function changeMode(nextMode) {
    setMode(nextMode);
    resetForm();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    const normalizedEmail = email.trim();

    if (!normalizedEmail || !password) {
      setError("이메일과 비밀번호를 입력해주세요.");
      return;
    }

    if (mode === "signup") {
      if (!passwordConfirm) {
        setError("비밀번호 확인을 입력해주세요.");
        return;
      }

      if (password !== passwordConfirm) {
        setError("비밀번호가 일치하지 않습니다.");
        return;
      }
    }

    setSubmitting(true);

    try {
      if (mode === "signup") {
        await signup(normalizedEmail, password, passwordConfirm);
      } else {
        await login(normalizedEmail, password);
      }

      await getMe();
      window.dispatchEvent(new Event("auth-changed"));
      resetForm();
      router.push("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (checkingSession) {
    return (
      <div className="login-page flex-1 flex items-center justify-center p-6">
        <div className="feature-card-elevated w-full max-w-md text-center">
          <p className="text-body-md text-ink-secondary">
            로그인 상태를 확인하고 있습니다.
          </p>
        </div>
        <style jsx>{`
          .login-page {
            background-image: radial-gradient(
              circle at 50% 20%,
              color-mix(in srgb, var(--color-accent-sky) 14%, transparent) 0%,
              color-mix(in srgb, var(--color-secondary) 8%, transparent) 45%,
              transparent 75%
            );
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="login-page flex-1 flex items-center justify-center p-6">
      <div className="login-card login-card-appear w-full flex flex-col gap-6">
        <h1 className="login-card-title">
          {mode === "login"
            ? "다시 오신 것을 환영합니다"
            : "계정을 만들어볼까요?"}
        </h1>

        <div className="flex flex-col gap-3">
          <button type="button" className="login-social-btn login-social-btn--facebook">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M22 12c0-5.523-4.477-10-10-10S2 6.477 2 12c0 4.991 3.657 9.128 8.438 9.878v-6.987h-2.54V12h2.54V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.89h-2.33v6.988C18.343 21.128 22 16.991 22 12z" />
            </svg>
            <span>Facebook으로 로그인</span>
          </button>

          <button type="button" className="login-social-btn login-social-btn--apple">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M16.365 1.43c0 1.14-.415 2.15-1.246 3.03-1.03 1.1-2.27 1.73-3.61 1.62-.14-1.13.42-2.31 1.24-3.11.86-.85 2.32-1.48 3.5-1.54.03.34.116.67.116 1zM20.75 17.36c-.5 1.15-.74 1.66-1.38 2.68-.9 1.44-2.16 3.23-3.73 3.24-1.4.02-1.76-.92-3.66-.91-1.9.01-2.3.93-3.7.92-1.57-.02-2.77-1.63-3.67-3.07-2.52-4.02-2.78-8.74-1.23-11.25.95-1.53 2.5-2.5 4.25-2.5 1.68 0 2.74.93 4.14.93 1.36 0 2.18-.93 4.14-.93 1.4 0 2.88.74 3.94 2.02-1.44.86-2.36 2.25-2.36 3.86 0 1.83 1.06 3.33 2.24 3.86-.42 1.22-.63 1.7-.99 2.15z" />
            </svg>
            <span>Apple로 로그인</span>
          </button>
        </div>

        <div className="login-divider" />

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <label htmlFor="email" className="login-label">
              이메일
            </label>

            <input
              id="email"
              type="email"
              className="login-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              disabled={submitting}
              placeholder="이메일을 입력해주세요"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="password" className="login-label">
              비밀번호
            </label>

            <input
              id="password"
              type="password"
              className="login-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              disabled={submitting}
              placeholder="비밀번호를 입력해주세요"
            />
          </div>

          {mode === "signup" && (
            <div className="flex flex-col gap-2">
              <label htmlFor="password-confirm" className="login-label">
                비밀번호 확인
              </label>

              <input
                id="password-confirm"
                type="password"
                className="login-input"
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                autoComplete="new-password"
                disabled={submitting}
                placeholder="비밀번호를 다시 입력해주세요"
              />
            </div>
          )}

          {error && <p className="login-error">{error}</p>}

          <button
            type="submit"
            className="login-submit-btn"
            disabled={submitting}
          >
            {submitting
              ? "처리 중..."
              : mode === "login"
                ? "로그인"
                : "회원가입"}
          </button>
        </form>

        {mode === "login" && (
          <a
            href="#"
            className="login-forgot-link"
            onClick={(e) => e.preventDefault()}
          >
            비밀번호를 잊으셨나요?
          </a>
        )}

        <p className="login-switch-text">
          {mode === "login" ? (
            <>
              계정이 없으신가요?{" "}
              <a
                href="#"
                className="login-link"
                onClick={(e) => {
                  e.preventDefault();
                  changeMode("signup");
                }}
              >
                회원가입하기
              </a>
            </>
          ) : (
            <>
              이미 계정이 있으신가요?{" "}
              <a
                href="#"
                className="login-link"
                onClick={(e) => {
                  e.preventDefault();
                  changeMode("login");
                }}
              >
                로그인하기
              </a>
            </>
          )}
        </p>
      </div>

      <style jsx>{`
        .login-page {
          background-image: radial-gradient(
            circle at 50% 20%,
            color-mix(in srgb, var(--color-accent-sky) 14%, transparent) 0%,
            color-mix(in srgb, var(--color-secondary) 8%, transparent) 45%,
            transparent 75%
          );
        }
        .login-card {
          max-width: 400px;
          background-color: var(--color-surface);
          padding: 32px 24px;
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-elevation-2);
        }
        .login-card-appear {
          opacity: 0;
          animation: login-card-rise 0.45s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes login-card-rise {
          from {
            opacity: 0;
            transform: translateY(18px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .login-card-appear {
            animation: none;
            opacity: 1;
          }
        }
        .login-card-title {
          text-align: center;
          font: var(--text-heading-3) / var(--text-heading-3--line-height) var(--font-sans);
          font-weight: var(--text-heading-3--font-weight);
          color: var(--color-ink);
        }
        .login-social-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          width: 100%;
          padding: 12px 16px;
          border: none;
          border-radius: var(--radius-md);
          color: var(--color-on-primary);
          font: var(--text-button) / var(--text-button--line-height) var(--font-sans);
          font-weight: var(--text-button--font-weight);
          cursor: pointer;
          box-shadow: var(--shadow-elevation-1);
          transition: filter 0.15s ease;
        }
        .login-social-btn:hover {
          filter: brightness(1.08);
        }
        .login-social-btn--facebook {
          background-color: var(--color-primary);
        }
        .login-social-btn--apple {
          background-color: var(--color-ink);
        }
        .login-divider {
          width: 100%;
          height: 1px;
          background-color: var(--color-hairline);
        }
        .login-label {
          font: var(--text-caption) / var(--text-caption--line-height) var(--font-sans);
          color: var(--color-ink-muted);
        }
        .login-input {
          width: 100%;
          padding: 12px 16px;
          border-radius: var(--radius-md);
          border: 1px solid var(--color-hairline);
          background-color: var(--color-surface);
          color: var(--color-ink);
          font: var(--text-body-sm) / var(--text-body-sm--line-height) var(--font-sans);
        }
        .login-input:focus {
          outline: none;
          border-color: var(--color-primary);
          box-shadow: var(--shadow-elevation-1);
        }
        .login-error {
          color: var(--color-accent-orange-deep);
          font: var(--text-body-sm) / var(--text-body-sm--line-height) var(--font-sans);
        }
        .login-submit-btn {
          width: 100%;
          padding: 12px 16px;
          color: var(--color-on-primary);
          background-color: var(--color-ink);
          border: none;
          border-radius: var(--radius-md);
          font: var(--text-button) / var(--text-button--line-height) var(--font-sans);
          font-weight: var(--text-button--font-weight);
          cursor: pointer;
          box-shadow: var(--shadow-elevation-1);
          transition: background-color 0.15s ease;
        }
        .login-submit-btn:hover:not(:disabled) {
          background-color: var(--color-ink-secondary);
        }
        .login-submit-btn:disabled {
          cursor: not-allowed;
          opacity: 0.6;
        }
        .login-forgot-link {
          align-self: flex-end;
          margin-top: -8px;
          color: var(--color-primary);
          font: var(--text-caption) / var(--text-caption--line-height) var(--font-sans);
          text-decoration: none;
        }
        .login-forgot-link:hover {
          text-decoration: underline;
        }
        .login-switch-text {
          text-align: center;
          color: var(--color-ink-secondary);
          font: var(--text-body-sm) / var(--text-body-sm--line-height) var(--font-sans);
        }
        .login-link {
          color: var(--color-primary);
          font-weight: 600;
          text-decoration: none;
          cursor: pointer;
        }
        .login-link:hover {
          text-decoration: underline;
        }
      `}</style>
    </div>
  );
}
