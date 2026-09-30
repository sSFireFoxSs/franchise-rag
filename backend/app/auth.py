from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel
from psycopg.errors import UniqueViolation

from app.db import get_db_connection
from app.security import hash_password, verify_password
from app.session import create_session, delete_session, get_session_user_id

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


class SignupRequest(BaseModel):
    email: str
    password: str
    password_confirm: str



class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    id: int
    email: str

class CurrentUserResponse(BaseModel):
    id: int
    email: str



class SignupResponse(BaseModel):
    id: int
    email: str


def validate_signup_input(data: SignupRequest) -> str:
    email = data.email.strip()

    if not email:
        raise ValueError("Email is required.")

    if len(data.password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    if data.password != data.password_confirm:
        raise ValueError("Password confirmation does not match.")

    return email


def create_user(data: SignupRequest) -> SignupResponse:
    email = validate_signup_input(data)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM users WHERE email = %s",
                (email,),
            )

            if cur.fetchone():
                raise ValueError("Email is already registered.")

            password_hash = hash_password(data.password)

            try:
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash)
                    VALUES (%s, %s)
                    RETURNING id, email
                    """,
                    (email, password_hash),
                )
            except UniqueViolation as exc:
                raise ValueError("Email is already registered.") from exc

            row = cur.fetchone()

    return SignupResponse(
        id=row[0],
        email=row[1],
    )

def authenticate_user(data: LoginRequest) -> tuple[int, str]:
    email = data.email.strip()

    if not email:
        raise ValueError("Invalid email or password.")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, password_hash
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError("Invalid email or password.")

    user_id, stored_email, password_hash = row

    if not verify_password(data.password, password_hash):
        raise ValueError("Invalid email or password.")

    return user_id, stored_email


def create_login_session(data: LoginRequest):
    user_id, email = authenticate_user(data)
    token, expires_at = create_session(user_id)

    return user_id, email, token, expires_at

def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=3600,
        samesite="lax",
        secure=False,
        path="/",
    )

def get_current_user(session_token: str) -> CurrentUserResponse:
    user_id = get_session_user_id(session_token)

    if user_id is None:
        raise ValueError("Invalid or expired session.")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError("Invalid or expired session.")

    return CurrentUserResponse(
        id=row[0],
        email=row[1],
    )


# API endpoint
@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(data: SignupRequest, response: Response):
    try:
        user = create_user(data)
    except ValueError as exc:
        message = str(exc)

        if message == "Email is already registered.":
            raise HTTPException(
                status_code=409,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=400,
            detail=message,
        ) from exc

    token, _ = create_session(user.id)
    set_session_cookie(response, token)

    return user

@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, response: Response):
    try:
        user_id, email, token, _ = create_login_session(data)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        ) from exc

    set_session_cookie(response, token)

    return LoginResponse(
        id=user_id,
        email=email,
    )

@router.get("/me", response_model=CurrentUserResponse)
def me(
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

    try:
        return get_current_user(session_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
        ) from exc

@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session_token: str | None = Cookie(
        default=None,
        alias="session_token",
    ),
):
    if session_token is not None:
        delete_session(session_token)

    response.delete_cookie(
        key="session_token",
        path="/",
        samesite="lax",
    )