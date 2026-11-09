import os
import tempfile
from pathlib import Path
import pytest

# Isolate credentials, files and database before importing the application.
directory = tempfile.TemporaryDirectory()
os.environ.update(
    STATE_DIR=directory.name,
    DATABASE_URL="sqlite:///" + (Path(directory.name) / "test.db").as_posix(),
    AI_PROVIDER="local",
    JOBS_INLINE="1",
)
os.environ.pop("DATABASE_PASSWORD_FILE", None)
os.environ.pop("REDIS_URL", None)

from app.main import app
from fastapi.testclient import TestClient
from app.db import engine


@pytest.fixture(scope="session", autouse=True)
def close_database():
    yield
    engine.dispose()
    directory.cleanup()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
