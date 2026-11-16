from contextlib import asynccontextmanager
import os

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import Base, engine, session
from app.jobs import resume_pending


from app.api import auth, claims, documents, analysis, samples


@asynccontextmanager
async def lifespan(_):
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
        if not os.getenv("REDIS_URL"):
            resume_pending()
    yield


app = FastAPI(title="ClaimPilot AI", version="1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Validation input can include passwords or entire document values.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [{"loc": e["loc"], "type": e["type"], "msg": e["msg"]} for e in exc.errors()]
        },
    )


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health(db=Depends(session)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


for router in (auth.api, claims.api, documents.api, analysis.api, samples.api):
    app.include_router(router, prefix="/api/v1")
