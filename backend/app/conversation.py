from datetime import datetime

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from app.db import get_db_connection
from app.session import get_session_user_id


TITLE_MAX_LENGTH = 50
ALLOWED_ROLES = {"user", "assistant"}


router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
)


class ConversationSummaryResponse(BaseModel):
    id: int
    title: str
    updated_at: datetime


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ConversationHistoryResponse(BaseModel):
    id: int
    title: str
    messages: list[MessageResponse]


def make_conversation_title(first_question: str) -> str:
    normalized = " ".join(first_question.split())

    if not normalized:
        raise ValueError("Message content is required.")

    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized

    return normalized[: TITLE_MAX_LENGTH - 3] + "..."


def create_conversation_with_user_message(
    user_id: int,
    content: str,
) -> tuple[int, int, str]:
    message_content = content.strip()

    if not message_content:
        raise ValueError("Message content is required.")

    title = make_conversation_title(message_content)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (user_id, title)
                VALUES (%s, %s)
                RETURNING id
                """,
                (user_id, title),
            )
            conversation_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (%s, 'user', %s)
                RETURNING id
                """,
                (conversation_id, message_content),
            )
            message_id = cur.fetchone()[0]

    return conversation_id, message_id, title


def save_message(
    user_id: int,
    conversation_id: int,
    role: str,
    content: str,
) -> int:
    message_content = content.strip()

    if role not in ALLOWED_ROLES:
        raise ValueError("Invalid message role.")

    if not message_content:
        raise ValueError("Message content is required.")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                SELECT id, %s, %s
                FROM conversations
                WHERE id = %s
                  AND user_id = %s
                RETURNING id
                """,
                (
                    role,
                    message_content,
                    conversation_id,
                    user_id,
                ),
            )
            row = cur.fetchone()

            if row is None:
                raise ValueError("Conversation not found.")

            message_id = row[0]

            cur.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND user_id = %s
                """,
                (conversation_id, user_id),
            )

    return message_id
def list_conversations(user_id: int) -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, updated_at
                FROM conversations
                WHERE user_id = %s
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "updated_at": row[2],
        }
        for row in rows
    ]


def get_conversation_history(
    user_id: int,
    conversation_id: int,
) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title
                FROM conversations
                WHERE id = %s
                  AND user_id = %s
                """,
                (conversation_id, user_id),
            )
            conversation = cur.fetchone()

            if conversation is None:
                raise ValueError("Conversation not found.")

            cur.execute(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id,),
            )
            message_rows = cur.fetchall()

    return {
        "id": conversation[0],
        "title": conversation[1],
        "messages": [
            {
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "created_at": row[3],
            }
            for row in message_rows
        ],
    }


def build_conversation_context(
    user_id: int,
    conversation_id: int,
    current_message_id: int,
) -> list[dict[str, str]]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.id,
                    m.role,
                    m.content,
                    m.created_at
                FROM messages AS m
                JOIN conversations AS c
                  ON c.id = m.conversation_id
                WHERE m.id = %s
                  AND m.conversation_id = %s
                  AND c.user_id = %s
                """,
                (
                    current_message_id,
                    conversation_id,
                    user_id,
                ),
            )
            current_message = cur.fetchone()

            if current_message is None:
                raise ValueError("Current user message not found.")

            if current_message[1] != "user":
                raise ValueError("Current message must be a user message.")

            current_content = current_message[2]
            current_created_at = current_message[3]

            cur.execute(
                """
                SELECT role, content
                FROM messages
                WHERE conversation_id = %s
                  AND (
                        created_at < %s
                        OR (
                            created_at = %s
                            AND id < %s
                        )
                  )
                ORDER BY created_at ASC, id ASC
                """,
                (
                    conversation_id,
                    current_created_at,
                    current_created_at,
                    current_message_id,
                ),
            )
            previous_messages = cur.fetchall()

    completed_turns: list[list[dict[str, str]]] = []
    pending_user: dict[str, str] | None = None

    for role, content in previous_messages:
        if role == "user":
            pending_user = {
                "role": "user",
                "content": content,
            }
            continue

        if role == "assistant" and pending_user is not None:
            completed_turns.append(
                [
                    pending_user,
                    {
                        "role": "assistant",
                        "content": content,
                    },
                ]
            )
            pending_user = None

    recent_turns = completed_turns[-3:]

    context: list[dict[str, str]] = []

    for turn in recent_turns:
        context.extend(turn)

    context.append(
        {
            "role": "user",
            "content": current_content,
        }
    )

    return context

@router.get("", response_model=list[ConversationSummaryResponse])
def get_conversations(
    session_token: str | None = Cookie(
        default=None,
        alias="session_token",
    ),
):
    if session_token is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
        )

    user_id = get_session_user_id(session_token)

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
        )

    return list_conversations(user_id)


@router.get(
    "/{conversation_id}",
    response_model=ConversationHistoryResponse,
)
def get_conversation(
    conversation_id: int,
    session_token: str | None = Cookie(
        default=None,
        alias="session_token",
    ),
):
    if session_token is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
        )

    user_id = get_session_user_id(session_token)

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
        )

    try:
        return get_conversation_history(
            user_id,
            conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        ) from exc