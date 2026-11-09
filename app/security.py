import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

from .db import Login, STATE, User, session

hasher = PasswordHasher()
bearer = HTTPBearer()


def signing_key():
    if os.getenv("JWT_SECRET"):
        return os.environ["JWT_SECRET"]
    path = STATE / "jwt.key"
    if not path.exists():
        candidate = STATE / secrets.token_hex(12)
        candidate.write_bytes(secrets.token_bytes(48))
        candidate.chmod(0o600)
        try:
            os.link(candidate, path)
        except FileExistsError:
            pass
        finally:
            candidate.unlink()
    return path.read_bytes()


def token(login):
    return jwt.encode(
        {"sub": login.user_id, "jti": login.id, "exp": datetime.now(timezone.utc) + timedelta(hours=8)},
        signing_key(),
        algorithm="HS256",
    )


def identity(raw=Depends(bearer), db=Depends(session)):
    try:
        payload = jwt.decode(
            raw.credentials,
            signing_key(),
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "jti"]},
        )
        login = db.get(Login, payload["jti"])
        if login and login.user_id == payload["sub"]:
            return db.get(User, login.user_id), login
    except jwt.InvalidTokenError:
        pass
    raise HTTPException(401, "Session expired")
