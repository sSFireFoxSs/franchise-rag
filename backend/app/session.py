import hashlib
import secrets
from datetime import datetime

from app.db import get_db_connection


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> tuple[str, datetime]:
    token = generate_session_token()
    token_hash = hash_session_token(token)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (token_hash, user_id)
                VALUES (%s, %s)
                RETURNING expires_at
                """,
                (token_hash, user_id),
            )
            expires_at = cur.fetchone()[0]

    return token, expires_at

def get_session_user_id(token: str) -> int | None:
    token_hash = hash_session_token(token)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id
                FROM sessions
                WHERE token_hash = %s
                  AND expires_at > CURRENT_TIMESTAMP
                """,
                (token_hash,),
            )
            row = cur.fetchone()

    if row is None:
        return None

    return row[0]


def delete_session(token: str) -> None:
    token_hash = hash_session_token(token)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE token_hash = %s",
                (token_hash,),
            )