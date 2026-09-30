"""scripts/rag/total_cost.py("총창업비용" 합성 카테고리)가 이중계산 없이 정확한지
확인하는 회귀 테스트(작업로그 (41) 참고).

2026-09-17에 실제로 있었던 버그를 재발 방지하기 위한 테스트다: "예치가맹금의 범위와
그 금액"은 최초 가맹금과 별도로 추가되는 금액이 아니라 최초 가맹금(가입비+교육비)에
보증금 성격의 금액을 더해 다시 계산한 값인데, 처음 구현에서는 이걸 모르고 최초 가맹금 +
그 밖의 비용 + 예치가맹금을 전부 더해서 가입비/교육비를 두 번 세는 이중계산 버그가 있었음
(백청우칼국수 실측: 최초가맹금 16,500,000원 + 예치가맹금 21,500,000원을 그대로 더하면
38,000,000원이 나왔는데, 실제로는 예치가맹금 21,500,000원 자체가 이미 최초가맹금+보증금
5,000,000원을 합친 값이라 정답은 21,500,000원이어야 함).

실제 clauses.jsonl(.gz) 데이터를 그대로 읽어서 검증한다(LLM/네트워크 불필요, 수 초 내 완료
— total_cost.py는애초에 LLM을 안 씀). 데이터가 갱신되면(03_extract_clauses.py 재실행 등)
이 테스트가 쓰는 brandMnno의 금액이 바뀔 수 있으니, 실패하면 먼저 그 브랜드 원문이 실제로
바뀌었는지부터 확인할 것.

사용법:
  python scripts/15_test_total_cost.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.rag import total_cost  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def main():
    # --- 1) 백청우칼국수(BRD_20090100226): 사용자가 직접 지정한 검증 케이스.
    #        예치가맹금 합계 21,500,000원, 그 밖의 비용 없음(0원) -> 총창업비용은
    #        21,500,000원이어야 함. 최초 가맹금(16,500,000원)까지 따로 더해서
    #        38,000,000원이 나오면 이중계산 버그가 남아있는 것. ---
    r = total_cost.compute_total_startup_cost("BRD_20090100226")
    check(
        "백청우칼국수 mode=single",
        r.get("mode") == "single",
        str(r),
    )
    check(
        "백청우칼국수 총창업비용 = 21,500,000원 (38,000,000원이면 이중계산 버그)",
        r.get("total_won") == 21_500_000,
        f"실제: {r.get('total_won')}",
    )
    labels = [b["label"] for b in r.get("breakdown", [])]
    check(
        "백청우칼국수 breakdown에 '최초 가맹금'이 안 보임(예치가맹금에 이미 포함돼서 표시 안 함)",
        "최초 가맹금" not in labels,
        str(labels),
    )
    check(
        "백청우칼국수 breakdown에 '예치가맹금의 범위와 그 금액'만 있음",
        labels == ["예치가맹금의 범위와 그 금액"],
        str(labels),
    )

    # --- 2) 비비큐(BRD_20161241): 매장 타입 6개, 예치가맹금 있음(multi 모드).
    #        components에 '최초 가맹금'이 없어야 하고(이중계산 방지), 예치가맹금 BSK
    #        타입 금액이 실측값(14,180,000원)과 정확히 일치해야 함. ---
    r = total_cost.compute_total_startup_cost("BRD_20161241")
    check("비비큐 mode=multi", r.get("mode") == "multi", str(r.get("mode")))
    components = r.get("components", {})
    check(
        "비비큐 components에 '최초 가맹금'이 없음(예치가맹금에 이미 포함돼서 안 보여줌)",
        "최초 가맹금" not in components,
        str(list(components.keys())),
    )
    check(
        "비비큐 components에 '예치가맹금의 범위와 그 금액'/'그 밖에 지급하여야 하는 비용'이 있음",
        set(components.keys()) == {"예치가맹금의 범위와 그 금액", "그 밖에 지급하여야 하는 비용"},
        str(list(components.keys())),
    )
    bsk_deposit = [
        it for it in components.get("예치가맹금의 범위와 그 금액", [])
        if "BSK" in it["column"]
    ]
    check(
        "비비큐 예치가맹금 BSK 타입 금액 = 14,180,000원(가입비 5.5M+교육비 4.18M+계약이행보증금 5M)",
        bool(bsk_deposit) and bsk_deposit[0]["amount_won"] == 14_180_000,
        str(bsk_deposit),
    )

    # --- 3) 타요키즈카페(BRD_20130112): 예치가맹금 데이터 자체가 없는 브랜드 ->
    #        최초 가맹금 + 별도 보증금 카테고리를 더해야 함(이 경로는 이중계산 버그와
    #        무관하므로 회귀 없이 그대로 유지되는지 확인). ---
    r = total_cost.compute_total_startup_cost("BRD_20130112")
    check(
        "타요키즈카페(예치가맹금 없음) mode=single, 총액=39,000,000원(최초가맹금 36M+보증금 3M)",
        r.get("mode") == "single" and r.get("total_won") == 39_000_000,
        str(r),
    )
    labels = [b["label"] for b in r.get("breakdown", [])]
    check(
        "타요키즈카페 breakdown에 '최초 가맹금'과 '보증금'이 있음(예치가맹금이 없을 때만 쓰는 경로)",
        labels == ["최초 가맹금", "보증금"],
        str(labels),
    )

    # --- 4) 빽다방(BRD_20090100502): 최초 가맹금/예치가맹금 둘 다 라벨이 TOTAL_LABELS와
    #        완전일치하지 않는 브랜드(예: "가맹비등 합계", "총 합계") -> 억지로 계산하지
    #        않고 unavailable로 정직하게 안내해야 함. ---
    r = total_cost.compute_total_startup_cost("BRD_20090100502")
    check(
        "빽다방(완전일치 합계 라벨 없음) mode=unavailable",
        r.get("mode") == "unavailable",
        str(r),
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)}개 실패: {FAILURES}")
        sys.exit(1)
    print("전부 통과.")


if __name__ == "__main__":
    main()
