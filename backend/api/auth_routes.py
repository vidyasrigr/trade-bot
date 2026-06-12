"""
Auth routes: login, me, logout, one-time setup.

POST /auth/setup   — create V and N accounts (only works when 0 users exist)
POST /auth/login   — username + password → JWT
GET  /auth/me      — returns current user from token
POST /auth/logout  — client-side only (clears cookie), but provided for completeness
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from core.auth import create_token, get_current_user, hash_password, verify_password
from core.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    v_password: str
    n_password: str
    v_display_name: str = "V"
    n_display_name: str = "N"


@router.post("/setup")
async def setup_users(req: SetupRequest):
    """
    One-time user creation. Only works when the users table is empty.
    Call this once after running migration 006:

      curl -X POST http://localhost:8000/auth/setup \\
        -H "Content-Type: application/json" \\
        -d '{"v_password": "yourpwd", "n_password": "theirpwd"}'
    """
    async for session in get_db():
        count = await session.execute(text("SELECT COUNT(*) FROM users"))
        if count.scalar() > 0:
            raise HTTPException(status_code=409, detail="Users already created. Use /auth/login.")

        await session.execute(
            text("INSERT INTO users (username, password_hash, display_name) VALUES (:u, :h, :d)"),
            {"u": "v", "h": hash_password(req.v_password), "d": req.v_display_name},
        )
        await session.execute(
            text("INSERT INTO users (username, password_hash, display_name) VALUES (:u, :h, :d)"),
            {"u": "n", "h": hash_password(req.n_password), "d": req.n_display_name},
        )
        await session.commit()

    return {"status": "created", "users": ["v", "n"]}


@router.post("/login")
async def login(req: LoginRequest):
    """Validate credentials and return a 30-day JWT."""
    row = None
    async for session in get_db():
        result = await session.execute(
            text("SELECT id, username, password_hash, display_name FROM users WHERE username = :u"),
            {"u": req.username.lower().strip()},
        )
        row = result.fetchone()

    if not row or not verify_password(req.password, row.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(row.id, row.username)
    return {
        "token": token,
        "user": {
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name,
        },
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Return current user info from token."""
    return user


@router.post("/logout")
async def logout():
    """Token is cleared client-side. This endpoint exists for completeness."""
    return {"status": "ok"}
