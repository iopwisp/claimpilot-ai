from typing import Literal

from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import Login, User, WorkflowSettings, session, uid
from app.schemas import Credentials
from app.security import hasher, identity, token
from app.workflow import row


from .access import audit

api = APIRouter(tags=["auth"])

DUMMY_HASH = hasher.hash(uid())


@api.post("/auth/register", status_code=201)
def register(body: Credentials, db=Depends(session)):
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
def login(body: Credentials, db=Depends(session)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    try:
        hasher.verify(user.password_hash if user else DUMMY_HASH, body.password)
    except VerificationError:
        raise HTTPException(401, "Incorrect email or password")
    if not user:
        raise HTTPException(401, "Incorrect email or password")
    record = Login(user_id=user.id)
    db.add(record)
    db.flush()
    audit(db, user, "user.login")
    db.commit()
    return {"access_token": token(record), "token_type": "bearer", "user": row(user, "id email role")}


@api.post("/auth/logout")
def logout(auth=Depends(identity), db=Depends(session)):
    audit(db, auth[0], "user.logout")
    db.delete(auth[1])
    db.commit()
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
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    user.role = body.role
    audit(db, auth[0], "user.role", entity=user_id, details=body.model_dump())
    db.commit()
    return row(user, "id email role")
