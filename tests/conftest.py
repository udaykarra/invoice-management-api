import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# Dedicated test database file with WAL mode supports concurrent transactions cleanly
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "test_invoices_suite.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)
with engine.connect() as conn:
    conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    conn.exec_driver_sql("PRAGMA foreign_keys=ON;")

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """Ensure every test starts and ends with clean database tables."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(setup_database):
    """Yield a database session for querying test state."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(setup_database):
    """FastAPI TestClient fixture with dependency override pointing to isolated in-memory DB."""
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
