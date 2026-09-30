"""RAG 1차 구현 — 골드셋(40문항) 평가 러너.

data/qa/rag_gold_40.json을 순서대로 scripts/rag/pipeline.answer_question()에 태워서
결과를 logs/13_eval_gold_result.jsonl(원시 결과 전체)과 logs/13_eval_gold_report.md
(사람이 읽을 요약)로 남긴다.

expect_contains는 "이 문자열이 답변에 들어있어야 한다"는 아주 단순한 휴리스틱이라
구조화 카테고리(숫자 그대로 나옴)에는 잘 맞지만, 서술형 카테고리는 LLM이 표현을 바꿀 수
있어서 이 스크립트의 PASS/FAIL만으로 품질을 확정하지 말고 answer 원문을 같이 읽을 것.

사용법:
  python scripts/13_eval_gold.py                 # 전체 40문항
  python scripts/13_eval_gold.py --only 1 2 3     # 특정 번호만 (재검증용)
"""
import argparse
import json
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag.pipeline import answer_question  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = PROJECT_ROOT / "data" / "qa" / "rag_gold_40.json"
RESULT_JSONL = PROJECT_ROOT / "logs" / "13_eval_gold_result.jsonl"
REPORT_MD = PROJECT_ROOT / "logs" / "13_eval_gold_report.md"


def run_one(item: dict) -> dict:
    t0 = time.time()
    try:
        result = answer_question(item["question"])
        error = None
    except Exception as e:  # 평가 도중 하나가 죽어도 전체가 안 멈추게
        result = {"answer": f"(예외 발생: {e})", "citations": [], "intent": None,
                   "category": None, "canonical_title": None,
                   "brands_resolved": [], "brands_unresolved": []}
        error = str(e)
    elapsed = time.time() - t0

    expect = item.get("expect_contains") or []
    answer_text = result.get("answer", "")
    hits = [e for e in expect if e in answer_text]
    misses = [e for e in expect if e not in answer_text]
    if not expect:
        verdict = "N/A(수동확인)"
    elif not misses:
        verdict = "PASS"
    elif hits:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    return {
        "no": item["no"], "group": item["group"], "question": item["question"],
        "note": item.get("note", ""), "expect_contains": expect,
        "verdict": verdict, "hits": hits, "misses": misses,
        "elapsed_sec": round(elapsed, 1), "error": error,
        **result,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, nargs="*", default=None, help="이 no 번호만 실행")
    args = ap.parse_args()

    items = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    if args.only:
        items = [i for i in items if i["no"] in args.only]

    results = []
    RESULT_JSONL.parent.mkdir(exist_ok=True)
    with open(RESULT_JSONL, "w", encoding="utf-8") as f:
        for item in items:
            print(f"[{item['no']:>2}/{len(items)}] {item['question']} ...", end=" ", flush=True)
            r = run_one(item)
            print(f"{r['verdict']} ({r['elapsed_sec']}s)")
            results.append(r)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 요약 리포트
    by_verdict = {}
    for r in results:
        by_verdict.setdefault(r["verdict"], []).append(r)

    lines = ["# RAG 골드셋(40문항) 평가 결과", ""]
    lines.append(f"- 실행 문항: {len(results)}개")
    for v in ["PASS", "PARTIAL", "FAIL", "N/A(수동확인)"]:
        lines.append(f"- {v}: {len(by_verdict.get(v, []))}건")
    lines.append("")

    # 카테고리(group)별 커버리지 — 어떤 그룹에서 실패/미매칭이 몰려있는지 한눈에
    lines.append("## 그룹별 결과")
    lines.append("")
    lines.append("| No | 그룹 | 질문 | intent | category | 브랜드매칭 | 판정 | 소요(s) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        resolved = ",".join(r.get("brands_resolved") or []) or "-"
        unresolved = r.get("brands_unresolved") or []
        brand_col = resolved + (f" (미매칭:{','.join(unresolved)})" if unresolved else "")
        q = r["question"].replace("|", "\\|")
        lines.append(
            f"| {r['no']} | {r['group']} | {q} | {r.get('intent')} | {r.get('category')} | "
            f"{brand_col} | {r['verdict']} | {r['elapsed_sec']} |"
        )
    lines.append("")

    lines.append("## 상세 (질문/답변/출처)")
    for r in results:
        lines.append(f"\n### {r['no']}. [{r['verdict']}] {r['question']}")
        lines.append(f"- group: {r['group']} / note: {r['note']}")
        lines.append(f"- intent={r.get('intent')} category={r.get('category')} canonical_title={r.get('canonical_title')}")
        if r.get("error"):
            lines.append(f"- ⚠️ 예외: {r['error']}")
        lines.append(f"- 답변:\n\n  > {r['answer'][:1500].replace(chr(10), chr(10)+'  > ')}")
        cites = r.get("citations") or []
        if cites:
            tags = "; ".join(f"[{c.get('brandNm')}-{c.get('category')}-{c.get('canonical_title')}]" for c in cites[:8])
            lines.append(f"- 출처({len(cites)}건): {tags}")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n리포트: {REPORT_MD}")
    print(f"원시 결과: {RESULT_JSONL}")


if __name__ == "__main__":
    main()
