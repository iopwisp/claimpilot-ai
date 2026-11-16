from typing import Literal
import os

from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import Login, User, WorkflowSettings, session, uid
from app.schemas import Credentials
from app.security import COOKIE, hasher, identity, token
from app.workflow import row


from .access import audit

api = APIRouter(tags=["auth"])

DUMMY_HASH = hasher.hash(uid())


@api.get("/auth/options")
def auth_options():
    return {"registration_open": os.getenv("ALLOW_REGISTRATION", "1") == "1"}


@api.post("/auth/register", status_code=201)
def register(body: Credentials, db=Depends(session)):
    if not auth_options()["registration_open"]:
        raise HTTPException(403, "Ask your administrator to provision an account")
    user = User(email=body.email.lower(), password_hash=hasher.hash(body.password), role="handler")
    db.add(user)
    try:
        db.flush()
        audit(db, user, "user.register")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    return row(user, "id email role")


@api.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, db=Depends(session)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    try:
        hasher.verify(user.password_hash if user else DUMMY_HASH, body.password)
    except VerificationError:
        raise HTTPException(401, "Incorrect email or password")
    if not user:
        raise HTTPException(401, "Incorrect email or password")
    # Serialize session creation with administrative role changes.
    db.refresh(user, with_for_update=True)
    record = Login(user_id=user.id)
    db.add(record)
    db.flush()
    audit(db, user, "user.login")
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("X-ClaimPilot-Request") == "browser":
        response.set_cookie(
            COOKIE,
            token(record),
            max_age=28800,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https" or os.getenv("COOKIE_SECURE") == "1",
            path="/api/v1",
        )
        return {"user": row(user, "id email role")}
    return {"access_token": token(record), "token_type": "bearer", "user": row(user, "id email role")}


@api.post("/auth/logout")
def logout(response: Response, auth=Depends(identity), db=Depends(session)):
    audit(db, auth[0], "user.logout")
    db.delete(auth[1])
    db.commit()
    response.delete_cookie(COOKIE, path="/api/v1", httponly=True, samesite="strict")
    return {"ok": True}


@api.get("/auth/me")
def me(auth=Depends(identity)):
    return row(auth[0], "id email role")


@api.get("/users")
def users(auth=Depends(identity), db=Depends(session)):
    if auth[0].role != "admin":
        raise HTTPException(403)
    return [row(u, "id email role") for u in db.scalars(select(User))]


class RoleChange(BaseModel):
    role: Literal["admin", "handler", "reviewer"]


class RulesChange(BaseModel):
    police_report: Literal["conditional", "required", "optional"]


@api.get("/settings", response_model=RulesChange)
def settings(auth=Depends(identity), db=Depends(session)):
    if auth[0].role != "admin":
        raise HTTPException(403)
    rules = db.get(WorkflowSettings, 1)
    return {"police_report": rules.police_report if rules else "conditional"}


@api.put("/settings", response_model=RulesChange)
def save_settings(body: RulesChange, auth=Depends(identity), db=Depends(session)):
    if auth[0].role != "admin":
        raise HTTPException(403)
    db.merge(WorkflowSettings(id=1, police_report=body.police_report))
    audit(db, auth[0], "settings.update", details=body.model_dump())
    db.commit()
    return body


@api.patch("/users/{user_id}")
def change_role(user_id: str, body: RoleChange, auth=Depends(identity), db=Depends(session)):
    if auth[0].role != "admin" or auth[0].id == user_id:
        raise HTTPException(403)
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(404)
    if user.role != body.role:
        db.query(Login).filter_by(user_id=user.id).delete()
        user.role = body.role
    audit(db, auth[0], "user.role", entity=user_id, details=body.model_dump())
    db.commit()
    return row(user, "id email role")
