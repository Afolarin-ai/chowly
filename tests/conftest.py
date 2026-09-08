import os

# Must be set before app.database is imported anywhere, so the app
# points at a disposable test database instead of the real dev/prod one.
os.environ["DATABASE_URL"] = "sqlite:///./test_chowly.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine
from app.seed import seed


@pytest.fixture(autouse=True)
def clean_db():
    """Every test gets a fresh, fully-seeded database — no state leaks
    between tests (an order created in one test can't affect IDs or
    counts in another)."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield


@pytest.fixture
def client():
    return TestClient(app)
