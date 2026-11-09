from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text

from app.db import Base, engine, session


from app.api import auth, claims, documents, analysis


@asynccontextmanager
async def lifespan(_):
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="ClaimPilot AI", version="1.0", lifespan=lifespan)


@app.get("/health")
def health(db=Depends(session)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


for router in (auth.api, claims.api, documents.api, analysis.api):
    app.include_router(router, prefix="/api/v1")
