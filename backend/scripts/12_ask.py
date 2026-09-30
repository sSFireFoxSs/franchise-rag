"""RAG 1차 구현 — CLI 빠른 테스트용.

scripts/rag/pipeline.py의 answer_question()을 터미널에서 바로 불러본다. Streamlit 없이도
파이프라인이 잘 동작하는지 확인하는 용도(app.py 통합 전 최소 동작 확인).

사용법:
  python scripts/12_ask.py "GS25 보증금 총액이 얼마야?"
  python scripts/12_ask.py   # 인자 없이 실행하면 대화형 모드
"""
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    # Windows 콘솔 기본 코드페이지(cp949)로는 em dash(—)나 화살표 같은 문자가 깨져서
    # print()가 UnicodeEncodeError로 죽는 경우가 있어 강제로 utf-8로 바꾼다.
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag.pipeline import answer_question  # noqa: E402


def ask(question: str):
    print(f"\n질문: {question}")
    result = answer_question(question)
    print(f"[intent={result['intent']} category={result['category']} "
          f"canonical_title={result['canonical_title']}]")
    print(f"브랜드 매칭: {result['brands_resolved']} (미매칭: {result['brands_unresolved']})")
    print("-" * 60)
    print(result["answer"])
    print("-" * 60)
    print(f"출처 {len(result['citations'])}건:")
    for c in result["citations"][:10]:
        print(f"  - [{c['brandNm']}-{c['category']}-{c['canonical_title']}] "
              f"(brandMnno={c['brandMnno']}, attr={c['attr']})")
    print()


def main():
    if len(sys.argv) > 1:
        ask(" ".join(sys.argv[1:]))
        return
    print("대화형 모드 (빈 줄 입력하면 종료)")
    while True:
        try:
            q = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        ask(q)


if __name__ == "__main__":
    main()
