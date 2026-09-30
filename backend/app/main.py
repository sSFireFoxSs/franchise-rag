"""FastAPI 백엔드 — RAG 파이프라인(backend/scripts/rag/)을
감싸서 HTTP API로 노출한다.

RAG 로직 자체(질문 이해 -> 브랜드 매칭 -> 조회 -> 답변 조립)는 여기서 한 줄도 다시 구현하지
않는다 — pipeline.answer_question() 하나만 호출하고, 그 결과를 프론트엔드가 쓰기 좋은
JSON으로 다듬기만 한다(출처 citation에 원문 텍스트 조각을 붙이는 것 정도).
"""
import sys
from pathlib import Path
from typing import Any

from fastapi import Cookie, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth import router as auth_router
from app.conversation import (
    build_conversation_context,
    create_conversation_with_user_message,
    router as conversation_router,
    save_message,
)
from app.session import get_session_user_id

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))

from rag import data as rag_data  # noqa: E402
from rag.pipeline import answer_question  # noqa: E402

from app.routers import compare, home, top20  # noqa: E402

app = FastAPI(title="franchise-web API")

# 교차 출처 리소스 공유 설정(CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(conversation_router)

# 지침사항.txt "백엔드 API 만드는 규칙" — 새 API는 backend/app/routers/에 만들고
# main.py에는 등록 한 줄만 추가한다(여러 명이 main.py 한 파일에 동시에 손대면서 생기는
# 병합 충돌을 막기 위함). /health, /api/chat 외의 엔드포인트는 여기 두지 않는다.
app.include_router(top20.router)
app.include_router(compare.router)
app.include_router(home.router)

class ChatRequest(BaseModel):
    question: str
    # 2026-09-19(라운드3 작업지시 0번): 동명이인(ambiguous) 브랜드 추천 버튼 클릭 전용 —
    # scripts/rag/pipeline.py의 answer_question() forced_brand_mnno 주석 참고.
    brand_mnno: "str | None" = None
    conversation_id: "int | None" = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _enrich_source(citation: dict) -> dict:
    """citation(브랜드/카테고리/조항/attr/jngIfrmpSn 포인터)에 실제 원문 조각을 붙인다.
    data.find_row()는 rag 패키지에 이미 있는 함수를 그대로 쓴다(새로 만들지 않음) — 이
    함수가 반환하는 row에서 text/amounts/tables 중 있는 것만 프론트에 넘긴다."""
    row = rag_data.find_row(
        citation.get("brandMnno"), citation.get("attr"), citation.get("jngIfrmpSn")
    )
    source: dict[str, Any] = dict(citation)
    if row is None:
        return source
    text = row.get("text") or ""
    source["text"] = text[:800]
    if row.get("amounts"):
        source["amounts"] = row["amounts"]
    if row.get("tables"):
        source["tables"] = row["tables"]
    if row.get("violation_flag") is not None:
        source["violation_flag"] = row["violation_flag"]
    return source


@app.post("/api/chat")
def chat(
    req: ChatRequest,
    session_token: str | None = Cookie(
        default=None,
        alias="session_token",
    ),
) -> dict:
    if session_token is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
        )

    current_user_id = get_session_user_id(session_token)

    if current_user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
        )

    question = req.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Message content is required.",
        )

    if req.conversation_id is None:
        (
            conversation_id,
            current_message_id,
            _,
        ) = create_conversation_with_user_message(
            current_user_id,
            question,
        )
    else:
        conversation_id = req.conversation_id

        try:
            current_message_id = save_message(
                current_user_id,
                conversation_id,
                "user",
                question,
            )
        except ValueError as exc:
            if str(exc) == "Conversation not found.":
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found.",
                ) from exc

            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

    conversation_context = build_conversation_context(
        current_user_id,
        conversation_id,
        current_message_id,
    )

    result = answer_question(
        question,
        forced_brand_mnno=req.brand_mnno,
        conversation_context=conversation_context,
    )

    assistant_answer = result.get("answer", "")

    save_message(
        current_user_id,
        conversation_id,
        "assistant",
        assistant_answer,
    )

    citations = result.get("citations") or []

    return {
        "answer": assistant_answer,
        "citations": citations,
        "sources": [_enrich_source(c) for c in citations],
        "intent": result.get("intent"),
        "category": result.get("category"),
        "canonical_title": result.get("canonical_title"),
        "use_structured": result.get("use_structured", False),
        "use_total_cost": result.get("use_total_cost", False),
        "brands_resolved": result.get("brands_resolved") or [],
        "brands_unresolved": result.get("brands_unresolved") or [],
        "brand_suggestions": result.get("brand_suggestions") or [],
        "conversation_id": conversation_id,
    }
