import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models
from app.main import app
from app.core.database import Base, get_db

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables ONCE at import time
Base.metadata.create_all(bind=engine)

@pytest.fixture(scope="function", autouse=True)
def wipe_db_data():
    """Wipe all data from tables before every test to guarantee isolation."""
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    yield

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    """HTTP client for integration-style tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db_session():
    """Standalone DB session for unit-style tests."""
    session = TestingSessionLocal()
    session.rollback()  # Ensure SQLite starts a fresh transaction (fixes stale reads)
    yield session
    session.close()
