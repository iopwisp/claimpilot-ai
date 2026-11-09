import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

STATE = Path(os.getenv("STATE_DIR", "state"))
STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
URL = os.getenv("DATABASE_URL", f"sqlite:///{STATE}/claims.db")
if os.getenv("DATABASE_PASSWORD_FILE"):
    from urllib.parse import quote_plus

    password = Path(os.environ["DATABASE_PASSWORD_FILE"]).read_text().strip()
    URL = f"postgresql+psycopg://pilot:{quote_plus(password)}@postgres/claims"
engine = create_engine(URL, pool_pre_ping=True)
if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


Session = sessionmaker(engine, expire_on_commit=False)


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="handler")
    created_at = Column(DateTime(timezone=True), default=now)


class Login(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(ForeignKey("users.id"), nullable=False)


class Claim(Base):
    __tablename__ = "claims"
    id = Column(String, primary_key=True, default=uid)
    claim_number = Column(String, unique=True, default=lambda: "CP-" + uid()[:10].upper())
    created_by = Column(ForeignKey("users.id"), nullable=False, index=True)
    reviewer_id = Column(ForeignKey("users.id"))
    claimant_name = Column(String, nullable=False)
    policy_number = Column(String, nullable=False)
    incident_date = Column(Date, nullable=False)
    incident_description = Column(Text, nullable=False)
    claim_amount = Column(Numeric(16, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String, default="DRAFT", nullable=False)
    job_id = Column(String)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    created_at = Column(DateTime(timezone=True), default=now)


class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=uid)
    claim_id = Column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    digest = Column(String, nullable=False)
    kind = Column(String, default="OTHER")
    status = Column(String, default="QUEUED")
    pages = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)
    uploaded_at = Column(DateTime(timezone=True), default=now)


class Field(Base):
    __tablename__ = "extracted_fields"
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    value = Column(String, nullable=False)
    page = Column(Integer, nullable=False)
    quote = Column(Text, nullable=False)
    review = Column(String, default="UNREVIEWED")
    corrected = Column(String)


class Chunk(Base):
    __tablename__ = "policy_chunks"
    id = Column(String, primary_key=True, default=uid)
    document_id = Column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(256).with_variant(JSON, "sqlite"), nullable=False)


class Analysis(Base):
    __tablename__ = "analyses"
    id = Column(String, primary_key=True)
    claim_id = Column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    result = Column(JSON, default=dict)
    model = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now)


class WorkflowSettings(Base):
    __tablename__ = "workflow_settings"
    id = Column(Integer, primary_key=True)
    police_report = Column(String, nullable=False, default="conditional")


class Inconsistency(Base):
    __tablename__ = "inconsistencies"
    id = Column(String, primary_key=True, default=uid)
    analysis_id = Column(ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=False)
    review_status = Column(String, nullable=False, default="PENDING")


class Audit(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=uid)
    claim_id = Column(String, index=True)
    user_id = Column(ForeignKey("users.id"))
    action = Column(String, nullable=False)
    entity_id = Column(String)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=now)


def session():
    with Session() as db:
        yield db
