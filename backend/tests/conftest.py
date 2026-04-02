from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


import pytest


@pytest.fixture
def client():
    reset_db()
    with TestClient(app) as test_client:
        yield test_client
