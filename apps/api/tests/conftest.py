import os
os.environ["DATABASE_URL"] = "sqlite:///./kadoku-test-unused.db"
os.environ["GUEST_QUOTA_SECRET"] = "test-hmac-secret"
os.environ["AI_MODEL"] = ""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.seed import seed


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed(session)
    yield factory
    engine.dispose()


@pytest.fixture
def client(database):
    def override_db():
        with database() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
