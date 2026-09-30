import { Inter } from "next/font/google";
import "./globals.css";
import NavBar from "./components/NavBar";

// DESIGN-notion.md: 전체 시스템 폰트는 NotionInter(비공개 폰트) — 문서에 명시된 대로
// Inter를 그대로 대체 폰트로 씀.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata = {
  title: "프차진단 | 프랜차이즈 정보공개서 비교",
  description: "정보공개서 조항을 자연어로 검색하고 브랜드를 비교하는 서비스",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko" className={`${inter.variable} h-dvh antialiased`}>
      <head>
        {/* 한글 최적화 폰트(Pretendard) — Inter는 라틴 문자만 지원해서 한글은 지금까지
            OS 기본 폰트로 렌더링되고 있었음. globals.css의 --font-sans 체인에서
            Inter 다음 폴백으로 사용. */}
        <link
          rel="stylesheet"
          as="style"
          crossOrigin="anonymous"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@latest/dist/web/static/pretendard.css"
        />
      </head>
      {/* body에 실제 뷰포트 높이(h-full → 위 html의 h-dvh를 상속)를 줘야, 채팅 페이지의
          메시지 영역이 내부에서만 스크롤되고 페이지 전체가 늘어나지 않는다. */}
      <body className="h-full flex flex-col bg-canvas-soft text-ink">
        <NavBar />
        <main className="flex-1 flex flex-col min-h-0">{children}</main>
      </body>
    </html>
  );
}
